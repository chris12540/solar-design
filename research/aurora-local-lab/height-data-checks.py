"""Synthetic raster alignment/lifetime checks. Never accesses Google or source cache."""
import importlib.util,json,tempfile,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import Affine

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/chris/code/solar-designer')
from backend import solar_roof
spec=importlib.util.spec_from_file_location('height_data',ROOT/'height-data.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
crs='+proj=aeqd +lat_0=33 +lon_0=-112 +datum=WGS84 +units=m +no_defs'
transform=Affine(.1,0,-20,0,-.1,20)
rows,cols=np.meshgrid(np.arange(400),np.arange(400),indexing='ij');x=-19.95+cols*.1;y=19.95-rows*.1
mask=((abs(x)<6)&(abs(y)<4)).astype('uint8');dsm=np.where(mask,104+.5*(4-abs(y)),100).astype('float32');dsm[:5,:5]=-9999

def tiff(data,nodata):
 with MemoryFile() as memory:
  with memory.open(driver='GTiff',width=400,height=400,count=1,dtype=data.dtype,transform=transform,crs=crs,nodata=nodata) as raster:raster.write(data,1)
  return memory.read()
rasters={'dsm':tiff(dsm,-9999),'mask':tiff(mask,0)}
with tempfile.TemporaryDirectory() as folder:
 cache=Path(folder);now=datetime.now(timezone.utc)
 manifest={'expiresAt':(now+timedelta(days=20)).isoformat(),'pngSha256':'a'*64,'origin':{'latitude':33,'longitude':-112},'localCRS':crs,'pixelToEditor':[.1,0,-19.95,0,-.1,19.95],'width':400,'height':400,'captureDate':'2023-10-17'}
 (cache/'manifest.json').write_text(json.dumps(manifest))
 layers={'imageryDate':{'year':2023,'month':10,'day':17},'dsmUrl':'dsm','maskUrl':'mask'}
 with patch('scripts.dev.environment',return_value={'GOOGLE_SOLAR_API_KEY':'synthetic'}),patch.object(solar_roof,'_json_request',return_value=layers),patch.object(solar_roof,'_raster_request',side_effect=lambda url,key:rasters[url]):
  assert module.acquire(cache)['reused'] is False
 metadata=json.loads((cache/'height.json').read_text());assert metadata['expiresAt']==manifest['expiresAt'];assert abs(metadata['groundElevation']-100)<1e-7;assert metadata['width']==80 and metadata['height']==80
 heights=np.frombuffer((cache/'height.bin').read_bytes(),dtype='<f4').reshape(80,80);assert np.isnan(heights[0,0]);assert abs(heights[40,40]-105.975)<1e-4
 assert metadata['pixelToEditor']==[.5,0,-19.95,0,-.5,19.95]
 with patch.object(solar_roof,'_json_request',side_effect=AssertionError('Unexpected network')):assert module.acquire(cache)['reused'] is True
 (cache/'height.json').unlink()
 with patch.object(solar_roof,'_json_request',side_effect=AssertionError('Processing must reuse raw cache')):
  assert module.acquire(cache)['rawReused'] is True
 (cache/'height.json').unlink();(cache/'height-source.json').unlink();layers['imageryDate']['day']=18
 with patch('scripts.dev.environment',return_value={'GOOGLE_SOLAR_API_KEY':'synthetic'}),patch.object(solar_roof,'_json_request',return_value=layers),patch.object(solar_roof,'_raster_request',side_effect=AssertionError('Mismatched dates must stop before downloads')):
  try:module.acquire(cache);raise AssertionError('Date mismatch accepted')
  except ValueError as error:assert str(error)=='HEIGHT_IMAGERY_DATE_MISMATCH'
 manifest['expiresAt']=(now-timedelta(seconds=1)).isoformat();(cache/'manifest.json').write_text(json.dumps(manifest))
 with patch.object(solar_roof,'_json_request',side_effect=AssertionError('Expired source must not fetch')):
  try:module.acquire(cache);raise AssertionError('Expired input accepted')
  except RuntimeError as error:assert str(error)=='Source expired'
print(json.dumps({'passed':True,'syntheticOnly':True,'registration':True,'nodata':True,'groundEstimate':True,'originalExpiryPreserved':True,'cacheReuse':True,'dateMismatchRejectedBeforeDownload':True,'expiredRejectedBeforeNetwork':True}))
