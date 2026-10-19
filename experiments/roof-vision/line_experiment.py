"""Isolated DeepLSD learned-field filtering of OpenCV LSD proposals.

No semantic roof-edge detector, fine tuning, manual-reference use, or production
integration. The cached inputs.pkl is trusted locally generated data; downloaded
model weights are loaded only with torch.load(weights_only=True).
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import os
import pickle
import resource
import sys
import time
import types
import collections
import typing

PROCESS_START = time.perf_counter()
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor/DeepLSD'))
import cv2
import numpy as np
import torch
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT/'.cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load_model():
    native = importlib.util.find_spec('pytlsd') is not None
    if not native:
        # Official module imports its native extractor even if detect_lines=False.
        # This shim only permits import; calling the unavailable extractor fails.
        shim = types.ModuleType('pytlsd')
        def unavailable(*args, **kwargs):
            raise RuntimeError('Native pytlsd unavailable: extraction disabled')
        shim.lsd = unavailable
        sys.modules['pytlsd'] = shim
    from deeplsd.models.deeplsd_inference import DeepLSD
    model = DeepLSD({'detect_lines': False}).eval()
    # Checkpoint includes unused OmegaConf config metadata. Resolve those names
    # to an inert local class, never the original constructors or unsafe pickle.
    class InertMetadata:
        pass
    metadata_names = ['omegaconf.dictconfig.DictConfig',
        'omegaconf.listconfig.ListConfig', 'omegaconf.base.Metadata',
        'omegaconf.base.ContainerMetadata', 'omegaconf.nodes.AnyNode']
    permitted = [(InertMetadata, name) for name in metadata_names]
    permitted += [typing.Any, collections.defaultdict, list, int, dict]
    with torch.serialization.safe_globals(permitted):
        checkpoint = torch.load(ROOT / 'models/deeplsd_md.tar', map_location='cpu', weights_only=True)
    if not all(isinstance(value, torch.Tensor) for value in checkpoint['model'].values()):
        raise TypeError('Model state contains non-tensor values')
    model.load_state_dict(checkpoint['model'], strict=True)
    return model, native


def context(data):
    aligned, raw = data['aligned'], data['raw']
    rgb, transform = aligned['rgb'], aligned['transform']
    h, w = rgb.shape[:2]
    inverse = ~transform
    outline = raw['roof_outline']
    mask = np.zeros((h,w), np.uint8)
    def vertices(ring):
        return np.round([inverse * tuple(p) for p in ring]).astype(np.int32)
    cv2.fillPoly(mask, [vertices(outline['polygon'])], 1)
    for hole in outline.get('holes', []):
        cv2.fillPoly(mask, [vertices(hole)], 0)
    origin = raw['origin']
    crs = CRS.from_user_input(origin['crs'])
    ox, oy = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(origin['longitude'], origin['latitude'])
    world = Affine(transform.a, transform.b, transform.c+ox,
                   transform.d, transform.e, transform.f+oy)
    dsm = np.full((h,w), np.nan, np.float32)
    with MemoryFile(data['inputs']['dsm']) as mem, mem.open() as src:
        reproject(src.read(1), dsm, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=world, dst_crs=crs, src_nodata=src.nodata,
                  dst_nodata=np.nan, resampling=Resampling.bilinear)
    return mask, dsm


def sample(array, xy):
    x = np.clip(np.rint(xy[:,0]).astype(int),0,array.shape[1]-1)
    y = np.clip(np.rint(xy[:,1]).astype(int),0,array.shape[0]-1)
    return array[y,x]


def plane_evidence(line, dsm, mask, pixel):
    """Two local DSM strip fits. Thresholds are exploratory, never semantic labels."""
    a,b = line
    delta=b-a
    length=np.linalg.norm(delta)
    tangent=delta/length
    normal=np.array([-tangent[1],tangent[0]])
    tt=np.linspace(0.1,0.9,max(8,int(length)))
    offsets=np.linspace(0.2/pixel,0.6/pixel,5)
    models=[]
    valid_fractions=[]
    for sign in (-1,1):
        points=(a[None,None,:]+tt[:,None,None]*delta[None,None,:]
                +sign*offsets[None,:,None]*normal).reshape(-1,2)
        zz=sample(dsm,points)
        valid=np.isfinite(zz)&(sample(mask,points)>0)
        valid_fractions.append(float(valid.mean()))
        if valid.sum()<15:
            models.append(None)
            continue
        xy=(points[valid]-(a+b)/2)*pixel
        design=np.c_[xy,np.ones(len(xy))]
        coef=np.linalg.lstsq(design,zz[valid],rcond=None)[0]
        rmse=float(np.sqrt(np.mean((design@coef-zz[valid])**2)))
        models.append((coef,rmse))
    fold=None; step=None; residuals=[]
    if all(m is not None for m in models):
        c0,c1=models[0][0],models[1][0]
        normals=[np.r_[-c[:2],1.] for c in (c0,c1)]
        fold=float(np.degrees(np.arccos(np.clip(np.dot(*normals)/(np.linalg.norm(normals[0])*np.linalg.norm(normals[1])),-1,1))))
        step=float(abs(c0[2]-c1[2]))
        residuals=[m[1] for m in models]
    return {'strip_roof_valid_fractions':valid_fractions,
            'side_plane_normal_difference_deg':fold,'side_plane_midpoint_height_difference_m':step,
            'side_fit_rmse_m':residuals,
            'fold_or_step_evidence':bool(fold is not None and (fold>=8 or step>=.15) and max(residuals)<=.35)}


def main():
    total_start=time.perf_counter()
    output=ROOT/'outputs'; output.mkdir(exist_ok=True)
    previous_report=json.loads((output/'lines.json').read_text()) if (output/'lines.json').exists() else None
    with open(ROOT/'data/inputs.pkl','rb') as handle:
        data=pickle.load(handle)
    rgb=data['aligned']['rgb']; gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    pixel=data['aligned']['pixel_size_m']; transform=data['aligned']['transform']
    mask,dsm=context(data)
    torch.set_num_threads(2)
    start=time.perf_counter(); model,native=load_model(); load_seconds=time.perf_counter()-start
    x=torch.from_numpy(gray.astype(np.float32)/255)[None,None]
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    fallback=None
    start=time.perf_counter()
    try:
        with torch.inference_mode():
            model=model.to(device); prediction=model({'image':x.to(device)})
            df=prediction['df'][0].cpu().numpy()
            angles=prediction['line_level'][0].cpu().numpy()
        if device=='mps': torch.mps.synchronize()
    except Exception as error:
        if device!='mps': raise
        fallback=f'{type(error).__name__}: {error}'
        device='cpu'; model=model.to(device)
        with torch.inference_mode():
            prediction=model({'image':x}); df=prediction['df'][0].numpy(); angles=prediction['line_level'][0].numpy()
    inference_seconds=time.perf_counter()-start
    # One fresh-process warm-up above; three steady passes below. Transfer and
    # result copies are outside the steady model-forward timing. No filter tuning.
    steady_seconds=[]
    steady_field_max_difference=[]
    resident_x=x.to(device)
    for _ in range(3):
        if device=='mps': torch.mps.synchronize()
        steady_start=time.perf_counter()
        with torch.inference_mode():
            steady=model({'image':resident_x})
        if device=='mps': torch.mps.synchronize()
        steady_seconds.append(time.perf_counter()-steady_start)
        steady_df=steady['df'][0].cpu().numpy()
        steady_angle=steady['line_level'][0].cpu().numpy()
        steady_field_max_difference.append(float(max(np.max(np.abs(steady_df-df)),np.max(np.abs(steady_angle-angles)))))
    start=time.perf_counter()
    proposals=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    lines=np.empty((0,2,2)) if proposals is None else proposals.reshape(-1,2,2)
    classical_seconds=time.perf_counter()-start
    edge=cv2.morphologyEx(mask,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))
    boundary_distance=cv2.distanceTransform((1-edge).astype(np.uint8),cv2.DIST_L2,5)
    records=[]
    for index,line in enumerate(lines):
        delta=line[1]-line[0]; length=float(np.linalg.norm(delta))
        samples=line[0]+np.linspace(.05,.95,max(16,int(length)))[:,None]*delta
        angle=float(np.arctan2(delta[1],delta[0])%np.pi)
        angdiff=np.abs((sample(angles,samples)-angle+np.pi/2)%np.pi-np.pi/2)
        distances=sample(df,samples)
        learned=float(((distances<1.5)&(angdiff<np.pi/9)).mean())
        roof_fraction=float((sample(mask,samples)>0).mean())
        boundary_fraction=float((sample(boundary_distance,samples)*pixel<=.35).mean())
        evidence=plane_evidence(line,dsm,mask,pixel)
        dsm_valid=float(np.isfinite(sample(dsm,samples)).mean())
        roof_ok=length*pixel>=.8 and roof_fraction>=.65
        learned_ok=learned>.5
        contextual_ok=dsm_valid>=.8 and (evidence['fold_or_step_evidence'] or boundary_fraction>=.5)
        records.append({'id':index,'pixel_xy':line.tolist(),
            'local_xy_m':[[float(v) for v in transform*tuple(p+.5)] for p in line],
            'length_m':length*pixel,'roof_fraction':roof_fraction,
            'raw_mask_boundary_fraction':boundary_fraction,'dsm_valid_fraction':dsm_valid,
            'learned_inlier_fraction':learned,'learned_mean_distance_px':float(np.mean(distances)),
            'learned_median_angle_error_deg':float(np.degrees(np.median(angdiff))),
            'geometry_supported':bool(roof_ok),'learned_supported':bool(learned_ok),
            'dsm_or_mask_boundary_supported':bool(contextual_ok),
            'classical_context_selected':bool(roof_ok and contextual_ok),
            'learned_filtered_selected':bool(roof_ok and contextual_ok and learned_ok),
            'dsm_evidence':evidence,'semantic_type':'generic_line_unknown'})
    selected=[r for r in records if r['learned_filtered_selected']]
    baseline=[r for r in records if r['classical_context_selected']]
    np.savez_compressed(output/'lines-fields.npz',distance_px=df,line_angle_rad=angles,roof_mask=mask,dsm_m=dsm)
    report={'method':'OpenCV LSD proposals filtered by pretrained DeepLSD distance and angle fields, then roof-mask and DSM context',
        'model_training_domain':'Official generic outdoor MegaDepth checkpoint; not roof-specific fine tuning',
        'semantic_roof_edges':False,'native_deeplsd_extractor_used':False,'native_pytlsd_available':native,
        'coordinate_convention':'pixel_xy are OpenCV center coordinates; local_xy_m applies raster transform to pixel_xy + 0.5',
        'input_image_size_xy':[rgb.shape[1],rgb.shape[0]],'image_was_cropped_or_resized_by_experiment':False,
        'device':device,'torch_version':torch.__version__,'opencv_version':cv2.__version__,'mps_fallback_error':fallback,'checkpoint_load_seconds':load_seconds,
        'learned_inference_seconds':inference_seconds,
        'initial_recorded_warm_inference_seconds':previous_report.get('initial_recorded_warm_inference_seconds',previous_report['learned_inference_seconds']) if previous_report else inference_seconds,
        'steady_model_forward_seconds':steady_seconds,
        'steady_model_forward_median_seconds':float(np.median(steady_seconds)),
        'steady_field_max_absolute_differences_from_warm':steady_field_max_difference,
        'timing_scope':'Warm timing includes model/input transfer and CPU output copy. Steady timings measure model forward with MPS synchronization before/after; resident model/input, no CPU result transfer.','classical_lsd_seconds':classical_seconds,
        'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'mps_retained_allocated_bytes_sampled_after_inference':int(torch.mps.current_allocated_memory()) if device=='mps' else None,
        'memory_scope':'Process RSS is process high-water RSS, not isolated model memory. MPS is a retained allocation sample, not peak GPU memory; separately measured processes are not directly comparable.',
        'counts':{'classical_full_image':len(records),'classical_context_selected':len(baseline),'learned_filtered_selected':len(selected)},
        'thresholds':{'min_length_m':.8,'roof_fraction_min':.65,'learned_distance_px_max':1.5,
          'learned_angle_error_deg_max':20,'learned_inlier_fraction_min_exclusive':.5,
          'dsm_valid_fraction_min':.8,'fold_angle_deg_min':8,'step_height_m_min':.15,'side_rmse_m_max':.35,
          'mask_boundary_distance_m_max':.35,'mask_boundary_fraction_min':.5},
        'limitations':['Generic image line features; no ridge/hip/valley/eave semantics or roof topology.',
          'All endpoints originate from OpenCV LSD, so the learned model cannot recover missed candidates.',
          'Roof membership uses cached raw DSM/mask outline as an explicit prior.',
          'DSM strip fits and boundary support are exploratory heuristics, not validated accuracy.',
          'Model sees complete cached RGB crop with no mask applied; no hand reference used.',
          'Source imagery and DSM may have different acquisition dates and imperfect registration.'],
        'attribution':{'DeepLSD':'https://github.com/cvg/DeepLSD','DeepLSD_commit':'f7d9d6258c0cd25d4f6eea882853565403d289be',
          'model_url':'https://cvg-data.inf.ethz.ch/DeepLSD/deeplsd_md.tar',
          'model_sha256':hashlib.sha256((ROOT/'models/deeplsd_md.tar').read_bytes()).hexdigest(),
          'DeepLSD_code_and_model_license':'MIT per LICENSE and README; copyright 2022 Rémi Pautrat',
          'OpenCV':'https://github.com/opencv/opencv (5.0.0 root Apache-2.0; LSD source retains BSD-style notice)',
          'OpenCV_LSD_license_source':'https://raw.githubusercontent.com/opencv/opencv/5.0.0/modules/imgproc/src/lsd.cpp',
          'unused_native_submodules':['pytlsd','pytlbd','progressive-x','homography_est','pybind11'],
          'submodule_license_status':'Unused/uninitialized. Root licenses: pytlsd/pytlbd/progressive-x/homography_est MIT; pybind11 BSD-3-Clause. Pinned pytlsd src/lsd.cpp is AGPL-3.0-or-later despite wrapper MIT. Native dependency and nested licenses need separate review before integration.',
          'pytlsd_AGPL_source':'https://raw.githubusercontent.com/iago-suarez/pytlsd/21381ca4c5c8da297ef44ce07dda115075c5a648/src/lsd.cpp'},
        'source_fetched_at':data.get('source_fetched_at'),'expires_at':data.get('expires_at'),'lines':records}
    fig,axes=plt.subplots(1,3,figsize=(13.2,5.2))
    panels=[('Classical LSD: full image',records,'#fbbf24'),
            ('Classical + mask / DSM context',baseline,'#60a5fa'),
            ('Learned-filtered classical + context',selected,'#34d399')]
    for ax,(title,items,color) in zip(axes,panels):
        ax.imshow(rgb)
        ax.contour(mask,levels=[.5],colors=['white'],linewidths=.6,alpha=.6)
        for item in items:
            xy=np.array(item['pixel_xy']); ax.plot(xy[:,0],xy[:,1],color=color,lw=1.3)
        ax.set_title(f'{title}\n{len(items)} generic segments',fontsize=11); ax.axis('off')
    fig.suptitle('Cached aerial crop • generic line evidence, not semantic roof edges',fontsize=14)
    fig.text(.5,.055,'DeepLSD: Pautrat et al., CVPR 2023 (MIT code/model) • OpenCV LSD proposals • white: cached raw roof mask',ha='center',fontsize=9)
    fig.text(.5,.022,'Whole RGB crop used. DSM / mask context is a prior; no hand reference used. Counts do not measure accuracy.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.93)); fig.savefig(output/'lines-comparison.png',dpi=170); plt.close(fig)
    report['total_seconds']=time.perf_counter()-total_start
    report['pipeline_seconds_excluding_steady_benchmark']=report['total_seconds']-sum(steady_seconds)
    report['whole_process_wall_seconds_through_artifacts']=time.perf_counter()-PROCESS_START
    if previous_report:
        report['same_output_as_previous_run']=records==previous_report['lines']
        report['same_selected_ids_as_previous_run']=[r['id'] for r in selected]==[r['id'] for r in previous_report['lines'] if r['learned_filtered_selected']]
    report['peak_process_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (output/'lines.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in report.items() if k in ['device','counts','learned_inference_seconds','classical_lsd_seconds','peak_process_rss_bytes','total_seconds','mps_fallback_error','steady_model_forward_seconds','steady_model_forward_median_seconds','same_selected_ids_as_previous_run','same_output_as_previous_run','whole_process_wall_seconds_through_artifacts']},indent=2))

if __name__=='__main__': main()
