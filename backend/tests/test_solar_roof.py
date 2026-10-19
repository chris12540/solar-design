"""Google roof inputs are fetched only through bounded, validated requests."""
import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from backend import solar_roof


HOME = {'geometry': {'type': 'Polygon', 'coordinates': [[
    [-112.1, 33.4], [-112.0, 33.4], [-112.0, 33.5], [-112.1, 33.5], [-112.1, 33.4]]]} }
INSIGHTS = {
    'center': {'latitude': 33.45, 'longitude': -112.05},
    'boundingBox': {'sw': {'latitude': 33.4498, 'longitude': -112.0502},
                    'ne': {'latitude': 33.4502, 'longitude': -112.0498}},
}
LAYERS = {
    'dsmUrl': 'https://solar.googleapis.com/v1/geoTiff:get?id=dsm-signature',
    'rgbUrl': 'https://solar.googleapis.com/v1/geoTiff:get?id=rgb-signature',
    'maskUrl': 'https://solar.googleapis.com/v1/geoTiff:get?id=mask-signature',
}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_fetch_uses_one_insights_and_one_layer_request_and_returns_bytes(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'test-secret')
    requests = []

    def open_request(request):
        requests.append(request)
        if request.full_url.startswith(solar_roof.INSIGHTS_ENDPOINT):
            return Response(json.dumps(INSIGHTS).encode())
        if request.full_url.startswith(solar_roof.LAYERS_ENDPOINT):
            return Response(json.dumps(LAYERS).encode())
        return Response(b'geotiff')

    monkeypatch.setattr(solar_roof, '_open', open_request)
    result = solar_roof.fetch_roof_inputs(HOME)
    assert len(requests) == 5  # two API calls and three raster downloads
    assert result['insights'] == INSIGHTS
    assert result['dsm'] == result['mask'] == b'geotiff'
    assert result['rgb'] == b'geotiff'
    assert result['source_warnings'] == ['Imagery date consistency could not be verified']
    assert result['request_metadata'] == {
        'building_insights_requests': 1, 'data_layers_requests': 1}
    assert result['expires_at'] > result['fetched_at']
    for request in requests:
        assert 'test-secret' not in request.full_url
        assert request.get_header('X-goog-api-key') == 'test-secret'
    layer_query = parse_qs(urlparse(requests[1].full_url).query)
    assert layer_query['view'] == ['IMAGERY_LAYERS']
    assert layer_query['requiredQuality'] == ['HIGH']
    assert layer_query['pixelSizeMeters'] == ['0.1']
    assert int(layer_query['radiusMeters'][0]) <= 100


@pytest.mark.parametrize('url', [
    'http://solar.googleapis.com/v1/geoTiff:get?id=x',
    'https://evil.example/v1/geoTiff:get?id=x',
    'https://solar.googleapis.com.evil.example/v1/geoTiff:get?id=x',
    'https://solar.googleapis.com/v1/dataLayers:get?id=x',
    'https://solar.googleapis.com/v1/geoTiff:get?key=secret',
    'https://user@solar.googleapis.com/v1/geoTiff:get?id=x',
])
def test_raster_url_must_be_google_https_geotiff_without_api_key(url):
    with pytest.raises(solar_roof.SolarUnavailable):
        solar_roof._validated_raster_url(url)


def test_building_center_outside_parcel_stops_before_layers(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'test-secret')
    calls = []

    def open_request(request):
        calls.append(request.full_url)
        return Response(json.dumps({**INSIGHTS, 'center': {'latitude': 34, 'longitude': -112}}).encode())

    monkeypatch.setattr(solar_roof, '_open', open_request)
    with pytest.raises(solar_roof.SolarUnavailable, match='outside the selected parcel'):
        solar_roof.fetch_roof_inputs(HOME)
    assert len(calls) == 1 and calls[0].startswith(solar_roof.INSIGHTS_ENDPOINT)


def test_google_http_error_is_sanitized_and_not_retried(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'private-key')
    calls = []

    def fail(request):
        calls.append(request)
        raise HTTPError('https://solar.googleapis.com/private-key', 403, 'private body', None, None)

    monkeypatch.setattr(solar_roof, '_open', fail)
    with pytest.raises(solar_roof.SolarUnavailable) as error:
        solar_roof.fetch_roof_inputs(HOME)
    assert len(calls) == 1
    assert 'private-key' not in str(error.value) and 'private body' not in str(error.value)


def test_mismatched_nested_imagery_dates_warn_and_preserve_downloads(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'test-secret')
    calls = []
    insight_response = {**INSIGHTS, 'imageryDate': {'year': 2024, 'month': 5, 'day': 2}}
    layer_response = {**LAYERS, 'imageryDate': {'year': 2024, 'month': 5, 'day': 3}}

    def open_request(request):
        calls.append(request)
        body = insight_response if request.full_url.startswith(solar_roof.INSIGHTS_ENDPOINT) else layer_response
        return Response(json.dumps(body).encode())

    monkeypatch.setattr(solar_roof, '_open', open_request)
    result = solar_roof.fetch_roof_inputs(HOME)
    assert len(calls) == 5
    assert result['source_warnings'] == [
        'Insights imagery date: 2024-05-02; raster imagery date: 2024-05-03. '
        'Imagery dates differ; geometry is experimental and not approved for design.']
    assert result['source_metadata'] == {
        'insights_imagery_date': '2024-05-02', 'raster_imagery_date': '2024-05-03'}


