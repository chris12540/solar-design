import hashlib, json, os, re, uuid, math, asyncio
from contextlib import suppress
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from shapely.geometry import shape
from shapely.validation import explain_validity
from backend import map_selection, gis, neighborhood_review, eligibility, solar, property_facts

DATABASE_URL = os.getenv('DATABASE_URL')
STAFF_TOKEN = os.getenv('STAFF_TOKEN')
SESSION_SECRET = os.getenv('SESSION_SECRET')
ALLOWED_ORIGINS = {x.strip() for x in os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000').split(',') if x.strip()}
COOKIE_SECURE = os.getenv('COOKIE_SECURE', '0') == '1'
serializer = URLSafeTimedSerializer(SESSION_SECRET or 'unconfigured', salt='solar-session')
@asynccontextmanager
async def lifespan(application):
    init_db()
    purge_solar_data()
    async def clean_expired():
        while True:
            await asyncio.sleep(3600)
            await asyncio.to_thread(purge_solar_data)
    cleanup = asyncio.create_task(clean_expired())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
app = FastAPI(lifespan=lifespan)
MIGRATIONS = Path(__file__).parent / 'migrations'
SCHEMA = MIGRATIONS / '001_init.sql'  # Kept for the streaming importer compatibility.


def connect():
    if not DATABASE_URL: raise RuntimeError('DATABASE_URL must be configured')
    return psycopg.connect(DATABASE_URL)

def init_db():
    if not STAFF_TOKEN or not SESSION_SECRET: raise RuntimeError('STAFF_TOKEN and SESSION_SECRET must be configured')
    with connect() as c:
        for migration in sorted(MIGRATIONS.glob('*.sql')):
            for statement in migration.read_text().split(';'):
                if statement.strip(): c.execute(statement)


def purge_solar_data():
    """Expire cached Solar API content and reports containing that content."""
    with connect() as c:
        c.execute("DELETE FROM parcel_solar_facts WHERE fetched_at <= now() - interval '30 days'")
        c.execute("DELETE FROM roof_reconstructions WHERE expires_at <= now()")
        c.execute("""DELETE FROM eligibility_reports WHERE report->>'solar_expires_at' IS NOT NULL
          AND (report->>'solar_expires_at')::timestamptz <= now()""")


def _selection_homes(c, user, selection):
    normalized, areas, included_ids, excluded_ids, sample_ids, coverage = map_selection.build_selection(c, user, selection)
    membership = {}
    for area in areas:
        for parcel in area.get('parcels', []):
            membership.setdefault(parcel['id'], parcel)
    return normalized, areas, included_ids, excluded_ids, sample_ids, coverage, membership


def _local_home_facts(c, homes):
    """Re-read live sourced flags without changing saved area membership."""
    by_dataset = {}
    for home in homes:
        if home.get('dataset_id'):
            by_dataset.setdefault(str(home['dataset_id']), []).append(home['id'])
    for dataset_id, ids in by_dataset.items():
        rows = c.execute("""SELECT parcel_id,rental_ind,puc,property_type,num_units FROM parcel_source_facts
          WHERE dataset_id=%s AND parcel_id=ANY(%s)""", (dataset_id,ids)).fetchall()
        facts = {row[0]:row[1:] for row in rows}
        for home in homes:
            if str(home.get('dataset_id')) != dataset_id:
                continue
            fact = facts.get(home['id'])
            raw, puc, prop, units = fact if fact else (None,home.get('puc'),home.get('property_type'),None)
            home['rental_ind'] = raw
            home['rental_status'] = property_facts.rental_status(raw)
            home['dwelling_type'] = property_facts.classify_dwelling(puc, prop, units)
            home['dwelling_type_source'] = property_facts.CLASSIFICATION_SOURCE
    return homes


@app.post('/api/parcel-flags')
def parcel_flags(body: dict, request: Request):
    user = session_user(request)
    if not isinstance(body.get('selection'), dict):
        raise HTTPException(422, 'selection is required')
    with connect() as c:
        *_, membership = _selection_homes(c,user,body['selection'])
        homes = _local_home_facts(c, [dict(h) for h in membership.values()])
        return {'homes':[{'parcel_id':h['id'], 'rental_status':h.get('rental_status'),
                          'dwelling_type':h.get('dwelling_type')} for h in homes]}


def session_user(request: Request):
    value = request.cookies.get('solar_session')
    if not value: raise HTTPException(401, 'Authentication required')
    try:
        data = serializer.loads(value, max_age=43200)
        if not isinstance(data.get('user'), str) or not data['user']: raise ValueError()
        return data['user']
    except (BadSignature, SignatureExpired, ValueError, KeyError): raise HTTPException(401, 'Authentication required')

@app.middleware('http')
async def origin_policy(request: Request, call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin = request.headers.get('origin')
        if origin and origin not in ALLOWED_ORIGINS: return JSONResponse({'detail':'Origin not allowed'}, status_code=403)
    return await call_next(request)

@app.post('/api/session')
def login(body: dict, response: Response):
    if not STAFF_TOKEN or body.get('token') != STAFF_TOKEN: raise HTTPException(401, 'Invalid token')
    response.set_cookie('solar_session', serializer.dumps({'user':'local-admin'}), httponly=True, samesite='lax', secure=COOKIE_SECURE, max_age=43200, path='/')
    return {'user':'local-admin'}

@app.get('/api/session')
def get_session(request: Request): return {'user':session_user(request)}

@app.delete('/api/session')
def logout(response: Response):
    response.delete_cookie('solar_session', path='/')
    return {'ok':True}

@app.get('/api/status')
def status(request: Request):
    session_user(request)
    with connect() as c:
        row=c.execute('SELECT id, imported_at, snapshot_date, input_rows, imported_rows, rejected_rows, files FROM datasets WHERE active').fetchone()
    if not row: return {'dataset':None}
    return {'dataset':{'id':row[0], 'imported_at':row[1].isoformat(), 'snapshot_date':row[2].isoformat() if row[2] else None, 'input_rows':row[3], 'imported_rows':row[4], 'rejected_rows':row[5], 'files':row[6]}}

def normalize(s: str):
    s=re.sub(r'\s+',' ',s.upper().strip())
    # Remove common apartment/unit labels while retaining the unit number itself.
    s=re.sub(r'(?<![A-Z0-9])(?:APARTMENT|APT|UNIT|SUITE|STE)(?=\s|[0-9])\s*','#',s)
    s=s.replace('#',' ')
    s=re.sub(r'\b(STREET)\b','ST',s); s=re.sub(r'\b(AVENUE)\b','AVE',s); s=re.sub(r'\b(ROAD)\b','RD',s); s=re.sub(r'\b(BOULEVARD)\b','BLVD',s); s=re.sub(r'\b(DRIVE)\b','DR',s); s=re.sub(r'\b(LANE)\b','LN',s); s=re.sub(r'\b(COURT)\b','CT',s)
    s=re.sub(r'\b(NORTH)\b','N',s); s=re.sub(r'\b(SOUTH)\b','S',s); s=re.sub(r'\b(EAST)\b','E',s); s=re.sub(r'\b(WEST)\b','W',s)
    s=re.sub(r'\bAZ\s*(?=\d{5}\b)',' ',s)
    return re.sub(r'\s+',' ',re.sub(r'[^A-Z0-9 ]+',' ',s)).strip()

def search_parts(value: str):
    # Units are filters, not positional address tokens: city/ZIP are optional.
    match = re.search(r'(?i)(?<![A-Z0-9])(?:(?:APARTMENT|APT|UNIT|SUITE|STE)\s*|#\s*)([A-Z0-9-]+)', value)
    unit = re.sub(r'[^A-Z0-9]', '', match.group(1).upper()) if match else None
    if match:
        value = value[:match.start()] + ' ' + value[match.end():]
    return normalize(value), unit


def search_normalize(value: str):
    base, unit = search_parts(value)
    return ' '.join(part for part in (base, unit) if part)

def parcel_dict(row):
    return {'id':row[0], 'apn':row[1], 'address':row[2], 'unit':row[3] or None, 'city':row[4], 'postal_code':row[5], 'year_built':row[6], 'mcr_key':row[7] or None, 'mcr_name':row[8] or None, 'occupancy':row[9], 'occupancy_reason':row[10], 'dataset_id':row[11], 'source_file':row[12], 'source_row':row[13], 'latitude':None, 'longitude':None, 'property_type':row[14] if len(row)>14 else None, 'puc':row[15] if len(row)>15 else None, 'residential':row[16] if len(row)>16 else None}

@app.get('/api/parcels/search')
def search(q: str, request: Request):
    session_user(request)
    if not 3 <= len(q.strip()) <= 200:
        raise HTTPException(422, 'Search query must contain 3 to 200 characters')
    query, unit_filter = search_parts(q)
    if len(query) < 3:
        raise HTTPException(422, 'Include a property address before its unit')
    apn_query = re.sub(r'[-.\s]', '', q.strip().upper())
    with connect() as c:
        active = c.execute('SELECT id FROM datasets WHERE active').fetchone()
        if not active:
            raise HTTPException(503, 'No parcel dataset is active')
        sql = '''SELECT parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,
          occupancy,occupancy_reason,dataset_id,source_file,source_row,property_type,puc,residential
          FROM parcels WHERE dataset_id=%s AND (search_norm LIKE %s OR apn LIKE %s)'''
        parameters = [active[0], query + '%', apn_query + '%']
        if unit_filter is not None:
            sql += " AND regexp_replace(regexp_replace(upper(COALESCE(unit,'')), '^(APARTMENT|APT|UNIT|SUITE|STE)[[:space:]#]*', '', 'g'), '[^A-Z0-9]', '', 'g') = %s"
            parameters.append(unit_filter)
        rows = c.execute(sql + ' ORDER BY search_norm LIMIT 51', parameters).fetchall()
    return {'matches':[parcel_dict(x) for x in rows[:50]],'truncated':len(rows)>50}

@app.get('/api/neighborhoods/search')
def search_neighborhoods(q: str, request: Request):
    session_user(request)
    if not 3 <= len(q.strip()) <= 200:
        raise HTTPException(422, 'Search query must contain 3 to 200 characters')
    with connect() as c:
        return map_selection.search_neighborhoods(c, q)

@app.post('/api/areas/resolve')
def resolve_area(body: dict, request: Request):
    user = session_user(request)
    with connect() as c:
        return map_selection.resolve_area(c, user, body)

def _local_mcr_aliases(c, county_key):
    """Match county/local MCR spellings only within the Maricopa dataset namespace."""
    text = str(county_key)
    if not text.isdigit():
        return []
    canonical = text.lstrip('0') or '0'
    active = c.execute('SELECT id FROM datasets WHERE active').fetchone()
    if not active:
        return []
    rows = c.execute('''SELECT DISTINCT mcr_key FROM parcels WHERE dataset_id=%s
      AND split_part(parcel_id, ':', 1)='04013' AND mcr_key ~ '^[0-9]+$'
      AND COALESCE(NULLIF(ltrim(mcr_key, '0'), ''), '0')=%s ORDER BY mcr_key''',
      (active[0], canonical)).fetchall()
    return [str(row[0]) for row in rows]

@app.get('/api/neighborhoods/at')
def neighborhoods_at(lat: float, lng: float, request: Request):
    user = session_user(request)
    del user  # The shared county boundary cache contains no staff-specific data.
    if not math.isfinite(lat) or not math.isfinite(lng) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(422, 'Latitude and longitude must be valid WGS84 coordinates')
    if not (EXTENT[0] <= lng <= EXTENT[2] and EXTENT[1] <= lat <= EXTENT[3]):
        raise HTTPException(422, 'Point is outside the configured Maricopa extent')
    point = json.dumps({'type':'Point','coordinates':[lng,lat]}, separators=(',',':'))
    with connect() as c:
        warnings = []
        try:
            features = gis.subdivisions_at_point(lat, lng)
        except gis.GISUnavailable:
            cached = c.execute('''SELECT mcr_key,mcr_name,ST_AsGeoJSON(geometry),fetched_at,county_mcr_key
              FROM county_subdivisions WHERE geometry IS NOT NULL AND ST_Covers(
              geometry,ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326)) ORDER BY mcr_name,mcr_key''',
              (point,)).fetchall()
            if not cached:
                raise HTTPException(503, 'County subdivision lookup is unavailable; no matching cache exists')
            cache_rows = [(row[0], row[1], row[2], row[4] or row[0]) for row in cached]
            warnings.append('County GIS is unavailable; cached matches may omit other county candidates.')
        else:
            cache_rows = []
            from shapely.geometry import Point, shape, mapping
            query_point = Point(lng, lat)
            for feature in features:
                props = feature.get('properties') or {}
                key = props.get('mcrnum_secured')
                name = props.get('subname')
                if key is None or not name:
                    continue
                geometry = feature.get('geometry')
                try:
                    geom = shape(geometry) if geometry else None
                except Exception:
                    geom = None
                if geom is not None and (geom.is_empty or not geom.is_valid or not geom.covers(query_point)):
                    continue
                if geom is not None:
                    geometry_json = json.dumps(mapping(geom), separators=(',',':'))
                else:
                    geometry_json = None
                local_keys = _local_mcr_aliases(c, key)
                if not local_keys:
                    local_keys = [str(key)]
                    warnings.append(f'County subdivision {name} has no matching local MCR key.')
                for local_key in local_keys:
                    if geom is not None:
                        map_selection._cache_subdivision(c, local_key, feature)
                    cache_rows.append((str(local_key), str(name), geometry_json, str(key)))
            # Keep distinct returned candidates without silently resolving overlaps.
            cache_rows = list({(str(key), str(name), str(county_key)):
                (str(key), str(name), geom, str(county_key))
                for key, name, geom, county_key in cache_rows}.values())
        matches = []
        for key, name, geometry, county_key in cache_rows:
            count = c.execute('''SELECT count(*) FROM parcels p JOIN datasets d ON d.id=p.dataset_id
              AND d.active WHERE p.mcr_key=%s''', (str(key),)).fetchone()[0]
            try:
                geometry = json.loads(geometry) if geometry else None
            except (TypeError, ValueError):
                geometry = None
            matches.append({'mcr_key':str(key), 'mcr_name':name, 'geometry':geometry,
                'boundary_source':'county', 'parcel_count':count,
                'county_mcr_key':str(county_key)})
    return {'matches':matches, 'warnings':warnings}

@app.get('/api/ahjs')
def get_ahjs(request: Request):
    session_user(request)
    from backend import ahj
    with connect() as c:
        return ahj.registry(c)

@app.post('/api/neighborhoods/review')
def review_neighborhoods(body: dict, request: Request):
    user = session_user(request)
    selection = body.get('selection')
    if not isinstance(selection, dict):
        raise HTTPException(422, 'selection is required')
    with connect() as c:
        _, review = neighborhood_review.build_review(c, user, selection, body.get('ahj_overrides'))
        return review


def _eligibility_report(c, user, selection, filter_input):
    try:
        filters = eligibility.normalize_filters(filter_input)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    normalized, areas, included_ids, excluded_ids, sample_ids, coverage = map_selection.build_selection(c, user, selection)
    membership = {}
    for area in areas:
        for parcel in area.get('parcels', []):
            membership.setdefault(parcel['id'], parcel)
    homes = [dict(membership[parcel_id]) for parcel_id in included_ids]
    by_dataset = {}
    for home in homes:
        dataset_id = home.get('dataset_id')
        if dataset_id:
            by_dataset.setdefault(str(dataset_id), []).append(str(home['id']))
    source_snapshots = []
    dataset_manifests = []
    warnings = []
    for dataset_id, parcel_ids in sorted(by_dataset.items()):
        dataset = c.execute('SELECT files,snapshot_date FROM datasets WHERE id=%s', (dataset_id,)).fetchone()
        if dataset:
            dataset_manifests.append({'dataset_id':dataset_id, 'source_files':dataset[0],
                'snapshot_date':dataset[1].isoformat() if dataset[1] else None})
            if dataset[1] is None:
                warnings.append(f'Source snapshot date is unknown for dataset {dataset_id}.')
        snapshot = c.execute('''SELECT source_files,source_snapshot_date,transform_version
          FROM parcel_source_fact_snapshots WHERE dataset_id=%s''', (dataset_id,)).fetchone()
        if snapshot:
            source_snapshots.append({'dataset_id': dataset_id, 'source_files': snapshot[0],
                'source_snapshot_date': snapshot[1].isoformat() if snapshot[1] else None,
                'transform_version': snapshot[2]})
            fact_rows = c.execute('''SELECT parcel_id,sale_date,fcv,num_units,puc,property_type,construction_year,rental_ind
              FROM parcel_source_facts WHERE dataset_id=%s AND parcel_id=ANY(%s)''',
              (dataset_id, parcel_ids)).fetchall()
            facts_by_id = {row[0]: row[1:] for row in fact_rows}
            for home in homes:
                if str(home.get('dataset_id')) != dataset_id:
                    continue
                fact = facts_by_id.get(home['id'])
                if fact:
                    for key, value in zip(('sale_date','fcv','num_units','puc','property_type','construction_year','rental_ind'), fact):
                        home[key] = value
        else:
            warnings.append(f'No optional source facts were imported for dataset {dataset_id}.')
    solar_expiries = []
    _local_home_facts(c, homes)
    for dataset_id, parcel_ids in by_dataset.items():
        rows = c.execute("""SELECT parcel_id,facts,fetched_at,fetched_at + interval '30 days'
          FROM parcel_solar_facts WHERE dataset_id=%s AND parcel_id=ANY(%s)
          AND fetched_at > now() - interval '30 days'""", (dataset_id,parcel_ids)).fetchall()
        cached = {row[0]:row for row in rows}
        for home in homes:
            if str(home.get('dataset_id')) != dataset_id:
                continue
            row = cached.get(home['id'])
            if row:
                home.update(row[1])
                home['solar_fetched_at'] = row[2].isoformat()
                solar_expiries.append(row[3].isoformat())
    for dataset_id, dataset_homes in by_dataset.items():
        geometry_homes = [home for home in homes if str(home.get('dataset_id')) == dataset_id and home.get('geometry')]
        if not geometry_homes:
            continue
        areas = c.execute('''SELECT item.parcel_id,
              ST_Area(ST_SetSRID(ST_GeomFromGeoJSON(item.geometry_json),4326)::geography)
          FROM unnest(%s::text[],%s::text[]) AS item(parcel_id,geometry_json)''',
          ([home['id'] for home in geometry_homes],
           [json.dumps(home['geometry']) for home in geometry_homes])).fetchall()
        area_by_id = {row[0]:row[1] for row in areas}
        for home in geometry_homes:
            value = area_by_id.get(home['id'])
            home['lot_area_sqft'] = float(value) * solar.SQUARE_METRES_TO_FEET if value else None
    snapshot_date_values = {item['snapshot_date'] for item in dataset_manifests if item['snapshot_date']}
    all_snapshot_dates_known = bool(dataset_manifests) and all(item['snapshot_date'] for item in dataset_manifests)
    if len(snapshot_date_values) > 1:
        warnings.append('Selected datasets have different source snapshot dates.')
    fact_snapshot = {'datasets': source_snapshots, 'dataset_manifests':dataset_manifests,
        'source_files': [file for item in source_snapshots for file in item['source_files']],
        'source_snapshot_date': (next(iter(snapshot_date_values)) if all_snapshot_dates_known and
                                 len(snapshot_date_values) == 1 else None),
        'transform_version': (source_snapshots[0]['transform_version'] if source_snapshots and
                              len({x['transform_version'] for x in source_snapshots}) == 1 else None)}
    report = eligibility.evaluate(homes, filters, selection={
        'mode': normalized['mode'], 'area_ids': normalized['area_ids'],
        'excluded_ids': excluded_ids, 'sample_ids': sample_ids, 'intent': normalized['intent'],
        'existing_excluded_ids': excluded_ids,
    }, fact_snapshot=fact_snapshot, source_warnings=warnings)
    report['solar_expires_at'] = min(solar_expiries) if solar_expiries else None
    report['solar_configured'] = solar.configured()
    report['preexisting_excluded_ids'] = excluded_ids
    report['preexisting_excluded_count'] = len(excluded_ids)
    report['coverage'].append({'code':'selection_coverage','label':'Saved area coverage',
        'status':'available' if coverage.get('complete') else 'partial',
        'source':'saved Step 2 area snapshot','warnings':coverage.get('warnings',[])})
    return report


def _house_selection(selection):
    """Use every parcel in the user's saved areas for the shared house record."""
    if not isinstance(selection, dict):
        raise HTTPException(422, 'selection is required')
    result = dict(selection)
    result.update({'intent':'all', 'excluded_ids':[], 'sample_ids':[]})
    return result


def _house_event(c, user, dataset_id, parcel_id, kind, label, report_id=None, created_at=None):
    c.execute('''INSERT INTO house_review_events
      (id,created_by,dataset_id,parcel_id,source_version,kind,label,report_id,created_at)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,now())) ON CONFLICT DO NOTHING''',
      (uuid.uuid4(),user,str(dataset_id),str(parcel_id),str(dataset_id),kind,label,report_id,created_at))


def _house_review_inputs(c, user, homes):
    by_dataset = {}
    for home in homes:
        by_dataset.setdefault(str(home['dataset_id']), []).append(str(home['id']))
    result = {}
    for dataset_id, parcel_ids in by_dataset.items():
        fresh = c.execute("""SELECT parcel_id,outcome,facts,fetched_at,
              fetched_at + interval '30 days'
          FROM parcel_solar_facts WHERE dataset_id=%s AND parcel_id=ANY(%s)
            AND fetched_at > now() - interval '30 days'""", (dataset_id,parcel_ids)).fetchall()
        for row in fresh:
            result.setdefault((dataset_id,row[0]),[None,[]])[0] = (row[1],row[2],row[3],row[4])
        events = c.execute('''SELECT DISTINCT ON (parcel_id,kind)
              id,parcel_id,kind,created_at,label,report_id
          FROM house_review_events WHERE created_by=%s AND dataset_id=%s AND parcel_id=ANY(%s)
          ORDER BY parcel_id,kind,created_at DESC,id DESC''', (user,dataset_id,parcel_ids)).fetchall()
        for row in events:
            result.setdefault((dataset_id,row[1]),[None,[]])[1].append(
                (row[0],row[2],row[3],row[4],row[5]))
    for values in result.values():
        values[1].sort(key=lambda event:(event[2],str(event[0])),reverse=True)
    return result


def _house_review(c, user, home, facts, review_inputs=None):
    dataset_id, parcel_id = str(home['dataset_id']), str(home['id'])
    if review_inputs is None:
        cached = c.execute("""SELECT outcome,facts,fetched_at,fetched_at + interval '30 days'
          FROM parcel_solar_facts WHERE dataset_id=%s AND parcel_id=%s
          AND fetched_at > now() - interval '30 days'""", (dataset_id,parcel_id)).fetchone()
        events = c.execute('''SELECT id,kind,created_at,label,report_id FROM house_review_events
          WHERE created_by=%s AND dataset_id=%s AND parcel_id=%s
          ORDER BY created_at DESC,id DESC LIMIT 100''', (user,dataset_id,parcel_id)).fetchall()
    else:
        cached, events = review_inputs
    latest_solar = next((event for event in events if event[1] == 'solar_lookup'), None)
    latest_report = next((event for event in events if event[1] == 'eligibility_report'), None)
    solar_outcome = facts.get('solar_outcome') if cached else None
    detection = facts.get('solar_detection_status') if cached else None
    capture_date = facts.get('solar_capture_date') if cached else None
    roof_area = facts.get('roof_area_sqft') if cached else None
    system_kw = facts.get('system_kw') if cached else None
    if cached and solar_outcome == 'success' and detection in (
            'DETECTION_STATUS_ARRAYS_DETECTED','DETECTION_STATUS_NO_ARRAYS_DETECTED'):
        status = 'checked'
    elif cached:
        status = 'needs_review'
    elif latest_solar:
        status = 'refresh_needed'
    elif latest_report:
        status = 'checked'
    else:
        status = 'not_reviewed'
    last_reviewed = events[0][2] if events else (cached[2] if cached else None)
    return {
        'status': status,
        'last_reviewed_at': last_reviewed.isoformat() if last_reviewed else None,
        'solar_outcome': solar_outcome,
        'solar_detection_status': detection,
        'solar_capture_date': capture_date,
        'roof_area_sqft': roof_area,
        'system_kw': system_kw,
        'expires_at': cached[3].isoformat() if cached else None,
    }, events


def _house_record(c, user, home, areas, eligibility_home, source_warnings=None, *,
                  review_inputs=None, assignment=None, include_history=True, refresh_local=True,
                  include_neighborhoods=True):
    from backend import ahj
    if refresh_local:
        _local_home_facts(c, [home])
    facts = eligibility_home.get('facts', {}) if eligibility_home else {}
    review, event_rows = _house_review(c,user,home,facts,review_inputs)
    property_fields = ('year_built','construction_year','property_type','puc','dwelling_type',
                       'rental_status','fcv','num_units','lot_area_sqft')
    property_data = {key:facts.get(key,home.get(key)) for key in property_fields
                     if facts.get(key,home.get(key)) is not None}
    if assignment is None:
        assignment = ahj.assess(c,[home],{}).get('assignments',[{}])[0]
    elig = eligibility_home or {}
    history = ([{'id':str(row[0]),'kind':row[1],'created_at':row[2].isoformat(),
                 'label':row[3],**({'report_id':str(row[4])} if row[4] else {})}
                for row in event_rows] if include_history else [])
    memberships = ([{'area_id':area['id'],'label':area.get('label') or ''} for area in areas
                    if any(parcel['id'] == home['id'] for parcel in area.get('parcels',[]))]
                   if include_neighborhoods else [])
    attention = bool(assignment.get('status') == 'unresolved' or assignment.get('method') in ('ambiguous','unresolved')
        or review['status'] == 'needs_review'
        or property_data.get('dwelling_type') in (None,'unknown','ambiguous'))
    return {
        'parcel_id':home['id'],'dataset_id':home['dataset_id'],'apn':home.get('apn'),
        'address':home.get('address'),'city':home.get('city'),'postal_code':home.get('postal_code'),
        'property':property_data,
        'review':review,
        'design':{'status':'not_run','available':False,'history':[]},
        'ahj':{'id':assignment.get('ahj_id'),'name':assignment.get('ahj_name'),
               'status':assignment.get('status'),'method':assignment.get('method'),
               'source':assignment.get('source'),'candidates':assignment.get('candidates',[])},
        'eligibility':{'status':elig.get('status','not_checked'),
            'reason_codes':elig.get('reason_codes',[]),'reasons':elig.get('reasons',[]),
            'unknown_checks':elig.get('unknown_checks',[]),'pending_checks':elig.get('pending_checks',[])},
        'history':history,'neighborhoods':memberships,'source_warnings':list(source_warnings or []),
        '_needs_attention':attention,
    }


def _roof_home(c, user, body):
    parcel_id = body.get('parcel_id')
    if not isinstance(parcel_id,str) or not parcel_id:
        raise HTTPException(422,'parcel_id is required')
    if not isinstance(body.get('selection'),dict):
        raise HTTPException(422,'selection is required')
    *_, membership = _selection_homes(c,user,body['selection'])
    home = membership.get(parcel_id)
    if not home:
        raise HTTPException(404,'House not found in the selected areas')
    return home


@app.post('/api/houses/roof/status')
def roof_status(body: dict, request: Request):
    from backend import roof_service
    user = session_user(request)
    with connect() as c:
        return roof_service.status(c,user,_roof_home(c,user,body))


@app.post('/api/houses/roof/reconstruct')
def reconstruct_roof(body: dict, request: Request):
    from backend import roof_service
    user = session_user(request)
    with connect() as c:
        return roof_service.reconstruct(c,user,_roof_home(c,user,body))


@app.post('/api/houses/inspect')
def inspect_house(body: dict, request: Request):
    user = session_user(request)
    selection = body.get('selection')
    parcel_id = body.get('parcel_id')
    if not isinstance(parcel_id,str) or not parcel_id:
        raise HTTPException(422,'parcel_id is required')
    if not isinstance(selection,dict):
        raise HTTPException(422,'selection is required')
    with connect() as c:
        _, areas, _, _, _, _, membership = _selection_homes(c,user,selection)
        home = membership.get(parcel_id)
        if not home:
            raise HTTPException(404,'House not found in the selected areas')
        focused_selection = _house_selection(selection)
        focused_selection['excluded_ids'] = sorted(set(membership) - {parcel_id})
        report = _eligibility_report(c,user,focused_selection,{})
        eligibility_by_id = {item['parcel_id']:item for item in report['homes']}
        record = _house_record(c,user,dict(home),areas,eligibility_by_id.get(parcel_id),report.get('source_warnings'))
        record.pop('_needs_attention',None)
        return record


@app.post('/api/houses/summary')
def summarize_houses(body: dict, request: Request):
    user = session_user(request)
    selection = _house_selection(body.get('selection'))
    with connect() as c:
        _, areas, included, _, _, _, membership = _selection_homes(c,user,selection)
        report = _eligibility_report(c,user,selection,{})
        eligibility_by_id = {item['parcel_id']:item for item in report['homes']}
        source_homes = [dict(membership[parcel_id]) for parcel_id in included]
        from backend import ahj
        assignments = {item['parcel_id']:item for item in
            ahj.assess(c,source_homes,{}).get('assignments',[])}
        review_inputs = _house_review_inputs(c,user,source_homes)
        homes = []
        for parcel_id in included:
            record = _house_record(c,user,dict(membership[parcel_id]),areas,
                eligibility_by_id.get(parcel_id),report.get('source_warnings'),
                review_inputs=review_inputs.get((str(membership[parcel_id]['dataset_id']),str(parcel_id)),(None,[])),
                assignment=assignments.get(parcel_id,{}),include_history=False,refresh_local=False,
                include_neighborhoods=False)
            homes.append({'parcel_id':record['parcel_id'],'address':record['address'],
                'review_status':record['review']['status'],
                'last_reviewed_at':record['review']['last_reviewed_at'],
                'design_status':record['design']['status'],
                'needs_attention':record['_needs_attention'],
                'rental_status':record['property'].get('rental_status'),
                'eligibility_status':record['eligibility']['status'],
                'reason_codes':record['eligibility']['reason_codes']})
        counts = {'total':len(homes),
            'reviewed':sum(home['review_status'] in ('checked','needs_review','refresh_needed') for home in homes),
            'not_reviewed':sum(home['review_status'] == 'not_reviewed' for home in homes),
            'needs_attention':sum(home['needs_attention'] for home in homes),
            'designed':sum(home['design_status'] == 'designed' for home in homes)}
        return {'homes':homes,'counts':counts}


@app.post('/api/eligibility/enrich')
def enrich_eligibility(body: dict, request: Request):
    user = session_user(request)
    selection = body.get('selection')
    if not isinstance(selection, dict):
        raise HTTPException(422, 'selection is required')
    if not solar.configured():
        raise HTTPException(503, 'Google Solar is not configured. Follow docs/google-solar-setup.md.')
    from psycopg.types.json import Jsonb
    checked = cached_count = failed = 0
    # Each click advances at most ten uncached homes, bounding paid requests and latency.
    # Per-home transactions retain completed work if a later request fails.
    with connect() as c:
        report = _eligibility_report(c,user,selection,body.get('filters'))
        *_, membership = _selection_homes(c,user,selection)
    candidates = [h for h in report['homes'] if h['status'] != 'excluded']
    for result in candidates:
        home = membership[result['parcel_id']]
        with connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                      ('solar:' + str(home['dataset_id']) + ':' + home['id'],))
            fresh = c.execute("""SELECT 1 FROM parcel_solar_facts WHERE dataset_id=%s AND parcel_id=%s
              AND fetched_at > now() - CASE WHEN outcome='failed' THEN interval '5 minutes' ELSE interval '30 days' END""",(home['dataset_id'],home['id'])).fetchone()
            if fresh:
                cached_count += 1
                continue
            if checked >= 10:
                continue
            try:
                outcome, facts = solar.fetch_home(home)
            except solar.SolarUnavailable as exc:
                raise HTTPException(503, str(exc)) from None
            c.execute("""INSERT INTO parcel_solar_facts(dataset_id,parcel_id,outcome,facts)
              VALUES(%s,%s,%s,%s) ON CONFLICT(dataset_id,parcel_id) DO UPDATE
              SET outcome=EXCLUDED.outcome,facts=EXCLUDED.facts,fetched_at=now()""",
              (home['dataset_id'],home['id'],outcome,Jsonb(facts)))
            _house_event(c,user,home['dataset_id'],home['id'],'solar_lookup',
                'Solar lookup completed' if outcome == 'success' else 'Solar lookup needs review')
            checked += 1
            failed += outcome != 'success'
    return {'checked_count':checked,'cached_count':cached_count,'failed_count':failed,
            'remaining_count':max(0,len(candidates)-cached_count-checked)}


@app.post('/api/eligibility/preview')
def preview_eligibility(body: dict, request: Request):
    user = session_user(request)
    selection = body.get('selection')
    if not isinstance(selection, dict):
        raise HTTPException(422, 'selection is required')
    with connect() as c:
        return _eligibility_report(c, user, selection, body.get('filters'))


@app.post('/api/runs/{run_id}/eligibility', status_code=201)
def save_run_eligibility(run_id: str, body: dict, request: Request):
    user = session_user(request)
    purge_solar_data()
    try:
        rid = uuid.UUID(run_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, 'Run not found')
    key = request.headers.get('Idempotency-Key', '').strip()
    if not 1 <= len(key) <= 200:
        raise HTTPException(422, 'Idempotency-Key header is required and must be 1 to 200 characters')
    try:
        filters = eligibility.normalize_filters(body.get('filters'))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (user + ':eligibility:' + key,))
        run = c.execute('SELECT selection FROM runs WHERE id=%s AND created_by=%s', (rid,user)).fetchone()
        if not run:
            raise HTTPException(404, 'Run not found')
        run_selection = run[0]
        if not isinstance(run_selection, dict) or run_selection.get('mode') != 'areas':
            raise HTTPException(422, 'Eligibility reports require a saved area selection')
        requested_selection = body.get('selection')
        scoped = requested_selection is not None
        if scoped:
            if not isinstance(requested_selection,dict) or requested_selection.get('mode') != 'areas':
                raise HTTPException(422,'selection must be a saved area selection')
            run_area_ids = set(run_selection.get('area_ids',[]))
            *_, run_membership = _selection_homes(c,user,run_selection)
            normalized_scope, _, scope_included, _, _, _, scope_membership = \
                _selection_homes(c,user,requested_selection)
            if not set(normalized_scope['area_ids']) <= run_area_ids:
                raise HTTPException(422,'Scoped report areas must belong to the saved run')
            if not set(scope_membership) <= set(run_membership):
                raise HTTPException(422,'Scoped report parcels must belong to the saved run')
            selection = requested_selection
            request_data = {'run_id':str(rid),'filters':filters,'selection':normalized_scope}
        else:
            selection = run_selection
            request_data = {'run_id':str(rid),'filters':filters}
        request_hash = hashlib.sha256(json.dumps(request_data,
            sort_keys=True, separators=(',',':')).encode()).hexdigest()
        existing = c.execute('''SELECT id,request_hash,report FROM eligibility_reports
          WHERE created_by=%s AND idempotency_key=%s''', (user,key)).fetchone()
        if existing:
            if existing[1] != request_hash:
                raise HTTPException(409, 'Idempotency key was already used with a different request')
            return {'id':str(existing[0]), 'run_id':str(rid), 'created':False, 'report':existing[2]}
        report = _eligibility_report(c,user,selection,filters)
        if scoped:
            report['review_scope'] = {'area_ids':normalized_scope['area_ids'],
                'parcel_ids':scope_included,'selection':normalized_scope}
        else:
            report['review_scope'] = {'area_ids':selection.get('area_ids',[]),
                'parcel_ids':[item['parcel_id'] for item in report['homes']],
                'selection':selection}
        *_, membership = _selection_homes(c,user,selection)
        report_id = uuid.uuid4()
        c.execute('''INSERT INTO eligibility_reports(id,created_by,run_id,idempotency_key,request_hash,report)
          VALUES(%s,%s,%s,%s,%s,%s)''', (report_id,user,rid,key,request_hash,json.dumps(report)))
        for result in report['homes']:
            home = membership.get(result['parcel_id'])
            if home:
                _house_event(c,user,home['dataset_id'],home['id'],'eligibility_report',
                    'Eligibility review saved',report_id)
    return {'id':str(report_id), 'run_id':str(rid), 'created':True, 'report':report}


