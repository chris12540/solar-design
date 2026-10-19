import json
import uuid

import pytest
from shapely.geometry import mapping, shape

from backend import gis


def _polygon(x1, y1, x2, y2, holes=None):
    return {'type':'Polygon','coordinates':[
        [[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]],
        *([[*ring] for ring in (holes or [])])
    ]}


def _feature(apn, geometry=None, lat=33.4, lng=-112.1):
    return {'type':'Feature','properties':{'APN':apn,'LATITUDE':lat,'LONGITUDE':lng},
            'geometry':geometry}


def _box(x1, y1, x2, y2):
    return _polygon(x1,y1,x2,y2)['coordinates'][0]


def _seed(appmod, entries):
    with appmod.connect() as c:
        c.execute("insert into datasets(id,input_rows,imported_rows,rejected_rows,files,active) values('map-fixture',0,0,0,'[]',true) on conflict(id) do nothing")
        for idx, item in enumerate(entries, 1):
            apn, mcr, residential, property_type, geom = item
            c.execute('''insert into parcels(dataset_id,parcel_id,apn,address,city,postal_code,mcr_key,mcr_name,
              occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential)
              values('map-fixture',%s,%s,%s,'PHOENIX','85001',%s,'TEST SUBDIVISION','unknown','test','fixture',%s,%s,%s,%s,%s)''',
              ('04013:'+apn,apn,f'{idx} TEST ST',mcr,idx,f'{idx} TEST ST PHOENIX 85001',property_type,'001',residential))
            if geom is not None:
                c.execute('update parcels set county_geometry=ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) where dataset_id=\'map-fixture\' and apn=%s',
                          (json.dumps(geom),apn))


def _login(client):
    assert client.post('/api/session',json={'token':'test-staff-token'}).status_code == 200


def test_county_boundary_uses_representative_point_and_preserves_holes_and_multipolygons(client,appmod,monkeypatch):
    _login(client)
    hole = [[-112.1,33.39],[-112.08,33.39],[-112.08,33.41],[-112.1,33.41],[-112.1,33.39]]
    boundary = {'type':'MultiPolygon','coordinates':[
        [[[-112.2,33.2],[-112.0,33.2],[-112.0,33.6],[-112.2,33.6],[-112.2,33.2]],hole],
        [[[-111.9,33.2],[-111.8,33.2],[-111.8,33.4],[-111.9,33.4],[-111.9,33.2]]]
    ]}
    geometries = {
      'A1':_polygon(-112.16,33.3,-112.14,33.32),  # inside shell
      'A2':_polygon(-112.095,33.395,-112.09,33.405),  # inside boundary hole
      'A3':_polygon(-111.88,33.28,-111.86,33.30),  # second MultiPolygon component
      'A4':_polygon(-112.001,33.30,-111.999,33.32),  # representative point on boundary
      'A5':_polygon(-111.75,33.3,-111.73,33.32),  # intersects candidate service response, point outside
      'A6':_polygon(-112.15,33.35,-112.13,33.37),  # non-residential
      'A7':_polygon(-112.12,33.34,-112.10,33.36),  # unknown classification
    }
    _seed(appmod,[(apn,'700',None if apn=='A7' else (True if apn!='A6' else False),
      'UNKNOWN' if apn=='A7' else ('RESIDENTIAL' if apn!='A6' else 'COMMERCIAL'),geom) for apn,geom in geometries.items()])
    _seed(appmod,[('A8','700',True,'RESIDENTIAL',None)])
    monkeypatch.setattr(gis,'subdivision',lambda key:[{'type':'Feature','properties':{'mcrnum_secured':key,'mcrnum':'7','subname':'Exact Name'},'geometry':boundary}])
    def spatial(_geometry):
        return [_feature(apn,geom) for apn,geom in geometries.items()] + [_feature('A8',None)]
    monkeypatch.setattr(gis,'parcels_in_geometry',spatial)

    response=client.post('/api/areas/resolve',json={'kind':'subdivision','mcr_key':'700'})
    assert response.status_code==200,response.text
    area=response.json()
    assert area['boundary_source']=='county'
    assert area['label']=='Exact Name'
    assert area['geometry']['type']=='MultiPolygon'
    assert area['geometry']['coordinates'][0][1]  # The county boundary hole survives.
    assert {p['apn'] for p in area['parcels']}=={'A1','A3','A4'}
    assert area['coverage']['mapped_count']==3
    assert area['coverage']['unresolved_count']==1
    assert area['coverage']['unknown_classification_count']==1
    assert area['coverage']['complete'] is False