def test_matching_nested_imagery_dates_have_no_date_warning(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'test-secret')
    calls = []
    day = {'year': 2024, 'month': 5, 'day': 2}

    def open_request(request):
        calls.append(request)
        if request.full_url.startswith(solar_roof.INSIGHTS_ENDPOINT):
            body = {**INSIGHTS, 'imageryDate': day}
        elif request.full_url.startswith(solar_roof.LAYERS_ENDPOINT):
            body = {**LAYERS, 'imageryDate': day}
        else:
            body = None
        return Response(json.dumps(body).encode() if body is not None else b'geotiff')

    monkeypatch.setattr(solar_roof, '_open', open_request)
    result = solar_roof.fetch_roof_inputs(HOME)
    assert len(calls) == 5
    assert result['source_warnings'] == []
    assert result['source_metadata'] == {
        'insights_imagery_date': '2024-05-02', 'raster_imagery_date': '2024-05-02'}


@pytest.mark.parametrize('quality', ['MEDIUM', 'BASE'])
def test_lower_than_high_imagery_quality_stops_before_raster_downloads(monkeypatch, quality):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'test-secret')
    calls = []

    def open_request(request):
        calls.append(request)
        if request.full_url.startswith(solar_roof.INSIGHTS_ENDPOINT):
            body = {**INSIGHTS, 'imageryQuality': 'HIGH'}
        else:
            body = {**LAYERS, 'imageryQuality': quality}
        return Response(json.dumps(body).encode())

    monkeypatch.setattr(solar_roof, '_open', open_request)
    with pytest.raises(solar_roof.SolarUnavailable, match='Requested HIGH imagery quality'):
        solar_roof.fetch_roof_inputs(HOME)
    assert len(calls) == 2


def test_raster_download_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(solar_roof, 'MAX_TIFF_BYTES', 3)
    monkeypatch.setattr(solar_roof, '_open', lambda request: Response(b'1234'))
    with pytest.raises(solar_roof.SolarUnavailable, match='larger than the allowed limit'):
        solar_roof._raster_request(LAYERS['dsmUrl'], 'test-key')


def test_invalid_raster_url_never_reaches_network(monkeypatch):
    monkeypatch.setattr(solar_roof, '_open', lambda request: pytest.fail('unexpected request'))
    with pytest.raises(solar_roof.SolarUnavailable):
        solar_roof._raster_request('https://attacker.example/v1/geoTiff:get', 'test-key')


def test_safe_read_caps_response_bytes():
    with pytest.raises(solar_roof.SolarUnavailable, match='larger than the allowed limit'):
        solar_roof._safe_read(Response(b'1234'), 3)


def test_radius_above_google_limit_is_rejected():
    huge = {**INSIGHTS, 'boundingBox': {
        'sw': {'latitude': 33.44, 'longitude': -112.06},
        'ne': {'latitude': 33.46, 'longitude': -112.04}}}
    with pytest.raises(solar_roof.SolarUnavailable, match='too large'):
        solar_roof._radius(huge, type('P', (), {'x': -112.05, 'y': 33.45})())


def test_cached_insights_upgrade_uses_only_one_layer_request(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','test-key')
    calls=[]
    def open_request(request):
        calls.append(request)
        if request.full_url.startswith(solar_roof.INSIGHTS_ENDPOINT):
            pytest.fail('Cached Insights must not be fetched again')
        return Response(json.dumps(LAYERS).encode() if request.full_url.startswith(solar_roof.LAYERS_ENDPOINT) else b'tiff')
    monkeypatch.setattr(solar_roof,'_open',open_request)
    result=solar_roof.fetch_imagery_inputs(HOME,INSIGHTS)
    assert len(calls)==4
    assert result['rgb']==result['dsm']==result['mask']==b'tiff'
    assert result['request_metadata']=={'building_insights_requests':0,'data_layers_requests':1}


def test_rgb_download_failure_retains_paid_height_and_mask_without_retry(monkeypatch):
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY','test-key')
    calls=[]
    def open_request(request):
        calls.append(request)
        if request.full_url.startswith(solar_roof.LAYERS_ENDPOINT):return Response(json.dumps(LAYERS).encode())
        if 'rgb-signature' in request.full_url:raise HTTPError('private-key',403,'private error',None,None)
        return Response(b'tiff')
    monkeypatch.setattr(solar_roof,'_open',open_request)
    result=solar_roof.fetch_imagery_inputs(HOME,INSIGHTS)
    assert len(calls)==4
    assert result['rgb'] is None and result['dsm']==result['mask']==b'tiff'
    assert any('retained' in warning for warning in result['source_warnings'])
    assert 'private' not in str(result['source_warnings'])
