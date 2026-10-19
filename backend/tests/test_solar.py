"""Solar requests stay explicit, reject wrong buildings, and preserve uncertainty."""
import io
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from backend import solar


HOME = {'id': 'A', 'geometry': {'type': 'Polygon', 'coordinates': [[
    [-112.1, 33.4], [-112.0, 33.4], [-112.0, 33.5], [-112.1, 33.5], [-112.1, 33.4]]]} }


def insights(**changes):
    return {'center': {'latitude': 33.45, 'longitude': -112.05},
            'detectedArrays': {'detectionStatus': 'DETECTION_STATUS_NO_ARRAYS_DETECTED',
                               'latestCaptureDate': {'year': 2025, 'month': 7, 'day': 30}},
            'solarPotential': {'wholeRoofStats': {'areaMeters2': 100},
                               'maxArrayPanelsCount': 20, 'panelCapacityWatts': 400}, **changes}


@pytest.mark.parametrize('status', ['DETECTION_STATUS_ARRAYS_DETECTED',
                                  'DETECTION_STATUS_NO_ARRAYS_DETECTED'])
def test_parse_detected_arrays_capture_date_and_units(status):
    response=insights(detectedArrays={'detectionStatus': status,
        'latestCaptureDate': {'year': 2025, 'month': 7, 'day': 30}})
    outcome,facts=solar.parse_insights(response, HOME)
    assert outcome=='success' and facts['solar_detection_status']==status
    assert facts['solar_capture_date']=='2025-07-30'
    assert facts['roof_area_sqft']==pytest.approx(1076.39104167)
    assert facts['system_kw']==8


@pytest.mark.parametrize('center', [None, {}, {'latitude': 34, 'longitude': -112},
    {'latitude': True, 'longitude': -112.05}, {'latitude': float('nan'), 'longitude': -112.05}])
def test_wrong_or_invalid_center_never_leaks_roof_or_detection(center):
    outcome,facts=solar.parse_insights(insights(center=center), HOME)
    assert outcome=='building_mismatch'
    assert facts=={'solar_outcome': 'building_mismatch'}


def test_no_array_field_means_unavailable_but_matched_roof_can_exist():
    outcome,facts=solar.parse_insights(insights(detectedArrays={}), HOME)
    assert outcome=='unavailable' and facts['solar_detection_status'] is None
    assert facts['roof_area_sqft']>1000


@pytest.mark.parametrize('number', [True, -1, float('nan'), float('inf'), '100', None, 10**400])
def test_invalid_potential_numbers_never_become_threshold_facts(number):
    outcome,facts=solar.parse_insights(insights(solarPotential={
        'wholeRoofStats': {'areaMeters2': number},
        'maxArrayPanelsCount': number, 'panelCapacityWatts': number}), HOME)
    assert outcome=='success'
    assert facts['roof_area_sqft'] is None and facts['system_kw'] is None


@pytest.mark.parametrize('code,expected', [(404,'unavailable'), (500,'failed'), (400,'failed')])
def test_http_lookup_failure_classified_without_key_exposure(monkeypatch, code, expected):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    def fail(*args,**kwargs):
        raise HTTPError('https://example.test/private-test-key',code,'secret response',None,None)
    monkeypatch.setattr(solar,'urlopen',fail)
    assert solar.fetch_home(HOME)==(expected,{'solar_outcome':expected})


@pytest.mark.parametrize('code', [401,403,429])
def test_auth_and_quota_errors_stop_lookup_without_leaking_secret(monkeypatch,code):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    monkeypatch.setattr(solar,'urlopen',lambda *a,**kw: (_ for _ in ()).throw(
        HTTPError('https://example.test/private-test-key',code,'secret',None,None)))
    with pytest.raises(solar.SolarUnavailable) as error:
        solar.fetch_home(HOME)
    assert 'private-test-key' not in str(error.value) and 'secret' not in str(error.value)


def test_missing_key_makes_no_request(monkeypatch):
    monkeypatch.delenv('GOOGLE_SOLAR_API_KEY',raising=False)
    monkeypatch.setattr(solar,'urlopen',lambda *a,**kw: pytest.fail('Unexpected network call'))
    with pytest.raises(solar.SolarUnavailable):
        solar.fetch_home(HOME)


def test_request_uses_header_and_requests_array_insights(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    requests=[]
    def respond(request,timeout):
        requests.append(request)
        assert timeout==12
        return io.BytesIO(json.dumps(insights()).encode())
    monkeypatch.setattr(solar,'urlopen',respond)
    outcome,facts=solar.fetch_home(HOME)
    assert outcome=='success'
    request=requests[0]
    assert 'private-test-key' not in request.full_url
    assert request.get_header('X-goog-api-key')=='private-test-key'
    params=parse_qs(urlparse(request.full_url).query)
    assert params['additionalInsights']==['DETECTED_ARRAYS']
    assert float(params['location.latitude'][0])==pytest.approx(33.45)


@pytest.mark.parametrize('response', [b'not-json',b'[]', b'{"center": []}'])
def test_invalid_response_returns_failed_or_mismatch_without_crash(monkeypatch,response):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    monkeypatch.setattr(solar,'urlopen',lambda *a,**kw: io.BytesIO(response))
    outcome,facts=solar.fetch_home(HOME)
    assert outcome in ('failed','building_mismatch')


@pytest.mark.parametrize('error', [URLError('network detail'), TimeoutError('network detail')])
def test_network_failure_marks_only_failed(monkeypatch,error):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    monkeypatch.setattr(solar,'urlopen',lambda *a,**kw: (_ for _ in ()).throw(error))
    assert solar.fetch_home(HOME)==('failed',{'solar_outcome':'failed'})


@pytest.mark.parametrize('field', ['center','detectedArrays','solarPotential'])
def test_nonobject_nested_response_does_not_crash(monkeypatch,field):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','private-test-key')
    monkeypatch.setattr(solar,'urlopen',lambda *a,**kw: io.BytesIO(json.dumps(insights(**{field: ['bad']})).encode()))
    outcome,facts=solar.fetch_home(HOME)
    assert outcome in ('failed','building_mismatch','unavailable','success')
    if field=='solarPotential':
        assert facts.get('roof_area_sqft') is None and facts.get('system_kw') is None


def test_numeric_conversion_overflow_never_produces_infinity():
    outcome,facts=solar.parse_insights(insights(solarPotential={
        'wholeRoofStats': {'areaMeters2': 1e308},
        'maxArrayPanelsCount': 1e308, 'panelCapacityWatts': 1e308}),HOME)
    assert facts['roof_area_sqft'] is None and facts['system_kw'] is None