@app.get('/api/runs/{run_id}/eligibility')
def list_run_eligibility(run_id: str, request: Request):
    user = session_user(request)
    purge_solar_data()
    try:
        rid = uuid.UUID(run_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, 'Run not found')
    with connect() as c:
        if not c.execute('SELECT 1 FROM runs WHERE id=%s AND created_by=%s', (rid,user)).fetchone():
            raise HTTPException(404, 'Run not found')
        rows = c.execute('''SELECT id,created_at,report->>'policy_version',report->>'as_of_date',
          report->>'selection_fingerprint',report->>'input_count',report->>'excluded_count',
          report->>'needs_review_count',report->>'passes_available_checks_count'
          FROM eligibility_reports WHERE run_id=%s AND created_by=%s
          ORDER BY created_at DESC,id DESC LIMIT 101''', (rid,user)).fetchall()
    return {'reports':[{'id':str(row[0]), 'created_at':row[1].isoformat(),
        'policy_version':row[2], 'as_of_date':row[3], 'selection_fingerprint':row[4],
        'input_count':int(row[5]) if row[5] is not None else None,
        'excluded_count':int(row[6]) if row[6] is not None else None,
        'needs_review_count':int(row[7]) if row[7] is not None else None,
        'passes_available_checks_count':int(row[8]) if row[8] is not None else None}
        for row in rows[:100]], 'truncated':len(rows)>100}


