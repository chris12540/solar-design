import json
import importlib
import uuid
from concurrent.futures import ThreadPoolExecutor

from backend import gis


def _polygon(x1, y1, x2, y2):
    return {'type': 'Polygon', 'coordinates': [[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]]}


def _feature(apn, geometry, name='TEST AREA', key='700'):
    return {'type':'Feature','properties':{'APN':apn,'LATITUDE':33.4,'LONGITUDE':-112.1,
        'mcrnum_secured':key,'mcrnum':key,'subname':name},'geometry':geometry}


def _login(client):
    assert client.post('/api/session', json={'token':'test-staff-token'}).status_code == 200


def _seed_area(client, appmod, monkeypatch):
    ahj = importlib.import_module('backend.ahj')
    boundary = _polygon(-112.2,33.2,-112.0,33.6)
    one = _polygon(-112.15,33.3,-112.14,33.31)
    two = _polygon(-112.12,33.3,-112.11,33.31)
    with appmod.connect() as c:
        c.execute("insert into datasets(id,input_rows,imported_rows,rejected_rows,files,active) values('review-fixture',0,0,0,'[]',true) on conflict(id) do nothing")
        for apn, year, geom in [('R1',1970,one),('R2',2005,two)]:
            c.execute('''insert into parcels(dataset_id,parcel_id,apn,address,city,postal_code,year_built,mcr_key,mcr_name,
              occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
              values('review-fixture',%s,%s,%s,'PHOENIX','85001',%s,'97000','TEST AREA','unknown','test','fixture',1,%s,'RESIDENTIAL','001',true)''',
              ('04013:'+apn,apn,'1 TEST ST',year,'1 TEST ST PHOENIX 85001'))
            c.execute('update parcels set county_geometry=ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) where dataset_id=\'review-fixture\' and apn=%s',
                      (json.dumps(geom),apn))
    monkeypatch.setattr(gis, 'subdivision', lambda key: [{**_feature('x', boundary), 'properties':
        {'mcrnum_secured':key,'mcrnum':key,'subname':'TEST AREA'}}])
    monkeypatch.setattr(gis, 'parcels_in_geometry', lambda geom: [_feature('R1',one),_feature('R2',two)])
    monkeypatch.setattr(ahj, 'registry', lambda c: {'ahjs':[{'id':'draft-1','name':'Draft AHJ',
        'ahj_type':'city','county':'Maricopa','state':'AZ','boundary_ref':None,'status':'provisional'}],
        'source':'user_provided_d1_snapshot'})
    def assess(c, parcels, overrides):
        return {'assignments':[{'parcel_id':p['id'],'ahj_id':overrides.get(p['id'],'draft-1'),
            'ahj_name':'Draft AHJ','method':'manual' if p['id'] in overrides else 'boundary',
            'status':'provisional','source':{'kind':'fixture'},'candidates':['draft-1']}
            for p in parcels], 'summary':[{'ahj_id':'draft-1','name':'Draft AHJ','count':len(parcels),
            'status':'provisional'}], 'unresolved_count':0}
    monkeypatch.setattr(ahj, 'assess', assess)
    response=client.post('/api/areas/resolve', json={'kind':'subdivision','mcr_key':'97000'})
    assert response.status_code == 200, response.text
    return response.json()


def test_review_auth_ambiguity_no_match_and_gis_outage(client, appmod, monkeypatch):
    _login(client)
    _seed_area(client, appmod, monkeypatch)
    assert client.get('/api/neighborhoods/review', params={'lat':33.4,'lng':-112.1}).status_code == 405
    client.delete('/api/session')
    assert client.get('/api/neighborhoods/at', params={'lat':33.4,'lng':-112.1}).status_code == 401
    _login(client)
    with appmod.connect() as c:
        c.execute('delete from county_subdivisions')
    shared = _polygon(-112.2,33.2,-112.0,33.6)
    monkeypatch.setattr(gis, 'subdivisions_at_point', lambda lat,lng: [
        _feature('x', shared, 'Candidate A', '701'), _feature('y', shared, 'Candidate B', '702')])
    response=client.get('/api/neighborhoods/at', params={'lat':33.4,'lng':-112.1})
    assert response.status_code == 200
    assert {item['mcr_key'] for item in response.json()['matches']} == {'701','702'}
    monkeypatch.setattr(gis, 'subdivisions_at_point', lambda lat,lng: [])
    assert client.get('/api/neighborhoods/at', params={'lat':33.4,'lng':-112.1}).json()['matches'] == []
    def outage(*args): raise gis.GISUnavailable('offline')
    monkeypatch.setattr(gis, 'subdivisions_at_point', outage)
    fallback=client.get('/api/neighborhoods/at', params={'lat':33.4,'lng':-112.1})
    assert fallback.status_code == 200 and len(fallback.json()['matches']) == 2
    assert 'may omit' in fallback.json()['warnings'][0]
    with appmod.connect() as c:
        c.execute('delete from county_subdivisions')
    assert client.get('/api/neighborhoods/at', params={'lat':33.4,'lng':-112.1}).status_code == 503


