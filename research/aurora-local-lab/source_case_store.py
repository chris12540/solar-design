"""Local, expiry-bound source cases. No acquisition, browser storage, or evaluator writes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,hmac,json,os,re,uuid,math

SCHEMA='roof-lab-case/v2'

def legacy_canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def canonical(value):
    def normalize(item):
        if isinstance(item,list):return [normalize(v) for v in item]
        if isinstance(item,dict):return {k:normalize(v) for k,v in item.items()}
        if type(item)==float:
            if not math.isfinite(item):raise ValueError('Nonfinite packet value')
            if item.is_integer():return int(item)
        return item
    return legacy_canonical(normalize(value))
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def instant(value):
    if not isinstance(value,str):raise ValueError('Timestamp must be text')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamp needs timezone')
    return parsed

def geometry_from_native(native):
    buildings=native.get('site_json',{}).get('buildings')
    if not isinstance(buildings,list):raise ValueError('Native building geometry missing')
    result=[];complete=True
    for index,building in enumerate(buildings):
        vertices=[]
        for node in building['nodes']:
            values=[node['x'],node['y'],node['z']]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Nonfinite geometry')
            vertices.append(values)
        def ring(indices):
            if not isinstance(indices,list) or len(indices)<3 or any(type(i)!=int or i<0 or i>=len(vertices) for i in indices):raise ValueError('Invalid geometry ring')
            return [vertices[i] for i in indices]
        faces=[]
        for face in building['faces']:
            known=isinstance(face.get('holes'),list)
            if face.get('holes') is not None and not known:raise ValueError('Unsupported holes')
            complete=complete and known
            faces.append({'id':face.get('id'),'sourceKey':face.get('source_key'),'vertices':ring(face['nodes']),
                'holes':[ring(h) for h in face['holes']] if known else None,'holesKnown':known,
                'nativePitchDegrees':face.get('pitch') if type(face.get('pitch')) in (int,float) and math.isfinite(face['pitch']) else None,'nativeAzimuthDegrees':face.get('azimuth') if type(face.get('azimuth')) in (int,float) and math.isfinite(face['azimuth']) else None})
        result.append({'id':building.get('id') if building.get('id') is not None else f'building-{index}','roofIds':building.get('roofs') or [],'faces':faces,
            'walls':[{'id':wall.get('id'),'sourceKey':wall.get('source_key'),'vertices':ring(wall['nodes'])} for wall in building.get('walls',[])]})
    return {'scope':'native-computed-building-faces-and-walls','holeTopologyComplete':complete,'visibilityIndependentlyVerified':False,'buildings':result}

class SourceCases:
    def __init__(self,root,manifest_getter,engine):
        self.root=Path(root);self.get_manifest=manifest_getter;self.engine=engine
    def key(self):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=self.root/'signing-key'
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(os.urandom(32))
        except FileExistsError:pass
        return path.read_bytes()
    def path(self,case_id,kind):
        if not isinstance(case_id,str) or not re.fullmatch(r'[a-f0-9-]{36}',case_id):raise ValueError('Invalid case identity')
        if kind not in ('draft','saved'):raise ValueError('Invalid case type')
        return self.root/(case_id+'.'+kind+'.json')
    def sign(self,packet):
        packet={k:v for k,v in packet.items() if k!='signature'}
        packet['signatureVersion']=2
        packet['signature']=hmac.new(self.key(),canonical(packet).encode(),hashlib.sha256).hexdigest()
        return packet
    def validate(self,packet,require_source=True):
        if not isinstance(packet,dict) or packet.get('schema')!=SCHEMA:raise ValueError('Unsupported source test case')
        signature=packet.get('signature','');body={k:v for k,v in packet.items() if k!='signature'}
        if not isinstance(signature,str) or not hmac.compare_digest(signature,hmac.new(self.key(),(canonical(body) if packet.get('signatureVersion')==2 else legacy_canonical(body)).encode(),hashlib.sha256).hexdigest()):raise ValueError('Case signature invalid or from another local installation')
        source=packet['source'];now=datetime.now(timezone.utc);expiry=instant(packet['expiresAt'])
        if expiry<=now or expiry>instant(source['originalExpiresAt']):raise ValueError('Source case expired or lifetime invalid')
        if packet['engineArtifacts']!=self.engine:raise ValueError('Editor version mismatch')
        raw=packet['nativeDesignJson']
        if not isinstance(raw,str) or len(raw.encode())>20*1024*1024 or digest(raw)!=packet['nativeDesignSha256']:raise ValueError('Model checksum mismatch')
        native=json.loads(raw)
        if native.get('format_version')!='3' or not isinstance(native.get('system_json'),dict):raise ValueError('Unsupported native model')
        if geometry_from_native(native)!=packet['geometry']:raise ValueError('Model and geometry differ')
        self.path(packet['caseId'],'draft')
        if require_source:
            current=self.get_manifest(source['id'])
            if not current or current['pngSha256']!=source['imageSha256'] or current['expiresAt']!=source['originalExpiresAt'] or current['fetchedAt']!=source['originalFetchedAt']:raise ValueError('Matching unexpired source imagery unavailable')
        return packet
    def make(self,payload):
        source_id=payload.get('sourceId');manifest=self.get_manifest(source_id)
        if not manifest:raise ValueError('Source unavailable or expired')
        if payload.get('expectedImageSha256') is not None and payload['expectedImageSha256']!=manifest['pngSha256']:raise ValueError('Source image changed; refusing to relabel existing geometry')
        name=payload.get('name','Untitled example')
        if not isinstance(name,str) or not name.strip() or len(name)>500 or any(ord(c)<32 for c in name):raise ValueError('Invalid example name')
        raw=payload.get('nativeDesignJson')
        if not isinstance(raw,str) or len(raw.encode())>20*1024*1024:raise ValueError('Missing or oversized native model')
        native=json.loads(raw)
        if native.get('format_version')!='3' or not isinstance(native.get('system_json'),dict):raise ValueError('Unsupported native model')
        context=payload.get('heightContext') or {};ground=context.get('groundElevation')
        if ground is not None and (type(ground) not in (int,float) or not math.isfinite(ground) or not -500<=ground<=10000):raise ValueError('Invalid height reference')
        height_sha=context.get('heightSha256')
        if height_sha is not None and (not isinstance(height_sha,str) or not re.fullmatch(r'[a-f0-9]{64}',height_sha)):raise ValueError('Invalid height identity')
        case_id=payload.get('caseId') or str(uuid.uuid4());self.path(case_id,'draft')
        expiry=manifest['expiresAt'];previous=None
        for kind in ('draft','saved'):
            file=self.path(case_id,kind)
            if file.exists():
                previous=self.validate(json.loads(file.read_text()))
                if previous['source']['id']!=source_id:raise ValueError('Cannot change source of an existing case')
                if instant(previous['expiresAt'])<instant(expiry):expiry=previous['expiresAt']
        if payload.get('inputExpiresAt'):
            extra=instant(payload['inputExpiresAt'])
            if extra<instant(expiry):expiry=payload['inputExpiresAt']
        if instant(expiry)<=datetime.now(timezone.utc):raise ValueError('Input case expired')
        packet={'schema':SCHEMA,'caseId':case_id,'name':name.strip(),'createdAt':previous['createdAt'] if previous else datetime.now(timezone.utc).isoformat(),
            'updatedAt':datetime.now(timezone.utc).isoformat(),'expiresAt':expiry,'engineArtifacts':self.engine,
            'source':{'id':source_id,'provider':manifest['provider'],'imageSha256':manifest['pngSha256'],'originalFetchedAt':manifest['fetchedAt'],
                'originalExpiresAt':manifest['expiresAt'],'captureDate':manifest.get('captureDate')},
            'coordinates':{'units':'m','axes':['east','north','up'],'horizontalCRS':manifest['localCRS'],'horizontalOrigin':manifest['origin'],
                'verticalDatum':'EGM96-minus-ground-reference' if ground is not None else 'unverified-editor-relative-zero','groundElevation':ground,
                'alignment':'provider-local-frame; not surveyed'},'heightContext':{'groundElevation':ground,'heightSha256':height_sha},
            'nativeDesignJson':raw,'nativeDesignSha256':digest(raw),'geometry':geometry_from_native(native),'benchmarkCompatible':False,
            'generator':previous.get('generator') if previous else payload.get('generator'),'importedFrom':previous.get('importedFrom') if previous else None,'limitations':['Not surveyed truth or an accuracy certification.','Image bytes are not included. Matching cached imagery is required to reopen.',
                'This file contains source-derived data: delete by expiresAt. This app refuses expired cases but cannot delete copies outside its storage.',
                'Signature validates on this local installation. Other tools must preserve expiry and coordinate context.']}
        return self.sign(packet)
    def save(self,payload):
        packet=self.make(payload);self.validate(packet);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        kind='saved' if payload.get('checkpoint') else 'draft';target=self.path(packet['caseId'],kind)
        pending=target.with_suffix('.pending');pending.write_text(canonical(packet));pending.chmod(0o600);pending.replace(target)
        if kind=='saved':self.path(packet['caseId'],'draft').unlink(missing_ok=True)
        return packet
    def read(self,case_id,checkpoint=False):
        self.purge()
        for kind in (['saved'] if checkpoint else ['draft','saved']):
            path=self.path(case_id,kind)
            if path.exists():return self.validate(json.loads(path.read_text()))
        raise ValueError('Source case not found or expired')
    def list(self,source):
        self.purge();items={}
        for file in self.root.glob('*.json'):
            if not re.fullmatch(r'[a-f0-9-]{36}\.(draft|saved)\.json',file.name):continue
            try:
                packet=self.validate(json.loads(file.read_text()),False)
                if packet['source']['id']!=source:continue
                entry=items.setdefault(packet['caseId'],{'caseId':packet['caseId'],'name':packet['name'],'expiresAt':packet['expiresAt'],'hasSaved':False,'hasDraft':False})
                entry['hasSaved']|='.saved.' in file.name;entry['hasDraft']|='.draft.' in file.name
                if '.draft.' in file.name:entry['name']=packet['name']
            except (ValueError,KeyError,TypeError):continue
        return list(items.values())
    def import_packet(self,packet):
        packet=self.validate(packet);packet={**packet,'importedFrom':{'caseId':packet['caseId'],'nativeDesignSha256':packet['nativeDesignSha256'],'expiresAt':packet['expiresAt']},'caseId':str(uuid.uuid4()),'updatedAt':datetime.now(timezone.utc).isoformat()};packet=self.sign(packet)
        target=self.path(packet['caseId'],'saved');target.write_text(canonical(packet));target.chmod(0o600);return packet
    def recover(self,case_id):
        path=self.path(case_id,'draft')
        if path.exists():
            old=self.read(case_id)
            saved=self.path(case_id,'saved')
            if saved.exists():
                checkpoint=self.validate(json.loads(saved.read_text()))
                if all(old.get(k)==checkpoint.get(k) for k in ('name','nativeDesignSha256','heightContext')):
                    path.unlink();return
            copy={**old,'caseId':str(uuid.uuid4()),'name':old['name']+' (recovery)'};copy=self.sign(copy)
            target=self.path(copy['caseId'],'draft');target.write_text(canonical(copy));target.chmod(0o600);path.unlink()
    def purge(self):
        for file in self.root.glob('*.json'):
            if not re.fullmatch(r'[a-f0-9-]{36}\.(draft|saved)\.json',file.name):continue
            try:
                packet=json.loads(file.read_text());self.validate(packet,False)
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):file.unlink(missing_ok=True)
        # Incomplete atomic writes are never loadable and carry source data.
        for file in self.root.glob('*.pending'):
            if re.fullmatch(r'[a-f0-9-]{36}\.(draft|saved)\.pending',file.name):file.unlink(missing_ok=True)
