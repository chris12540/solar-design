"""Read-only AHJ registry snapshot and conservative parcel geometry matching."""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import unary_union

DATA_DIR = Path(__file__).with_name('data')
REGISTRY_PATH = DATA_DIR / 'ahj_registry.json'
BOUNDARIES_PATH = DATA_DIR / 'ahj_boundaries.geojson'
BOUNDARIES_META_PATH = DATA_DIR / 'ahj_boundaries.meta.json'
REGISTRY_SOURCE = 'user_provided_d1_snapshot'

BOUNDARY_SOURCES = {
    'city_town': {
        'kind': 'official_state_boundary_snapshot',
        'source_url': 'https://services6.arcgis.com/clPWQMwZfdWn4MQZ/arcgis/rest/services/Incorporated_Places_Boundaries/FeatureServer/0',
        'source_version': '2025-08-18',
    },
    'tribal': {
        'kind': 'census_tiger_statistical_boundary_snapshot',
        'source_url': 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/AIANNHA/MapServer/2',
        'source_version': '2026-01-01',
    },
}


@lru_cache(maxsize=1)
def _registry_data():
    with REGISTRY_PATH.open(encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _registry_snapshot_sha256():
    return hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _boundary_metadata():
    with BOUNDARIES_META_PATH.open(encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _boundary_rows():
    """Load only valid polygonal features from the checked-in WGS84 snapshot."""
    with BOUNDARIES_PATH.open(encoding='utf-8') as f:
        collection = json.load(f)
    rows = []
    for feature in collection.get('features', []):
        props = feature.get('properties') or {}
        ahj_id = props.get('ahj_id')
        try:
            geom = shape(feature['geometry'])
        except (KeyError, TypeError, ValueError):
            continue
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.geom_type == 'GeometryCollection':
            polygons = [part for part in geom.geoms if part.geom_type in ('Polygon', 'MultiPolygon') and not part.is_empty]
            if not polygons:
                continue
            geom = unary_union(polygons)
        if not ahj_id or geom.is_empty or not geom.is_valid or geom.geom_type not in ('Polygon', 'MultiPolygon'):
            continue
        rows.append((ahj_id, geom))
    return tuple(rows)


def registry(c):
    """Return the local user-provided snapshot; this function never reads or writes D1."""
    data = _registry_data()
    return {'ahjs': [dict(row) for row in data['ahjs']], 'source': REGISTRY_SOURCE,
            'snapshot_sha256': _registry_snapshot_sha256()}


def _value(parcel, key, default=None):
    if isinstance(parcel, dict):
        return parcel.get(key, default)
    return getattr(parcel, key, default)


def _parcel_id(parcel):
    value = _value(parcel, 'id')
    if value is None:
        value = _value(parcel, 'parcel_id')
    return str(value) if value is not None else ''


def _representative_point(parcel):
    """Use the parcel polygon's interior point before its coordinate fallback."""
    geometry = _value(parcel, 'geometry')
    if geometry:
        try:
            geom = shape(geometry)
            if not geom.is_valid:
                geom = make_valid(geom)
            if geom.is_valid and not geom.is_empty and geom.geom_type in ('Polygon', 'MultiPolygon'):
                return geom.representative_point()
            if geom.is_valid and not geom.is_empty and geom.geom_type == 'Point':
                if math.isfinite(geom.x) and math.isfinite(geom.y) and -180 <= geom.x <= 180 and -90 <= geom.y <= 90:
                    return geom
        except (TypeError, ValueError):
            pass
    lat, lng = _value(parcel, 'latitude'), _value(parcel, 'longitude')
    try:
        if isinstance(lat, bool) or isinstance(lng, bool):
            return None
        if lat is not None and lng is not None:
            lat, lng = float(lat), float(lng)
            if math.isfinite(lat) and math.isfinite(lng) and -180 <= lng <= 180 and -90 <= lat <= 90:
                return Point(lng, lat)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _source(ahj_id=None, *, manual=False, boundary=False, reason=None, kind=None):
    if manual:
        result = {'kind': kind or 'manual_override'}
    elif ahj_id in ('az-fort-mcdowell-yavapai', 'az-gila-river-community', 'az-salt-river-pima-maricopa'):
        result = dict(BOUNDARY_SOURCES['tribal'])
    else:
        result = dict(BOUNDARY_SOURCES['city_town'])
    result['registry_snapshot_sha256'] = _registry_snapshot_sha256()
    if boundary:
        metadata = _boundary_metadata()
        result['boundary_snapshot_sha256'] = metadata['artifact_sha256']
        result['boundary_snapshot_date'] = metadata['snapshot_date']
    if reason:
        result['reason'] = reason
    return result


def assess(c, parcels: list, overrides: dict):
    """Match each parcel once; preserve overlaps and unknowns instead of guessing.

    The county-unincorporated registry entry deliberately has no polygon. A point
    outside the available city and reservation layers is not enough to assign it.
    """
    rows = _registry_data()['ahjs']
    names = {row['id']: row['name'] for row in rows}
    statuses = {
        row['id']: ('provisional' if row['status'] == 'draft'
                    else 'verified' if row['status'] == 'verified' else 'unresolved')
        for row in rows
    }
    overrides = overrides if isinstance(overrides, dict) else {}
    assignments = []
    counts = {}

    for parcel in parcels or []:
        parcel_id = _parcel_id(parcel)
        point = _representative_point(parcel)
        override_id = overrides.get(parcel_id) if parcel_id in overrides else None
        if override_id is not None:
            if isinstance(override_id, str) and override_id in names:
                ahj_id = override_id
                method = 'manual'
                status = statuses[ahj_id]
                source = _source(ahj_id, manual=True)
                candidates = [ahj_id]
            else:
                ahj_id = None
                method = 'unresolved'
                status = 'unresolved'
                source = _source(manual=True, kind='invalid_manual_override', reason='unknown_ahj_id')
                candidates = []
        elif point is None:
            ahj_id = None
            method = 'unresolved'
            status = 'unresolved'
            source = _source(manual=True, kind='unresolved', reason='missing_parcel_point')
            candidates = []
        else:
            candidates = sorted({ahj_id for ahj_id, geom in _boundary_rows() if geom.covers(point)})
            if len(candidates) == 1:
                ahj_id = candidates[0]
                method = 'boundary'
                status = statuses[ahj_id]
                source = _source(ahj_id, boundary=True)
            elif len(candidates) > 1:
                ahj_id = None
                method = 'ambiguous'
                status = 'unresolved'
                source = _source(boundary=True, kind='overlapping_boundaries', reason='multiple_boundary_matches')
            else:
                ahj_id = None
                method = 'unresolved'
                status = 'unresolved'
                source = _source(boundary=True, kind='unresolved', reason='no_boundary_match_or_unincorporated_coverage')

        assignments.append({
            'parcel_id': parcel_id,
            'ahj_id': ahj_id,
            'ahj_name': names.get(ahj_id),
            'method': method,
            'status': status,
            'source': source,
            'candidates': candidates,
        })
        if ahj_id:
            counts[ahj_id] = counts.get(ahj_id, 0) + 1

    summary = [
        {'ahj_id': ahj_id, 'name': names[ahj_id], 'count': counts[ahj_id], 'status': statuses[ahj_id]}
        for ahj_id in sorted(counts)
    ]
    return {
        'assignments': assignments,
        'summary': summary,
        'unresolved_count': sum(1 for item in assignments if item['ahj_id'] is None),
    }
