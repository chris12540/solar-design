"""Cached-only fusion run and saved inspection data. No model/API calls."""
from pathlib import Path
import sys
import os
import json
import hashlib
import time
import numpy as np
from shapely.geometry import mapping

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'cache'))
sys.path.insert(0,str(BASE/'google-cleanup'))
from run_cleanup import load_cached
from cleanup import google_planes
from fusion import fuse
from pyproj import Proj
from affine import Affine
from scipy import ndimage as ndi


def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items() if not k.startswith('_')}
    if isinstance(value,(list,tuple)):
        return [clean(v) for v in value]
    if isinstance(value,np.ndarray):
        return value.tolist()
    if isinstance(value,np.generic):
        return value.item()
    if hasattr(value,'geom_type'):
        return mapping(value)
    return value


def main():
    source,content,rgb,fields,world,crs=load_cached()
    google,origin=google_planes(source['inputs']['insights'],crs)
    local=Affine.translation(-origin[0],-origin[1])*world
    components,_=ndi.label(fields['mask']>0)
    col,row=~local*(0.,0.)
    identifier=int(components[int(row),int(col)])
    if identifier==0:
        raise ValueError('Google center does not identify a roof-mask component; selection needs review')
    target=components==identifier
    line_bytes=(BASE/'roofmapnet-trial/outputs/lines.json').read_bytes()
    predicted=json.loads(line_bytes)
    model_report=json.loads((BASE/'roofmapnet-trial/outputs/report.json').read_text())
    if model_report['source_input_sha256']!=hashlib.sha256(content).hexdigest():
        raise ValueError('RoofMapNet predictions belong to a different cached source')
    if model_report['preprocessing']['source_shape']!=list(rgb.shape):
        raise ValueError('RoofMapNet native image size differs from cached RGB')
    started=time.perf_counter()
    result=fuse(np.array(predicted['lines_yx']),np.array(predicted['scores']),google,
                fields['dsm'],target,local)
    result['solver_seconds']=time.perf_counter()-started
    convergence=float(Proj(crs).get_factors(source['inputs']['insights']['center']['longitude'],
                                          source['inputs']['insights']['center']['latitude']).meridian_convergence)
    for face in result['faces']:
        if 'azimuth_grid_degrees' in face:
            face['azimuth_true_north_degrees']=(face['azimuth_grid_degrees']+convergence)%360
        face['design_ready']=False
    report={'status':'experimental_fusion_inspection_only','result':clean(result),
            'coordinate_system':{'crs':str(crs),'origin_xy_m':origin.tolist(),
                                  'local_affine':list(local)[:6],'z':'meters above sea level; not wall height'},
            'alignment':{'prediction_source_hash_verified':True,'native_image_shape_verified':True,
                         'raster_grid':'cached native RGB pixel-corner affine; DSM reprojected to that grid',
                         'physical_registration':'unverified; no alignment correction applied'},
            'inputs':{'original_sha256':hashlib.sha256(content).hexdigest(),
                      'roofmapnet_lines_sha256':hashlib.sha256(line_bytes).hexdigest(),
                      'source_expires_at':str(source['expires_at']),
                      'capture_dates':{'rgb_and_dsm':'2023-09-27','google_insights':'2023-10-17'},
                      'model_inference':False,'new_api_requests':0,'annotations_used':False},
            'limits':['Fixed XY photo graph; this version jointly fits planes, not image vertices',
                      'Unresolved faces and joins retained; no automatic complete roof claim',
                      'Height consistency is not surveyed physical accuracy',
                      'No walls, 3D viewer, obstruction completeness, AHJ rules or panel placement',
                      'Google and raster capture dates differ; physical registration is unverified',
                      'Single-house development run; no held-out roofs available']}
    out=ROOT/'outputs';out.mkdir(parents=True,exist_ok=True)
    (out/'fusion.json').write_text(json.dumps(report,indent=2))
    np.savez_compressed(out/'inspection.npz',rgb=rgb,dsm=fields['dsm'],target=target)
    summary={'faces':len(result['faces']),
             'google_supported':sum(f['source']=='google_plane' for f in result['faces']),
             'new_provisional':sum(f['source']=='dsm_fit_to_image_face' for f in result['faces']),
             'unresolved_faces':sum(f['coefficients'] is None for f in result['faces']),
             'joint_groups':result['joint_groups'],
             'supported_coverage':result['coverage_fraction'],'unsupported_m2':result['unsupported_area_m2'],
             'overlap_m2':result['overlap_m2'],'seconds':result['solver_seconds']}
    (out/'summary.json').write_text(json.dumps(clean(summary),indent=2))
    print(json.dumps(clean(summary),indent=2))
    for f in result['faces']:
        print(f['id'],round(f['area_horizontal_m2'],2),f['state'],
              round(f.get('final_rmse_m',999),3),f['joint_fit_applied'])


if __name__=='__main__':
    main()
