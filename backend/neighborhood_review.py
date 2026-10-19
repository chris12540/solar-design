"""Server-authored neighborhood review snapshots for confirmation."""
import hashlib
import importlib
import math
import re
from datetime import date

from fastapi import HTTPException
from shapely.geometry import shape

from backend import map_selection


def _ahj_module():
    return importlib.import_module('backend.ahj')


def _warning(area, code, message, parcel_ids=(), severity='warning'):
    anchor = None
    geometry = area.get('geometry')
    if geometry:
        try:
            point = shape(geometry).representative_point()
            if math.isfinite(point.x) and math.isfinite(point.y):
                anchor = {'lat': point.y, 'lng': point.x}
        except Exception:
            anchor = None
    digest = hashlib.sha256(f"{area['id']}:{code}".encode()).hexdigest()[:16]
    return {'id': f'{area["id"]}:{digest}', 'area_id': area['id'], 'code': code,
            'severity': severity, 'message': message,
            'parcel_ids': sorted(set(str(value) for value in parcel_ids)), 'anchor': anchor}


def _registry_ids(registry):
    rows = registry.get('ahjs', []) if isinstance(registry, dict) else []
    return {str(row['id']) for row in rows if isinstance(row, dict) and row.get('id') is not None}


def _normalize_overrides(overrides, included_ids, registry):
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                               for k, v in overrides.items()):
        raise HTTPException(422, 'ahj_overrides must map parcel IDs to AHJ IDs')
    if not set(overrides) <= set(included_ids):
        raise HTTPException(422, 'AHJ overrides must refer to included parcels')
    allowed = _registry_ids(registry)
    if any(value not in allowed for value in overrides.values()):
        raise HTTPException(422, 'AHJ override refers to an unknown registry entry')
    return dict(overrides)


