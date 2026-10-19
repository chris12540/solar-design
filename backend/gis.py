"""Bounded client for the public Maricopa County ArcGIS layers."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PARCEL_LAYER = os.getenv('MARICOPA_PARCEL_LAYER', 'https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0')
SUBDIVISION_LAYER = os.getenv('MARICOPA_SUBDIVISION_LAYER', 'https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Subdivisions/MapServer/0')
GIS_VERSION = 'maricopa-arcgis-live-v1'
TIMEOUT_SECONDS = float(os.getenv('GIS_TIMEOUT_SECONDS', '8'))
PAGE_SIZE = 1000
MAX_PAGES = 20
MAX_FEATURES = PAGE_SIZE * MAX_PAGES
APN_BATCH = 100


class GISUnavailable(Exception):
    pass


def _request_json(url, params):
    query = urlencode(params)
    if len(query) > 1500:
        request = Request(url + '/query', data=query.encode('utf-8'),
                          headers={'User-Agent': 'SolarAutoEstimation/1.0',
                                   'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    else:
        request = Request(url + '/query?' + query, headers={'User-Agent': 'SolarAutoEstimation/1.0'})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise GISUnavailable('County GIS request failed') from exc
    if data.get('error'):
        raise GISUnavailable('County GIS returned an error')
    return data


def _page(params, layer):
    features = []
    for page in range(MAX_PAGES):
        page_params = {**params, 'f': 'geojson', 'resultOffset': page * PAGE_SIZE,
                       'resultRecordCount': PAGE_SIZE, 'orderByFields': 'OBJECTID'}
        data = _request_json(layer, page_params)
        batch = data.get('features')
        if not isinstance(batch, list):
            raise GISUnavailable('County GIS returned an invalid response')
        features.extend(batch)
        exceeded = data.get('exceededTransferLimit') or data.get('properties', {}).get('exceededTransferLimit')
        if exceeded and not batch:
            raise GISUnavailable('County GIS paging stopped before the result was complete')
        if not exceeded and len(batch) < PAGE_SIZE:
            return features
    raise GISUnavailable('County GIS result exceeds the bounded page limit')


def subdivision(mcr_key):
    key = str(mcr_key)
    # County records sometimes left-pad the same secured MCR value. Query only
    # bounded exact aliases; callers still receive every returned candidate.
    aliases = list(dict.fromkeys((key, key.zfill(5), key.zfill(6))))
    values = ','.join("'" + value.replace("'", "''") + "'" for value in aliases)
    rows = _page({'where': 'mcrnum_secured IN (' + values + ')',
                  'outFields': 'mcrnum_secured,mcrnum,subname', 'returnGeometry': 'true', 'outSR': 4326}, SUBDIVISION_LAYER)
    return rows


def subdivisions_at_point(lat, lng):
    """Return county subdivision polygons covering a WGS84 point.

    ArcGIS may return more than one record at an overlap. Callers must keep all
    candidates visible instead of choosing a best-looking name.
    """
    point = json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}}, separators=(',', ':'))
    return _page({'where': '1=1', 'geometry': point,
                  'geometryType': 'esriGeometryPoint', 'inSR': 4326,
                  'spatialRel': 'esriSpatialRelIntersects',
                  'outFields': 'mcrnum_secured,mcrnum,subname',
                  'returnGeometry': 'true', 'outSR': 4326}, SUBDIVISION_LAYER)


def parcels_in_geometry(geometry):
    from shapely.geometry import shape
    from shapely.geometry.polygon import orient
    geom = shape(geometry)
    polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
    rings = []
    for polygon in polygons:
        polygon = orient(polygon, sign=-1.0)  # ArcGIS shell clockwise, holes counter-clockwise.
        rings.append(list(polygon.exterior.coords))
        rings.extend(list(ring.coords) for ring in polygon.interiors)
    esri_geometry = json.dumps({'rings': rings, 'spatialReference': {'wkid': 4326}}, separators=(',', ':'))
    return _page({'where': '1=1', 'geometry': esri_geometry,
                  'geometryType': 'esriGeometryPolygon', 'inSR': 4326,
                  'spatialRel': 'esriSpatialRelIntersects',
                  'outFields': 'APN,LATITUDE,LONGITUDE', 'returnGeometry': 'true', 'outSR': 4326}, PARCEL_LAYER)


def parcels_by_apn(apns):
    result = []
    values = list(dict.fromkeys(str(x) for x in apns if x))
    for start in range(0, len(values), APN_BATCH):
        chunk = values[start:start + APN_BATCH]
        quoted = ','.join("'" + value.replace("'", "''") + "'" for value in chunk)
        result.extend(_page({'where': 'APN IN (' + quoted + ')',
                             'outFields': 'APN,LATITUDE,LONGITUDE', 'returnGeometry': 'true', 'outSR': 4326}, PARCEL_LAYER))
    return result
