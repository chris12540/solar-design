import uuid
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from fastapi.testclient import TestClient
from backend.tests.test_eligibility_api import _saved_run


def _inputs():
    fetched = datetime.now(timezone.utc)
    return {'insights':{'name':'test-roof'},'dsm':b'fixture-dsm','mask':b'fixture-mask',
            'fetched_at':fetched.isoformat(),'expires_at':(fetched+timedelta(days=30)).isoformat(),
            'source_warnings':['Fixture source-date uncertainty']}


def _result():
    return {'status':'needs_review','algorithm_version':'roof-1','faces':[
        {'id':'1','polygon':[[0,0],[2,0],[2,2],[0,2],[0,0]],'holes':[]}],
        'obstruction_candidates':[],'quality':{'assigned_fraction':1.0},
        'warnings':['Not validated for design.'],'design_ready':False}


def test_roof_status_auth_ownership_and_explicit_fetch_cached(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry
    run,dataset,parcel = _saved_run(client,appmod)
    calls=[]
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(calls.append(home['id']) or _inputs()))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:_result())
    body={'selection':run['selection'],'parcel_id':parcel}
    path='/api/houses/roof/'
    read=client.post(path+'status',json=body)
    assert read.status_code==200 and read.json()=={'status':'not_run'}
    assert calls==[]
    wrong=client.post(path+'reconstruct',json={**body,'parcel_id':'foreign'})
    assert wrong.status_code==404 and calls==[]
    first=client.post(path+'reconstruct',json=body)
    assert first.status_code==200, first.text
    assert first.json()['reused'] is False and first.json()['result']['design_ready'] is False
    assert first.json()['result']['ahj']=={'status':'pending_rules'}
    assert 'fixture-dsm' not in first.text
    second=client.post(path+'reconstruct',json=body)
    assert second.status_code==200 and second.json()['reused'] is True
    assert len(calls)==1
    assert second.json()['fetched_at']==first.json()['fetched_at']
    assert second.json()['expires_at']==first.json()['expires_at']
    with appmod.connect() as c:
        c.execute("UPDATE roof_reconstructions SET created_by='another-user' WHERE dataset_id=%s",(dataset,))
    assert client.post(path+'status',json=body).json()=={'status':'not_run'}
    client.cookies.clear()
    assert client.post(path+'status',json=body).status_code==401
    assert client.post(path+'reconstruct',json=body).status_code==401
    assert len(calls)==1


def test_roof_expiry_purges_sources_and_rerun_reacquires(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry
    run,dataset,parcel = _saved_run(client,appmod)
    calls=[]
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(calls.append(1) or _inputs()))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:_result())
    body={'selection':run['selection'],'parcel_id':parcel}
    assert client.post('/api/houses/roof/reconstruct',json=body).status_code==200
    with appmod.connect() as c:
        c.execute("UPDATE roof_reconstructions SET source_fetched_at=now()-interval '31 days',expires_at=now()-interval '1 day'")
    assert client.post('/api/houses/roof/status',json=body).json()=={'status':'not_run'}
    appmod.purge_solar_data()
    with appmod.connect() as c:
        assert c.execute('SELECT count(*) FROM roof_reconstructions').fetchone()[0]==0
    assert client.post('/api/houses/roof/reconstruct',json=body).status_code==200
    assert len(calls)==2


def test_algorithm_rerun_uses_cached_inputs_without_extending_expiry(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry
    run,dataset,parcel = _saved_run(client,appmod)
    calls=[]
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(calls.append(1) or _inputs()))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:_result())
    body={'selection':run['selection'],'parcel_id':parcel}
    first=client.post('/api/houses/roof/reconstruct',json=body).json()
    with appmod.connect() as c:
        c.execute("UPDATE roof_reconstructions SET algorithm_version='old-algorithm'")
    stale=client.post('/api/houses/roof/status',json=body).json()
    assert stale['status']=='not_run' and 'result' not in stale
    second=client.post('/api/houses/roof/reconstruct',json=body).json()
    assert len(calls)==1
    assert first['expires_at']==second['expires_at']
    assert second['reused'] is True
    assert 'Fixture source-date uncertainty' in second['result']['warnings']


def test_concurrent_roof_requests_do_not_duplicate_paid_fetch(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry
    run,dataset,parcel = _saved_run(client,appmod)
    started,release=Event(),Event()
    calls=[]
    def fetch(home):
        calls.append(1);started.set()
        assert release.wait(10)
        return _inputs()
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',fetch)
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:_result())
    body={'selection':run['selection'],'parcel_id':parcel}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.post,'/api/houses/roof/reconstruct',json=body)
        assert started.wait(5)
        try:
            second=client.post('/api/houses/roof/reconstruct',json=body)
            assert second.status_code==409
        finally:release.set()
        assert first.result().status_code==200
    assert len(calls)==1