def build_review(c, user, selection, overrides=None):
    normalized, areas, included, excluded, sample, coverage = map_selection.build_selection(
        c, user, selection)
    if not included:
        raise HTTPException(422, 'Cannot confirm an empty neighborhood group')

    parcels_by_id = {}
    for area in areas:
        for parcel in area.get('parcels', []):
            parcels_by_id.setdefault(parcel['id'], parcel)
    included_parcels = [parcels_by_id[parcel_id] for parcel_id in included]

    ahj = _ahj_module()
    registry = ahj.registry(c)
    normalized_overrides = _normalize_overrides(overrides, included, registry)
    assessment = ahj.assess(c, included_parcels, normalized_overrides)
    assignments = {item['parcel_id']: item for item in assessment.get('assignments', [])}

    area_summaries = []
    all_warnings = []
    for area in areas:
        area_ids = {parcel['id'] for parcel in area.get('parcels', [])}
        selected_ids = sorted((area_ids & set(included)) - set(excluded))
        selected = [parcels_by_id[parcel_id] for parcel_id in selected_ids]
        this_year = date.today().year
        years = [parcel.get('year_built') for parcel in selected
                 if isinstance(parcel.get('year_built'), int) and not isinstance(parcel.get('year_built'), bool)
                 and 1800 <= parcel['year_built'] <= this_year]
        year_unknown = len(selected) - len(years)
        area_warnings = []

        if area.get('boundary_source') == 'estimated':
            area_warnings.append(_warning(area, 'estimated_boundary',
                'This neighborhood outline is estimated from parcel shapes.'))
        area_coverage = area.get('coverage') or {}
        if not area_coverage.get('complete', False):
            ids = set(area.get('unresolved_ids', []))
            reasons = [str(value).strip() for value in area_coverage.get('warnings', []) if str(value).strip()]
            unresolved_count = area_coverage.get('unresolved_count', 0)
            if unresolved_count:
                reasons.append(f'{unresolved_count} unmatched or unmapped parcel(s)')
            unknown_count = area_coverage.get('unknown_classification_count', 0)
            if unknown_count:
                reasons.append(f'{unknown_count} parcel(s) with unknown residential classification')
            detail = '; '.join(dict.fromkeys(reasons)) or 'county parcel coverage is incomplete'
            area_warnings.append(_warning(area, 'coverage_incomplete',
                'Coverage is incomplete: ' + detail + '.', ids))
        if years and max(years) - min(years) > 20:
            area_warnings.append(_warning(area, 'construction_year_spread',
                f"Recorded construction years span {min(years)}–{max(years)}; this is a broad age-range heuristic, not a roof assessment.",
                selected_ids, 'info'))
        if year_unknown:
            area_warnings.append(_warning(area, 'construction_year_incomplete',
                f'{year_unknown} included parcel(s) have no usable construction year.',
                [p['id'] for p in selected if p.get('year_built') is None], 'info'))
        if area.get('kind') == 'parcel':
            area_warnings.append(_warning(area, 'single_parcel_scope',
                'This estimate covers a single parcel; the parcel boundary does not establish roof or building scope.',
                selected_ids, 'info'))
        scope_label = f"{area.get('label') or ''} {area.get('mcr_name') or ''}"
        if re.search(r'\b(?:REPLAT|ASSEMBLAGE|LOT\s*\d+)\b', scope_label, re.IGNORECASE):
            area_warnings.append(_warning(area, 'recorded_scope',
                'The recorded area name includes a replat, lot number, or assemblage cue. This naming heuristic does not establish construction phase or roof condition.',
                selected_ids, 'info'))

        counts = {}
        for parcel_id in selected_ids:
            assignment = assignments.get(parcel_id)
            if not assignment:
                continue
            key = assignment.get('ahj_id')
            if key is None:
                continue
            key = str(key)
            entry = counts.setdefault(key, {'ahj_id': key,
                'name': assignment.get('ahj_name') or key, 'count': 0,
                'status': assignment.get('status') or 'unresolved'})
            entry['count'] += 1
            if entry['status'] != assignment.get('status'):
                entry['status'] = 'mixed'
        unresolved = [parcel_id for parcel_id in selected_ids
                      if not assignments.get(parcel_id) or assignments[parcel_id].get('ahj_id') is None]
        statuses = {item['status'] for item in counts.values()}
        if unresolved:
            area_warnings.append(_warning(area, 'ahj_unresolved',
                f'{len(unresolved)} included parcel(s) have no resolved AHJ assignment.', unresolved))
        if any(status in ('provisional', 'draft') for status in statuses):
            area_warnings.append(_warning(area, 'ahj_provisional',
                'AHJ matches are provisional; geographic matching does not verify permitting authority.',
                selected_ids, 'info'))
        if len(counts) > 1:
            area_warnings.append(_warning(area, 'ahj_mixed',
                'This area contains parcels assigned to more than one AHJ.', selected_ids, 'info'))

        area_summaries.append({'area_id': area['id'], 'label': area.get('label') or '',
            'selected_count': len(selected_ids), 'year_min': min(years) if years else None,
            'year_max': max(years) if years else None, 'year_unknown_count': year_unknown,
            'boundary_source': area.get('boundary_source'), 'warnings': area_warnings,
            'ahjs': sorted(counts.values(), key=lambda item: item['ahj_id']),
            'unresolved_ahj_count': len(unresolved)})
        all_warnings.extend(area_warnings)

    review = {'included_count': len(included), 'sample_count': len(sample),
        'areas': area_summaries, 'warnings': all_warnings, 'ahj': assessment,
        'registry_source': registry.get('source', 'user_provided_d1_snapshot'),
        'registry_snapshot_sha256': registry.get('snapshot_sha256')}
    normalized.update({'areas': areas, 'included_ids': included,
        'excluded_ids': excluded, 'sample_ids': sample,
        'intent': normalized['intent'], 'coverage': coverage,
        'ahj_overrides': normalized_overrides, 'review': review})
    return normalized, review
