"""Persistent area resolution and selection snapshot helpers."""
import json
import hashlib
import math
import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from shapely.geometry import mapping, shape

from backend import gis

AREA_LIMIT = 20
PARCEL_LIMIT = 2000
VERTEX_LIMIT = 10000
EXTENT = (-113.4, 32.4, -111.0, 34.1)
SPATIAL_CACHE_TTL_SECONDS = int(os.getenv('GIS_SPATIAL_CACHE_TTL_SECONDS', '604800'))


def _feature_properties(feature):
    return feature.get('properties') or {}


def _feature_apn(feature):
    p = _feature_properties(feature)
    return str(p.get('APN') or p.get('apn') or '').strip().upper()


def _feature_geom(feature):
    value = feature.get('geometry')
    if not value:
        return None
    try:
        geom = shape(value)
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ('Polygon', 'MultiPolygon'):
            return None
        return geom
    except Exception:
        return None


def _local_rows(c, dataset_id, *, mcr_key=None, parcel_id=None):
    sql = '''SELECT parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,
      occupancy,occupancy_reason,dataset_id,source_file,source_row,property_type,puc,residential,
      county_latitude,county_longitude,ST_AsGeoJSON(county_geometry),county_fetched_at
      FROM parcels WHERE dataset_id=%s'''
    params = [dataset_id]
    if mcr_key is not None:
        sql += ' AND mcr_key=%s'; params.append(str(mcr_key))
    if parcel_id is not None:
        sql += ' AND parcel_id=%s'; params.append(parcel_id)
    sql += ' ORDER BY parcel_id'
    return c.execute(sql, params).fetchall()


def _cache_subdivision(c, key, feature):
    p = _feature_properties(feature)
    county_key = str(p.get('mcrnum_secured') or key)
    geom = _feature_geom(feature)
    geojson = json.dumps(mapping(geom), separators=(',', ':')) if geom else None
    if not p.get('subname'):
        return
    c.execute('''INSERT INTO county_subdivisions(mcr_key,mcr_num,mcr_name,geometry,fetched_at,gis_version,county_mcr_key)
      VALUES(%s,%s,%s,CASE WHEN %s::text IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326) END,now(),%s,%s)
      ON CONFLICT(mcr_key) DO UPDATE SET mcr_num=EXCLUDED.mcr_num,mcr_name=EXCLUDED.mcr_name,
      geometry=EXCLUDED.geometry,fetched_at=EXCLUDED.fetched_at,gis_version=EXCLUDED.gis_version,
      county_mcr_key=EXCLUDED.county_mcr_key''',
      (str(key), p.get('mcrnum'), str(p['subname']), geojson, geojson, gis.GIS_VERSION, county_key))


def _cache_parcels(c, dataset_id, features):
    cache = {}
    for feature in features:
        apn = _feature_apn(feature)
        if not apn:
            continue
        p = _feature_properties(feature)
        geom = _feature_geom(feature)
        geojson = json.dumps(mapping(geom), separators=(',', ':')) if geom else None
        try:
            lat = float(p['LATITUDE']) if p.get('LATITUDE') is not None else None
            lng = float(p['LONGITUDE']) if p.get('LONGITUDE') is not None else None
        except (TypeError, ValueError):
            lat = lng = None
        cache[apn] = (geom, lat, lng)
    if cache:
        c.cursor().executemany('''UPDATE parcels SET county_geometry=COALESCE(
          ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s::text),4326),county_geometry),
          county_latitude=COALESCE(%(latitude)s,county_latitude),
          county_longitude=COALESCE(%(longitude)s,county_longitude),county_fetched_at=now(),county_gis_version=%(version)s
          WHERE dataset_id=%(dataset)s AND upper(apn)=%(apn)s''', [
          {'geometry': json.dumps(mapping(g), separators=(',', ':')) if g else None,
           'latitude': lat, 'longitude': lng, 'version': gis.GIS_VERSION,
           'dataset': dataset_id, 'apn': apn} for apn, (g, lat, lng) in cache.items()])
    return cache


