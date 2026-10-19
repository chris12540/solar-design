"""Explicit Google Solar lookups; never called by preview/report reads."""
import json
import math
import os
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import Point, shape
from shapely.errors import GEOSException

ENDPOINT = 'https://solar.googleapis.com/v1/buildingInsights:findClosest'
SQUARE_METRES_TO_FEET = 10.7639104167


class SolarUnavailable(Exception):
    pass


def configured():
    return bool(os.getenv('GOOGLE_SOLAR_API_KEY', '').strip())


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (OverflowError, ValueError):
        return None


def _capture_date(value):
    if not isinstance(value, dict):
        return None
    try:
        return date(value['year'], value['month'], value['day']).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def _object(value):
    return value if isinstance(value, dict) else {}


def parse_insights(data, home):
    """Reject a nearby building outside the intended parcel before using its data."""
    data = _object(data)
    center = _object(data.get('center'))
    lat, lng = center.get('latitude'), center.get('longitude')
    geometry = home.get('geometry')
    if not geometry or type(lat) not in (int, float) or type(lng) not in (int, float):
        return 'building_mismatch', {'solar_outcome': 'building_mismatch'}
    try:
        if not math.isfinite(lat) or not math.isfinite(lng) or not shape(geometry).covers(Point(lng, lat)):
            return 'building_mismatch', {'solar_outcome': 'building_mismatch'}
    except (ValueError, TypeError, KeyError, GEOSException):
        return 'building_mismatch', {'solar_outcome': 'building_mismatch'}
    arrays = _object(data.get('detectedArrays'))
    status = arrays.get('detectionStatus')
    if not isinstance(status, str):
        status = None
    known = {'DETECTION_STATUS_ARRAYS_DETECTED', 'DETECTION_STATUS_NO_ARRAYS_DETECTED'}
    outcome = 'success' if status in known else 'unavailable'
    potential = _object(data.get('solarPotential'))
    area = _number(_object(potential.get('wholeRoofStats')).get('areaMeters2'))
    count, watts = _number(potential.get('maxArrayPanelsCount')), _number(potential.get('panelCapacityWatts'))
    facts = {
        'solar_outcome': outcome,
        'solar_detection_status': status if status in known | {'DETECTION_STATUS_DATA_UNAVAILABLE', 'DETECTION_STATUS_UNSPECIFIED'} else None,
        'solar_capture_date': _capture_date(arrays.get('latestCaptureDate')),
        'roof_area_sqft': _number(area * SQUARE_METRES_TO_FEET) if area is not None else None,
        'system_kw': _number(count * watts / 1000) if count is not None and watts is not None else None,
        'solar_source': 'Google Solar API',
    }
    return outcome, facts


def fetch_home(home):
    key = os.getenv('GOOGLE_SOLAR_API_KEY', '').strip()
    if not key:
        raise SolarUnavailable('Google Solar is not configured. Follow docs/google-solar-setup.md.')
    if not home.get('geometry'):
        return 'building_mismatch', {'solar_outcome': 'building_mismatch'}
    try:
        point = shape(home['geometry']).representative_point()
    except (ValueError, TypeError, KeyError, GEOSException):
        return 'building_mismatch', {'solar_outcome': 'building_mismatch'}
    params = {'location.latitude': point.y, 'location.longitude': point.x,
              'additionalInsights': 'DETECTED_ARRAYS'}
    # Key is a header, never a query parameter or part of an exception message.
    request = Request(ENDPOINT + '?' + urlencode(params), headers={'X-Goog-Api-Key': key})
    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read(2_000_001))
        if not isinstance(data, dict):
            raise ValueError('Invalid response')
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise SolarUnavailable('Google Solar access denied. Check API enablement, billing, and key restrictions.') from None
        if exc.code == 429:
            raise SolarUnavailable('Google Solar quota reached. Try later or check project limits.') from None
        return 'unavailable' if exc.code == 404 else 'failed', {'solar_outcome': 'unavailable' if exc.code == 404 else 'failed'}
    except (URLError, TimeoutError, OSError, ValueError):
        return 'failed', {'solar_outcome': 'failed'}
    return parse_insights(data, home)
