"""Read county GIS through the real adapter and report local-source join coverage.

Creates private area snapshots/cache entries but no design jobs or paid requests.
Run with the project environment; output deliberately excludes credentials/owner data.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for line in (ROOT / '.env').read_text().splitlines():
    if line.strip() and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key, value)
from backend import app as appmod
from fastapi.testclient import TestClient

samples = [('21648', 'Small subdivision'), ('16920', 'Medium subdivision'),
           ('17824', 'Replat'), ('8150', 'Estimated fallback'), ('62144', 'Unit parcels')]
report = []
with TestClient(appmod.app) as client:
    assert client.post('/api/session', json={'token': os.environ['STAFF_TOKEN']}).status_code == 200
    for key, category in samples:
        started = time.monotonic()
        response = client.post('/api/areas/resolve', json={'kind':'subdivision','mcr_key':key})
        result = {'mcr_key': key, 'category': category, 'status':response.status_code,
                  'seconds':round(time.monotonic()-started,3)}
        if response.status_code == 200:
            area=response.json()
            result.update(label=area['label'],boundary_source=area['boundary_source'],
                          residential_count=len(area['parcels']),coverage=area['coverage'])
        else:
            result['detail']=response.json().get('detail')
        report.append(result)
        print(json.dumps(result),flush=True)
    cold=client.post('/api/areas/resolve',json={'kind':'parcel','parcel_id':'04013:17707116'})
    assert cold.status_code==200,cold.text
    one=cold.json()
    assert len(one['parcels'])==1 and one['parcels'][0]['geometry'], 'Standalone home must resolve'
    print('Standalone home verified.',flush=True)
output=ROOT/'docs/live-map-checks.json'
output.write_text(json.dumps({'checked_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                             'samples':report},indent=2)+'\n')
