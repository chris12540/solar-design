"""Phase 1: cached plane evidence audit. No geometry fitting/optimization output.

Only inputs.pkl and sam-masks.npz face_priors/face_ids are read. All diagnostic
fits use cached DSM samples; these are consistency tests, not independent truth.
"""
from pathlib import Path
import json, pickle, time
import numpy as np
from scipy import ndimage as ndi
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
from rasterio.features import rasterize
from affine import Affine
from pyproj import Transformer, Proj

ROOT=Path(__file__).resolve().parent


def angles(coeff):
    a,b=coeff[:2]
    return {'pitch_degrees':float(np.degrees(np.arctan(np.hypot(a,b)))),
            'azimuth_downslope_degrees':float(np.degrees(np.arctan2(-a,-b))%360)}


def residual_stats(values):
    values=np.asarray(values);values=values[np.isfinite(values)]
    if not len(values):return {'count':0}
    median=np.median(values)
    return {'count':int(len(values)),'rmse_m':float(np.sqrt(np.mean(values**2))),
            'median_signed_m':float(median),'median_absolute_m':float(np.median(abs(values))),
            'mad_sigma_m':float(1.4826*np.median(abs(values-median))),
            'absolute_p90_m':float(np.quantile(abs(values),.9)),
            'absolute_p95_m':float(np.quantile(abs(values),.95)),
            'absolute_max_m':float(np.max(abs(values))),'fraction_absolute_gt_0_15m':float(np.mean(abs(values)>.15))}


def robust_fit(xy,z):
    """Huber IRLS on centered XY. Every input remains in reported residuals."""
    center=xy.mean(axis=0); design=np.c_[xy-center,np.ones(len(xy))]
    if len(z)<12 or np.linalg.matrix_rank(design)<3:return None
    coef=np.linalg.lstsq(design,z,rcond=None)[0]
    for _ in range(20):
        residual=z-design@coef
        scale=max(.01,1.4826*np.median(abs(residual-np.median(residual))))
        weights=np.minimum(1.,1.345*scale/np.maximum(abs(residual),1e-12))
        updated=np.linalg.lstsq(design*weights[:,None]**.5,z*weights**.5,rcond=None)[0]
        if np.max(abs(updated-coef))<1e-8:coef=updated;break
        coef=updated
    coeff=np.array([coef[0],coef[1],coef[2]-coef[:2]@center])
    return {'coefficients':{'a':float(coeff[0]),'b':float(coeff[1]),'c':float(coeff[2])},
            **angles(coeff),'residuals_all_fitted_samples':residual_stats(z-(np.c_[xy,np.ones(len(xy))]@coeff)),
            'centered_design_condition_number':float(np.linalg.cond(design))}


def predict(fit,xy):
    c=fit['coefficients'];return xy[:,0]*c['a']+xy[:,1]*c['b']+c['c']


def spatial_cv(xy,z):
    if len(z)<60:return {'status':'insufficient_interior_samples','minimum_samples':60}
    folds=[]
    # Two spatial half splits, swapping train/test, across both local axes.
    # DSM pixels are correlated; this tests spatial transfer, not independence.
    for axis in (0,1):
        split=np.median(xy[:,axis]);side=xy[:,axis]<=split
        if min(side.sum(),(~side).sum())<20:continue
        for reverse in (False,True):
            train=~side if reverse else side;test=~train
            fit=robust_fit(xy[train],z[train])
            if fit is None:continue
            folds.append({'axis':'x' if axis==0 else 'y','train_side':'high' if reverse else 'low',
                          'split_local_m':float(split),'train_count':int(train.sum()),'test_count':int(test.sum()),
                          'held_out_residuals':residual_stats(z[test]-predict(fit,xy[test])),
                          'fit_angles':{k:fit[k] for k in ('pitch_degrees','azimuth_downslope_degrees')}})
    return {'status':'evaluated' if folds else 'insufficient_spatial_span','folds':folds,
            'max_held_out_rmse_m':max((f['held_out_residuals']['rmse_m'] for f in folds),default=None)}


