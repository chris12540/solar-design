"""Deterministic, local-only filters for saved parcel snapshots."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

POLICY_VERSION = 'eligibility-2'
BUSINESS_TIMEZONE = 'America/Phoenix'
_BUSINESS_TODAY = datetime.now(ZoneInfo(BUSINESS_TIMEZONE)).date()
FILTER_KEYS = {
    'owner_occupied', 'recent_sale_days', 'exclude_condo_multifamily',
    'exclude_existing_solar', 'exclude_do_not_mail', 'year_min', 'year_max',
    'min_home_value', 'min_roof_area_sqft', 'min_lot_area_sqft', 'min_system_kw',
}
DEFAULT_FILTERS = {
    'owner_occupied': False,
    'recent_sale_days': 0,
    'exclude_condo_multifamily': True,
    'exclude_existing_solar': True,
    'exclude_do_not_mail': False,
    'year_min': None,
    'year_max': None,
    'min_home_value': None,
    'min_roof_area_sqft': None,
    'min_lot_area_sqft': None,
    'min_system_kw': None,
}

_NUMERIC_BOUNDS = {
    'min_home_value': 100_000_000,
    'min_roof_area_sqft': 10_000_000,
    'min_lot_area_sqft': 100_000_000,
    'min_system_kw': 100_000,
}
_INTEGER_BOUNDS = {'year_min': (1800, _BUSINESS_TODAY.year + 1),
                   'year_max': (1800, _BUSINESS_TODAY.year + 1)}


def normalize_filters(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError('filters must be an object')
    unknown = set(value) - FILTER_KEYS
    if unknown:
        raise ValueError('Unknown filter field: ' + sorted(unknown)[0])
    result = dict(DEFAULT_FILTERS)
    result.update(value)
    for key in ('owner_occupied', 'exclude_condo_multifamily', 'exclude_existing_solar', 'exclude_do_not_mail'):
        if type(result[key]) is not bool:
            raise ValueError(f'{key} must be a boolean')
    days = result['recent_sale_days']
    if type(days) is not int or not 0 <= days <= 3650:
        raise ValueError('recent_sale_days must be an integer from 0 to 3650')
    for key, (low, high) in _INTEGER_BOUNDS.items():
        item = result[key]
        if item is None:
            continue
        if type(item) is not int or not low <= item <= high:
            raise ValueError(f'{key} must be an integer from {low} to {high}')
    if result['year_min'] is not None and result['year_max'] is not None and result['year_min'] > result['year_max']:
        raise ValueError('year_min cannot be greater than year_max')
    for key, limit in _NUMERIC_BOUNDS.items():
        item = result[key]
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float, Decimal)):
            raise ValueError(f'{key} must be a finite nonnegative number or null')
        try:
            out_of_bounds = item < 0 or item > limit
            finite = math.isfinite(float(item)) if not out_of_bounds else False
        except (ArithmeticError, TypeError, ValueError):
            out_of_bounds, finite = True, False
        if out_of_bounds or not finite:
            raise ValueError(f'{key} must be a finite number from 0 to {limit}')
        result[key] = float(item)
    return result


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _known_year(value):
    return value if type(value) is int and 1800 <= value <= _BUSINESS_TODAY.year + 1 else None


def _snapshot_facts(home):
    """Audit every input that can affect a decision or its visible explanation."""
    keys = (
        'sale_date', 'fcv', 'num_units', 'puc', 'property_type', 'construction_year',
        'year_built', 'occupancy', 'occupancy_reason', 'dwelling_type',
        'dwelling_type_source', 'rental_status', 'rental_ind', 'solar_detection_status',
        'solar_capture_date', 'solar_outcome', 'solar_source', 'solar_building_id',
        'solar_fetched_at', 'solar_checked_at', 'roof_area_sqft', 'lot_area_sqft', 'system_kw',
        'do_not_mail',
    )
    def serializable(value):
        if isinstance(value, Decimal):
            return _numeric(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: serializable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [serializable(item) for item in value]
        return value
    return {key: serializable(home.get(key)) for key in keys}


def _fact_number(home, key):
    if key in ('roof_area_sqft', 'system_kw') and home.get('solar_outcome') in ('failed', 'building_mismatch'):
        return None
    return _numeric(home.get(key))


def _solar_pending(home):
    return home.get('solar_outcome', 'not_checked') in (None, 'not_checked')


def evaluate(homes, filters, *, as_of=None, selection=None, fact_snapshot=None, source_warnings=None):
    """Evaluate homes carrying safe parcel snapshot fields and optional source facts."""
    filters = normalize_filters(filters)
    as_of = as_of or datetime.now(ZoneInfo(BUSINESS_TIMEZONE)).date()
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    # Stable ordering and unique parcel identity are important for counts and report hashes.
    by_id = {}
    for home in homes:
        parcel_id = str(home.get('id') or home.get('parcel_id') or '')
        if not parcel_id:
            raise ValueError('Every home requires a parcel id')
        by_id.setdefault(parcel_id, home)
    ordered = [by_id[key] for key in sorted(by_id)]
    states = {str(h.get('id') or h.get('parcel_id')): {'reasons': [], 'unknown': [], 'pending': []} for h in ordered}
    steps = []

    def exclude(code, label, predicate, message, source):
        matched = []
        newly = 0
        for home in ordered:
            parcel_id = str(home.get('id') or home.get('parcel_id'))
            if not predicate(home):
                continue
            matched.append(parcel_id)
            state = states[parcel_id]
            if not state['reasons']:
                newly += 1
            state['reasons'].append({'code': code, 'message': message(home), 'source': source})
        steps.append({'code': code, 'label': label, 'matched_count': len(matched),
                      'newly_excluded_count': newly,
                      'remaining_count': len(ordered) - sum(bool(s['reasons']) for s in states.values())})

    if filters['owner_occupied']:
        exclude('not_owner_occupied', 'Owner occupancy',
                lambda h: h.get('occupancy') == 'likely_not_owner_occupied',
                lambda h: h.get('occupancy_reason') or 'Assessor mailing and situs fields suggest a non-owner occupant.',
                'assessor_address_match_heuristic')
        for home in ordered:
            if home.get('occupancy') not in ('likely_owner_occupied', 'likely_not_owner_occupied'):
                states[str(home.get('id') or home.get('parcel_id'))]['unknown'].append('owner_occupied')

    if filters['recent_sale_days'] > 0:
        def recent(home):
            sold = _day(home.get('sale_date'))
            return sold is not None and sold <= as_of and (as_of - sold).days <= filters['recent_sale_days']
        exclude('recent_sale', 'Recent sale', recent,
                lambda h: f"Sale date { _day(h.get('sale_date')).isoformat() } is within {filters['recent_sale_days']} days.",
                'assessor_sale_date')
        for home in ordered:
            sold = _day(home.get('sale_date'))
            if sold is None or sold > as_of:
                states[str(home.get('id') or home.get('parcel_id'))]['unknown'].append('recent_sale')

    if filters['year_min'] is not None or filters['year_max'] is not None:
        def year_out(home):
            year = _known_year(home.get('year_built'))
            return year is not None and ((filters['year_min'] is not None and year < filters['year_min']) or
                                         (filters['year_max'] is not None and year > filters['year_max']))
        exclude('construction_year', 'Construction year', year_out,
                lambda h: f"Recorded construction year {h['year_built']} is outside the selected range.",
                'assessor_construction_year')
        for home in ordered:
            if _known_year(home.get('year_built')) is None:
                states[str(home.get('id') or home.get('parcel_id'))]['unknown'].append('construction_year')

    optional = (
        ('min_home_value', 'home_value_below_minimum', 'Home value', 'fcv', 'assessor_fcv', 'Assessor FCV'),
        ('min_roof_area_sqft', 'roof_area_below_minimum', 'Roof area', 'roof_area_sqft', None, 'Roof area'),
        ('min_lot_area_sqft', 'lot_area_below_minimum', 'Lot area', 'lot_area_sqft', None, 'Lot area'),
        ('min_system_kw', 'system_size_below_minimum', 'System size', 'system_kw', None, 'System size'),
    )
    for filter_key, code, label, fact_key, source, fact_name in optional:
        threshold = filters[filter_key]
        if threshold is None:
            continue
        def below(home, k=fact_key, t=threshold):
            amount = _fact_number(home, k)
            return amount is not None and amount < t
        exclude(code, label, below,
                lambda h, k=fact_key, t=threshold, n=fact_name: f"Recorded {n.lower()} {_numeric(h.get(k)):g} is below {t:g}.",
                source or ('parcel_geometry' if fact_key == 'lot_area_sqft' else 'google_solar'))
        for home in ordered:
            if _fact_number(home, fact_key) is None:
                state = states[str(home.get('id') or home.get('parcel_id'))]
                bucket = 'pending' if fact_key in ('roof_area_sqft', 'system_kw') and _solar_pending(home) else 'unknown'
                state[bucket].append(filter_key)

    if filters['exclude_condo_multifamily']:
        exclude('condo_multifamily', 'Detached homes only',
                lambda h: h.get('dwelling_type') in ('attached', 'multifamily', 'nonresidential'),
                lambda h: f"Recorded dwelling type is {h['dwelling_type']}; detached homes only.",
                'assessor_dwelling_classification')
        for home in ordered:
            if home.get('dwelling_type') not in ('detached', 'attached', 'multifamily', 'nonresidential'):
                states[str(home.get('id') or home.get('parcel_id'))]['unknown'].append('condo_multifamily')

    if filters['exclude_existing_solar']:
        exclude('existing_solar', 'Existing solar',
                lambda h: h.get('solar_outcome') == 'success' and
                          h.get('solar_detection_status') == 'DETECTION_STATUS_ARRAYS_DETECTED',
                lambda h: 'Google imagery detected existing solar arrays' +
                          (f" as of {h['solar_capture_date']}." if h.get('solar_capture_date') else '.'),
                'google_solar_detected_arrays')
        for home in ordered:
            state = states[str(home.get('id') or home.get('parcel_id'))]
            if _solar_pending(home):
                state['pending'].append('existing_solar')
            elif not (home.get('solar_outcome') == 'success' and home.get('solar_detection_status') in (
                    'DETECTION_STATUS_ARRAYS_DETECTED', 'DETECTION_STATUS_NO_ARRAYS_DETECTED')):
                state['unknown'].append('existing_solar')

    # Legacy clients may explicitly request an internal suppression-list check.
    if filters['exclude_do_not_mail']:
        exclude('do_not_mail', 'Company opt-out list', lambda h: h.get('do_not_mail') is True,
                lambda h: 'Home appears on the company opt-out list.', 'company_suppression_list')
        for home in ordered:
            if type(home.get('do_not_mail')) is not bool:
                states[str(home.get('id') or home.get('parcel_id'))]['unknown'].append('do_not_mail')

    result_homes = []
    counts = {'excluded': 0, 'needs_review': 0, 'not_checked': 0, 'passes_available_checks': 0}
    for home in ordered:
        parcel_id = str(home.get('id') or home.get('parcel_id'))
        state = states[parcel_id]
        unknown = list(dict.fromkeys(state['unknown']))
        pending = list(dict.fromkeys(state['pending']))
        status = ('excluded' if state['reasons'] else 'needs_review' if unknown else
                  'not_checked' if pending else 'passes_available_checks')
        counts[status] += 1
        result_homes.append({
            'parcel_id': parcel_id,
            'apn': home.get('apn'), 'address': home.get('address'),
            'status': status,
            'reason_codes': [reason['code'] for reason in state['reasons']],
            'unknown_checks': unknown, 'pending_checks': pending,
            'reasons': state['reasons'],
            'facts': {
                **_snapshot_facts(home),
                'year_built': home.get('year_built'),
                'occupancy': home.get('occupancy'),
                'sale_date': _day(home.get('sale_date')).isoformat() if _day(home.get('sale_date')) else None,
                'home_value_fcv': _numeric(home.get('fcv')),
            },
        })

    coverage = []

    def cover(code, label, known, source, pending=None):
        known_count = sum(bool(known(h)) for h in ordered)
        pending_count = sum(bool(pending(h)) for h in ordered) if pending else 0
        status = ('available' if ordered and known_count == len(ordered) else
                  'partial' if known_count else 'not_checked' if pending_count else 'unavailable')
        coverage.append({'code': code, 'label': label, 'status': status, 'source': source,
                         'known_count': known_count, 'pending_count': pending_count,
                         'unknown_count': len(ordered) - known_count - pending_count})

    if filters['owner_occupied']:
        cover('owner_occupied', 'Owner occupancy',
              lambda h: h.get('occupancy') in ('likely_owner_occupied', 'likely_not_owner_occupied'),
              'assessor mailing and situs address match heuristic')
    if filters['recent_sale_days']:
        cover('recent_sale', 'Recent sale', lambda h: _day(h.get('sale_date')) is not None and
              _day(h.get('sale_date')) <= as_of, 'assessor SaleDate')
    if filters['exclude_condo_multifamily']:
        cover('condo_multifamily', 'Detached homes only',
              lambda h: h.get('dwelling_type') in ('detached', 'attached', 'multifamily', 'nonresidential'),
              'Arizona DOR use-code mapping; graded single-family is a detached-home proxy, not a shared-wall survey')
    if filters['exclude_existing_solar']:
        cover('existing_solar', 'Existing solar',
              lambda h: h.get('solar_outcome') == 'success' and h.get('solar_detection_status') in (
                  'DETECTION_STATUS_ARRAYS_DETECTED', 'DETECTION_STATUS_NO_ARRAYS_DETECTED'),
              'Google Solar detectedArrays; capture date retained', _solar_pending)
    if filters['exclude_do_not_mail']:
        cover('do_not_mail', 'Company opt-out list', lambda h: type(h.get('do_not_mail')) is bool,
              'company suppression list')
    cover('rental_status', 'Rental flag', lambda h: type(h.get('rental_status')) is bool,
          'assessor RentalInd; flag only')
    cover('year_built', 'Construction year', lambda h: _known_year(h.get('year_built')) is not None,
          'assessor ConstrYear')
    for code, label, key, source in (
        ('home_value_fcv', 'Assessor full cash value', 'fcv', 'assessor FCV'),
        ('roof_area_sqft', 'Roof area', 'roof_area_sqft', 'Google Solar'),
        ('lot_area_sqft', 'Lot area', 'lot_area_sqft', 'parcel geometry'),
        ('system_kw', 'Potential system size', 'system_kw', 'Google Solar panel configuration'),
    ):
        cover(code, label, lambda h, k=key: _fact_number(h, k) is not None, source,
              (lambda h, k=key: _fact_number(h, k) is None and _solar_pending(h))
              if key in ('roof_area_sqft', 'system_kw') else None)
    payload = {
        'policy_version': POLICY_VERSION, 'as_of_date': as_of.isoformat(),
        'as_of_timezone': BUSINESS_TIMEZONE, 'filters': filters,
        'input_count': len(ordered), 'excluded_count': counts['excluded'],
        'needs_review_count': counts['needs_review'], 'not_checked_count': counts['not_checked'],
        'passes_available_checks_count': counts['passes_available_checks'],
        'remaining_count': len(ordered) - counts['excluded'],
        'selection_fingerprint': None,
        'source_warnings': list(source_warnings or []), 'coverage': coverage,
        'steps': steps, 'homes': result_homes,
        'eligible_sample_ids': [h['parcel_id'] for h in result_homes
                                if h['status'] == 'passes_available_checks' and
                                h['parcel_id'] in set((selection or {}).get('sample_ids', []))],
        'needs_review_sample_ids': [h['parcel_id'] for h in result_homes
                                    if h['status'] == 'needs_review' and
                                    h['parcel_id'] in set((selection or {}).get('sample_ids', []))],
        'not_checked_sample_ids': [h['parcel_id'] for h in result_homes
                                   if h['status'] == 'not_checked' and
                                   h['parcel_id'] in set((selection or {}).get('sample_ids', []))],
        'excluded_sample_ids': [h['parcel_id'] for h in result_homes
                                if h['status'] == 'excluded' and
                                h['parcel_id'] in set((selection or {}).get('sample_ids', []))],
        'fact_snapshot': fact_snapshot or {'source_files': [], 'source_snapshot_date': None,
                                           'transform_version': None},
    }
    fingerprint_input = {'policy_version': POLICY_VERSION, 'as_of_date': payload['as_of_date'],
                         'as_of_timezone': BUSINESS_TIMEZONE,
                         'filters': filters, 'selection': selection,
                         'source_snapshot': payload['fact_snapshot'],
                         'homes': [{'parcel_id': h['parcel_id'], 'facts': h['facts']} for h in result_homes]}
    payload['selection_fingerprint'] = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    return payload