def _spatial_query(c, dataset_id, geometry, query_key, warnings, *, allow_cached=True):
    cached = c.execute('SELECT apns,fetched_at,complete FROM county_area_queries WHERE dataset_id=%s AND query_key=%s',
                       (dataset_id,query_key)).fetchone()
    if cached:
        age=(datetime.now(timezone.utc)-cached[1].astimezone(timezone.utc)).total_seconds()
        if cached[2] and age <= SPATIAL_CACHE_TTL_SECONDS:
            return list(cached[0]), cached[1].isoformat(), 0
    try:
        features=gis.parcels_in_geometry(geometry)
        apns=list(dict.fromkeys(_feature_apn(f) for f in features if _feature_apn(f)))
        _cache_parcels(c,dataset_id,features)
        c.execute('''INSERT INTO county_area_queries(dataset_id,query_key,apns,fetched_at,gis_version,complete)
          VALUES(%s,%s,%s,now(),%s,true) ON CONFLICT(dataset_id,query_key) DO UPDATE SET
          apns=EXCLUDED.apns,fetched_at=EXCLUDED.fetched_at,gis_version=EXCLUDED.gis_version,complete=true''',
          (dataset_id,query_key,json.dumps(apns),gis.GIS_VERSION))
        return apns,datetime.now(timezone.utc).isoformat(),0
    except gis.GISUnavailable:
        if not cached or not allow_cached:
            raise HTTPException(503,'County parcel geometry is unavailable for this area')
        warnings.append('County GIS is unavailable; using cached parcel coverage')
        return list(cached[0]),cached[1].isoformat(),0


def _area_query_key(kind, mcr_key, geometry):
    canonical=json.dumps(geometry,sort_keys=True,separators=(',',':'))
    source=f'{kind}:{mcr_key or ""}:{canonical}'
    return hashlib.sha256(source.encode()).hexdigest()


def _json_geometry(row, index=19):
    try:
        return shape(json.loads(row[index])) if row[index] else None
    except Exception:
        return None


def _map_parcel(row, geometry=None):
    geom = geometry if geometry is not None else _json_geometry(row)
    # Existing address fields intentionally exclude owner and mailing data.
    return {'id': row[0], 'apn': row[1], 'address': row[2], 'unit': row[3] or None,
      'city': row[4], 'postal_code': row[5], 'year_built': row[6], 'mcr_key': row[7] or None,
      'mcr_name': row[8] or None, 'occupancy': row[9], 'occupancy_reason': row[10],
      'dataset_id': row[11], 'source_file': row[12], 'source_row': row[13],
      'property_type': row[14], 'puc': row[15], 'residential': row[16],
      'latitude': row[17], 'longitude': row[18], 'geometry': mapping(geom) if geom else None}


def _residential(row):
    return row[16] is True


def _coverage(rows, selected, unresolved_ids, warnings, unknown_classification_count=0):
    return {'mapped_count': sum(1 for x in selected if x['geometry'] is not None),
      'unresolved_count': len(unresolved_ids), 'unknown_classification_count': unknown_classification_count,
      'complete': not warnings and not unresolved_ids and unknown_classification_count == 0,
      'warnings': list(dict.fromkeys(warnings))}


def search_neighborhoods(c, q):
    query = q.strip()
    rows = c.execute('''SELECT mcr_key, max(mcr_name), count(*) FROM parcels p
      JOIN datasets d ON d.id=p.dataset_id AND d.active WHERE lower(COALESCE(mcr_name,'')) LIKE lower(%s)
      AND mcr_key IS NOT NULL GROUP BY mcr_key ORDER BY lower(max(mcr_name)),mcr_key LIMIT 51''', (query + '%',)).fetchall()
    return {'matches':[{'mcr_key':r[0], 'mcr_name':r[1], 'parcel_count':r[2]} for r in rows[:50]], 'truncated':len(rows)>50}


