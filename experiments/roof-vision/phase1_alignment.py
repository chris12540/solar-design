"""Cached-only Phase 1 georeference audit and bounded alignment diagnostics.

No reference labels, fitting outputs, network, model inference, or correction.
Offset convention: translate DSM/mask evidence by (east_m, north_m) relative to
fixed RGB. Original source files/expiry are never changed.
"""
from pathlib import Path
import base64
import hashlib
import io
import json
import pickle
import time
from datetime import date

import cv2
import numpy as np
from affine import Affine
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling
from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parent


def iso(value):
    return date(value['year'],value['month'],value['day']).isoformat() if value else None


def metadata_and_arrays(content):
    with MemoryFile(content) as mem, mem.open() as src:
        arr=src.read()
        finite=np.isfinite(arr)
        info={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),
              'driver':src.driver,'shape_bands_height_width':list(arr.shape),
              'dtypes':list(src.dtypes),'crs':str(src.crs),'transform_corner_affine':list(src.transform)[:6],
              'resolution_m':list(src.res),'bounds_projected':list(src.bounds),
              'nodata':src.nodata,'dataset_tags':src.tags(),
              'band_tags':[src.tags(i+1) for i in range(src.count)],
              'mask_flags':[[str(f) for f in flags] for flags in src.mask_flag_enums],
              'dataset_mask_valid_fraction':float((src.dataset_mask()>0).mean()),
              'nonfinite_values':int((~finite).sum()),'minus9999_values':int((arr==-9999).sum()),
              'finite_min':float(arr[finite].min()),'finite_max':float(arr[finite].max()),
              'capture_date_in_tags':None}
        return info,arr,src.transform,src.crs,src.nodata


def shifted_score(points_yx,distance,dx,dy,pixel):
    positions=points_yx+np.array([-dy/pixel,dx/pixel])
    in_frame=(positions[:,0]>=0)&(positions[:,0]<distance.shape[0]-1)&(positions[:,1]>=0)&(positions[:,1]<distance.shape[1]-1)
    if in_frame.mean()<.98:return None
    values=ndi.map_coordinates(distance,positions[in_frame].T,order=1,mode='nearest')
    # Upper clipping bounds influence of evidence with no corresponding visible edge.
    return float(np.minimum(values,.5).mean())


def offset_diagnostic(name,evidence,distance,domain):
    points=np.column_stack(np.nonzero(evidence&domain)).astype(float)
    if len(points)<30:
        return {'name':name,'status':'insufficient_evidence','evidence_pixels':len(points)}
    pixel=.1; offsets=np.round(np.arange(-.8,.80001,.1),3)
    scores=[]
    for dy in offsets:
        for dx in offsets:
            score=shifted_score(points,distance,float(dx),float(dy),pixel)
            if score is not None:scores.append({'east_m':float(dx),'north_m':float(dy),'mean_clipped_distance_m':score})
    scores.sort(key=lambda q:(q['mean_clipped_distance_m'],abs(q['east_m'])+abs(q['north_m'])))
    best=scores[0]
    baseline=next(q for q in scores if q['east_m']==0 and q['north_m']==0)
    distinct=next(q for q in scores if np.hypot(q['east_m']-best['east_m'],q['north_m']-best['north_m'])>=.3-1e-8)
    close=[q for q in scores if q['mean_clipped_distance_m']<=best['mean_clipped_distance_m']+.01]
    return {'name':name,'status':'diagnostic_only','evidence_pixels':len(points),'baseline':baseline,'best':best,
            'runner_up_adjacent':scores[1],'runner_up_at_least_0_3m_away':distinct,
            'baseline_minus_best_m':baseline['mean_clipped_distance_m']-best['mean_clipped_distance_m'],
            'distinct_runner_up_minus_best_m':distinct['mean_clipped_distance_m']-best['mean_clipped_distance_m'],
            'best_at_search_boundary':abs(best['east_m'])==.8 or abs(best['north_m'])==.8,
            'within_0_01m_of_best_count':len(close),
            'within_0_01m_of_best_east_range_m':[min(q['east_m'] for q in close),max(q['east_m'] for q in close)],
            'within_0_01m_of_best_north_range_m':[min(q['north_m'] for q in close),max(q['north_m'] for q in close)],
            'grid_scores':scores}