def test_confirmation_freezes_review_retry_is_idempotent_and_warns_on_year_spread(client, appmod, monkeypatch):
    _login(client)
    area = _seed_area(client, appmod, monkeypatch)
    selection={'mode':'areas','area_ids':[area['id']],'excluded_ids':[],
        'sample_ids':[],'intent':'all'}
    review=client.post('/api/neighborhoods/review', json={'selection':selection})
    assert review.status_code == 200, review.text
    assert review.json()['included_count'] == 2
    assert any(w['code']=='construction_year_spread' and w['anchor'] for w in review.json()['warnings'])
    assert any(w['code']=='ahj_provisional' for w in review.json()['warnings'])
    body={'name':'Confirmed neighborhood','selection':selection}
    key=str(uuid.uuid4())
    headers={'Idempotency-Key':key}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _: client.post('/api/runs/confirm',json=body,headers=headers), range(4)))
    assert all(response.status_code == 201 for response in responses)
    ids={response.json()['id'] for response in responses}
    assert len(ids)==1
    run=responses[0].json()
    assert run['status']=='confirmed' and run['review']==review.json()
    with appmod.connect() as c:
        c.execute('update area_snapshots set payload=\'{}\'::jsonb where id=%s', (area['id'],))
    fetched=client.get('/api/runs/'+run['id'])
    assert fetched.status_code==200
    assert fetched.json()['review']==run['review']
    assert fetched.json()['areas'][0]['parcels']==area['parcels']


def test_confirmation_validates_overrides_and_rejects_empty_included_group(client, appmod, monkeypatch):
    _login(client)
    area=_seed_area(client, appmod, monkeypatch)
    selection={'mode':'areas','area_ids':[area['id']],'excluded_ids':area['parcels'] and
        [p['id'] for p in area['parcels']],'sample_ids':[],'intent':'all'}
    assert client.post('/api/runs/confirm',json={'name':'Empty','selection':selection},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    selection['excluded_ids']=[]
    bad={'name':'Bad override','selection':selection,'ahj_overrides':{'outside':'draft-1'}}
    assert client.post('/api/neighborhoods/review',json=bad).status_code==422
    unknown={'name':'Bad registry ID','selection':selection,
        'ahj_overrides':{area['parcels'][0]['id']:'unknown'}}
    assert client.post('/api/neighborhoods/review',json=unknown).status_code==422


def test_padded_county_mcr_maps_to_local_key_and_keeps_county_provenance(client, appmod, monkeypatch):
    _login(client)
    county_boundary = _polygon(-112.2,33.2,-112.0,33.6)
    parcel_geometry = _polygon(-112.15,33.3,-112.14,33.31)
    with appmod.connect() as c:
        c.execute("insert into datasets(id,input_rows,imported_rows,rejected_rows,files,active) values('mcr-alias-fixture',0,0,0,'[]',true) on conflict(id) do nothing")
        c.execute('''insert into parcels(dataset_id,parcel_id,apn,address,city,postal_code,year_built,mcr_key,mcr_name,
          occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
          values('mcr-alias-fixture','04013:ALIAS1','ALIAS1','1 TEST ST','GILA BEND','85337',1988,
          '8150','GILA BEND ESTATES','unknown','test','fixture',1,'1 TEST ST GILA BEND 85337','RESIDENTIAL','001',true)''')
        c.execute("delete from county_subdivisions where mcr_key in ('8150','08150')")
    feature={'type':'Feature','properties':{'mcrnum_secured':'08150','mcrnum':'081-50',
        'subname':'GILA BEND ESTATES'},'geometry':county_boundary}
    monkeypatch.setattr(gis,'subdivisions_at_point',lambda lat,lng:[feature])
    monkeypatch.setattr(gis,'parcels_in_geometry',lambda geometry:[])
    response=client.get('/api/neighborhoods/at',params={'lat':33.4,'lng':-112.1})
    assert response.status_code==200,response.text
    candidate=response.json()['matches'][0]
    assert candidate['mcr_key']=='8150'
    assert candidate['county_mcr_key']=='08150'
    area=client.post('/api/areas/resolve',json={'kind':'subdivision','mcr_key':candidate['mcr_key']})
    assert area.status_code==200,area.text
    assert area.json()['provenance']['county_mcr_key']=='08150'


def test_subdivision_query_tries_bounded_zero_padded_exact_keys(monkeypatch):
    seen=[]
    monkeypatch.setattr(gis,'_page',lambda params,layer:(seen.append(params) or []))
    assert gis.subdivision('8150')==[]
    assert "'08150'" in seen[0]['where']
    assert "'008150'" in seen[0]['where']