def _valid_polygon(geometry):
    if not isinstance(geometry, dict) or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
        raise HTTPException(422, 'Geometry must be a Polygon or MultiPolygon')
    coordinates=geometry.get('coordinates')
    polygons=[coordinates] if geometry.get('type')=='Polygon' else coordinates
    if not isinstance(polygons,list) or not polygons:
        raise HTTPException(422, 'Geometry coordinates are invalid')
    coords=[]
    try:
        for polygon in polygons:
            if not isinstance(polygon,list) or not polygon:
                raise ValueError()
            for ring in polygon:
                if not isinstance(ring,list) or not ring:
                    raise ValueError()
                for point in ring:
                    if not isinstance(point,(list,tuple)) or len(point)!=2 or any(
                        isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)
                        for value in point):
                        raise ValueError()
                    coords.append(point)
    except (TypeError,ValueError):
        raise HTTPException(422, 'Geometry coordinates must be finite 2D longitude/latitude pairs')
    if len(coords)>VERTEX_LIMIT:
        raise HTTPException(422, 'Geometry exceeds 10,000 vertices')
    try:
        geom = shape(geometry)
    except Exception:
        raise HTTPException(422, 'Geometry is invalid')
    if geom.is_empty or not geom.is_valid:
        raise HTTPException(422, 'Geometry is invalid')
    if any(not EXTENT[0] <= x <= EXTENT[2] or not EXTENT[1] <= y <= EXTENT[3] for x,y,*_ in coords):
        raise HTTPException(422, 'Geometry is outside the configured Maricopa extent')
    # Sum projected component areas so gaps between disconnected pieces do not count.
    lat0 = geom.representative_point().y
    xscale=111.32*math.cos(math.radians(lat0))
    from shapely.geometry import Polygon
    parts=[geom] if geom.geom_type=='Polygon' else list(geom.geoms)
    projected_area=0.0
    for part in parts:
        exterior=[(x*xscale,y*111.32) for x,y in part.exterior.coords]
        holes=[[(x*xscale,y*111.32) for x,y in ring.coords] for ring in part.interiors]
        projected_area+=Polygon(exterior,holes).area
    if projected_area > 100:
        raise HTTPException(422, 'Geometry exceeds 100 square km')
    return geom


def _coordinates(geom):
    if geom.geom_type == 'Polygon':
        for ring in [geom.exterior, *geom.interiors]:
            yield from ring.coords
    else:
        for part in geom.geoms:
            yield from _coordinates(part)