def main():
    started=time.perf_counter();out=ROOT/'outputs';out.mkdir(exist_ok=True)
    input_path=ROOT/'data/inputs.pkl';input_hash=hashlib.sha256(input_path.read_bytes()).hexdigest()
    data=pickle.loads(input_path.read_bytes())
    aligned,raw=data['aligned'],data['raw'];rgb=aligned['rgb'];h,w=rgb.shape[:2]
    pixel=float(aligned['pixel_size_m']);local=aligned['transform'];origin=raw['origin']
    if pixel!=.1 or local.b!=0 or local.d!=0:raise ValueError('Diagnostic assumes the cached north-up 0.1m crop')
    crs=CRS.from_user_input(origin['crs'])
    ox,oy=Transformer.from_crs(4326,crs,always_xy=True).transform(origin['longitude'],origin['latitude'])
    world=Affine.translation(ox,oy)*local
    raster_info={};arrays={};resampled={};source_transforms={};source_crs={}
    for key in ['dsm','mask','rgb']:
        info,arr,tf,sourcecrs,nodata=metadata_and_arrays(data['inputs'][key]);raster_info[key]=info;arrays[key]=arr
        source_transforms[key]=tf;source_crs[key]=sourcecrs
        dest=np.full((arr.shape[0],h,w),np.nan if key=='dsm' else 0,dtype=np.float32 if key=='dsm' else np.uint8)
        for band in range(arr.shape[0]):
            reproject(arr[band],dest[band],src_transform=tf,src_crs=sourcecrs,dst_transform=world,dst_crs=crs,
                      src_nodata=nodata if key!='rgb' else None,dst_nodata=np.nan if key=='dsm' else 0,
                      resampling=Resampling.nearest if key=='mask' else Resampling.bilinear)
        resampled[key]=dest
    rgb_reproduced=np.moveaxis(resampled['rgb'],0,-1)
    photo=Image.open(io.BytesIO(base64.b64decode(raw['photo']['data_url'].split(',',1)[1]))).convert('RGBA')
    photo_array=np.asarray(photo);png=np.asarray(Image.open(ROOT/'data/roof.png').convert('RGB'))
    outline=raw['roof_outline']
    roof=rasterize([({'type':'Polygon','coordinates':[outline['polygon']]+outline.get('holes',[])},1)],out_shape=(h,w),transform=local).astype(bool)
    source_mask=resampled['mask'][0]>0
    labels,n=ndi.label(source_mask)
    intersections=np.bincount(labels[roof],minlength=n+1);intersections[0]=0
    chosen=int(intersections.argmax());target_mask=labels==chosen
    if chosen==0:raise ValueError('Raw roof does not overlap a cached source mask component')
    dsm=resampled['dsm'][0]
    blurred=cv2.GaussianBlur(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),(5,5),.8)
    rgb_edges=cv2.Canny(blurred,40,100)>0
    rgb_edges_strict=cv2.Canny(blurred,70,140)>0
    distance=ndi.distance_transform_edt(~rgb_edges)*pixel
    strict_distance=ndi.distance_transform_edt(~rgb_edges_strict)*pixel
    mask_boundary=target_mask&~ndi.binary_erosion(target_mask)
    # Smooth derivative limits raster noise; high gradients isolate height jumps
    # rather than ordinary pitched-roof slopes. Domain is fixed before offsets.
    smoothed=ndi.gaussian_filter(dsm,sigma=.7)
    gy,gx=np.gradient(smoothed,pixel);height_gradient=np.hypot(gx,gy)
    near_boundary=ndi.distance_transform_edt(~mask_boundary)*pixel<=.4
    dsm_jump=(height_gradient>=1.5)&near_boundary&np.isfinite(dsm)
    domain=ndi.binary_dilation(roof,iterations=5)&ndi.binary_erosion(np.ones((h,w),bool),iterations=9)
    diagnostics=[offset_diagnostic('source_mask_boundary_to_RGB_Canny40_100',mask_boundary,distance,domain),
                 offset_diagnostic('DSM_height_jump_to_RGB_Canny40_100',dsm_jump,distance,domain),
                 offset_diagnostic('source_mask_boundary_to_RGB_Canny70_140_sensitivity',mask_boundary,strict_distance,domain),
                 offset_diagnostic('DSM_height_jump_to_RGB_Canny70_140_sensitivity',dsm_jump,strict_distance,domain)]
    center=local*(.5,.5);world_center=world*(.5,.5)
    inv_source=~source_transforms['rgb'];source_corner_position=inv_source*(world*(0,0))
    cache_path=ROOT/'data/phase1-cache-metadata.json'
    cache_metadata=json.loads(cache_path.read_text()) if cache_path.exists() else None
    cache_match_verified=bool(cache_metadata and cache_metadata.get('dsm_sha256')==raster_info['dsm']['sha256'] and len(cache_metadata.get('matches',[]))==1)
    cache_row=cache_metadata['matches'][0] if cache_match_verified else None
    if cache_row and (cache_row['source_fetched_at']!=data['source_fetched_at'] or cache_row['expires_at']!=data['expires_at']):
        raise ValueError('Recovered cache metadata timestamps differ from exported inputs')
    issues=[]
    if 'source_metadata' not in data['inputs']:issues.append('Exported inputs omit original DataLayers response/source_metadata. A separately recovered matching local cache record supplies source_metadata dates; TIFF tags contain no capture dates.')
    if raster_info['dsm']['nodata'] is None:issues.append('DSM has no declared nodata value; finite values and -9999 sentinel counts were checked explicitly.')
    if not np.isfinite(dsm).all():issues.append('Aligned DSM includes nonfinite samples; inspect coverage before using diagnostics.')
    dates={'insights_imagery_date':iso(data['inputs']['insights'].get('imageryDate')),
           'insights_processed_date':iso(data['inputs']['insights'].get('imageryProcessedDate')),
           'raster_imagery_date_retained':raw['photo'].get('imagery_date'),
           'raster_date_evidence_path':'data/inputs.pkl raw.photo.imagery_date; corroborated by raw.warnings',
           'original_source_metadata_in_export':data['inputs'].get('source_metadata'),
           'recovered_cache_source_metadata':cache_row.get('source_metadata') if cache_row else None,
           'recovered_cache_match_verified_by_DSM_sha256':cache_match_verified,
           'recovered_cache_evidence_path':'data/phase1-cache-metadata.json' if cache_metadata else None,
           'raster_capture_date_in_TIFF_tags':None}
    if cache_row and (cache_row['source_metadata']['insights_imagery_date']!=dates['insights_imagery_date'] or cache_row['source_metadata']['raster_imagery_date']!=dates['raster_imagery_date_retained']):
        raise ValueError('Retained imagery dates disagree with matching local cache metadata')
    dates['imagery_date_difference_days']=abs((date.fromisoformat(dates['insights_imagery_date'])-date.fromisoformat(dates['raster_imagery_date_retained'])).days)
    same_headers=all(source_crs[k]==source_crs['rgb'] and source_transforms[k]==source_transforms['rgb'] for k in ['dsm','mask'])
    report={'phase':'cached_house_evidence_only','source_input_sha256':input_hash,'source_rasters':raster_info,'dates':dates,
            'coordinates':{'local_crs':str(crs),'projected_origin_xy_m':[ox,oy],'aligned_shape_height_width':[h,w],
              'aligned_local_corner_affine':list(local)[:6],'aligned_projected_corner_affine':list(world)[:6],
              'pixel_size_m':pixel,'first_pixel_center_local_m':list(center),'first_pixel_center_projected_m':list(world_center),
              'formula':'For OpenCV center index (u,v), local x=0.1*(u+0.5)-11.95, y=-0.1*(v+0.5)+11.75. Projected x=local x+origin_x, projected y=local y+origin_y. Raster corner coordinates use no +0.5.',
              'raw_roof_local_bounds':raw['bounds'],'aligned_bounds':aligned['bounds'],
              'aligned_corner_position_in_RGB_source_corner_grid':list(source_corner_position),
              'center_corner_roundtrip_max_pixel_error':float(max(np.max(np.abs(np.array((~world)*(world*point))-np.array(point))) for point in [(0.,0.),(.5,.5),(w-.5,h-.5),(w,h)])),
              'crop_grid_is_exact_native_pixel_subset':bool(np.allclose(np.array(source_corner_position),np.round(source_corner_position),atol=1e-7)),
              'reprojection_note':'Crop origin is not native-grid aligned; RGB bilinear/DSM bilinear/mask nearest reprojection is required. Do not treat crop indexes as an integer source slice.'},
            'header_georeference_checks':{'raster_CRS_and_affine_equal':same_headers,'all_north_up':all(t.b==0 and t.d==0 for t in source_transforms.values()),
              'projected_CRS_units':[axis.unit_name for axis in crs.axis_info],
              'aligned_RGB_reproduction_max_byte_error':int(np.max(np.abs(rgb.astype(int)-rgb_reproduced.astype(int)))),
              'roof_PNG_matches_aligned_RGB':bool(np.array_equal(png,rgb)),
              'raw_photo_RGB_matches_aligned_RGB':bool(np.array_equal(photo_array[:,:,:3],rgb)),
              'raw_photo_alpha_matches_aligned_valid':bool(np.array_equal(photo_array[:,:,3]>0,aligned['valid'])),
              'aligned_valid_fraction':float(aligned['valid'].mean()),'aligned_DSM_finite_fraction':float(np.isfinite(dsm).mean()),
              'target_mask_overlap_raw_outline_IoU':float((target_mask&roof).sum()/(target_mask|roof).sum()),
              'header_agreement_proves_observable_registration':False},
            'offset_diagnostic':{'applied_correction':False,'registration_verified':False,
              'translation_convention':'Move cached DSM/mask evidence east/north relative to fixed RGB; image sampling delta=(row=-north/pixel,column=east/pixel).',
              'search_range_east_north_m':[-.8,.8],'grid_step_m':.1,'candidate_count_per_metric':289,
              'metric':'Mean nearest RGB Canny-edge distance in metres, clipped at 0.5m; lower is better. Fixed target-building domain and >=98% valid shifted samples.',
              'mask_selection':'Original cached mask component with greatest overlap to raw roof_outline; outline only selects house/domain, never supplies alignment targets.',
              'DSM_selection':'Gaussian sigma0.7px height gradient >=1.5m/m within0.4m of original target mask boundary; fixed before evaluating offsets.',
              'ambiguity_rule':'Report neighboring optimum and runner-up >=0.3m away, plus all offsets within0.01m mean distance of best. These are diagnostic sensitivity summaries, not statistical confidence.',
              'results':diagnostics,
              'interpretation':'Both Canny thresholds favor translating mask/DSM evidence east by0.1-0.2m. Mask optimum north=0m; DSM jump optimum north=-0.3m with broad near-optimal bands. North-axis disagreement and edge-selection confounds prevent a unique validated global shift; do not apply correction.',
              'limitations':['RGB edges include shadows, roof tiles, trees and ground texture; nearest-edge matching can select unrelated edges.',
                'Mask boundaries are sampled at inside pixel centers, not exact continuous outlines. Native0.1m resolution, nearest resampling and finite edge width limit subpixel interpretation.',
                'DSM jump and mask-boundary metrics use related source geometry and are not independent validation.',
                'A global translation cannot identify local parallax, building-height orthorectification errors, rotation, scale, changing roof structures or different capture dates.',
                'A grid optimum is a diagnostic candidate, not permission to shift data. Header agreement alone does not verify object alignment.']},
            'data_issues':issues,'source_warnings':raw.get('warnings',[]),
            'source_fetched_at':data['source_fetched_at'],'expires_at':data['expires_at'],
            'source_expiry_unchanged':True,'input_file_unchanged':hashlib.sha256(input_path.read_bytes()).hexdigest()==input_hash,
            'network_calls':0,'Google_requests':0,'model_runs':0,'reference_labels_used':False,'fitter_outputs_used':False}
    report['elapsed_seconds']=time.perf_counter()-started
    np.savez_compressed(out/'phase1-alignment-fields.npz',rgb=rgb,valid=aligned['valid'],dsm_m=dsm,
                        source_target_mask=target_mask,raw_roof_domain=roof,rgb_edges=rgb_edges,
                        rgb_edges_strict=rgb_edges_strict,rgb_edge_distance_m=distance,
                        mask_boundary=mask_boundary,dsm_jump=dsm_jump,height_gradient_m_per_m=height_gradient,
                        scoring_domain=domain,pixel_size_m=pixel,local_affine=np.array(list(local)[:6]))
    (out/'phase1-alignment.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'dates':dates,'header_checks':report['header_georeference_checks'],'data_issues':issues,
        'offsets':[{k:v for k,v in d.items() if k!='grid_scores'} for d in diagnostics],'elapsed_seconds':report['elapsed_seconds']},indent=2))

if __name__=='__main__':main()
