"""Step 3 integration checks use fake Solar responses; never contact Google."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.tests.test_eligibility_api import _saved_run


def _preview(client, run, filters=None):
    response = client.post('/api/eligibility/preview', json={
        'selection': run['selection'], 'filters': filters or {}})
    assert response.status_code == 200, response.text
    return response.json()


def _enrich(client, run):
    return client.post('/api/eligibility/enrich', json={'selection': run['selection'], 'filters': {}})


def _facts(appmod, dataset, parcel_id, *, puc='0141', rental='Y'):
    with appmod.connect() as c:
        c.execute('''INSERT INTO parcel_source_fact_snapshots(dataset_id,source_files,transform_version)
          VALUES(%s,'[]',2) ON CONFLICT(dataset_id) DO NOTHING''', (dataset,))
        c.execute('''INSERT INTO parcel_source_facts(dataset_id,parcel_id,source_file,source_row,
          source_sha256,puc,property_type,rental_ind) VALUES(%s,%s,'Secured_Master_BK01.txt',2,%s,%s,
          'RESIDENTIAL',%s)''', (dataset, parcel_id, 'a' * 64, puc, rental))


def test_unconfigured_preview_and_rental_flags_never_fetch(client, appmod, monkeypatch):
    run, dataset, parcel_id = _saved_run(client, appmod)
    _facts(appmod, dataset, parcel_id)
    monkeypatch.delenv('GOOGLE_SOLAR_API_KEY', raising=False)
    monkeypatch.setattr(appmod.solar, 'fetch_home', lambda _: pytest.fail('Read triggered paid lookup'))
    report = _preview(client, run)
    assert report['solar_configured'] is False
    assert report['excluded_count'] == report['needs_review_count'] == 0
    assert report['not_checked_count'] == 1
    home = report['homes'][0]
    assert home['facts']['rental_status'] is True
    assert home['facts']['dwelling_type'] == 'detached'
    assert home['pending_checks'] == ['existing_solar']
    flags = client.post('/api/parcel-flags', json={'selection': run['selection']})
    assert flags.status_code == 200
    assert flags.json()['homes'] == [{'parcel_id': parcel_id, 'rental_status': True, 'dwelling_type': 'detached'}]
    assert _enrich(client, run).status_code == 503
    client.delete('/api/session')
    assert _enrich(client, run).status_code == 401
    assert client.post('/api/parcel-flags', json={'selection': run['selection']}).status_code == 401


@pytest.mark.parametrize('puc', ['0735', '0320', '0261'])
def test_known_non_detached_parcels_excluded_before_paid_lookup(client, appmod, monkeypatch, puc):
    run, dataset, parcel_id = _saved_run(client, appmod)
    _facts(appmod, dataset, parcel_id, puc=puc, rental='N')
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    monkeypatch.setattr(appmod.solar, 'fetch_home', lambda _: pytest.fail('Excluded home fetched'))
    report = _preview(client, run)
    assert report['excluded_count'] == 1
    assert report['homes'][0]['reason_codes'] == ['condo_multifamily']
    response = _enrich(client, run)
    assert response.status_code == 200
    assert response.json()['checked_count'] == 0


@pytest.mark.parametrize('outcome,detection,status', [
    ('success', 'DETECTION_STATUS_ARRAYS_DETECTED', 'excluded'),
    ('success', 'DETECTION_STATUS_NO_ARRAYS_DETECTED', 'passes_available_checks'),
    ('unavailable', 'DETECTION_STATUS_DATA_UNAVAILABLE', 'needs_review'),
    ('failed', None, 'needs_review'),
    ('building_mismatch', None, 'needs_review'),
])
def test_google_outcomes_cache_without_preview_network(client, appmod, monkeypatch, outcome, detection, status):
    run, _, parcel_id = _saved_run(client, appmod)
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    calls = []
    def fake(home):
        calls.append(home['id'])
        return outcome, {'solar_outcome': outcome, 'solar_detection_status': detection,
                         'solar_capture_date': '2025-07-30'}
    monkeypatch.setattr(appmod.solar, 'fetch_home', fake)
    assert _preview(client, run)['homes'][0]['status'] == 'not_checked'
    assert calls == []
    first = _enrich(client, run)
    assert first.status_code == 200, first.text
    assert first.json()['checked_count'] == 1
    report = _preview(client, run)
    assert report['homes'][0]['status'] == status
    assert report['solar_expires_at']
    assert calls == [parcel_id]
    second = _enrich(client, run)
    assert second.status_code == 200
    assert second.json()['checked_count'] == 0
    assert calls == [parcel_id]


def test_enrichment_ten_request_batches_cache_across_retries(client, appmod, monkeypatch):
    run, dataset, original_id = _saved_run(client, appmod)
    area_id = run['selection']['area_ids'][0]
    with appmod.connect() as c:
        payload = c.execute('SELECT payload FROM area_snapshots WHERE id=%s', (area_id,)).fetchone()[0]
        base = payload['parcels'][0]
        for index in range(1, 12):
            apn = str(12345678 + index)
            parcel_id = '04013:' + apn
            c.execute('''INSERT INTO parcels(dataset_id,parcel_id,apn,address,city,postal_code,
              occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
              VALUES(%s,%s,%s,'1 TEST ST','PHOENIX','85001','unknown','fixture',
              'Secured_Master_BK01.txt',%s,'1 TEST ST','RESIDENTIAL','0141',true)''',
              (dataset, parcel_id, apn, index + 2))
            payload['parcels'].append({**base, 'id': parcel_id, 'apn': apn, 'source_row': index + 2})
        c.execute('UPDATE area_snapshots SET payload=%s WHERE id=%s', (json.dumps(payload), area_id))
    calls = []
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    def fake(home):
        calls.append(home['id'])
        return 'success', {'solar_outcome': 'success',
            'solar_detection_status': 'DETECTION_STATUS_NO_ARRAYS_DETECTED'}
    monkeypatch.setattr(appmod.solar, 'fetch_home', fake)
    assert _enrich(client, run).json() == {'checked_count': 10, 'cached_count': 0,
                                          'failed_count': 0, 'remaining_count': 2}
    assert _enrich(client, run).json() == {'checked_count': 2, 'cached_count': 10,
                                          'failed_count': 0, 'remaining_count': 0}
    assert _enrich(client, run).json()['checked_count'] == 0
    assert len(calls) == len(set(calls)) == 12


def test_expired_google_content_not_returned_and_saved_reports_purged(client, appmod, monkeypatch):
    run, dataset, parcel_id = _saved_run(client, appmod)
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    monkeypatch.setattr(appmod.solar, 'fetch_home', lambda home: ('success', {
        'solar_outcome': 'success', 'solar_detection_status': 'DETECTION_STATUS_NO_ARRAYS_DETECTED'}))
    assert _enrich(client, run).status_code == 200
    url = '/api/runs/' + run['id'] + '/eligibility'
    saved = client.post(url, json={'filters': {}}, headers={'Idempotency-Key': 'expiry-test'})
    assert saved.status_code == 201
    report_id = saved.json()['id']
    with appmod.connect() as c:
        c.execute("UPDATE parcel_solar_facts SET fetched_at=now()-interval '31 days'")
        c.execute("""UPDATE eligibility_reports SET report=jsonb_set(report,'{solar_expires_at}',
          to_jsonb((now()-interval '1 day')::text)) WHERE id=%s""", (report_id,))
    assert _preview(client, run)['homes'][0]['status'] == 'not_checked'
    # Retry must not bypass retention by returning frozen, expired Google content.
    retry = client.post(url, json={'filters': {}}, headers={'Idempotency-Key': 'expiry-test'})
    assert retry.status_code == 201
    assert retry.json()['report']['homes'][0]['status'] == 'not_checked'
    assert client.get('/api/eligibility/' + report_id).status_code == 404
    with appmod.connect() as c:
        assert c.execute('SELECT count(*) FROM parcel_solar_facts').fetchone()[0] == 0


def test_flags_and_enrichment_require_owned_area(client, appmod, monkeypatch):
    run, _, _ = _saved_run(client, appmod)
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    monkeypatch.setattr(appmod.solar, 'fetch_home', lambda _: pytest.fail('Foreign area fetched'))
    client.cookies.set('solar_session', appmod.serializer.dumps({'user': 'other-user'}))
    assert client.post('/api/parcel-flags', json={'selection': run['selection']}).status_code == 404
    assert _enrich(client, run).status_code == 404


def test_concurrent_lookup_clicks_fetch_same_home_once(client, appmod, monkeypatch):
    run, _, parcel_id = _saved_run(client, appmod)
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    calls = []
    def fake(home):
        calls.append(home['id'])
        time.sleep(0.1)
        return 'success', {'solar_outcome': 'success',
            'solar_detection_status': 'DETECTION_STATUS_NO_ARRAYS_DETECTED'}
    monkeypatch.setattr(appmod.solar, 'fetch_home', fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _enrich(client, run), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert sum(response.json()['checked_count'] for response in responses) == 1
    assert calls == [parcel_id]


def test_failed_lookup_retry_after_short_cache_without_retrying_success(client, appmod, monkeypatch):
    run, dataset, parcel_id = _saved_run(client, appmod)
    monkeypatch.setenv('GOOGLE_SOLAR_API_KEY', 'fake-no-network')
    calls = []
    def fake(home):
        calls.append(home['id'])
        if len(calls) == 1:
            return 'failed', {'solar_outcome': 'failed'}
        return 'success', {'solar_outcome': 'success',
            'solar_detection_status': 'DETECTION_STATUS_NO_ARRAYS_DETECTED'}
    monkeypatch.setattr(appmod.solar, 'fetch_home', fake)
    assert _enrich(client, run).json()['failed_count'] == 1
    assert _enrich(client, run).json()['checked_count'] == 0
    with appmod.connect() as c:
        c.execute("UPDATE parcel_solar_facts SET fetched_at=now()-interval '6 minutes'")
    assert _enrich(client, run).json()['checked_count'] == 1
    assert _preview(client, run)['homes'][0]['status'] == 'passes_available_checks'
    with appmod.connect() as c:
        c.execute("UPDATE parcel_solar_facts SET fetched_at=now()-interval '6 minutes'")
    assert _enrich(client, run).json()['checked_count'] == 0
    assert calls == [parcel_id, parcel_id]


def test_saved_report_serializes_native_database_numeric_and_date_facts(client,appmod,monkeypatch):
    run,dataset,parcel_id=_saved_run(client,appmod)
    _facts(appmod,dataset,parcel_id)
    monkeypatch.delenv('GOOGLE_SOLAR_API_KEY',raising=False)
    with appmod.connect() as c:
        c.execute('''UPDATE parcel_source_facts SET fcv=300000.25,sale_date='2026-10-01'
          WHERE dataset_id=%s AND parcel_id=%s''',(dataset,parcel_id))
    url='/api/runs/'+run['id']+'/eligibility'
    filters={'min_home_value':300000,'exclude_existing_solar':False}
    first=client.post(url,json={'filters':filters},headers={'Idempotency-Key':'native-facts-report'})
    assert first.status_code==201,first.text
    report=first.json()['report']
    facts=report['homes'][0]['facts']
    assert facts['fcv']==300000.25 and isinstance(facts['fcv'],(int,float))
    assert facts['sale_date']=='2026-10-01'
    assert report['remaining_count']==report['passes_available_checks_count']==1
    assert report['excluded_count']==report['needs_review_count']==report['not_checked_count']==0
    fetched=client.get('/api/eligibility/'+first.json()['id'])
    assert fetched.status_code==200 and fetched.json()['report']==report
    retry=client.post(url,json={'filters':filters},headers={'Idempotency-Key':'native-facts-report'})
    assert retry.status_code==201 and retry.json()['id']==first.json()['id']