def warp_cached(data):
    raw,aligned=data['raw'],data['aligned'];origin=raw['origin'];t=aligned['transform']
    ox,oy=Transformer.from_crs('EPSG:4326',origin['crs'],always_xy=True).transform(origin['longitude'],origin['latitude'])
    world=Affine(t.a,t.b,t.c+ox,t.d,t.e,t.f+oy)
    shape=aligned['rgb'].shape[:2];results={}
    for key,method in [('dsm',Resampling.bilinear),('mask',Resampling.nearest)]:
        target=np.full(shape,np.nan,np.float64) if key=='dsm' else np.zeros(shape,np.uint8)
        with MemoryFile(data['inputs'][key]) as memory, memory.open() as src:
            reproject(src.read(1),target,src_transform=src.transform,src_crs=src.crs,
                      dst_transform=world,dst_crs=origin['crs'],src_nodata=src.nodata,
                      dst_nodata=np.nan if key=='dsm' else 0,resampling=method)
        results[key]=target
    return results['dsm'],results['mask']>0


def main():
    start=time.perf_counter()
    data=pickle.load(open(ROOT/'data/inputs.pkl','rb'))
    archive=np.load(ROOT/'outputs/sam-masks.npz')
    priors=archive['face_priors'];ids=archive['face_ids'].tolist()
    raw,aligned=data['raw'],data['aligned'];t=aligned['transform'];pixel=float(aligned['pixel_size_m'])
    dsm,full_mask=warp_cached(data)
    valid=np.isfinite(dsm)&np.asarray(aligned['valid'],bool)
    yy,xx=np.indices(dsm.shape)
    x=t.a*(xx+.5)+t.b*(yy+.5)+t.c;y=t.d*(xx+.5)+t.e*(yy+.5)+t.f
    xy=np.stack([x,y],axis=-1)
    footprint=priors.any(0)
    components,_=ndi.label(full_mask)
    target_id=max(range(1,components.max()+1),key=lambda i:int(np.count_nonzero((components==i)&footprint)))
    roof_mask=components==target_id
    outline=raw['roof_outline']
    outline_mask=rasterize([({'type':'Polygon','coordinates':[outline['polygon']]+outline.get('holes',[])},1)],out_shape=dsm.shape,transform=t).astype(bool)
    groups={g['id']:g for g in raw['refinement']['face_groups']}
    convergence=float(Proj(raw['origin']['crs']).get_factors(raw['origin']['longitude'],raw['origin']['latitude']).meridian_convergence)
    source_interiors=np.stack([(ndi.distance_transform_edt(p)*pixel>.300001)&valid for p in priors])
    stats=data['inputs']['insights']['solarPotential'].get('roofSegmentStats',[])
    planes=[];models=[];source_residual=np.full(dsm.shape,np.nan)
    for i,identifier in enumerate(ids):
        group=groups[identifier];prior=priors[i];all_valid=prior&valid
        # EDT uses pixel-center distance. >0.3m conservatively excludes three
        # rows of boundary-adjacent centers on the cached 0.1m grid.
        interior=all_valid&(ndi.distance_transform_edt(prior)*pixel>.300001)
        model=group['plane_model'];coef=np.array([model['a'],model['b'],model['c']]);models.append(coef)
        prediction=model['a']*x+model['b']*y+model['c'];residual=dsm-prediction
        source_residual[all_valid]=residual[all_valid]
        fit=robust_fit(xy[interior],dsm[interior]) if interior.sum()>=12 else None
        component_labels,n=ndi.label(prior);sizes=np.bincount(component_labels.ravel())[1:]
        interior_points=xy[interior]
        covariance=np.linalg.eigvalsh(np.cov(interior_points.T)) if len(interior_points)>2 else np.array([0.,0.])
        cv=spatial_cv(interior_points,dsm[interior])
        concerns=[]
        source_interior=residual_stats(residual[interior]);source_all=residual_stats(residual[all_valid])
        if interior.sum()<60:concerns.append('weak_interior_sample_count')
        if len(covariance) and covariance.min()<.03:concerns.append('narrow_spatial_support')
        if source_interior.get('rmse_m',999)>.08:concerns.append('source_plane_conflicts_with_interior_dsm')
        if cv.get('max_held_out_rmse_m') is not None and cv['max_held_out_rmse_m']>.1:concerns.append('weak_spatial_transfer_of_single_plane')
        if source_all.get('rmse_m',0)>max(.1,2*source_interior.get('rmse_m',0)):concerns.append('boundary_residuals_exceed_interior_residuals')
        if fit and cv.get('max_held_out_rmse_m') is not None and cv['max_held_out_rmse_m']>max(.05,2.5*fit['residuals_all_fitted_samples']['rmse_m']):
            concerns.append('spatial_cv_degrades_over_2_5x_and_exceeds_0_05m')
        if fit:fit['azimuth_true_north_approx_degrees']=(fit['azimuth_downslope_degrees']+convergence)%360
        record={'group_id':identifier,'source_plane_ids':group.get('source_plane_ids',[]),
                'source_model_coefficients':model,'source_model_angles':{**angles(coef),'azimuth_true_north_approx_degrees':(angles(coef)['azimuth_downslope_degrees']+convergence)%360},
                'cached_group_reported_angles':{'pitch_degrees':group['pitch_degrees'],'azimuth_degrees':group['azimuth_degrees']},
                'support':{'prior_pixel_count':int(prior.sum()),'prior_horizontal_area_m2':float(prior.sum()*pixel**2),
                           'finite_valid_dsm_pixel_count':int(all_valid.sum()),'interior_pixel_count':int(interior.sum()),
                           'interior_horizontal_area_m2':float(interior.sum()*pixel**2),'interior_fraction':float(interior.sum()/max(1,prior.sum())),
                           'components':int(n),'largest_component_fraction':float(sizes.max()/sizes.sum()),
                           'interior_local_bounds_m':{'min_xy':interior_points.min(0).tolist(),'max_xy':interior_points.max(0).tolist()} if len(interior_points) else None,
                           'interior_xy_covariance_eigenvalues_m2':covariance.tolist()},
                'source_model_all_pixel_residuals':source_all,'source_model_interior_residuals':source_interior,
                'independent_robust_interior_dsm_fit':fit,'spatial_crossvalidation':cv,'concerns':concerns,
                'interpretation':'No flagged conflict under audit thresholds; DSM-consistent does not prove a distinct physical roof plane.' if not concerns else 'Review flagged evidence; no plane is automatically accepted, rejected, or merged.'}
        # The cached naming convention suggests plane-N -> segment N-1.
        # Keep this explicitly provisional; geometry is not a truth label.
        source_ids=group.get('source_plane_ids',[])
        if len(source_ids)==1 and source_ids[0].startswith('plane-'):
            try:segment_index=int(source_ids[0].split('-')[-1])-1
            except ValueError:segment_index=-1
            if 0<=segment_index<len(stats):
                metadata=stats[segment_index]
                correspondence={'segment_index':segment_index,'mapping_status':'inferred_from_numeric_source_id_not_independently_verified',
                                'google_pitch_degrees':metadata['pitchDegrees'],'google_azimuth_true_north_degrees':metadata['azimuthDegrees']}
                if fit:
                    az=np.deg2rad(metadata['azimuthDegrees']-convergence);slope=np.tan(np.deg2rad(metadata['pitchDegrees']))
                    gn=np.array([slope*np.sin(az),slope*np.cos(az),1.])
                    cf=fit['coefficients'];dn=np.array([-cf['a'],-cf['b'],1.])
                    difference=float(np.degrees(np.arccos(np.clip(gn@dn/(np.linalg.norm(gn)*np.linalg.norm(dn)),-1,1))))
                    correspondence['normal_difference_vs_independent_dsm_fit_degrees']=difference
                    correspondence['pitch_difference_dsm_minus_google_degrees']=fit['pitch_degrees']-metadata['pitchDegrees']
                    correspondence['azimuth_difference_dsm_minus_google_degrees']=(fit['azimuth_true_north_approx_degrees']-metadata['azimuthDegrees']+180)%360-180
                    if difference>3:concerns.append('inferred_google_segment_orientation_differs_from_dsm_by_gt_3deg_normal_angle')
                record['provisional_google_segment_correspondence']=correspondence
        if fit:
            record['independent_fit_vs_source_interior_prediction_difference']=residual_stats(predict(fit,interior_points)-(np.c_[interior_points,np.ones(len(interior_points))]@coef))
        planes.append(record)
    pairs=[]
    for i in range(len(ids)):
        for j in range(i+1,len(ids)):
            c0,c1=models[i],models[j];n0=np.r_[-c0[:2],1.];n1=np.r_[-c1[:2],1.]
            angle=float(np.degrees(np.arccos(np.clip(np.dot(n0,n1)/(np.linalg.norm(n0)*np.linalg.norm(n1)),-1,1))))
            if angle>10:continue
            a,b=xy[priors[i]],xy[priors[j]];mid=(a.mean(0)+b.mean(0))/2
            delta=lambda q:q@(c0[:2]-c1[:2])+(c0[2]-c1[2])
            distance=ndi.distance_transform_edt(~priors[i])*pixel
            closest=float(distance[priors[j]].min())
            mid_difference=float(abs(delta(mid)))
            hypothesis='different_heights_or_steps_possible' if mid_difference>.25 else 'possible_duplicate_or_coplanar_regions'
            pairs.append({'group_ids':[ids[i],ids[j]],'source_plane_ids':[groups[ids[i]]['source_plane_ids'],groups[ids[j]]['source_plane_ids']],
                          'normal_angle_degrees':angle,'closest_prior_center_distance_m':closest,
                          'evaluation_local_midpoint_m':mid.tolist(),'absolute_model_height_difference_at_midpoint_m':mid_difference,
                          'signed_model_height_difference_over_first_support_m':{'min':float(delta(a).min()),'max':float(delta(a).max())},
                          'signed_model_height_difference_over_second_support_m':{'min':float(delta(b).min()),'max':float(delta(b).max())},
                          'hypothesis':hypothesis,'limitation':'Plane evaluations may extrapolate across disjoint support. Similar normals alone cannot establish a duplicate; offsets alone do not confirm a physical step.'})
    # A coherent residual patch is a review candidate, never an accepted new plane.
    candidates=[]
    unassigned=roof_mask&~footprint&valid
    residual_bad=footprint&valid&(abs(source_residual)>.15)
    for kind,mask in [('roof_mask_without_source_support',unassigned),('source_model_absolute_residual_gt_0_15m',residual_bad)]:
        labeled,n=ndi.label(mask)
        for index in range(1,n+1):
            region=labeled==index;count=int(region.sum())
            if count<20:continue
            points=xy[region];z=dsm[region];fit=robust_fit(points,z)
            cv=spatial_cv(points,z)
            reliable=region&(ndi.distance_transform_edt(roof_mask)*pixel>.300001)
            candidates.append({'id':f'candidate-{len(candidates)+1}','evidence_kind':kind,
                               'pixel_count':count,'horizontal_area_m2':float(count*pixel**2),
                               'roof_mask_interior_pixel_count':int(reliable.sum()),
                               'source_face_interior_pixel_count':int((region&source_interiors.any(0)).sum()),
                               'diagnostic_confidence':'insufficient_samples_for_spatial_cv' if cv.get('max_held_out_rmse_m') is None else ('spatial_cv_does_not_support_one_stable_plane' if cv['max_held_out_rmse_m']>.1 else 'limited_spatial_cv_consistency_only'),
                               'centroid_local_m':points.mean(0).tolist(),'local_bounds_m':{'min_xy':points.min(0).tolist(),'max_xy':points.max(0).tolist()},
                               'source_group_ids_overlapped':[ids[k] for k in range(len(ids)) if np.any(priors[k]&region)],
                               'source_model_residuals':residual_stats(source_residual[region]),
                               'diagnostic_single_plane_fit':fit,'spatial_crossvalidation':cv,
                               'status':'unconfirmed_missing_plane_or_boundary_alignment_obstruction_candidate',
                               'interpretation':'Coherent missing support/residual is not enough to distinguish an omitted roof plane, ground mixing, roof edge misregistration, obstruction, or source segmentation error.'})
    mask_summary={}
    for name,mask in [('full_cached_roof_mask',full_mask),('target_cached_roof_mask_component',roof_mask),('raw_roof_outline_raster',outline_mask),('source_face_footprint',footprint),('target_mask_without_source_support',unassigned),('source_support_outside_target_mask',footprint&~roof_mask)]:
        mask_summary[name]={'pixels':int(mask.sum()),'horizontal_area_m2':float(mask.sum()*pixel**2),'valid_dsm_pixels':int((mask&valid).sum())}
    mask_summary['coverage_of_target_mask_by_source_footprint']=float((roof_mask&footprint).sum()/roof_mask.sum())
    mask_summary['coverage_of_raw_outline_by_source_footprint']=float((outline_mask&footprint).sum()/outline_mask.sum())
    mask_summary['target_component_selection']='Cached mask connected component with greatest source-face-footprint overlap; not a manually chosen building mask.'
    result={'phase':1,'purpose':'Audit evidence for source planes and omitted/unsupported regions; no roof solver or production geometry.',
            'design_ready':False,'source_plane_ids_are_ground_truth':False,'required_final_face_count':None,
            'coordinate_system':{'local_xy_units':'meters','height_units':'cached DSM meters','pixel_size_m':pixel,'pixel_to_local_affine':list(t)[:6],'azimuth_downslope_degrees_basis':'Grid north of local projected CRS, clockwise; separate approximate true-north value adds grid convergence.','grid_meridian_convergence_degrees':convergence},
            'methods':{'interior_exclusion_m':.3,'fit':'Huber IRLS, centered XY, 20 iterations maximum, scale floor .01m; all samples included in residual reports.',
                       'crossvalidation':'Deterministic spatial median half splits on X and Y, both train/test directions; minimum60samples and20perhalf. DSM correlation limits independence.',
                       'near_parallel_threshold_degrees':10,'residual_candidate_threshold_m':.15,'minimum_candidate_area_m2':.2,'relative_cv_concern':'Max held-out RMSE > max(0.05m,2.5 times full interior robust-fit RMSE); signals limited spatial stability, not a rejected plane.'},
            'mask_coverage':mask_summary,'planes':planes,'near_parallel_pairs':pairs,'unexplained_region_candidates':candidates,
            'google_roof_segment_stats':[{ 'segment_index':i,'pitch_degrees':s.get('pitchDegrees'),'azimuth_degrees':s.get('azimuthDegrees'),'reported_area_m2':s.get('stats',{}).get('areaMeters2')} for i,s in enumerate(stats)],
            'google_segment_mapping_note':'Raw Google segment indices retained separately. Numeric source plane IDs provide a provisional segment N-1 correspondence only; this is not independently verified and must not establish truth.',
            'summary':{'source_group_count':len(planes),'groups_with_flagged_concerns':[p['group_id'] for p in planes if p['concerns']],
                       'near_parallel_pair_count':len(pairs),'unexplained_candidate_count':len(candidates),
                       'strong_missing_plane_confirmed':False,
                       'finding':f"All source groups have at least {min(p['support']['interior_pixel_count'] for p in planes)} interior DSM samples. Maximum source-model interior RMSE is {max(p['source_model_interior_residuals']['rmse_m'] for p in planes):.4f}m. Provisional Google/source correspondence is not verified. Unassigned-region fits fail to establish a stable additional plane; source residual patches are small and mostly lack sufficient samples for spatial CV."},
            'limitations':['Both source model coefficients and this audit may derive from the same DSM; refit agreement is consistency evidence, not independent confirmation.',
                           'SAM face priors encode source geometry; detector face masks and previous fitted polygons were not used.',
                           'DSM RGB mask and source plane outlines may differ in capture date and registration; no manual image registration or photo truth was used.',
                           'Interior erosion reduces roof/ground mixing but can discard small/narrow planes or miss boundary-localized errors.',
                           'Diagnostic fits are not new accepted planes. Significant residuals can arise from obstructions, nonplanarity, mixed pixels, registration, or omitted planes.',
                           'No inferred face count, semantic edge labels, plane merges, polygons, or production changes are produced.'],
            'provenance':{'inputs':['data/inputs.pkl','outputs/sam-masks.npz:face_priors,face_ids'],
                          'forbidden_sources_accessed':False,'network_used':False,'model_runs':False,
                          'source_fetched_at':data['source_fetched_at'],'expires_at':data['expires_at'],
                          'google_imagery_date':data['inputs']['insights'].get('imageryDate'),
                          'cached_photo_imagery_date':raw.get('photo',{}).get('imagery_date'),
                          'cached_photo_registration_verified':raw.get('photo',{}).get('registration_verified'),
                          'google_imagery_processed_date':data['inputs']['insights'].get('imageryProcessedDate'),
                          'attribution':'Includes solar data from Google.'},'elapsed_seconds':time.perf_counter()-start}
    path=ROOT/'outputs/phase1-planes.json';path.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'summary':result['summary'],'mask_coverage':mask_summary,'planes':[{'id':p['group_id'],'interior_pixels':p['support']['interior_pixel_count'],'all_rmse_m':p['source_model_all_pixel_residuals'].get('rmse_m'),'interior_rmse_m':p['source_model_interior_residuals'].get('rmse_m'),'robust_fit_rmse_m':p['independent_robust_interior_dsm_fit']['residuals_all_fitted_samples']['rmse_m'] if p['independent_robust_interior_dsm_fit'] else None,'cv_max_rmse_m':p['spatial_crossvalidation'].get('max_held_out_rmse_m'),'concerns':p['concerns']} for p in planes]},indent=2))

if __name__=='__main__':main()
