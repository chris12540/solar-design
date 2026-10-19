import os, subprocess, sys, uuid
from pathlib import Path
import pytest

HEADER='FolioKey|OwnerName|MailingAddress1|MailingAddress2|MailingCity|MailingState|MailingPostalCode|MailingCountry|SitusAddress|SitusUnitNumber|SitusCity|SitusPostalCode|PropertyType|DeedNumber|DeedDate|DeedType|LandValue|ImprovementValue|FCV|AssessedFCV|LPV|AssessedLPV|PUC|Lot|Parcel_Block|Parcel_Tract|LandClass|ImprvClass|RentalInd|LivingArea|TotalSqFt|ConstrYear|PoolSize|SalePrice|SaleDate|MCR_Key|MCR_Name|NumUnits|TaxAreaCode'

def row(folio, addr='100 MAIN ST', unit='', city='PHOENIX', zipc='85001',
        mailing=None, mcity=None, mzip=None, munit='', rental='N', year='2001',
        mcr='12345', mname='SYNTHETIC MCR'):
    v={k:'' for k in HEADER.split('|')}
    v.update(FolioKey=folio,OwnerName='TEST OWNER',
      MailingAddress1=mailing if mailing is not None else addr,MailingAddress2=munit,
      MailingCity=mcity if mcity is not None else city,MailingState='AZ',
      MailingPostalCode=mzip if mzip is not None else zipc,MailingCountry='USA',
      SitusAddress=addr,SitusUnitNumber=unit,SitusCity=city,SitusPostalCode=zipc,
      PropertyType='RESIDENTIAL',RentalInd=rental,ConstrYear=year,MCR_Key=mcr,MCR_Name=mname)
    return '|'.join(v[k] for k in HEADER.split('|'))

def run_import(data_dir, db_url):
    env=os.environ.copy(); env['DATABASE_URL']=db_url
    return subprocess.run([sys.executable,'-m','backend.import_data','--data-dir',str(data_dir)],
        cwd=Path(__file__).parents[2],env=env,text=True,capture_output=True)

def login(client):
    assert client.post('/api/session',json={'token':'test-staff-token'}).status_code==200

def test_auth_origin_search_unit_and_response_privacy(client,tmp_path,test_db_url):
    assert client.get('/api/status').status_code==401
    login(client)
    assert client.get('/api/status').json()=={'dataset':None}
    assert client.get('/api/parcels/search',params={'q':'100 Main St'}).status_code==503
    assert client.post('/api/session',json={'token':'test-staff-token'},
        headers={'Origin':'https://evil.test'}).status_code==403
    data=tmp_path/'Data'; data.mkdir()
    p=data/'Secured_Master_BK100.txt'
    body='\n'.join([row('00000001',unit='1',munit='APT 1',mcr='123'),
      row('00000002',unit='2',munit='UNIT2',mcr='12345'),row('00000003',addr='300 OAK ST',rental='Y',year='')])+'\n'
    p.write_bytes((HEADER+'\n'+body+'\\n').encode('cp1252'))
    # Put a non-UTF8 byte after the initial header/sample to exercise full-file detection.
    p.write_bytes((HEADER+'\n'+body+row('00000004',addr='200 CAFÉ RD')+'\n').encode('cp1252'))
    result=run_import(data,test_db_url)
    assert result.returncode==0,result.stderr
    response=client.get('/api/parcels/search',params={'q':'100 main street Phoenix AZ 85001'})
    assert response.status_code==200
    matches=response.json()['matches']
    assert {x['unit'] for x in matches}=={'1','2'}
    unit_match=client.get('/api/parcels/search',params={'q':'100 main street Apt1 Phoenix AZ 85001'}).json()['matches']
    assert {x['unit'] for x in unit_match}=={'1'}
    for query in ('100 Main Street Apt 1', '100 Main St #1', '100 Main St Unit1', '100 Main St #1, Phoenix, AZ 85001'):
        result=client.get('/api/parcels/search',params={'q':query})
        assert result.status_code==200,result.text
        assert {x['unit'] for x in result.json()['matches']}=={'1'},query
    assert all(x['occupancy']=='likely_owner_occupied' for x in matches)
    assert 'TEST OWNER' not in response.text
    assert all('mailing' not in key.lower() and 'owner' not in key.lower()
        for item in matches for key in item)
    assert client.get('/api/status').json()['dataset']['snapshot_date'] is None

