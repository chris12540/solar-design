"""Frozen, network-disabled inference and fusion over separately cached houses."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import pickle
import socket
import sys
import time

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT/'cache'))
sys.path[:0] = [str(BASE/'roof-fusion'), str(BASE/'google-cleanup'),
                str(BASE/'roofmapnet-trial/adapted')]
import cv2
import numpy as np
import torch
import yaml
from affine import Affine
from pyproj import Proj
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
from scipy import ndimage as ndi
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from cleanup import google_planes
from fusion import fuse, Settings
from roofmapnet.config import C, M
from roofmapnet.models.regression import MultitaskHead
from roofmapnet.models.roofmapnet import RoofMapNet


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    paths = [BASE/'roof-fusion/fusion.py', BASE/'google-cleanup/cleanup.py',
             BASE/'roofmapnet-trial/cache/weight-response',
             BASE/'roofmapnet-trial/vendor/config/config.yaml']
    paths += sorted((BASE/'roofmapnet-trial/adapted/roofmapnet').rglob('*.py'))
    manifest = {str(p.relative_to(BASE)): sha(p) for p in paths}
    file = ROOT/'frozen-pipeline.json'
    if file.exists():
        assert json.loads(file.read_text()) == manifest, 'Frozen pipeline changed; abort comparison'
    else:
        file.write_text(json.dumps(manifest, indent=2))
    return manifest


def deny_network(*args, **kwargs):
    raise RuntimeError('Network disabled during local trial inference')


def dummy_inputs(image):
    return {'image':image,'mode':'validation',
            'target':{'jmap':torch.zeros((1,1,128,128)),
                      'joff':torch.zeros((1,1,2,128,128)),
                      'lmap':torch.zeros((1,128,128))},
            'meta':[{'junc':torch.tensor([[-10000.,-10000.]]),
                     'jtyp':torch.zeros(1,dtype=torch.uint8),
                     'Lpos':torch.zeros((2,2)), 'Lneg':torch.zeros((2,2))}]}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items() if not k.startswith('_')}
    if isinstance(value, (tuple,list)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, 'geom_type'):
        return mapping(value)
    return value


def align(inputs):
    """Native RGB grid; center-connected roof-mask crop plus two-meter context."""
    with MemoryFile(inputs['rgb']) as mem, mem.open() as src:
        assert src.width*src.height <= 4_000_000 and src.count >= 3
        assert src.crs.is_projected and abs(src.transform.a-.1)<1e-6
        rgb = src.read([1,2,3]).transpose(1,2,0)
        world, crs = src.transform, src.crs
    fields = {}
    for key,method in [('dsm',Resampling.bilinear),('mask',Resampling.nearest)]:
        out = np.full(rgb.shape[:2], np.nan) if key == 'dsm' else np.zeros(rgb.shape[:2], dtype='uint8')
        with MemoryFile(inputs[key]) as mem, mem.open() as src:
            reproject(src.read(1),out,src_transform=src.transform,src_crs=src.crs,
                      dst_transform=world,dst_crs=crs,src_nodata=src.nodata,
                      dst_nodata=np.nan if key=='dsm' else 0,resampling=method)
        fields[key] = out
    google, origin = google_planes(inputs['insights'], crs)
    local = Affine.translation(-origin[0],-origin[1])*world
    col,row = ~local*(0.,0.)
    row,col = int(np.floor(row)),int(np.floor(col))
    assert 0<=row<rgb.shape[0] and 0<=col<rgb.shape[1], 'Center outside raster'
    components,_ = ndi.label(fields['mask']>0)
    component = int(components[row,col])
    assert component > 0, 'Google center outside roof mask; no fallback'
    target = components == component
    yy,xx = np.where(target)
    r0,r1 = max(0,yy.min()-20),min(rgb.shape[0],yy.max()+21)
    c0,c1 = max(0,xx.min()-20),min(rgb.shape[1],xx.max()+21)
    assert not target[0,:].any() and not target[-1,:].any() and not target[:,0].any() and not target[:,-1].any(), 'Target truncated at source boundary'
    return (rgb[r0:r1,c0:c1],fields['dsm'][r0:r1,c0:c1],target[r0:r1,c0:c1],
            local*Affine.translation(c0,r0),google,origin,crs)


def predict(model,rgb):
    image = cv2.resize(rgb,(512,512),interpolation=cv2.INTER_LINEAR).astype('float32')
    image = (image-np.array(M.image.mean,dtype='float32'))/np.array(M.image.stddev,dtype='float32')
    image = torch.from_numpy(image.transpose(2,0,1).copy()).unsqueeze(0)
    started = time.perf_counter()
    with torch.inference_mode():
        predictions = model(dummy_inputs(image))['preds']
    elapsed = time.perf_counter()-started
    lines = predictions['lines'][0].cpu().numpy()
    scores = predictions['score'][0].cpu().numpy()
    unique = {}
    for line,score in zip(lines,scores):
        if float(score) <= .1:
            continue
        pair = sorted(tuple(float(v) for v in p) for p in line)
        unique[tuple(pair[0]+pair[1])] = (line,float(score))
    ordered = sorted(unique.values(),key=lambda p:-p[1])
    lines = np.array([p[0] for p in ordered]).reshape(-1,2,2)
    lines *= np.array([rgb.shape[0]/128,rgb.shape[1]/128])
    return lines,np.array([p[1] for p in ordered]),elapsed


def validate(result):
    faces = result['faces']
    polys = [f['geometry'] for f in faces]
    assert all(g.is_valid for g in polys)
    assert abs(sum(g.area for g in polys)-unary_union(polys).area) < 1e-7
    for f in faces:
        assert not f['design_ready']
        if f['coefficients'] is None:
            assert not f.get('xyz_rings')
    for e in result['edges']:
        if e.get('joint_enforced'):
            assert e['final_max_gap_m'] < 1e-7


def main():
    frozen = freeze()
    if '--freeze-only' in sys.argv:
        print('Frozen files:',len(frozen))
        return
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    torch.set_num_threads(8)
    torch.manual_seed(0)
    np.random.seed(0)
    config = yaml.safe_load((BASE/'roofmapnet-trial/vendor/config/config.yaml').read_text())
    C.update(config)
    M.update(config['model'])
    model = RoofMapNet(depth=M.depth,head=lambda a,b:MultitaskHead(a,b),
        num_stacks=M.num_stacks,num_blocks=M.num_blocks,num_classes=sum(sum(M.head_size,[])))
    model.load_state_dict(torch.load(BASE/'roofmapnet-trial/cache/weight-response',
                                    map_location='cpu',weights_only=True),strict=True)
    model.eval()
    summary = []
    for home in json.loads((ROOT/'selection.json').read_text()):
        folder = ROOT/'houses'/home['trial_id']
        source_path = folder/'source.pkl'
        if not source_path.exists():
            summary.append({'trial_id':home['trial_id'],'status':'source_unavailable'})
            continue
        try:
            content = source_path.read_bytes()
            source = pickle.loads(content)  # Trusted project-generated cache.
            inputs = source['inputs']
            assert datetime.fromisoformat(inputs['expires_at']) > datetime.now(timezone.utc)
            rgb,dsm,target,transform,google,origin,crs = align(inputs)
            lines,scores,inference_seconds = predict(model,rgb)
            started = time.perf_counter()
            result = fuse(lines,scores,google,dsm,target,transform,Settings())
            fusion_seconds = time.perf_counter()-started
            convergence = float(Proj(crs).get_factors(inputs['insights']['center']['longitude'],
                                                     inputs['insights']['center']['latitude']).meridian_convergence)
            for f in result['faces']:
                f['design_ready'] = False
                if 'azimuth_grid_degrees' in f:
                    f['azimuth_true_north_degrees'] = (f['azimuth_grid_degrees']+convergence)%360
            validate(result)
            report = dict(trial_id=home['trial_id'],role=home['role'],result=clean(result),
                source_sha256=hashlib.sha256(content).hexdigest(),expires_at=inputs['expires_at'],
                source_metadata=inputs.get('source_metadata',{}),coordinate_system={
                    'crs':str(crs),'origin_xy_m':origin.tolist(),'local_affine':list(transform)[:6],
                    'z':'source meters above sea level, not wall height'},
                physical_registration='unverified',new_api_requests=0,model_device='cpu',
                inference_seconds=inference_seconds,fusion_seconds=fusion_seconds)
            (folder/'fusion.json').write_text(json.dumps(report,indent=2))
            np.savez_compressed(folder/'inspection.npz',rgb=rgb,dsm=dsm,target=target)
            (folder/'lines.json').write_text(json.dumps(dict(lines_yx=lines.tolist(),scores=scores.tolist())))
            counts={s:sum(f['state']==s for f in result['faces']) for s in
                    ['google_supported','new_plane_provisional','unresolved']}
            unknown_areas=sorted([g.area for g in result['unknown_geometries']],reverse=True)
            row=dict(trial_id=home['trial_id'],status='completed',role=home['role'],
                google_planes=len(google),faces=len(result['faces']),**counts,
                coverage=result['coverage_fraction'],unsupported_m2=result['unsupported_area_m2'],
                largest_unknown_m2=unknown_areas[:3],raw_line_count=int((scores>=.5).sum()),
                inference_seconds=inference_seconds,fusion_seconds=fusion_seconds,
                median_pitch=float(np.median([p['source_pitch_degrees'] for p in google])))
            summary.append(row)
            print(home['trial_id'],'coverage',round(row['coverage'],3),'faces',row['faces'],flush=True)
        except Exception as exc:
            summary.append(dict(trial_id=home['trial_id'],status='failed',error_type=type(exc).__name__,
                                reason=str(exc)[:180]))
            print(home['trial_id'],'offline pipeline failed:',type(exc).__name__,flush=True)
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