@app.get('/api/eligibility/{report_id}')
def get_eligibility_report(report_id: str, request: Request):
    user = session_user(request)
    purge_solar_data()
    try:
        report_uuid = uuid.UUID(report_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, 'Eligibility report not found')
    with connect() as c:
        row = c.execute('''SELECT id,run_id,created_at,report FROM eligibility_reports
          WHERE id=%s AND created_by=%s''', (report_uuid,user)).fetchone()
    if not row:
        raise HTTPException(404, 'Eligibility report not found')
    return {'id':str(row[0]), 'run_id':str(row[1]), 'created_at':row[2].isoformat(), 'report':row[3]}

EXTENT=(-113.4,32.4,-111.0,34.1)
def validate_selection(selection, parcel):
    mode=selection.get('mode')
    if mode=='mcr':
        if not parcel or not re.fullmatch(r'\d{3,6}', str(parcel.get('mcr_key') or '')): raise HTTPException(422,'MCR selection requires a parcel with a valid MCR')
        return {'mode':'mcr','mcr_key':parcel['mcr_key'],'mcr_name':parcel['mcr_name']}
    if mode=='radius':
        center=selection.get('center'); radius=selection.get('radius_meters')
        if not isinstance(center,dict): raise HTTPException(422,'Radius center must contain latitude and longitude')
        lat=center.get('lat'); lng=center.get('lng')
        if isinstance(lat,bool) or isinstance(lng,bool) or isinstance(radius,bool) or not isinstance(lat,(int,float)) or not isinstance(lng,(int,float)) or not isinstance(radius,(int,float)) or not all(math.isfinite(v) for v in (lat,lng,radius)) or not 0<radius<=10000: raise HTTPException(422,'Radius selection is invalid')
        if not EXTENT[0]<=lng<=EXTENT[2] or not EXTENT[1]<=lat<=EXTENT[3]: raise HTTPException(422,'Center is outside the configured Maricopa extent')
        return {'mode':'radius','center':{'lat':lat,'lng':lng},'radius_meters':radius}
    if mode=='polygon':
        geom=selection.get('geometry')
        try: g=shape(geom)
        except Exception: raise HTTPException(422,'Polygon geometry is invalid')
        coords=geom.get('coordinates',[]) if isinstance(geom,dict) else []
        if geom.get('type')!='Polygon' or len(coords)!=1: raise HTTPException(422,'Polygon must have one exterior ring and no holes')
        ring=coords[0]
        if not isinstance(ring,list) or len(ring)<4 or ring[0]!=ring[-1]: raise HTTPException(422,'Polygon ring must be closed')
        if any(not isinstance(point,(list,tuple)) or len(point)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in point) for point in ring): raise HTTPException(422,'Polygon coordinates must be finite longitude/latitude pairs')
        if len(ring)>501: raise HTTPException(422,'Polygon exceeds 500 vertices')
        if not g.is_valid or not g.exterior.is_ring: raise HTTPException(422,'Polygon is invalid: '+explain_validity(g))
        lat0=sum(y for _,y,*_ in ring)/len(ring)
        projected=[(x*111.32*math.cos(math.radians(lat0)),y*111.32) for x,y,*_ in ring]
        from shapely.geometry import Polygon
        if Polygon(projected).area>100: raise HTTPException(422,'Polygon exceeds 100 square km')
        if any(x<EXTENT[0] or x>EXTENT[2] or y<EXTENT[1] or y>EXTENT[3] for x,y,*_ in ring): raise HTTPException(422,'Polygon is outside the configured Maricopa extent')
        return {'mode':'polygon','geometry':geom}
    raise HTTPException(422,'Unknown selection mode')