def test_import_rejections_idempotence_and_atomic_failure(client,tmp_path,test_db_url,appmod):
    login(client)
    data=tmp_path/'Data'; data.mkdir()
    p=data/'Secured_Master_BK100.txt'
    p.write_text(HEADER+'\n'+row('00000010')+'\n'+row('badfolio')+'\n'+'too|few|fields\n',encoding='utf-8')
    first=run_import(data,test_db_url)
    assert first.returncode==0,first.stderr
    ds=client.get('/api/status').json()['dataset']
    assert (ds['input_rows'],ds['imported_rows'],ds['rejected_rows'])==(3,1,2)
    with appmod.connect() as c:
        assert c.execute('select count(*) from rejected_rows').fetchone()[0]==2
    repeat=run_import(data,test_db_url)
    assert repeat.returncode==0 and 'Identical dataset already imported' in repeat.stdout
    p.write_text('wrong|header\n'+row('00000011')+'\n',encoding='utf-8')
    failed=run_import(data,test_db_url)
    assert failed.returncode!=0
    assert client.get('/api/status').json()['dataset']['id']==ds['id']

def test_run_validation_idempotency_persistence_and_auth_isolation(client,appmod):
    login(client)
    with appmod.connect() as c:
        c.execute("insert into datasets(id,input_rows,imported_rows,rejected_rows,files,active) values('test-data',0,0,0,'[]',true)")
        c.execute("""insert into parcels(dataset_id,parcel_id,apn,address,city,postal_code,occupancy,occupancy_reason,source_file,source_row,search_norm,mcr_key,mcr_name)
          values('test-data','04013:00000021','00000021','100 MAIN ST','PHOENIX','85001','unknown','test','fixture',2,'100 MAIN ST PHOENIX 85001','12345','SYNTHETIC MCR')""")
        c.execute("""insert into parcels(dataset_id,parcel_id,apn,address,city,postal_code,occupancy,occupancy_reason,source_file,source_row,search_norm)
          values('test-data','04013:00000022','00000022','200 OAK ST','PHOENIX','85001','unknown','test','fixture',3,'200 OAK ST PHOENIX 85001')""")
    key=str(uuid.uuid4())
    body={'name':'Test run','original_address':'100 Main Street','parcel_id':'04013:00000021','selection':{'mode':'mcr'}}
    response=client.post('/api/runs',json=body,headers={'Idempotency-Key':key})
    assert response.status_code==201,response.text
    run=response.json()
    assert run['selection']=={'mode':'mcr','mcr_key':'12345','mcr_name':'SYNTHETIC MCR'}
    assert client.get('/api/runs/'+run['id']).json()==run
    assert client.post('/api/runs',json=body,headers={'Idempotency-Key':key}).json()['id']==run['id']
    from concurrent.futures import ThreadPoolExecutor
    fresh_key=str(uuid.uuid4())
    def concurrent_create(_): return client.post('/api/runs',json=body,headers={'Idempotency-Key':fresh_key})
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent=[future.result() for future in [pool.submit(concurrent_create,i) for i in range(4)]]
    assert all(r.status_code==201 for r in concurrent)
    assert len({r.json()['id'] for r in concurrent})==1
    assert client.post('/api/runs',json={**body,'name':'Changed'},
        headers={'Idempotency-Key':key}).status_code==409
    assert client.post('/api/runs',json={**body,'parcel_id':None},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**body,'parcel_id':'04013:00000022'},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**body,'parcel_id':'04013:99999999'},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    radius={'name':'Radius','original_address':'Map center selection','parcel_id':None,
      'selection':{'mode':'radius','center':{'lat':33.4,'lng':-112.1},'radius_meters':10000}}
    assert client.post('/api/runs',json=radius,headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==201
    assert client.post('/api/runs',json={**radius,'selection':{**radius['selection'],'radius_meters':10001}},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**radius,'selection':{'mode':'radius','center':[-112,33],'radius_meters':100}},headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**radius,'parcel_id':[]},headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**radius,'original_address':''},headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    assert client.post('/api/runs',json={**radius,'name':'x'*121},headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    polygon={'type':'Polygon','coordinates':[[[-112.1,33.4],[-112.05,33.4],[-112.05,33.45],[-112.1,33.45],[-112.1,33.4]]]}
    pbody={**radius,'selection':{'mode':'polygon','geometry':polygon}}
    assert client.post('/api/runs',json=pbody,headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==201
    bowtie={'type':'Polygon','coordinates':[[[-112.1,33.4],[-112.05,33.45],[-112.05,33.4],[-112.1,33.45],[-112.1,33.4]]]}
    assert client.post('/api/runs',json={**pbody,'selection':{'mode':'polygon','geometry':bowtie}},
        headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==422
    client.delete('/api/session')
    assert client.get('/api/runs/'+run['id']).status_code==401
    login(client)
    assert client.get('/api/runs/'+run['id']).status_code==200
    other_cookie=appmod.serializer.dumps({'user':'other-user'})
    client.cookies.set('solar_session',other_cookie)
    assert client.get('/api/runs/'+run['id']).status_code==404

    # Saved facts remain stable after the live parcel record changes.
    client.cookies.clear()
    login(client)
    with appmod.connect() as c:
        c.execute("UPDATE parcels SET address='999 UPDATED ADDRESS' WHERE parcel_id='04013:00000021'")
    assert client.get('/api/runs/'+run['id']).json()['parcel']['address']=='100 MAIN ST'