def test_estimated_boundary_is_polygon_union_and_same_mcr_membership(client,appmod,monkeypatch):
    _login(client)
    first=_polygon(-112.1,33.3,-112.08,33.32)
    second={'type':'Polygon','coordinates':[
      [[-112.04,33.3],[-112.02,33.3],[-112.02,33.32],[-112.04,33.32],[-112.04,33.3]],
      [[-112.035,33.305],[-112.03,33.305],[-112.03,33.31],[-112.035,33.31],[-112.035,33.305]]
    ]}
    _seed(appmod,[('B1','8150',True,'RESIDENTIAL',None),('B2','8150',True,'RESIDENTIAL',None),('B3','8150',False,'COMMERCIAL',None)])
    monkeypatch.setattr(gis,'subdivision',lambda key:[])
    monkeypatch.setattr(gis,'parcels_by_apn',lambda apns:[_feature('B1',first),_feature('B2',second)])
    area=client.post('/api/areas/resolve',json={'kind':'subdivision','mcr_key':'8150'}).json()
    assert area['boundary_source']=='estimated'
    assert area['geometry']['type']=='MultiPolygon'
    assert len(area['geometry']['coordinates'])==2
    assert len(area['geometry']['coordinates'][1])==2  # parcel hole survives the union
    assert {p['apn'] for p in area['parcels']}=={'B1','B2'}
    assert area['coverage']['unresolved_count']==0


