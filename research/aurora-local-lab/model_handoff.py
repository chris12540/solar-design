"""Independent coordinate/planar-face handoff. Never runs or changes reconstruction."""
import copy,json,math,re
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from pyproj import CRS,Transformer,Geod,network
from shapely.geometry import Polygon
from shapely import constrained_delaunay_triangles

ROOT=Path(__file__).resolve().parent
network.set_network_enabled(False)

def instant(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.tzinfo is None:raise ValueError('Source date requires timezone')
    return date

def origin_frame(origin):
    if not isinstance(origin,dict) or not re.fullmatch(r'EPSG:\d{3,6}',origin.get('crs','')):raise ValueError('Projected source CRS required')
    crs=CRS.from_user_input(origin['crs'])
    if not crs.is_projected or any(abs(axis.unit_conversion_factor-1)>1e-9 for axis in crs.axis_info[:2]):raise ValueError('Source coordinates must be projected meters')
    lat,lng=origin.get('latitude'),origin.get('longitude')
    if type(lat) not in (float,int) or type(lng) not in (float,int) or not math.isfinite(lat+lng) or abs(lat)>90 or abs(lng)>180:raise ValueError('Invalid source origin')
    ox,oy=Transformer.from_crs('EPSG:4326',crs,always_xy=True).transform(lng,lat)
    return crs,(ox,oy)

def native_from_faces(faces):
    native=json.loads((ROOT/'native-empty-template.json').read_text());site=native['site_json'];counter=10000
    def next_id():
        nonlocal counter
        counter+=1;return str(counter)
    for kind in ['roof.plane','node.roof-plane','edge.roof-plane','face.roof-plane','node.implicit','wall.roof-plane']:site[kind]=[]
    mapping=[]
    for item in faces:
        vertices=[list(p) for p in item['vertices']]
        if sum(vertices[i][0]*vertices[(i+1)%len(vertices)][1]-vertices[(i+1)%len(vertices)][0]*vertices[i][1] for i in range(len(vertices)))>0:vertices.reverse()
        n=len(vertices);matrix=np.array([[p[0],p[1],1] for p in vertices]);z=np.array([p[2] for p in vertices]);coeff=np.linalg.lstsq(matrix,z,rcond=None)[0]
        pitch=math.degrees(math.atan(math.hypot(coeff[0],coeff[1])));azimuth=math.degrees(math.atan2(-coeff[0],-coeff[1]))%360
        roof_id=next_id();node_ids=[next_id() for _ in vertices];edge_ids=[next_id() for _ in vertices];face_id=next_id();ground_ids=[next_id() for _ in vertices];wall_ids=[next_id() for _ in vertices]
        def node(id,p):return {'id':id,'x':p[0],'y':p[1],'z':p[2],'lat':p[1]*180/(math.pi*6371000),'lng':p[0]*180/(math.pi*6371000)}
        site['node.roof-plane'] += [node(id,p) for id,p in zip(node_ids,vertices)]
        reverse=list(reversed(node_ids));ground_vertices=[[p[0],p[1],0] for p in reversed(vertices)]
        site['node.implicit'] += [node(id,p) for id,p in zip(ground_ids,ground_vertices)]
        edge_azimuth=[]
        for i in range(n):
            p,q=vertices[i],vertices[(i+1)%n];edge_azimuth.append(math.degrees(math.atan2(-(q[1]-p[1]),q[0]-p[0]))%360)
        active=min(range(n),key=lambda i:abs((edge_azimuth[i]-azimuth+180)%360-180))
        for i,id in enumerate(edge_ids):site['edge.roof-plane'].append({'id':id,'nodes':[node_ids[i],node_ids[(i+1)%n]],'azimuth':edge_azimuth[i],'implicit_setback_type':'eave' if i==active else 'rake','is_azimuth_edge':i==active})
        ordered_edges=[edge_ids[(n-2-i)%n] for i in range(n)]
        area=Polygon([(p[0],p[1]) for p in vertices]).area*math.sqrt(1+coeff[0]**2+coeff[1]**2)
        site['face.roof-plane'].append({'id':face_id,'nodes':reverse,'edges':ordered_edges,'area':area,'pitch':pitch,'azimuth':azimuth})
        for i,id in enumerate(wall_ids):site['wall.roof-plane'].append({'id':id,'nodes':[reverse[i],ground_ids[i],ground_ids[(i+1)%n],reverse[(i+1)%n]]})
        site['roof.plane'].append({'id':roof_id,'perimeter_nodes':node_ids,'perimeter_edges':edge_ids,'faces':[face_id],'ground_nodes':ground_ids,'walls':wall_ids,'height':min(z),'pitch':pitch,'azimuth':azimuth,'building_usage_type':'primary'})
        site['buildings'].append({'id':next_id(),'roofs':[roof_id],'nodes':[node(next_id(),p) for p in vertices+ground_vertices],
            'faces':[{'id':next_id(),'nodes':list(reversed(range(n))),'holes':[],'pitch':pitch,'azimuth':azimuth}],
            'walls':[{'id':next_id(),'nodes':[n-1-i,n+i,n+(i+1)%n,n-1-(i+1)%n]} for i in range(n)]})
        mapping.append({'roofId':roof_id,'sourceFaceId':item['sourceFaceId'],'piece':item['piece']})
    return native,mapping

def convert_generated(payload,manifest,height):
    if payload.get('schema')!='roof-reconstruction-handoff/v1' or payload.get('heightDatum')!='EGM96':raise ValueError('Unsupported generator handoff')
    expires=instant(payload['expiresAt']);fetched=instant(payload['fetchedAt'])
    if expires<=datetime.now(timezone.utc) or expires<=fetched:raise ValueError('Generated model expired')
    result=payload['result'];origin=result['origin'];crs,offset=origin_frame(origin)
    if Geod(ellps='WGS84').inv(origin['longitude'],origin['latitude'],manifest['origin']['longitude'],manifest['origin']['latitude'])[2]>3:raise ValueError('Generated model is for a different building')
    if height['imageSha256']!=manifest['pngSha256'] or height['expiresAt']!=manifest['expiresAt']:raise ValueError('Matching height reference required')
    ground=height['groundElevation'];transform=Transformer.from_crs(crs,manifest['localCRS'],always_xy=True)
    stage=payload.get('stage','raw');groups=result.get('faces',[]) if stage=='raw' else result.get('fitting' if stage=='fitted' else 'refinement',{}).get('face_groups',[])
    if not groups or len(groups)>200:raise ValueError('No supported generated faces')
    converted=[];area_total=0;largest_error=0
    for group in groups:
        plane=group.get('plane_model')
        if not isinstance(plane,dict) or any(type(plane.get(k)) not in (int,float) or not math.isfinite(plane[k]) for k in ('a','b','c')):raise ValueError('Selected geometry lacks 3D planes; use raw or fitted roof')
        parts=[group] if stage=='raw' else group.get('parts',[])
        for index,part in enumerate(parts):
            if not isinstance(part.get('polygon'),list) or len(part['polygon'])>300 or len(part.get('holes',[]))>30 or any(len(h)>300 for h in part.get('holes',[])):raise ValueError('Generated face too complex')
            polygon=Polygon(part['polygon'],part.get('holes',[]))
            if not polygon.is_valid or polygon.is_empty or polygon.area<.05 or polygon.area>10000:raise ValueError('Invalid generated polygon')
            if any(abs(v)>500 for xy in polygon.exterior.coords for v in xy):raise ValueError('Generated polygon is outside local bounds')
            pieces=list(constrained_delaunay_triangles(polygon).geoms) if polygon.interiors else [polygon]
            if len(converted)+len(pieces)>500:raise ValueError('Too many generated pieces')
            if abs(sum(p.area for p in pieces)-polygon.area)>1e-5:raise ValueError('Could not preserve polygon holes')
            area_total+=polygon.area
            for piece_index,piece in enumerate(pieces):
                ring=list(piece.exterior.coords)[:-1]
                if len(ring)>300:raise ValueError('Generated face too complex')
                vertices=[]
                for x,y in ring:
                    ex,ey=transform.transform(x+offset[0],y+offset[1]);z=plane['a']*x+plane['b']*y+plane['c']-ground
                    if not all(math.isfinite(v) for v in (ex,ey,z)) or z<.1 or z>80:raise ValueError('Generated heights incompatible with ground reference')
                    vertices.append([ex,ey,z])
                matrix=np.array([[x,y,1] for x,y,z in vertices]);values=np.array([z for x,y,z in vertices]);model=np.linalg.lstsq(matrix,values,rcond=None)[0];error=float(np.max(abs(matrix@model-values)));largest_error=max(largest_error,error)
                if error>.02:raise ValueError('Projection would distort roof planarity')
                for vertex,value in zip(vertices,matrix@model):vertex[2]=float(value)
                converted.append({'vertices':vertices,'sourceFaceId':str(group['id']),'piece':f'{index}:{piece_index}'})
    if len(converted)>500:raise ValueError('Too many generated faces')
    native,mapping=native_from_faces(converted)
    return {'nativeDesignJson':json.dumps(native,separators=(',',':')),'inputExpiresAt':payload['expiresAt'],
        'heightContext':{'groundElevation':ground,'heightSha256':height['sha256']},
        'generator':{'kind':'local-reconstruction-handoff','algorithmVersion':result.get('algorithm_version'),'stage':stage,'sourceOrigin':origin,'sourceFetchedAt':payload['fetchedAt'],'sourceExpiresAt':payload['expiresAt'],'mapping':mapping,'projectionMaxHeightResidual':largest_error,'sourceArea':area_total}}

def return_geometry(packet,target):
    crs,offset=origin_frame(target['origin']);coordinates=packet['coordinates'];ground=coordinates.get('groundElevation')
    if ground is None or coordinates['verticalDatum']!='EGM96-minus-ground-reference':raise ValueError('Load heights and save a ground reference before returning geometry')
    if Geod(ellps='WGS84').inv(coordinates['horizontalOrigin']['longitude'],coordinates['horizontalOrigin']['latitude'],target['origin']['longitude'],target['origin']['latitude'])[2]>3:raise ValueError('Correction belongs to a different building')
    if instant(target['expiresAt'])<=datetime.now(timezone.utc):raise ValueError('Target model expired')
    transform=Transformer.from_crs(coordinates['horizontalCRS'],crs,always_xy=True)
    def ring(vertices):
        result=[]
        for x,y,z in vertices:
            px,py=transform.transform(x,y)
            if not all(math.isfinite(v) for v in (px,py,z+ground)):raise ValueError('Invalid returned coordinate')
            result.append([px-offset[0],py-offset[1],z+ground])
        return result
    faces=[]
    for building in packet['geometry']['buildings']:
        for face in building['faces']:faces.append({'id':face['id'],'vertices':ring(face['vertices']),'holes':[ring(h) for h in face['holes']] if face['holesKnown'] else None,'holesKnown':face['holesKnown']})
    expires=min([packet['expiresAt'],target['expiresAt']],key=instant)
    return {'schema':'roof-correction/v1','caseId':packet['caseId'],'expiresAt':expires,'origin':target['origin'],'heightDatum':'EGM96','faces':faces,'benchmarkCompatible':False,'referenceStatus':'manual-correction-needs-review','sourceCaseSha256':packet['nativeDesignSha256']}
