from datetime import date

import pytest

from backend.eligibility import evaluate, normalize_filters


def _home(parcel_id, **values):
    return {'id':parcel_id, 'apn':parcel_id.split(':')[-1], 'address':'1 TEST ST', **values}


def test_strict_filter_validation_rejects_unknown_bool_nan_and_reversed_ranges():
    for filters in (
        {'owner_occupied':1}, {'roof_min':100}, {'min_home_value':float('nan')},
        {'year_min':2020,'year_max':2010}, {'recent_sale_days':True}, {'year_min':1800.0},
        {'min_system_kw':-0.1},
    ):
        with pytest.raises(ValueError):
            normalize_filters(filters)
    defaults=normalize_filters({})
    assert defaults['recent_sale_days']==0 and defaults['owner_occupied'] is False
    assert defaults['min_roof_area_sqft'] is None


def test_missing_enabled_checks_hold_homes_and_never_clear_unknowns():
    result=evaluate([_home('04013:A',occupancy='likely_owner_occupied',year_built=2001)],{},
        as_of=date(2026,10,13),selection={'sample_ids':['04013:A']})
    home=result['homes'][0]
    assert home['status']=='needs_review'
    assert set(home['unknown_checks'])=={'condo_multifamily'}
    assert home['pending_checks']==['existing_solar']
    assert result['excluded_count']==0 and result['passes_available_checks_count']==0
    assert result['eligible_sample_ids']==[] and result['needs_review_sample_ids']==['04013:A']


def test_reason_overlap_counts_only_first_exclusion_and_returns_all_reasons():
    homes=[
        _home('04013:A',occupancy='likely_not_owner_occupied',occupancy_reason='Rental flag',sale_date=date(2026,10,1)),
        _home('04013:B',occupancy='likely_not_owner_occupied',occupancy_reason='Rental flag',sale_date=date(2024,1,1)),
        _home('04013:C',occupancy='likely_owner_occupied',sale_date=date(2024,1,1)),
    ]
    result=evaluate(homes,{'exclude_condo_multifamily':False,'exclude_existing_solar':False,
        'exclude_do_not_mail':False,'owner_occupied':True,'recent_sale_days':180},as_of=date(2026,10,13),
        selection={'sample_ids':['04013:A']})
    assert result['excluded_count']==2
    assert sum(step['newly_excluded_count'] for step in result['steps'])==2
    assert result['homes'][0]['reason_codes']==['not_owner_occupied','recent_sale']
    assert result['homes'][1]['reason_codes']==['not_owner_occupied']
    assert result['homes'][2]['reason_codes']==[]
    assert result['excluded_sample_ids']==['04013:A']
    assert result['eligible_sample_ids']==[] and result['needs_review_sample_ids']==[]


def test_recent_sale_boundary_future_and_invalid_dates_are_distinct():
    result=evaluate([
        _home('04013:IN',sale_date=date(2026,4,16)),  # exactly 180 days before the selected date
        _home('04013:OLD',sale_date=date(2026,4,15)),
        _home('04013:FUTURE',sale_date=date(2026,10,14)),
        _home('04013:MISSING'),
    ],{'owner_occupied':False,'exclude_condo_multifamily':False,
       'exclude_existing_solar':False,'exclude_do_not_mail':False,'recent_sale_days':180},as_of=date(2026,10,13))
    status={home['parcel_id']:home for home in result['homes']}
    assert status['04013:IN']['reason_codes']==['recent_sale']
    assert status['04013:OLD']['status']=='passes_available_checks'
    assert status['04013:FUTURE']['unknown_checks']==['recent_sale']
    assert status['04013:MISSING']['unknown_checks']==['recent_sale']


