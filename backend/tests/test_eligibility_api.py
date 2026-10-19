import json
import uuid


def _login(client):
    assert client.post('/api/session',json={'token':'test-staff-token'}).status_code==200


def _saved_run(client, appmod):
    _login(client)
    dataset='eligibility-api-fixture'
    area_id=uuid.uuid4()
    parcel_id='04013:12345678'
    parcel={'id':parcel_id,'apn':'12345678','address':'1 TEST ST','unit':None,'city':'PHOENIX',
        'postal_code':'85001','year_built':1998,'mcr_key':'123','mcr_name':'TEST AREA',
        'occupancy':'likely_owner_occupied','occupancy_reason':'Fixture heuristic','dataset_id':dataset,
        'source_file':'Secured_Master_BK01.txt','source_row':2,'property_type':'RESIDENTIAL','puc':'0141',
        'residential':True,'latitude':None,'longitude':None,'geometry':None}
    with appmod.connect() as c:
        c.execute("INSERT INTO datasets(id,input_rows,imported_rows,rejected_rows,files,active) VALUES(%s,1,1,0,'[]',true)",(dataset,))
        c.execute('''INSERT INTO parcels(dataset_id,parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,
          occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
          VALUES(%s,%s,%s,%s,NULL,%s,%s,1998,'123','TEST AREA','likely_owner_occupied','Fixture heuristic',
          'Secured_Master_BK01.txt',2,'1 TEST ST PHOENIX 85001','RESIDENTIAL','0141',true)''',
          (dataset,parcel_id,'12345678','1 TEST ST','PHOENIX','85001'))
        c.execute('''INSERT INTO area_snapshots(id,created_by,dataset_id,payload) VALUES(%s,'local-admin',%s,%s)''',
          (area_id,dataset,json.dumps({'id':str(area_id),'kind':'subdivision','label':'Test area',
            'parcels':[parcel],'coverage':{'complete':True,'unknown_classification_count':0,'warnings':[]},
            'unresolved_ids':[]})))
    selection={'mode':'areas','area_ids':[str(area_id)],'excluded_ids':[],'sample_ids':[parcel_id],'intent':'sample'}
    response=client.post('/api/runs',json={'name':'Eligibility fixture','selection':selection},
        headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==201,response.text
    return response.json(),dataset,parcel_id


def test_preview_requires_auth_and_returns_unknowns_for_enabled_unsupported_rules(client,appmod):
    run,_,_= _saved_run(client,appmod)
    client.delete('/api/session')
    assert client.post('/api/eligibility/preview',json={'selection':run['selection']}).status_code==401
    _login(client)
    response=client.post('/api/eligibility/preview',json={'selection':run['selection'],'filters':{}})
    assert response.status_code==200,response.text
    report=response.json()
    assert report['not_checked_count']==1 and report['needs_review_count']==0 and report['excluded_count']==0
    assert report['homes'][0]['unknown_checks']==[]
    assert report['homes'][0]['pending_checks']==['existing_solar']
    assert report['eligible_sample_ids']==[] and report['needs_review_sample_ids']==[]
    assert report['not_checked_sample_ids']==['04013:12345678']
    assert report['excluded_sample_ids']==[]
    assert any('Source snapshot date is unknown' in warning for warning in report['source_warnings'])
    huge=client.post('/api/eligibility/preview',json={'selection':run['selection'],
        'filters':{'min_home_value':10**400}})
    assert huge.status_code==422


def test_saved_report_is_creator_scoped_idempotent_and_frozen_across_new_facts(client,appmod):
    _login(client)
    run,dataset,parcel_id=_saved_run(client,appmod)
    url='/api/runs/'+run['id']+'/eligibility'
    key='saved-filter-report-1'
    first=client.post(url,json={'filters':{}},headers={'Idempotency-Key':key})
    assert first.status_code==201,first.text
    report_id=first.json()['id']
    retry=client.post(url,json={'filters':{}},headers={'Idempotency-Key':key})
    assert retry.status_code==201 and retry.json()['id']==report_id and retry.json()['created'] is False
    changed=client.post(url,json={'filters':{'recent_sale_days':90}},headers={'Idempotency-Key':key})
    assert changed.status_code==409
    with appmod.connect() as c:
        c.execute('''INSERT INTO parcel_source_fact_snapshots(dataset_id,source_files,transform_version)
          VALUES(%s,'[]',1)''',(dataset,))
        c.execute('''INSERT INTO parcel_source_facts(dataset_id,parcel_id,source_file,source_row,source_sha256,sale_date,fcv)
          VALUES(%s,%s,'Secured_Master_BK01.txt',2,%s,'2026-10-01',300000)''',(dataset,parcel_id,'a'*64))
    fetched=client.get('/api/eligibility/'+report_id)
    assert fetched.status_code==200
    assert fetched.json()['report']==first.json()['report']
    listing=client.get(url)
    assert listing.status_code==200 and listing.json()['reports'][0]['id']==report_id
    with appmod.connect() as c:
        c.execute("UPDATE eligibility_reports SET created_by='different-user' WHERE id=%s",(report_id,))
    assert client.get('/api/eligibility/'+report_id).status_code==404
