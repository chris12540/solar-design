"""Source-case security, draft/checkpoint and retention checks on synthetic models."""
import copy,json,tempfile,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from source_case_store import SourceCases

now=datetime.now(timezone.utc)
manifest={'provider':'Google Solar API','fetchedAt':now.isoformat(),'expiresAt':(now+timedelta(days=20)).isoformat(),
 'pngSha256':'a'*64,'captureDate':'2023-10-17','localCRS':'LOCAL:SYNTHETIC','origin':{'latitude':0,'longitude':0}}
engine={'cad-bundle.js':'b'*64,'datamodel-api-js.wasm':'c'*64}
native={'format_version':'3','system_json':{},'site_json':{'buildings':[{'id':'building','roofs':['roof'],
 'nodes':[{'x':0,'y':0,'z':3},{'x':4,'y':0,'z':3},{'x':0,'y':4,'z':4}],
 'faces':[{'id':'face','nodes':[0,1,2],'pitch':10,'azimuth':180}],'walls':[]}]}}
with tempfile.TemporaryDirectory() as directory:
 store=SourceCases(Path(directory),lambda source:manifest if source=='synthetic' else None,engine)
 payload={'sourceId':'synthetic','name':'Synthetic case','caseId':str(uuid.uuid4()),'nativeDesignJson':json.dumps(native),'heightContext':{'groundElevation':100,'heightSha256':'d'*64}}
 packet=store.save({**payload,'checkpoint':True});assert store.read(packet['caseId'])==packet
 normalized=json.loads(json.dumps(packet).replace('3.0','3'))
 assert store.validate(normalized)
 assert store.list('synthetic')[0]['hasSaved']
 draft=store.save({**payload,'name':'Edited draft'});assert store.read(packet['caseId'])['name']=='Edited draft';assert store.read(packet['caseId'],True)['name']=='Synthetic case'
 store.recover(packet['caseId']);assert store.read(packet['caseId'])['name']=='Synthetic case';assert any(r['name']=='Edited draft (recovery)' for r in store.list('synthetic'))
 imported=store.import_packet(packet);assert imported['caseId']!=packet['caseId'] and imported['expiresAt']==packet['expiresAt'];assert imported['importedFrom']['caseId']==packet['caseId']
 for key,value in [('expiresAt',(now+timedelta(days=25)).isoformat()),('name','Tampered'),('nativeDesignJson','{}')]:
  corrupt=copy.deepcopy(packet);corrupt[key]=value
  try:store.import_packet(corrupt);raise AssertionError('Tampered packet accepted')
  except ValueError:pass
 shortened=store.save({**payload,'inputExpiresAt':(now+timedelta(days=1)).isoformat()});later=store.save(payload);assert later['expiresAt']==shortened['expiresAt']
 try:store.save({**payload,'heightContext':{'groundElevation':float('nan')}});raise AssertionError('NaN accepted')
 except ValueError:pass
 before=manifest['expiresAt'];manifest['expiresAt']=(now+timedelta(days=21)).isoformat()
 try:store.read(packet['caseId']);raise AssertionError('Source expiry mutation accepted')
 except ValueError:pass
 manifest['expiresAt']=before
 expired=copy.deepcopy(packet);expired['caseId']=str(uuid.uuid4());expired['expiresAt']=(now-timedelta(seconds=1)).isoformat();expired=store.sign(expired)
 store.path(expired['caseId'],'draft').write_text(json.dumps(expired));store.purge();assert not store.path(expired['caseId'],'draft').exists()
 print(json.dumps({'passed':True,'checkpointDraftRecovery':True,'signedExportImport':True,'tamperingRejected':True,'expiryNeverExtended':True,'sourceIdentityRequired':True,'expiredPurged':True,'syntheticOnly':True}))
