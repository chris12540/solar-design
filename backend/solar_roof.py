"""Explicit Google Solar roof raster fetches for reconstruction workflows."""
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from shapely.geometry import Point, shape
from shapely.errors import GEOSException

from backend.solar import SolarUnavailable

INSIGHTS_ENDPOINT = 'https://solar.googleapis.com/v1/buildingInsights:findClosest'
LAYERS_ENDPOINT = 'https://solar.googleapis.com/v1/dataLayers:get'
MAX_JSON_BYTES = 2_000_000
MAX_TIFF_BYTES = 50_000_000
MAX_RADIUS_METERS = 100.0
TIMEOUT_SECONDS = 20
REQUEST_METADATA = {'building_insights_requests': 1, 'data_layers_requests': 1}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request):
    """Make a single request and reject redirects before following them."""
    return build_opener(_NoRedirect()).open(request, timeout=TIMEOUT_SECONDS)


def _safe_read(response, limit):
    body = response.read(limit + 1)
    if len(body) > limit:
        raise SolarUnavailable('Google Solar returned data larger than the allowed limit.')
    return body


def _json_request(url, key):
    request = Request(url, headers={'X-Goog-Api-Key': key, 'Accept': 'application/json'})
    with _open(request) as response:
        return json.loads(_safe_read(response, MAX_JSON_BYTES))


def _raster_request(url, key):
    safe_url = _validated_raster_url(url)
    request = Request(safe_url, headers={
        'X-Goog-Api-Key': key,
        'Accept': 'image/tiff,application/octet-stream',
    })
    with _open(request) as response:
        return _safe_read(response, MAX_TIFF_BYTES)


def _validated_raster_url(value):
    if not isinstance(value, str):
        raise SolarUnavailable('Google Solar returned an invalid raster URL.')
    try:
        parts = urlsplit(value)
        query = parse_qsl(parts.query, keep_blank_values=True)
        path_ok = parts.path in ('/v1/geoTiff:get', '/v1/solar/geoTiff:get')
        if (parts.scheme != 'https' or parts.hostname != 'solar.googleapis.com'
                or parts.port not in (None, 443) or parts.username or parts.password
                or not path_ok or any(name.lower() == 'key' for name, _ in query)):
            raise ValueError
        return urlunsplit(('https', 'solar.googleapis.com', parts.path, parts.query, ''))
    except (TypeError, ValueError):
        raise SolarUnavailable('Google Solar returned an invalid raster URL.') from None


def _point(home):
    geometry = home.get('geometry') if isinstance(home, dict) else None
    if not geometry:
        raise SolarUnavailable('The selected parcel has no usable geometry.')
    try:
        geom = shape(geometry)
        point = geom.representative_point()
        if geom.is_empty or not geom.is_valid:
            raise ValueError
        return geom, point
    except (ValueError, TypeError, KeyError, GEOSException):
        raise SolarUnavailable('The selected parcel has no usable geometry.') from None


def _inside_parcel(insights, parcel):
    center = insights.get('center') if isinstance(insights, dict) else None
    lat = center.get('latitude') if isinstance(center, dict) else None
    lng = center.get('longitude') if isinstance(center, dict) else None
    if (isinstance(lat, bool) or isinstance(lng, bool)
            or not isinstance(lat, (int, float)) or not isinstance(lng, (int, float))
            or not math.isfinite(lat) or not math.isfinite(lng)):
        return None
    try:
        point = Point(lng, lat)
        return point if parcel.covers(point) else None
    except (ValueError, TypeError, GEOSException):
        return None


def _radius(insights, center):
    """Cover the insights bounding box with a small safety margin, capped at 100m."""
    box = insights.get('boundingBox') if isinstance(insights, dict) else None
    sw = box.get('sw') if isinstance(box, dict) else None
    ne = box.get('ne') if isinstance(box, dict) else None
    try:
        latitudes = (float(sw['latitude']), float(ne['latitude']))
        longitudes = (float(sw['longitude']), float(ne['longitude']))
        if not all(math.isfinite(v) for v in (*latitudes, *longitudes)):
            raise ValueError
    except (TypeError, ValueError, KeyError):
        raise SolarUnavailable('Google Solar returned invalid building bounds.') from None
    lat0, lon0 = float(center.y), float(center.x)
    # Haversine distance to all four box corners; radiusMeters is a ground radius.
    def distance(lat, lon):
        p1, p2 = math.radians(lat0), math.radians(lat)
        dp, dl = p2 - p1, math.radians(lon - lon0)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 12_742_000 * math.asin(min(1.0, math.sqrt(a)))
    furthest = max(distance(lat, lon) for lat in latitudes for lon in longitudes)
    radius = max(1.0, math.ceil(furthest + 5.0))
    if radius > MAX_RADIUS_METERS:
        raise SolarUnavailable('The building is too large for a bounded Solar data request.')
    return radius


def _friendly_error(exc):
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return 'Google Solar access denied. Check API enablement, billing, and key restrictions.'
        if exc.code == 429:
            return 'Google Solar quota reached. Try later or check project limits.'
        if exc.code == 404:
            return 'Google Solar has no roof data for this location.'
    if isinstance(exc, SolarUnavailable):
        return str(exc)
    return 'Google Solar roof data is unavailable. Try again later.'