def test_unique_homes_deduplicate_and_fingerprint_binds_filters_and_sources():
    home=_home('04013:A',occupancy='likely_owner_occupied',sale_date=date(2020,1,1))
    source={'datasets':[{'dataset_id':'d1'}], 'source_files':[], 'source_snapshot_date':None}
    kwargs={'as_of':date(2026,10,13),'selection':{'sample_ids':['04013:A']},'fact_snapshot':source}
    first=evaluate([home,dict(home)],{'owner_occupied':False,'recent_sale_days':0,
        'exclude_condo_multifamily':False,'exclude_existing_solar':False,'exclude_do_not_mail':False},**kwargs)
    changed=evaluate([home],{'owner_occupied':False,'recent_sale_days':1,
        'exclude_condo_multifamily':False,'exclude_existing_solar':False,'exclude_do_not_mail':False},**kwargs)
    assert first['input_count']==1
    assert first['selection_fingerprint'] != changed['selection_fingerprint']


@pytest.mark.parametrize('filter_key,fact_key,reason', [
    ('min_home_value','fcv','home_value_below_minimum'),
    ('min_roof_area_sqft','roof_area_sqft','roof_area_below_minimum'),
    ('min_lot_area_sqft','lot_area_sqft','lot_area_below_minimum'),
    ('min_system_kw','system_kw','system_size_below_minimum'),
])
def test_numeric_thresholds_exclude_below_keep_equal_and_hold_missing(filter_key,fact_key,reason):
    filters={'owner_occupied':False,'recent_sale_days':0,'exclude_condo_multifamily':False,
        'exclude_existing_solar':False,'exclude_do_not_mail':False,filter_key:100}
    result=evaluate([_home('A',**{fact_key:99}),_home('B',**{fact_key:100}),_home('C')],
        filters,as_of=date(2026,10,13))
    homes={home['parcel_id']:home for home in result['homes']}
    assert homes['A']['status']=='excluded'
    assert homes['A']['reason_codes']==[reason]
    assert '99' in homes['A']['reasons'][0]['message']
    assert homes['B']['status']=='passes_available_checks'
    assert homes['C']['status']==('not_checked' if fact_key in ('roof_area_sqft','system_kw') else 'needs_review')
    assert result['excluded_count']==result['passes_available_checks_count']==1
    assert result['needs_review_count']+result['not_checked_count']==1


def test_default_policy_keeps_rentals_and_recent_sales_without_mail_list():
    result=evaluate([_home('A', dwelling_type='detached', rental_status=True,
        occupancy='likely_not_owner_occupied', sale_date='2026-10-12')], {},
        as_of=date(2026,10,13),selection={'sample_ids':['A']})
    home=result['homes'][0]
    assert result['policy_version']=='eligibility-2'
    assert home['status']=='not_checked'
    assert home['facts']['rental_status'] is True
    assert home['pending_checks']==['existing_solar'] and home['unknown_checks']==[]
    assert result['not_checked_count']==1 and result['not_checked_sample_ids']==['A']
    assert not {'owner_occupied','recent_sale','do_not_mail'} & {c['code'] for c in result['coverage']}


@pytest.mark.parametrize('dwelling_type,expected', [
    ('detached','passes_available_checks'), ('attached','excluded'),
    ('multifamily','excluded'), ('nonresidential','excluded'), ('unknown','needs_review'),
])
def test_detached_only_classification(dwelling_type,expected):
    home=evaluate([_home('A',dwelling_type=dwelling_type)],
        {'exclude_existing_solar':False})['homes'][0]
    assert home['status']==expected
    if expected=='excluded':
        assert home['reason_codes']==['condo_multifamily']


@pytest.mark.parametrize('outcome,detection,expected,pending', [
    ('not_checked',None,'not_checked',True),
    ('success','DETECTION_STATUS_ARRAYS_DETECTED','excluded',False),
    ('success','DETECTION_STATUS_NO_ARRAYS_DETECTED','passes_available_checks',False),
    ('success','DETECTION_STATUS_DATA_UNAVAILABLE','needs_review',False),
    ('success','DETECTION_STATUS_UNSPECIFIED','needs_review',False),
    ('success',None,'needs_review',False),
    ('failed',None,'needs_review',False),
    ('unavailable',None,'needs_review',False),
    ('building_mismatch','DETECTION_STATUS_NO_ARRAYS_DETECTED','needs_review',False),
])
def test_solar_detection_and_lookup_outcome(outcome,detection,expected,pending):
    result=evaluate([_home('A',dwelling_type='detached',solar_outcome=outcome,
        solar_detection_status=detection,solar_capture_date='2025-07-30')],{})
    home=result['homes'][0]
    assert home['status']==expected
    assert ('existing_solar' in home['pending_checks']) is pending
    assert home['facts']['solar_capture_date']=='2025-07-30'
    if expected=='excluded':
        assert home['reason_codes']==['existing_solar']
        assert '2025-07-30' in home['reasons'][0]['message']
    elif expected=='needs_review':
        assert home['unknown_checks']==['existing_solar']


