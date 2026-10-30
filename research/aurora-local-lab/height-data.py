"""Explicit Google DSM/mask acquisition aligned to existing, unexpired imagery."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/chris/code/solar-designer')


def acquire(cache):
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import Affine
    from rasterio.warp import reproject,Resampling
    from scripts.dev import environment
    from backend import solar_roof
    cache=Path(cache)
    manifest=json.loads((cache/'manifest.json').read_text())
    deadline=datetime.fromisoformat(manifest['expiresAt'])
    if deadline<=datetime.now(timezone.utc):raise RuntimeError('Source expired')
    if (cache/'height.json').exists():
        existing=json.loads((cache/'height.json').read_text())
        if existing['expiresAt']==manifest['expiresAt'] and existing['imageSha256']==manifest['pngSha256'] and all((cache/name).is_file() and hashlib.sha256((cache/name).read_bytes()).hexdigest()==existing[key] for name,key in [('height.bin','sha256'),('height-mask.bin','maskSha256')]):return {'reused':True}
    source_path=cache/'height-source.json'
    raw_reused=False
    if source_path.exists():
        retained=json.loads(source_path.read_text())
        if retained['expiresAt']==manifest['expiresAt'] and retained['imageSha256']==manifest['pngSha256'] and retained['captureDate']==manifest['captureDate']:
            dsm=(cache/'height-dsm.tif').read_bytes();mask=(cache/'height-mask.tif').read_bytes()
            raw_reused=hashlib.sha256(dsm).hexdigest()==retained['dsmSha256'] and hashlib.sha256(mask).hexdigest()==retained['maskSha256']
    if not raw_reused:
        key=environment().get('GOOGLE_SOLAR_API_KEY','').strip()
        if not key:raise RuntimeError('Solar key missing')
        center=manifest['origin']
        layers=solar_roof._json_request(solar_roof.LAYERS_ENDPOINT+'?'+urlencode({
            'location.latitude':format(center['latitude'],'.8f'),'location.longitude':format(center['longitude'],'.8f'),
            'radiusMeters':'40','view':'IMAGERY_LAYERS','requiredQuality':'HIGH','pixelSizeMeters':'0.1'}),key)
        date=layers.get('imageryDate',{})
        capture=f"{date.get('year',0):04d}-{date.get('month',0):02d}-{date.get('day',0):02d}"
        if capture!=manifest.get('captureDate'):raise ValueError('HEIGHT_IMAGERY_DATE_MISMATCH')
        dsm=solar_roof._raster_request(layers.get('dsmUrl'),key)
        mask=solar_roof._raster_request(layers.get('maskUrl'),key)
        retained={'expiresAt':manifest['expiresAt'],'imageSha256':manifest['pngSha256'],'captureDate':capture,
                  'fetchedAt':datetime.now(timezone.utc).isoformat(),'dsmSha256':hashlib.sha256(dsm).hexdigest(),'maskSha256':hashlib.sha256(mask).hexdigest()}
        if datetime.now(timezone.utc)>=deadline:raise RuntimeError('Source expired while downloading')
        # Retain original bytes before processing so a local fix does not rebill.
        for name,content in [('height-dsm.tif',dsm),('height-mask.tif',mask),('height-source.json',json.dumps(retained).encode())]:
            pending=cache/(name+'.pending');pending.write_bytes(content);pending.chmod(0o600);pending.replace(cache/name)
    capture=retained['captureDate']
    a,b,tx,d,e,ty=manifest['pixelToEditor']
    transform=Affine(a,b,tx-(a+b)/2,d,e,ty-(d+e)/2)
    shape=(manifest['height'],manifest['width'])
    aligned=np.full(shape,np.nan,dtype='float32');roof=np.full(shape,255,dtype='uint8')
    originals=[]
    for content,output,resampling in [(dsm,aligned,Resampling.bilinear),(mask,roof,Resampling.nearest)]:
        with MemoryFile(content) as memory,memory.open() as raster:
            if raster.count!=1 or not raster.crs or raster.width*raster.height>4000000:raise RuntimeError('Unsupported height raster')
            originals.append({'crs':raster.crs.to_string(),'transform':list(raster.transform)[:6],'width':raster.width,'height':raster.height})
            # Binary roof mask's zero means valid non-roof, even when TIFF nodata=0.
            # Read array to prevent GDAL inferring zero as nodata from the band.
            source=raster.read(1) if output is roof else rasterio.band(raster,1)
            reproject(source=source,destination=output,src_transform=raster.transform,src_crs=raster.crs,
                src_nodata=(raster.nodata if raster.nodata is not None else -9999) if output is aligned else 255,
                dst_transform=transform,dst_crs=manifest['localCRS'],dst_nodata=np.nan if output is aligned else 255,resampling=resampling)
    aligned[(aligned<=-9990)|(~np.isfinite(aligned))]=np.nan
    stride=5
    heights=aligned[::stride,::stride].copy();roofs=roof[::stride,::stride].copy()
    width,height=heights.shape[1],heights.shape[0]
    cols,rows=np.meshgrid(np.arange(width)*stride,np.arange(height)*stride)
    x=a*cols+b*rows+tx;y=d*cols+e*rows+ty
    ground=heights[np.isfinite(heights)&(roofs==0)&(x*x+y*y<25*25)]
    if ground.size<100:raise ValueError('INSUFFICIENT_GROUND_SAMPLES')
    estimated=float(np.percentile(ground,20))
    raw=heights.astype('<f4').tobytes();mask_raw=roofs.tobytes()
    result={'schema':'roof-lab-height/v1','expiresAt':manifest['expiresAt'],'imageSha256':manifest['pngSha256'],
        'fetchedAt':retained['fetchedAt'],'width':width,'height':height,
        'pixelToEditor':[a*stride,b*stride,tx,d*stride,e*stride,ty],'datum':'EGM96','units':'m',
        'groundElevation':estimated,'groundMethod':'20th percentile of valid non-roof pixels within25m; estimate only',
        'sha256':hashlib.sha256(raw).hexdigest(),'maskSha256':hashlib.sha256(mask_raw).hexdigest(),
        'originalSha256':hashlib.sha256(dsm).hexdigest(),'originalMaskSha256':hashlib.sha256(mask).hexdigest(),
        'originalGrids':originals,'captureDate':capture,'byteOrder':'little-endian-float32',
        'requests':{'dataLayers':1,'dsmDownload':1,'maskDownload':1}}
    if datetime.now(timezone.utc)>=deadline:raise RuntimeError('Source expired while loading')
    for name,content in [('height.bin',raw),('height-mask.bin',mask_raw),('height.json',json.dumps(result).encode())]:
        pending=cache/(name+'.pending');pending.write_bytes(content);pending.chmod(0o600);pending.replace(cache/name)
    return {'reused':False,'rawReused':raw_reused,'samples':int(np.isfinite(heights).sum())}