def test_refinement_and_ranking_version_changes_reuse_sources(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry,roof_refinement,roof_ranking
    run,dataset,parcel = _saved_run(client,appmod)
    acquisitions=[]
    raw=_result()
    raw['roof_outline']={'polygon':[[0,0],[2,0],[2,2],[0,2],[0,0]],'holes':[]}
    def refine(raw,inputs,home):
        return {'status':'experimental','face_groups':[{'id':'face-1','parts':[
            {'polygon':raw['faces'][0]['polygon'],'holes':[]}]}],
            'edges':[],'warnings':[],'design_ready':True}
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(acquisitions.append(1) or _inputs()))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:dict(raw))
    monkeypatch.setattr(roof_refinement,'refine',refine)
    monkeypatch.setattr(roof_ranking,'rank_candidates',lambda refined,raw,inputs:[
        {'face_id':'face-1','rank':1,'unknown_checks':['AHJ setbacks']}])
    body={'selection':run['selection'],'parcel_id':parcel}
    first=client.post('/api/houses/roof/reconstruct',json=body)
    assert first.status_code==200,first.text
    assert first.json()['result']['refinement']['design_ready'] is False
    assert first.json()['result']['refinement']['candidates'][0]['rank']==1
    monkeypatch.setattr(roof_ranking,'ALGORITHM_VERSION','rank-test-2')
    assert client.post('/api/houses/roof/status',json=body).json()['status']=='not_run'
    second=client.post('/api/houses/roof/reconstruct',json=body)
    assert second.status_code==200,second.text
    assert len(acquisitions)==1
    assert second.json()['reused'] is True
    assert second.json()['expires_at']==first.json()['expires_at']
    assert 'rank-test-2' in second.json()['algorithm_version']


def test_refinement_failure_retains_raw_and_sources(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry,roof_refinement
    run,dataset,parcel = _saved_run(client,appmod)
    raw=_result()
    raw['roof_outline']={'polygon':raw['faces'][0]['polygon'],'holes':[]}
    calls=[]
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(calls.append(1) or _inputs()))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda inputs,home:dict(raw))
    def fail(*args):raise ValueError('Bad topology')
    monkeypatch.setattr(roof_refinement,'refine',fail)
    body={'selection':run['selection'],'parcel_id':parcel}
    response=client.post('/api/houses/roof/reconstruct',json=body)
    assert response.status_code==200,response.text
    assert response.json()['result']['faces']==raw['faces']
    assert response.json()['result']['refinement']['status']=='unavailable'
    assert 'Bad topology' not in response.text
    assert client.post('/api/houses/roof/reconstruct',json=body).json()['reused'] is True
    assert len(calls)==1


def test_rgb_fitting_versions_reuse_bytes_and_original_expiry(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry,roof_fitting,roof_photo
    run,dataset,parcel=_saved_run(client,appmod)
    inputs={**_inputs(),'rgb':b'fixture-rgb','source_metadata':{'raster_imagery_date':'2023-09-27'}}
    raw=_result();raw['roof_outline']={'polygon':raw['faces'][0]['polygon'],'holes':[]}
    acquisitions=[];seen=[]
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:(acquisitions.append(1) or inputs))
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda *args:dict(raw))
    monkeypatch.setattr(roof_photo,'preview',lambda *args:{'data_url':'data:image/png;base64,cG5n','bounds':{}})
    def fit(raw,inputs,home):
        seen.append((inputs['rgb'],inputs['source_metadata']))
        return {'status':'experimental','face_groups':[],'quality':{},'design_ready':True}
    monkeypatch.setattr(roof_fitting,'fit',fit)
    body={'selection':run['selection'],'parcel_id':parcel}
    first=client.post('/api/houses/roof/reconstruct',json=body)
    assert first.status_code==200,first.text
    assert first.json()['result']['fitting']['design_ready'] is False
    monkeypatch.setattr(roof_fitting,'ALGORITHM_VERSION','fit-test-2')
    assert client.post('/api/houses/roof/status',json=body).json()['status']=='not_run'
    second=client.post('/api/houses/roof/reconstruct',json=body)
    assert second.status_code==200,second.text
    assert len(acquisitions)==1 and seen==[(b'fixture-rgb',inputs['source_metadata'])]*2
    assert first.json()['expires_at']==second.json()['expires_at']
    with appmod.connect() as c:
        stored=c.execute('SELECT rgb,source_metadata FROM roof_reconstructions').fetchone()
    assert bytes(stored[0])==b'fixture-rgb' and stored[1]==inputs['source_metadata']


def test_fitting_and_photo_failure_preserve_raw_and_cached_inputs(client,appmod,monkeypatch):
    from backend import solar_roof,roof_geometry,roof_fitting,roof_photo
    run,dataset,parcel=_saved_run(client,appmod)
    raw=_result();raw['roof_outline']={'polygon':raw['faces'][0]['polygon'],'holes':[]}
    monkeypatch.setattr(solar_roof,'fetch_roof_inputs',lambda home:{**_inputs(),'rgb':b'rgb'})
    monkeypatch.setattr(roof_geometry,'reconstruct',lambda *args:dict(raw))
    def fail(*args):raise ValueError('private internal details')
    monkeypatch.setattr(roof_fitting,'fit',fail);monkeypatch.setattr(roof_photo,'preview',fail)
    response=client.post('/api/houses/roof/reconstruct',json={'selection':run['selection'],'parcel_id':parcel})
    assert response.status_code==200,response.text
    result=response.json()['result']
    assert result['photo'] is None and result['fitting']['status']=='unavailable'
    assert result['faces']==raw['faces'] and not result['design_ready']
    assert 'private internal details' not in response.text