def resolve_area(c, user, body):
    kind = body.get('kind')
    if kind not in ('subdivision', 'parcel', 'address', 'polygon'):
        raise HTTPException(422, 'Unknown area kind')
    active = c.execute('SELECT id FROM datasets WHERE active').fetchone()
    if not active:
        raise HTTPException(503, 'No parcel dataset is active')
    dataset_id = active[0]
    mcr_key = None
    county_mcr_key = None
    county_geom = None
    original_geom = None
    original_provenance = None
    label = str(body.get('label') or '').strip()[:120]
    boundary_source = 'user_drawn' if kind == 'polygon' else 'county'
    warnings = []
    fetched_at = None

    if kind in ('parcel', 'address'):
        parcel_id = body.get('parcel_id')
        if not isinstance(parcel_id, str):
            raise HTTPException(422, 'parcel_id is required')
        rows = _local_rows(c, dataset_id, parcel_id=parcel_id)
        if not rows:
            raise HTTPException(404, 'Parcel not found')
        mcr_key = rows[0][7]
        if kind == 'parcel' or not mcr_key:
            kind = 'parcel'; boundary_source = 'parcel'; label = label or rows[0][2]
            candidates = rows
            county_geom = _json_geometry(rows[0])
        else:
            body = {'kind':'subdivision', 'mcr_key':mcr_key, 'label':label}
            kind = 'subdivision'

    if kind == 'polygon':
        county_geom = _valid_polygon(body.get('geometry'))
        original_area_id=body.get('original_area_id')
        if original_area_id:
            try:
                original_area_id=str(uuid.UUID(original_area_id))
            except (ValueError,TypeError,AttributeError):
                raise HTTPException(422,'original_area_id must be a UUID')
            found=c.execute('SELECT payload FROM area_snapshots WHERE id=%s AND created_by=%s',(original_area_id,user)).fetchone()
            if not found:
                raise HTTPException(404,'Original area was not found')
            source_area=found[0]
            original_provenance={'boundary_source':source_area.get('boundary_source'),
              'provenance':source_area.get('provenance')}
            try:
                original_geom=shape(source_area['original_geometry']) if source_area.get('original_geometry') else None
            except Exception:
                raise HTTPException(422,'Original area geometry is invalid')
        else:
            original_area_id=None
            original_geom = county_geom
        label = label or 'Drawn area'

    if kind == 'subdivision':
        mcr_key = str(body.get('mcr_key') or '')
        if not mcr_key or len(mcr_key) > 20:
            raise HTTPException(422, 'mcr_key is required')
        rows = _local_rows(c, dataset_id, mcr_key=mcr_key)
        if not rows:
            raise HTTPException(404, 'Subdivision has no local parcels')
        cached = c.execute('SELECT mcr_name,ST_AsGeoJSON(geometry),fetched_at,county_mcr_key FROM county_subdivisions WHERE mcr_key=%s',(mcr_key,)).fetchone()
        if cached and cached[1]:
            county_geom = shape(json.loads(cached[1])); label = label or cached[0]; fetched_at = cached[2].isoformat()
            county_mcr_key = cached[3] or mcr_key
        else:
            try:
                matches = gis.subdivision(mcr_key)
            except gis.GISUnavailable:
                raise HTTPException(503, 'County GIS is unavailable and this boundary is not cached')
            if matches:
                # Do not choose among multiple county records silently.
                distinct = []
                for item in matches:
                    props = _feature_properties(item)
                    geom = _feature_geom(item)
                    distinct.append((props, geom))
                if len(distinct) > 1:
                    raise HTTPException(409, 'County returned multiple subdivision records for this key')
                props, county_geom = distinct[0]
                _cache_subdivision(c, mcr_key, matches[0])
                county_mcr_key = str(props.get('mcrnum_secured') or mcr_key)
                label = label or str(props.get('subname') or rows[0][8] or mcr_key)
                fetched_at = datetime.now(timezone.utc).isoformat()
            else:
                boundary_source = 'estimated'
                label = label or rows[0][8] or mcr_key

    local_mcr_rows = _local_rows(c,dataset_id,mcr_key=mcr_key) if mcr_key else []
    # County and drawn areas begin with county parcel features that intersect the outline.
    # Final membership still uses point-on-surface containment, which avoids selecting
    # adjacent lots that only touch or overlap the outline.
    spatial_apns = None
    if county_geom is not None and boundary_source in ('county', 'user_drawn'):
        query_key=_area_query_key(kind,mcr_key,mapping(county_geom))
        spatial_apns,fetched_at,unmatched_count=_spatial_query(c,dataset_id,mapping(county_geom),query_key,warnings)
        if unmatched_count:
            warnings.append(f'{unmatched_count} county parcel(s) could not be joined to the local dataset')
        local_apns=set()
        if spatial_apns:
            rows = c.execute('''SELECT parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,
              occupancy,occupancy_reason,dataset_id,source_file,source_row,property_type,puc,residential,
              county_latitude,county_longitude,ST_AsGeoJSON(county_geometry),county_fetched_at FROM parcels
              WHERE dataset_id=%s AND upper(apn)=ANY(%s)''',(dataset_id,spatial_apns)).fetchall()
            local_apns={str(r[1]).upper() for r in rows}
        else:
            rows = []
        if spatial_apns:
            unmatched_count=len(set(spatial_apns)-local_apns)
            if unmatched_count:
                warnings.append(f'{unmatched_count} county parcel(s) could not be joined to the local dataset')
        # MCR and county spatial matches are independent sources. Keep their discrepancy visible.
        if local_mcr_rows:
            mcr_apns={str(r[1]).upper() for r in local_mcr_rows}
            omitted=mcr_apns-set(spatial_apns or [])
            if omitted:
                warnings.append(f'{len(omitted)} local same-MCR parcel(s) were absent from county spatial results')
                rows_by_id={r[0]:r for r in rows}
                rows_by_id.update({r[0]:r for r in local_mcr_rows})
                rows=list(rows_by_id.values())
    else:
        rows = _local_rows(c, dataset_id, mcr_key=mcr_key) if kind == 'subdivision' else (candidates if kind == 'parcel' else [])
        missing = [row[1] for row in rows if row[19] is None]
        if missing:
            try:
                fetched_features = gis.parcels_by_apn(missing)
            except gis.GISUnavailable:
                warnings.append('County parcel geometry is incomplete; cached matches are shown')
            else:
                _cache_parcels(c, dataset_id, fetched_features)
                fetched_at=datetime.now(timezone.utc).isoformat()
                rows = _local_rows(c, dataset_id, mcr_key=mcr_key) if kind == 'subdivision' else _local_rows(c, dataset_id, parcel_id=body.get('parcel_id'))

    if kind == 'subdivision' and county_geom is None:
        # Estimated fallback is same-MCR membership; union only available parcel shapes.
        county_geom = _estimated_union(c,dataset_id,rows)
        boundary_source = 'estimated'
        if county_geom is None:
            warnings.append('No parcel geometry is available to draw this estimated boundary')

    if kind == 'parcel' and county_geom is None and rows:
        county_geom = _json_geometry(rows[0])
    if fetched_at is None:
        fetched_values=[row[20] for row in rows if len(row)>20 and row[20] is not None]
        if fetched_values:
            latest=max(fetched_values)
            fetched_at=latest.isoformat()

    selected_rows = []
    unresolved = []
    unknown_classification_count = 0
    if kind == 'subdivision' and boundary_source == 'estimated':
        selected_rows = [r for r in rows if _residential(r)]
        unresolved = [r[0] for r in selected_rows if _json_geometry(r) is None]
        unknown_classification_count=sum(1 for r in rows if r[16] is None)
        if unknown_classification_count:
            warnings.append(f'{unknown_classification_count} same-MCR parcel(s) have unknown residential classification')
    elif kind == 'parcel':
        selected_rows=[r for r in rows if _residential(r)]
        unresolved=[r[0] for r in selected_rows if _json_geometry(r) is None]
        unknown_classification_count=sum(1 for r in rows if r[16] is None)
        if unknown_classification_count:
            warnings.append('Parcel residential classification is unknown')
    else:
        member_ids=_parcel_membership(c,dataset_id,rows,mapping(county_geom) if county_geom is not None else None)
        for row in rows:
            geom = _json_geometry(row)
            if geom is None:
                if row[16] is True:
                    unresolved.append(row[0])
                elif row[16] is None:
                    unknown_classification_count += 1
                continue
            if row[0] in member_ids:
                if _residential(row):
                    selected_rows.append(row)
                elif row[16] is None:
                    unknown_classification_count += 1
    if unresolved:
        warnings.append(f'{len(set(unresolved))} residential parcel(s) intersect the area but lack geometry for the membership rule')
    if unknown_classification_count:
        warnings.append(f'{unknown_classification_count} parcel(s) inside the area have unknown residential classification')
    selected = [_map_parcel(r) for r in selected_rows]
    if len(selected) > PARCEL_LIMIT:
        raise HTTPException(422, 'Area exceeds 2,000 residential parcels')
    if not label:
        label = str(body.get('label') or kind.title())
    if original_geom is None:
        original_geom = county_geom
    geometry_json = mapping(county_geom) if county_geom is not None else None
    original_json = mapping(original_geom) if original_geom is not None else None
    area_id = uuid.uuid4()
    unresolved_ids=set(unresolved)
    if spatial_apns is not None:
        unresolved_ids.update('04013:'+apn for apn in set(spatial_apns)-local_apns)
    coverage = _coverage(rows, selected, unresolved_ids, warnings, unknown_classification_count)
    payload = {'id':str(area_id), 'label':label, 'kind':kind, 'mcr_key':mcr_key,
      'boundary_source':boundary_source, 'geometry':geometry_json, 'original_geometry':original_json,
      'parcels':selected, 'coverage':coverage, 'unresolved_ids':sorted(unresolved_ids),
      'provenance':{'dataset_id':dataset_id, 'gis_fetched_at':fetched_at,
        'gis_version':gis.GIS_VERSION, 'membership_rule':'ST_Covers(area, parcel representative point)' if boundary_source != 'estimated' else 'same MCR key',
        'county_mcr_key':county_mcr_key,
        'original_area_id':original_area_id if kind=='polygon' else None,
        'original_area_provenance':original_provenance if kind=='polygon' else None,
        'mcr_spatial_discrepancy_count':len(mcr_apns-set(spatial_apns or [])) if local_mcr_rows and spatial_apns is not None else 0,
        'source_snapshot_date': _snapshot_date(c, dataset_id)}}
    c.execute('INSERT INTO area_snapshots(id,created_by,dataset_id,payload) VALUES(%s,%s,%s,%s)',
      (area_id,user,dataset_id,json.dumps(payload)))
    return payload


