import json
import uuid

from backend import ahj
from backend.tests.test_eligibility_api import _saved_run


def _resolved_ahj(monkeypatch):
    monkeypatch.setattr(ahj,'assess',lambda c,parcels,overrides:{'assignments':[
        {'parcel_id':p['id'],'ahj_id':'city-test','ahj_name':'Test City',
         'method':'boundary','status':'verified','source':{},'candidates':['city-test']}
        for p in parcels]})


def test_house_inspect_includes_excluded_house_and_arrays_are_checked(client,appmod,monkeypatch):
    run,dataset,parcel_id = _saved_run(client,appmod)
    _resolved_ahj(monkeypatch)
    with appmod.connect() as c:
        c.execute('''INSERT INTO parcel_solar_facts(dataset_id,parcel_id,outcome,facts)
          VALUES(%s,%s,'success',%s::jsonb)''',(dataset,parcel_id,json.dumps({
              'solar_outcome':'success','solar_detection_status':'DETECTION_STATUS_ARRAYS_DETECTED',
              'solar_capture_date':'2025-07-30','roof_area_sqft':1200,'system_kw':8.2})))
    selection = dict(run['selection'],intent='all',excluded_ids=[parcel_id],sample_ids=[])
    detail = client.post('/api/houses/inspect',json={'selection':selection,'parcel_id':parcel_id})
    assert detail.status_code == 200, detail.text
    record = detail.json()
    assert record['property']['dwelling_type'] == 'detached'
    assert record['review']['status'] == 'checked'
    assert record['review']['solar_detection_status'] == 'DETECTION_STATUS_ARRAYS_DETECTED'
    assert record['eligibility']['status'] == 'excluded'
    assert record['design'] == {'status':'not_run','available':False,'history':[]}
    summary = client.post('/api/houses/summary',json={'selection':selection})
    assert summary.status_code == 200, summary.text
    assert summary.json()['counts'] == {'total':1,'reviewed':1,'not_reviewed':0,
        'needs_attention':0,'designed':0}


def test_saved_report_scope_uses_explicit_exclusions_and_rejects_foreign_scope(client,appmod):
    run,dataset,parcel_id = _saved_run(client,appmod)
    second_id = '04013:87654321'
    with appmod.connect() as c:
        row = c.execute('SELECT payload FROM area_snapshots WHERE id=%s',
                        (run['selection']['area_ids'][0],)).fetchone()
        payload = row[0]
        second = dict(payload['parcels'][0],id=second_id,apn='87654321',address='2 TEST ST')
        payload['parcels'].append(second)
        c.execute('''INSERT INTO parcels(dataset_id,parcel_id,apn,address,city,postal_code,occupancy,
          occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
          VALUES(%s,%s,'87654321','2 TEST ST','PHOENIX','85001','likely_owner_occupied',
          'Fixture heuristic','Secured_Master_BK01.txt',3,'2 TEST ST PHOENIX 85001','RESIDENTIAL','0141',true)''',
          (dataset,second_id))
        c.execute('UPDATE area_snapshots SET payload=%s WHERE id=%s',
                  (json.dumps(payload),run['selection']['area_ids'][0]))
    area_id = run['selection']['area_ids'][0]
    url = '/api/runs/'+run['id']+'/eligibility'
    whole = dict(run['selection'],intent='sample',sample_ids=[parcel_id])
    response = client.post(url,json={'filters':{},'selection':whole},
        headers={'Idempotency-Key':'scope-whole'})
    assert response.status_code == 201, response.text
    assert response.json()['report']['input_count'] == 2
    one = dict(run['selection'],intent='single',sample_ids=[parcel_id],excluded_ids=[second_id])
    response = client.post(url,json={'filters':{},'selection':one},
        headers={'Idempotency-Key':'scope-one'})
    assert response.status_code == 201, response.text
    assert response.json()['report']['input_count'] == 1
    assert response.json()['report']['review_scope']['parcel_ids'] == [parcel_id]
    scoped_report_id = response.json()['id']
    with appmod.connect() as c:
        c.execute('DELETE FROM house_review_events WHERE report_id=%s',(scoped_report_id,))
        c.execute('''UPDATE eligibility_reports SET report=jsonb_set(report,
          '{homes,0,facts,solar_fetched_at}',to_jsonb('2025-07-30T00:00:00+00:00'::text),true)
          WHERE id=%s''',(scoped_report_id,))
    appmod.init_db()
    with appmod.connect() as c:
        backfilled = c.execute('''SELECT count(*) FROM house_review_events
          WHERE report_id=%s AND created_by='local-admin' AND parcel_id=%s
            AND kind='eligibility_report' ''',
          (scoped_report_id,parcel_id)).fetchone()[0]
        solar_backfill = c.execute('''SELECT created_at FROM house_review_events
          WHERE report_id=%s AND created_by='local-admin' AND parcel_id=%s AND kind='solar_lookup' ''',
          (scoped_report_id,parcel_id)).fetchone()
    assert backfilled == 1
    assert solar_backfill is not None
    detail = client.post('/api/houses/inspect',json={'selection':run['selection'],'parcel_id':parcel_id})
    assert detail.status_code == 200, detail.text
    assert detail.json()['review']['status'] == 'refresh_needed'
    assert detail.json()['review']['solar_detection_status'] is None

    outside_id = uuid.uuid4()
    with appmod.connect() as c:
        c.execute('''INSERT INTO area_snapshots(id,created_by,dataset_id,payload)
          VALUES(%s,'local-admin',%s,%s)''',(outside_id,dataset,json.dumps({
              'id':str(outside_id),'kind':'subdivision','label':'Outside saved run',
              'parcels':[payload['parcels'][0]],'coverage':{'complete':True,'unknown_classification_count':0,'warnings':[]},
              'unresolved_ids':[]})))
    out_of_run = dict(run['selection'],area_ids=[str(outside_id)],sample_ids=[],intent='all')
    rejected = client.post(url,json={'filters':{},'selection':out_of_run},
        headers={'Idempotency-Key':'scope-outside'})
    assert rejected.status_code == 422

    foreign_id = uuid.uuid4()
    with appmod.connect() as c:
        c.execute('''INSERT INTO area_snapshots(id,created_by,dataset_id,payload)
          VALUES(%s,'another-user',%s,%s)''',(foreign_id,dataset,json.dumps({
              'id':str(foreign_id),'kind':'subdivision','label':'Private area',
              'parcels':[payload['parcels'][0]],'coverage':{'complete':True,'unknown_classification_count':0,'warnings':[]},
              'unresolved_ids':[]})))
    foreign = dict(run['selection'],area_ids=[str(foreign_id)],sample_ids=[],intent='all')
    rejected = client.post(url,json={'filters':{},'selection':foreign},
        headers={'Idempotency-Key':'scope-foreign'})
    assert rejected.status_code == 404