def test_review_precedes_pending_and_exclusion_precedes_review():
    result=evaluate([_home('A',dwelling_type='unknown'),
        _home('B',dwelling_type='attached',solar_outcome='failed')],{})
    a,b=result['homes']
    assert a['status']=='needs_review' and a['pending_checks']==['existing_solar']
    assert b['status']=='excluded' and b['unknown_checks']==['existing_solar']


def test_optional_solar_thresholds_wait_before_lookup_then_hold_failures():
    result=evaluate([_home('A',solar_outcome='not_checked'),
        _home('B',solar_outcome='failed')],{'exclude_condo_multifamily':False,
        'exclude_existing_solar':False,'min_roof_area_sqft':100,'min_system_kw':2})
    a,b=result['homes']
    assert a['status']=='not_checked' and a['pending_checks']==['min_roof_area_sqft','min_system_kw']
    assert b['status']=='needs_review' and b['unknown_checks']==['min_roof_area_sqft','min_system_kw']


def test_fingerprint_binds_per_home_facts_even_without_snapshot_change():
    base=_home('A',dwelling_type='detached',solar_outcome='success',
        solar_detection_status='DETECTION_STATUS_NO_ARRAYS_DETECTED',solar_capture_date='2025-07-30')
    first=evaluate([base],{},as_of=date(2026,10,13))
    for values in ({'solar_detection_status':'DETECTION_STATUS_ARRAYS_DETECTED'},
                   {'rental_status':True}, {'solar_capture_date':'2026-01-01'},
                   {'roof_area_sqft':100}, {'lot_area_sqft':200}, {'system_kw':3}):
        changed=evaluate([{**base,**values}],{},as_of=date(2026,10,13))
        assert first['selection_fingerprint']!=changed['selection_fingerprint']


def test_dynamic_coverage_reports_known_pending_and_unavailable():
    result=evaluate([_home('A',dwelling_type='detached',solar_outcome='not_checked'),
        _home('B',dwelling_type='attached',solar_outcome='success',
              solar_detection_status='DETECTION_STATUS_NO_ARRAYS_DETECTED'),
        _home('C',solar_outcome='failed')],{})
    solar=next(c for c in result['coverage'] if c['code']=='existing_solar')
    assert (solar['known_count'],solar['pending_count'],solar['unknown_count'])==(1,1,1)
    assert solar['status']=='partial'


def test_report_facts_are_json_serializable_with_database_dates_and_decimals():
    import json
    from decimal import Decimal
    result=evaluate([_home('A',dwelling_type='detached',fcv=Decimal('300000.25'),
        sale_date=date(2026,10,1),num_units=Decimal('1'),
        roof_area_sqft=Decimal('1500.5'),solar_capture_date=date(2025,7,30),
        solar_outcome='success',solar_detection_status='DETECTION_STATUS_NO_ARRAYS_DETECTED')],
        {'min_home_value':Decimal('200000')},as_of=date(2026,10,14))
    serialized=json.loads(json.dumps(result))
    facts=serialized['homes'][0]['facts']
    assert isinstance(facts['fcv'],(int,float)) and facts['fcv']==300000.25
    assert facts['home_value_fcv']==300000.25 and facts['num_units']==1
    assert facts['sale_date']=='2026-10-01' and facts['solar_capture_date']=='2025-07-30'
    assert facts['roof_area_sqft']==1500.5
    assert result['remaining_count']==result['passes_available_checks_count']==1
    assert result['excluded_count']==result['needs_review_count']==result['not_checked_count']==0