def _snapshot_date(c, dataset_id):
    value = c.execute('SELECT snapshot_date FROM datasets WHERE id=%s',(dataset_id,)).fetchone()[0]
    return value.isoformat() if value else None


def _parcel_membership(c, dataset_id, rows, geometry):
    ids=[r[0] for r in rows]
    if not ids:
        return set()
    geojson=json.dumps(geometry,separators=(',',':'))
    found=c.execute('''SELECT parcel_id FROM parcels WHERE dataset_id=%s AND parcel_id=ANY(%s)
      AND county_geometry IS NOT NULL AND ST_Covers(
        ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326),ST_PointOnSurface(county_geometry))''',
      (dataset_id,ids,geojson)).fetchall()
    return {r[0] for r in found}


def _estimated_union(c, dataset_id, rows):
    ids=[r[0] for r in rows]
    if not ids:
        return None
    result=c.execute('''SELECT ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(
      ST_UnaryUnion(ST_Collect(county_geometry)),3))) FROM parcels WHERE dataset_id=%s
      AND parcel_id=ANY(%s) AND county_geometry IS NOT NULL''',(dataset_id,ids)).fetchone()[0]
    return shape(json.loads(result)) if result else None


def load_areas(c, user, ids):
    if not isinstance(ids,list) or not ids or len(ids)>AREA_LIMIT:
        raise HTTPException(422, 'Select between 1 and 20 areas')
    try:
        normalized = [str(uuid.UUID(x)) for x in ids]
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'area_ids must contain UUIDs')
    if len(set(normalized)) != len(normalized):
        raise HTTPException(422, 'Duplicate area IDs are not allowed')
    rows = c.execute('SELECT id,payload FROM area_snapshots WHERE created_by=%s AND id=ANY(%s)',(user,normalized)).fetchall()
    found = {str(r[0]):r[1] for r in rows}
    if len(found) != len(normalized):
        raise HTTPException(404, 'One or more areas were not found')
    return [found[x] for x in normalized]


