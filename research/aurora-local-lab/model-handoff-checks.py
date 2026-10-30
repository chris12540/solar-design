"""Frame/height/holes/expiry checks against synthetic known planes only."""
from datetime import datetime,timedelta,timezone
import copy,json
import numpy as np
from pyproj import Transformer
from model_handoff import convert_generated,return_geometry
from source_case_store import geometry_from_native
now=datetime.now(timezone.utc);lat,lng=33.,-112.
crs='EPSG:32612';target=f'+proj=aeqd +lat_0={lat} +lon_0={lng} +datum=WGS84 +units=m +no_defs'
manifest={'origin':{'latitude':lat,'longitude':lng},'localCRS':target,'pngSha256':'a'*64,'expiresAt':(now+timedelta(days=20)).isoformat()}
height={'groundElevation':100,'imageSha256':'a'*64,'expiresAt':manifest['expiresAt'],'sha256':'b'*64}
face={'id':'known','polygon':[[-6,-5],[6,-5],[6,5],[-6,5]],'holes':[[[-1,-1],[1,-1],[1,1],[-1,1]]],'plane_model':{'a':.3,'b':.2,'c':105}}
handoff={'schema':'roof-reconstruction-handoff/v1','heightDatum':'EGM96','fetchedAt':now.isoformat(),'expiresAt':(now+timedelta(days=2)).isoformat(),'stage':'raw','result':{'origin':{'latitude':lat,'longitude':lng,'crs':crs},'faces':[face]}}
converted=convert_generated(handoff,manifest,height);native=json.loads(converted['nativeDesignJson']);geometry=geometry_from_native(native)
assert len(native['site_json']['roof.plane'])>1
assert abs(converted['generator']['sourceArea']-116)<1e-7
packet={'caseId':'synthetic','expiresAt':handoff['expiresAt'],'nativeDesignSha256':'c'*64,'coordinates':{'horizontalCRS':target,'horizontalOrigin':manifest['origin'],'groundElevation':100,'verticalDatum':'EGM96-minus-ground-reference'},'geometry':geometry}
returned=return_geometry(packet,{'origin':handoff['result']['origin'],'expiresAt':manifest['expiresAt']})
assert returned['expiresAt']==handoff['expiresAt']
for f in returned['faces']:
 for x,y,z in f['vertices']:assert abs(z-(105+.3*x+.2*y))<.0001
bad=copy.deepcopy(handoff);bad['result']['origin']['latitude']+=.01
try:convert_generated(bad,manifest,height);raise AssertionError('Wrong house accepted')
except ValueError:pass
bad=copy.deepcopy(handoff);bad['expiresAt']=(now-timedelta(seconds=1)).isoformat()
try:convert_generated(bad,manifest,height);raise AssertionError('Expired input accepted')
except ValueError:pass
bad=copy.deepcopy(handoff);bad['result']['faces'][0].pop('plane_model')
try:convert_generated(bad,manifest,height);raise AssertionError('Missing heights accepted')
except ValueError:pass
print(json.dumps({'passed':True,'knownProjectionRoundtrip':True,'absoluteHeightDatumPreserved':True,'holesAreaPreserved':True,'expiryMinimum':True,'wrongHouseExpiredMissingPlaneRejected':True,'syntheticOnly':True}))
