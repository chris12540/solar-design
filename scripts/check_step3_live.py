"""Exercise real local eligibility data without creating designs or changing selections."""
import json, os, uuid
from pathlib import Path
from scripts.dev import environment
os.environ.update(environment())
from fastapi.testclient import TestClient
from backend.app import app, STAFF_TOKEN
ROOT=Path('/Users/chris/code/solar-designer')
RUN='b53ba9a2-102e-4b39-93a3-bfec5c9ebf2f'
with TestClient(app) as client:
 assert client.post('/api/session',json={'token':STAFF_TOKEN}).status_code==200
 run=client.get('/api/runs/'+RUN).json()
 selection={key:run[key] for key in ('excluded_ids','sample_ids','intent')}
 selection.update(mode='areas',area_ids=[a['id'] for a in run['areas']])
 response=client.post('/api/eligibility/preview',json={'selection':selection,'filters':{}})
 assert response.status_code==200, response.text
 report=response.json()
 assert report['input_count']==109
 assert sum(report[k] for k in ('excluded_count','needs_review_count','not_checked_count','passes_available_checks_count'))==109
 assert sum(s['newly_excluded_count'] for s in report['steps'])==report['excluded_count']
 assert report['passes_available_checks_count']==0
 assert report['fact_snapshot']['source_files']
 assert report['source_warnings']
 minimum=client.post('/api/eligibility/preview',json={'selection':selection,'filters':{'year_min':2000,'min_home_value':1000000}})
 assert minimum.status_code==200, minimum.text
 chosen=minimum.json()
 assert chosen['excluded_count']>=report['excluded_count']
 key=str(uuid.uuid4());route='/api/runs/'+RUN+'/eligibility'
 saved=client.post(route,json={'filters':{}},headers={'Idempotency-Key':key})
 assert saved.status_code==201, saved.text
 body=saved.json();again=client.post(route,json={'filters':{}},headers={'Idempotency-Key':key}).json()
 assert body['id']==again['id']
 reloaded=client.get('/api/eligibility/'+body['id']).json()
 assert reloaded['report']==body['report']
 assert client.get('/api/runs/'+RUN).json()==run
 output={'run_id':RUN,'report_id':body['id'],'policy_version':report['policy_version'],'as_of_date':report['as_of_date'],'as_of_timezone':report['as_of_timezone'],'input_count':report['input_count'],'excluded_count':report['excluded_count'],'needs_review_count':report['needs_review_count'],'not_checked_count':report['not_checked_count'],'passes_available_checks_count':report['passes_available_checks_count'],'steps':report['steps'],'filtered_excluded_count':chosen['excluded_count'],'source_warnings':report['source_warnings'],'fact_file_count':len(report['fact_snapshot']['source_files']),'selected_sample_count':len(selection['sample_ids']),'excluded_sample_ids':report['excluded_sample_ids'],'snapshot_retry_and_immutability_verified':True}
 (ROOT/'docs/step-3-live-checks.json').write_text(json.dumps(output,indent=2)+'\n')
 print(json.dumps({k:v for k,v in output.items() if k!='steps'}))
