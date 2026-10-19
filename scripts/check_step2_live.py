"""Verify Step 2 against real local selection and public county lookup.
No design jobs; creates one private confirmed verification snapshot.
"""
import json,os,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from dev import environment
os.environ.update(environment())
from backend import app as appmod
from backend import ahj
from fastapi.testclient import TestClient

results={}
with TestClient(appmod.app) as c:
 assert c.post('/api/session',json={'token':os.environ['STAFF_TOKEN']}).status_code==200
 registry=c.get('/api/ahjs').json()
 assert len(registry['ahjs'])==28 and all(a['status']=='draft' for a in registry['ahjs'])
 results['registry_count']=len(registry['ahjs'])
 results['loaded_boundary_count']=len({a for a,g in ahj._boundary_rows()})
 prior=c.get('/api/runs/b53ba9a2-102e-4b39-93a3-bfec5c9ebf2f')
 assert prior.status_code==200,prior.text
 old=prior.json()
 selection={k:old['selection'][k] for k in ['mode','area_ids','excluded_ids','sample_ids','intent']}
 start=time.monotonic()
 response=c.post('/api/neighborhoods/review',json={'selection':selection})
 assert response.status_code==200,response.text
 review=response.json()
 assert review['included_count']==109 and review['sample_count']==2
 results['review_seconds']=round(time.monotonic()-start,3)
 results['review']={'included_count':review['included_count'],'sample_count':review['sample_count'],
                   'warnings':[{k:w[k] for k in ['code','area_id','anchor']} for w in review['warnings']],
                   'ahj_summary':review['ahj']['summary'],'ahj_unresolved_count':review['ahj']['unresolved_count']}
 print(json.dumps(results['review']),flush=True)
 for apn in ['17707116','40361130']:
  with appmod.connect() as conn:
   row=conn.execute('SELECT county_latitude,county_longitude FROM parcels p JOIN datasets d ON d.id=p.dataset_id AND d.active WHERE apn=%s',(apn,)).fetchone()
  assert row and row[0] is not None
  start=time.monotonic()
  at=c.get('/api/neighborhoods/at',params={'lat':row[0],'lng':row[1]})
  assert at.status_code==200,at.text
  candidates=at.json()
  results.setdefault('point_lookups',[]).append({'apn':apn,'seconds':round(time.monotonic()-start,3),
       'keys':[a['mcr_key'] for a in candidates['matches']], 'warnings':candidates['warnings']})
  print(json.dumps(results['point_lookups'][-1]),flush=True)
  if apn=='40361130':
   assert any(a['mcr_key']=='8150' for a in candidates['matches'])
   area=c.post('/api/areas/resolve',json={'kind':'subdivision','mcr_key':'8150'})
   assert area.status_code==200,area.text
   results['gila_bend_alias']={'county_key':area.json()['provenance'].get('county_mcr_key'),
                             'boundary_source':area.json()['boundary_source'],'homes':len(area.json()['parcels'])}
 body={'name':'Step 2 verified neighborhood','selection':selection}
 key=str(uuid.uuid4())
 confirmed=c.post('/api/runs/confirm',json=body,headers={'Idempotency-Key':key})
 assert confirmed.status_code==201,confirmed.text
 run=confirmed.json()
 assert run['status']=='confirmed' and run['review']==review
 assert c.post('/api/runs/confirm',json=body,headers={'Idempotency-Key':key}).json()['id']==run['id']
 assert c.get('/api/runs/'+run['id']).json()==run
 results['confirmed_run_id']=run['id'];results['confirmed_status']=run['status']
 print('Confirmation and immutable reload verified: '+run['id'],flush=True)
results['checked_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
(ROOT/'docs/step-2-live-checks.json').write_text(json.dumps(results,indent=2)+'\n')