def build_selection(c, user, selection):
    if selection.get('mode') != 'areas' or selection.get('intent') not in ('single','sample','all'):
        raise HTTPException(422, 'Invalid area selection')
    areas = load_areas(c, user, selection.get('area_ids'))
    membership = {}
    for area in areas:
        for parcel in area['parcels']:
            membership.setdefault(parcel['id'], parcel)
    if len(membership)>PARCEL_LIMIT:
        raise HTTPException(422, 'Selection exceeds 2,000 residential parcels')
    group = set(membership)
    excluded = selection.get('excluded_ids', [])
    sample = selection.get('sample_ids', [])
    if not isinstance(excluded,list) or not isinstance(sample,list) or any(not isinstance(x,str) for x in excluded+sample):
        raise HTTPException(422, 'excluded_ids and sample_ids must be parcel ID lists')
    if len(set(excluded)) != len(excluded) or len(set(sample)) != len(sample):
        raise HTTPException(422, 'Parcel ID lists cannot contain duplicates')
    if not set(excluded) <= group or not set(sample) <= group:
        raise HTTPException(422, 'Excluded and sample parcels must belong to the selected areas')
    included = group - set(excluded)
    if selection['intent'] == 'all':
        if sample:
            raise HTTPException(422, 'All intent must have an empty sample')
    elif selection['intent'] == 'single':
        if len(sample)!=1 or not set(sample)<=included:
            raise HTTPException(422, 'Single intent requires exactly one included sample parcel')
    elif len(sample)<1 or not set(sample)<=included:
        raise HTTPException(422, 'Sample intent requires one or more included sample parcels')
    coverage = {'unresolved_count':len(set().union(*(set(a.get('unresolved_ids',[])) for a in areas))),
      'unknown_classification_count':sum(a['coverage']['unknown_classification_count'] for a in areas),
      'complete':all(a['coverage']['complete'] for a in areas),
      'warnings':list(dict.fromkeys(w for a in areas for w in a['coverage']['warnings']))}
    normalized = {'mode':'areas','area_ids':[a['id'] for a in areas], 'excluded_ids':sorted(excluded),
      'sample_ids':sorted(sample), 'intent':selection['intent']}
    return normalized, areas, sorted(included), sorted(set(excluded)), sorted(set(sample)), coverage