@app.post('/api/runs',status_code=201)
def create_run(body: dict, request: Request):
    return _create_run(body, request, confirmed=False)

@app.post('/api/runs/confirm',status_code=201)
def confirm_run(body: dict, request: Request):
    return _create_run(body, request, confirmed=True)

def _create_run(body: dict, request: Request, *, confirmed=False):
    user=session_user(request)
    try: idem=uuid.UUID(request.headers.get('Idempotency-Key',''))
    except ValueError: raise HTTPException(422,'Idempotency-Key must be a UUID')
    name=body.get('name'); original=body.get('original_address'); pid=body.get('parcel_id'); selection=body.get('selection')
    if not isinstance(name,str) or not 1<=len(name.strip())<=120 or not isinstance(selection,dict): raise HTTPException(422,'Run name and selection are required')
    is_map = selection.get('mode') == 'areas'
    if is_map:
        if original is not None and (not isinstance(original,str) or not 1<=len(original)<=500):
            raise HTTPException(422,'original_address must contain 1 to 500 characters when supplied')
        if pid is not None: raise HTTPException(422,'parcel_id is not used with an area selection')
    elif not isinstance(original,str) or not 1<=len(original)<=500:
        raise HTTPException(422,'Run name, original address (1–500 characters), and selection are required')
    if pid is not None and not isinstance(pid,str): raise HTTPException(422,'parcel_id must be a string or null')
    if confirmed and not is_map:
        raise HTTPException(422, 'Confirmation requires an area selection')
    overrides = body.get('ahj_overrides') if confirmed else None
    payload={'name':name,'original_address':original,'parcel_id':pid,'selection':selection}
    if confirmed:
        payload['ahj_overrides'] = overrides or {}
        payload['confirmed'] = True
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(user+':'+str(idem),))
        old=c.execute('SELECT id,request_hash FROM runs WHERE created_by=%s AND idempotency_key=%s',(user,idem)).fetchone()
        if old:
            if old[1]!=digest: raise HTTPException(409,'Idempotency key was already used with a different request')
            rid=old[0]
        else:
            snap=None
            review=None
            if is_map:
                if confirmed:
                    sel, review = neighborhood_review.build_review(c, user, selection, overrides)
                else:
                    sel, areas, included, excluded, sample, coverage = map_selection.build_selection(c, user, selection)
                    sel.update({'areas':areas,'included_ids':included,'excluded_ids':excluded,
                                'sample_ids':sample,'intent':sel['intent'],'coverage':coverage})
            else:
                if pid is not None:
                    active=c.execute('SELECT id FROM datasets WHERE active').fetchone()
                    if not active: raise HTTPException(503,'No parcel dataset is active')
                    row=c.execute('SELECT parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,occupancy,occupancy_reason,dataset_id,source_file,source_row,property_type,puc,residential FROM parcels WHERE dataset_id=%s AND parcel_id=%s',(active[0],pid)).fetchone()
                    if not row: raise HTTPException(422,'Selected parcel does not exist')
                    snap=parcel_dict(row)
                sel=validate_selection(selection,snap)
            rid=uuid.uuid4()
            if confirmed:
                c.execute('''INSERT INTO runs(id,idempotency_key,request_hash,created_by,name,original_address,
                  parcel_id,parcel_snapshot,selection,status,review,confirmed_at)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,now())''',
                  (rid,idem,digest,user,name.strip(),original,pid,json.dumps(snap) if snap else None,
                   json.dumps(sel),json.dumps(review)))
            else:
                c.execute('INSERT INTO runs(id,idempotency_key,request_hash,created_by,name,original_address,parcel_id,parcel_snapshot,selection) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(rid,idem,digest,user,name.strip(),original,pid,json.dumps(snap) if snap else None,json.dumps(sel)))
    return fetch_run(rid,user)

def fetch_run(rid,user):
    with connect() as c: row=c.execute('SELECT id,name,status,created_at,created_by,original_address,parcel_snapshot,selection,county_fips,review FROM runs WHERE id=%s AND created_by=%s',(rid,user)).fetchone()
    if not row: raise HTTPException(404,'Run not found')
    result={'id':str(row[0]),'name':row[1],'status':row[2],'created_at':row[3].isoformat(),'created_by':row[4],'original_address':row[5],'parcel':row[6],'selection':row[7],'county_fips':row[8]}
    if isinstance(row[7],dict) and row[7].get('mode')=='areas':
        result.update({k:row[7].get(k) for k in ('areas','included_ids','excluded_ids','sample_ids','intent','coverage')})
    if row[9] is not None:
        result['review']=row[9]
    return result

@app.get('/api/runs')
def recent_runs(request: Request):
    user=session_user(request)
    with connect() as c:
        rows=c.execute('''SELECT id,name,created_at,status,selection,parcel_id FROM runs
          WHERE created_by=%s ORDER BY created_at DESC,id DESC LIMIT 51''',(user,)).fetchall()
    return {'runs':[{'id':str(r[0]),'name':r[1],'created_at':r[2].isoformat(),'status':r[3],
      'parcel_count':len(r[4].get('included_ids',[])) if isinstance(r[4],dict) and r[4].get('mode')=='areas' else (1 if r[5] else 0),
      'intent':r[4].get('intent') if isinstance(r[4],dict) and r[4].get('mode')=='areas' else 'legacy'} for r in rows[:50]],
      'truncated':len(rows)>50}

@app.get('/api/runs/{run_id}')
def get_run(run_id: str, request: Request):
    user=session_user(request)
    try: rid=uuid.UUID(run_id)
    except ValueError: raise HTTPException(404,'Run not found')
    return fetch_run(rid,user)
