import hashlib
import json

from shapely.geometry import shape

from backend import ahj


import pytest


@pytest.fixture(autouse=True)
def clear_db():
    """Override the shared database fixture: AHJ tests are pure local-file tests."""
    yield


def _feature_for(ahj_id):
    collection = json.loads(ahj.BOUNDARIES_PATH.read_text(encoding='utf-8'))
    return next(feature for feature in collection['features'] if feature['properties']['ahj_id'] == ahj_id)


def _parcel_at(ahj_id, parcel_id='p1'):
    geom = shape(_feature_for(ahj_id)['geometry'])
    point = geom.representative_point()
    return {'id': parcel_id, 'geometry': {'type': 'Point', 'coordinates': [point.x, point.y]}}


def test_registry_is_the_28_item_local_draft_snapshot():
    result = ahj.registry(None)
    assert result['source'] == 'user_provided_d1_snapshot'
    assert result['snapshot_sha256'] == hashlib.sha256(ahj.REGISTRY_PATH.read_bytes()).hexdigest()
    assert len(result['ahjs']) == 28
    assert all(row['status'] == 'draft' and row['boundary_ref'] is None for row in result['ahjs'])
    assert {row['id'] for row in result['ahjs']} >= {
        'az-maricopa-county-unincorporated', 'az-gila-river-community',
        'az-fort-mcdowell-yavapai', 'az-salt-river-pima-maricopa',
    }


def test_real_official_city_boundary_match_remains_provisional():
    result = ahj.assess(None, [_parcel_at('az-phoenix')], {})
    item = result['assignments'][0]
    assert item['ahj_id'] == 'az-phoenix'
    assert item['method'] == 'boundary'
    assert item['status'] == 'provisional'
    assert item['source']['source_version'] == '2025-08-18'
    assert item['source']['registry_snapshot_sha256'] == ahj.registry(None)['snapshot_sha256']
    assert item['source']['boundary_snapshot_sha256'] == ahj._boundary_metadata()['artifact_sha256']
    assert item['source']['boundary_snapshot_date'] == ahj._boundary_metadata()['snapshot_date']
    assert result['unresolved_count'] == 0


def test_city_and_tribal_snapshot_features_survive_source_geometry_repair():
    metadata = ahj._boundary_metadata()
    assert metadata['artifact_sha256'] == hashlib.sha256(ahj.BOUNDARIES_PATH.read_bytes()).hexdigest()
    ids = {ahj_id for ahj_id, _ in ahj._boundary_rows()}
    assert len(ids) == 27
    assert 'az-phoenix' in ids and 'az-scottsdale' in ids and 'az-tempe' in ids
    assert {'az-fort-mcdowell-yavapai', 'az-gila-river-community',
            'az-salt-river-pima-maricopa'} <= ids


def test_polygon_representative_point_takes_precedence_over_center_coordinates():
    phoenix = _feature_for('az-phoenix')['geometry']
    tempe_point = shape(_feature_for('az-tempe')['geometry']).representative_point()
    parcel = {'id': 'p-center-mismatch', 'geometry': phoenix,
              'latitude': tempe_point.y, 'longitude': tempe_point.x}
    item = ahj.assess(None, [parcel], {})['assignments'][0]
    assert item['ahj_id'] == 'az-phoenix'


def test_uncovered_point_stays_unresolved_instead_of_becoming_county():
    result = ahj.assess(None, [{'id': 'p-outside', 'latitude': 33.67, 'longitude': -112.35}], {})
    item = result['assignments'][0]
    assert item['ahj_id'] is None
    assert item['method'] == 'unresolved'
    assert item['source']['reason'] == 'no_boundary_match_or_unincorporated_coverage'
    assert result['unresolved_count'] == 1


def test_overlapping_features_return_all_candidates():
    phoenix = shape(_feature_for('az-phoenix')['geometry'])
    original = ahj._boundary_rows.__wrapped__
    monkey_rows = lambda: original() + (('az-glendale', phoenix),)
    ahj._boundary_rows.cache_clear()
    try:
        from unittest.mock import patch
        with patch('backend.ahj._boundary_rows', side_effect=monkey_rows):
            result = ahj.assess(None, [_parcel_at('az-phoenix')], {})
    finally:
        ahj._boundary_rows.cache_clear()
    item = result['assignments'][0]
    assert item['method'] == 'ambiguous'
    assert item['ahj_id'] is None
    assert item['candidates'] == ['az-glendale', 'az-phoenix']
    assert item['status'] == 'unresolved'


def test_valid_manual_override_is_audited_and_invalid_id_is_unresolved():
    parcel = _parcel_at('az-phoenix')
    manual = ahj.assess(None, [parcel], {'p1': 'az-tempe'})['assignments'][0]
    invalid = ahj.assess(None, [parcel], {'p1': 'not-in-registry'})['assignments'][0]
    assert manual['method'] == 'manual'
    assert manual['ahj_id'] == 'az-tempe'
    assert manual['status'] == 'provisional'
    assert manual['source']['kind'] == 'manual_override'
    assert manual['source']['registry_snapshot_sha256'] == ahj.registry(None)['snapshot_sha256']
    assert 'boundary_snapshot_sha256' not in manual['source']
    assert invalid['ahj_id'] is None
    assert invalid['method'] == 'unresolved'
    assert invalid['source']['kind'] == 'invalid_manual_override'


def test_missing_point_is_unresolved():
    result = ahj.assess(None, [{'id': 'p-no-point'}], {})
    assert result['assignments'][0]['source']['reason'] == 'missing_parcel_point'