def _imagery_date(value):
    if not isinstance(value, dict):
        return None
    parts = (value.get('year'), value.get('month'), value.get('day'))
    if any(isinstance(part, bool) or not isinstance(part, int) for part in parts):
        return None
    try:
        return date(*parts)
    except ValueError:
        return None


def _validate_source_match(insights, layers):
    qualities = (insights.get('imageryQuality'), layers.get('imageryQuality'))
    if any(quality in ('MEDIUM', 'BASE') for quality in qualities):
        raise SolarUnavailable('Requested HIGH imagery quality was unavailable; reconstruction withheld.')
    insight_date = _imagery_date(insights.get('imageryDate'))
    layer_date = _imagery_date(layers.get('imageryDate'))
    warnings = []
    if insight_date is not None and layer_date is not None:
        if insight_date != layer_date:
            warnings.append(
                f'Insights imagery date: {insight_date.isoformat()}; '
                f'raster imagery date: {layer_date.isoformat()}. '
                'Imagery dates differ; geometry is experimental and not approved for design.')
    else:
        warnings.append('Imagery date consistency could not be verified')
    return warnings, {
        'insights_imagery_date': insight_date.isoformat() if insight_date else None,
        'raster_imagery_date': layer_date.isoformat() if layer_date else None,
    }


def fetch_roof_inputs(home):
    """Fetch one Insights response and one DSM/mask DataLayers response.

    Call only from the explicit paid roof-reconstruction action. Google documents
    DataLayers as returning DSM, RGB, and mask together for ``IMAGERY_LAYERS``.
    The source URLs are temporary, so raster bytes are downloaded immediately.
    """
    key = os.getenv('GOOGLE_SOLAR_API_KEY', '').strip()
    if not key:
        raise SolarUnavailable('Google Solar is not configured. Follow docs/google-solar-setup.md.')
    parcel, query_point = _point(home)
    fetched_at = datetime.now(timezone.utc)
    params = {
        'location.latitude': format(query_point.y, '.8f'),
        'location.longitude': format(query_point.x, '.8f'),
        'requiredQuality': 'HIGH',
    }
    try:
        insights = _json_request(INSIGHTS_ENDPOINT + '?' + urlencode(params), key)
        if not isinstance(insights, dict):
            raise SolarUnavailable('Google Solar returned an invalid building response.')
        center = _inside_parcel(insights, parcel)
        if center is None:
            raise SolarUnavailable('Google Solar matched a building outside the selected parcel.')
        result = fetch_imagery_inputs(home, insights, fetched_at=fetched_at, key=key)
        result['request_metadata'] = dict(REQUEST_METADATA)
        return result
    except HTTPError as exc:
        raise SolarUnavailable(_friendly_error(exc)) from None
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SolarUnavailable(_friendly_error(exc)) from None


def fetch_imagery_inputs(home, insights, *, fetched_at=None, key=None):
    """One Data Layers request; download matching DSM, mask and RGB immediately.

    Accept cached Insights to avoid another Building Insights charge. No retries.
    """
    key = key or os.getenv('GOOGLE_SOLAR_API_KEY', '').strip()
    if not key:
        raise SolarUnavailable('Google Solar is not configured.')
    parcel, _ = _point(home)
    center = _inside_parcel(insights, parcel)
    if center is None:
        raise SolarUnavailable('Google Solar matched a building outside the selected parcel.')
    fetched_at = fetched_at or datetime.now(timezone.utc)
    layer_params = {
        'location.latitude':format(center.y,'.8f'), 'location.longitude':format(center.x,'.8f'),
        'radiusMeters':str(_radius(insights,center)), 'view':'IMAGERY_LAYERS',
        'requiredQuality':'HIGH', 'pixelSizeMeters':'0.1',
    }
    try:
        layers = _json_request(LAYERS_ENDPOINT+'?'+urlencode(layer_params),key)
        if not isinstance(layers,dict):
            raise SolarUnavailable('Google Solar returned invalid data layer metadata.')
        warnings, metadata = _validate_source_match(insights,layers)
        dsm = _raster_request(layers.get('dsmUrl'),key)
        mask = _raster_request(layers.get('maskUrl'),key)
        try:
            rgb = _raster_request(layers.get('rgbUrl'),key)
        except (SolarUnavailable,HTTPError,URLError,TimeoutError,OSError,ValueError):
            rgb = None
            warnings.append('RGB imagery was unavailable; height and mask inputs were retained without another request.')
        return {'insights':insights,'dsm':dsm,'mask':mask,'rgb':rgb,
                'fetched_at':fetched_at.isoformat(),
                'expires_at':(fetched_at+timedelta(days=30)).isoformat(),
                'request_metadata':{'building_insights_requests':0,'data_layers_requests':1},
                'source_warnings':warnings,'source_metadata':metadata}
    except HTTPError as exc:
        raise SolarUnavailable(_friendly_error(exc)) from None
    except (URLError,TimeoutError,OSError,ValueError) as exc:
        raise SolarUnavailable(_friendly_error(exc)) from None