def test_area_snapshots_overlap_exclusion_sample_and_idempotent_run(client,appmod,monkeypatch):
    _login(client)
    polygon=_polygon(-112.11,33.4,-112.09,33.42)
    _seed(appmod,[('C1','10',True,'RESIDENTIAL',None),('C2','10',True,'RESIDENTIAL',None)])
    monkeypatch.setattr(gis,'parcels_in_geometry',lambda geom:[_feature('C1',_polygon(-112.105,33.405,-112.104,33.406)),
      _feature('C2',_polygon(-112.095,33.405,-112.094,33.406))])
    one=client.post('/api/areas/resolve',json={'kind':'polygon','label':'Draw one','geometry':polygon})
    two=client.post('/api/areas/resolve',json={'kind':'polygon','label':'Draw two','geometry':polygon})
    assert one.status_code==200 and two.status_code==200
    a,b=one.json(),two.json()
    assert a['parcels']==b['parcels']
    body={'name':'Sample draft','selection':{'mode':'areas','area_ids':[a['id'],b['id']],
      'excluded_ids':['04013:C1'],'sample_ids':['04013:C2'],'intent':'sample'}}
    key=str(uuid.uuid4())
    created=client.post('/api/runs',json=body,headers={'Idempotency-Key':key})
    assert created.status_code==201,created.text
    run=created.json()
    assert run['included_ids']==['04013:C2']
    assert run['excluded_ids']==['04013:C1']
    assert run['sample_ids']==['04013:C2']
    assert len(run['areas'])==2
    assert client.post('/api/runs',json=body,headers={'Idempotency-Key':key}).json()['id']==run['id']
    assert client.get('/api/runs/'+run['id']).json()==run
    single_body={'name':'One home','selection':{'mode':'areas','area_ids':[a['id']],
      'excluded_ids':['04013:C1'],'sample_ids':['04013:C2'],'intent':'single'}}
    single=client.post('/api/runs',json=single_body,headers={'Idempotency-Key':str(uuid.uuid4())})
    assert single.status_code==201 and single.json()['intent']=='single'
    all_body={'name':'Whole group','selection':{'mode':'areas','area_ids':[a['id']],
      'excluded_ids':[],'sample_ids':[],'intent':'all'}}
    whole=client.post('/api/runs',json=all_body,headers={'Idempotency-Key':str(uuid.uuid4())})
    assert whole.status_code==201 and whole.json()['intent']=='all' and whole.json()['sample_ids']==[]
    recent=client.get('/api/runs').json()
    recent_by_id={item['id']:item for item in recent['runs']}
    assert recent_by_id[run['id']]['intent']=='sample'
    assert recent_by_id[whole.json()['id']]['intent']=='all'
    other=appmod.serializer.dumps({'user':'other-user'})
    client.cookies.set('solar_session',other)
    assert client.post('/api/runs',json=body,headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==404


def test_area_resolution_unavailable_without_cache_returns_503(client,appmod,monkeypatch):
    _login(client)
    _seed(appmod,[('D1','123',True,'RESIDENTIAL',None)])
    def unavailable(_): raise gis.GISUnavailable('offline')
    monkeypatch.setattr(gis,'subdivision',unavailable)
    response=client.post('/api/areas/resolve',json={'kind':'subdivision','mcr_key':'123'})
    assert response.status_code==503


def test_standalone_parcel_resolves_geometry_when_cold_and_original_area_must_be_owned(client,appmod,monkeypatch):
    _login(client)
    geom=_polygon(-112.1,33.4,-112.099,33.401)
    _seed(appmod,[('E1',None,True,'RESIDENTIAL',None)])
    monkeypatch.setattr(gis,'parcels_by_apn',lambda apns:[_feature('E1',geom)])
    parcel=client.post('/api/areas/resolve',json={'kind':'parcel','parcel_id':'04013:E1'})
    assert parcel.status_code==200,parcel.text
    area=parcel.json()
    assert [x['id'] for x in area['parcels']]==['04013:E1']
    assert area['geometry']['type']=='Polygon'
    assert area['provenance']['gis_fetched_at']

    edited=_polygon(-112.1,33.4,-112.098,33.402)
    updated=client.post('/api/areas/resolve',json={'kind':'polygon','geometry':edited,
      'original_area_id':area['id']})
    assert updated.status_code==200,updated.text
    assert updated.json()['provenance']['original_area_id']==area['id']
    assert updated.json()['original_geometry']==area['original_geometry']
    other=appmod.serializer.dumps({'user':'other-user'})
    client.cookies.set('solar_session',other)
    denied=client.post('/api/areas/resolve',json={'kind':'polygon','geometry':edited,
      'original_area_id':area['id']})
    assert denied.status_code==404


@pytest.mark.parametrize('geometry',[
    {'type':'Polygon','coordinates':[[[-112.1,33.4,10],[-112.09,33.4,10],[-112.09,33.41,10],[-112.1,33.41,10],[-112.1,33.4,10]]]},
    {'type':'Polygon','coordinates':[[[-112.1,33.4],[-112.09,33.4],[-112.09,float('nan')],[-112.1,33.41],[-112.1,33.4]]]},
])
def test_polygon_rejects_non_2d_and_nonfinite_coordinates_with_422(client,appmod,geometry):
    _login(client)
    _seed(appmod,[('F1','600',True,'RESIDENTIAL',None)])
    body=json.dumps({'kind':'polygon','geometry':geometry},allow_nan=True)
    response=client.post('/api/areas/resolve',content=body,headers={'Content-Type':'application/json'})
    assert response.status_code==422,response.text


def test_disconnected_small_components_are_bounded_by_polygon_area_not_the_gap(client,appmod,monkeypatch):
    _login(client)
    _seed(appmod,[('G1','600',True,'RESIDENTIAL',None)])
    geometry={'type':'MultiPolygon','coordinates':[
      [[[-113.2,33.3],[-113.18,33.3],[-113.18,33.32],[-113.2,33.32],[-113.2,33.3]]],
      [[[-112.8,33.3],[-112.78,33.3],[-112.78,33.32],[-112.8,33.32],[-112.8,33.3]]]
    ]}
    monkeypatch.setattr(gis,'parcels_in_geometry',lambda _:[])
    response=client.post('/api/areas/resolve',json={'kind':'polygon','geometry':geometry})
    assert response.status_code==200,response.text
    assert response.json()['geometry']['type']=='MultiPolygon'


def test_arcgis_paging_and_esri_geometry_encoding(monkeypatch):
    calls=[]
    def page(_url,params):
        calls.append(params)
        offset=int(params['resultOffset'])
        if offset==0:
            return {'features':[{'type':'Feature','properties':{'OBJECTID':i},'geometry':None} for i in range(1000)],'exceededTransferLimit':True}
        return {'features':[{'type':'Feature','properties':{'OBJECTID':1001},'geometry':None}]}
    monkeypatch.setattr(gis,'_request_json',page)
    assert len(gis._page({'where':'1=1'},'layer'))==1001
    assert [x['resultOffset'] for x in calls]==[0,1000]

    boundary={'type':'Polygon','coordinates':[[[-112,33],[-111,33],[-111,34],[-112,34],[-112,33]],
      [[-111.8,33.2],[-111.8,33.8],[-111.2,33.8],[-111.2,33.2],[-111.8,33.2]]]}
    monkeypatch.setattr(gis,'_request_json',lambda url,params:(calls.append(params) or {'features':[]}))
    gis.parcels_in_geometry(boundary)
    params=calls[-1]
    assert params['geometryType']=='esriGeometryPolygon'
    rings=json.loads(params['geometry'])['rings']
    assert len(rings)==2
    assert shape({'type':'Polygon','coordinates':[rings[0],rings[1]]}).is_valid

    monkeypatch.setattr(gis,'_request_json',lambda *_:{'features':[],'exceededTransferLimit':True})
    with pytest.raises(gis.GISUnavailable):
        gis._page({'where':'1=1'},'layer')
