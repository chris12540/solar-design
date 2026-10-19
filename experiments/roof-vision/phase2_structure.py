"""Finite structural roof hypotheses from cached planes and image/DSM evidence.

No source contour simplification: main roofs are analytic gables, lower roofs
are bounded primitive boxes clipped by supported analytic plane intersections.
All source groups are evidence, never a required final face count.
"""
from pathlib import Path
import itertools,json,pickle,time
import numpy as np
from scipy import ndimage as ndi
from shapely.geometry import Polygon,Point,LineString,MultiPoint,mapping,shape
from shapely.ops import unary_union
from rasterio.features import rasterize
from affine import Affine
from phase1_planes import warp_cached,residual_stats
ROOT=Path(__file__).resolve().parent


def coefficients(model):return np.array([model[k] for k in ('a','b','c')],float)
def polygons(geom):
    if geom.is_empty:return []
    if geom.geom_type=='Polygon':return [geom]
    return [p for p in getattr(geom,'geoms',[]) if p.geom_type=='Polygon' and p.area>1e-6]
def primitive_ring(ring):
    # Remove numerical collinear cut/junction vertices only; this changes no
    # primitive line, boundary, corner location, or roof footprint.
    points=[np.asarray(p,float) for p in list(ring)[:-1]]
    changed=True
    while changed and len(points)>3:
        changed=False;keep=[]
        for i,p in enumerate(points):
            a=p-points[i-1];b=points[(i+1)%len(points)]-p
            cross=abs(a[0]*b[1]-a[1]*b[0])
            if cross<1e-10*max(1.,np.linalg.norm(a)*np.linalg.norm(b)) and a@b>=0:changed=True
            else:keep.append(p)
        points=keep
    return [p.tolist() for p in points+[points[0]]]
def parts(geom):return [{'polygon':primitive_ring(p.exterior.coords),'holes':[primitive_ring(r.coords) for r in p.interiors]} for p in polygons(geom)]
def part_geometry(records):return unary_union([Polygon(p['polygon'],p.get('holes',[])) for p in records])
def bounds_polygon(n,d,u0,u1,v0,v1):return Polygon([n*u+d*v for u,v in [(u0,v0),(u1,v0),(u1,v1),(u0,v1)]])
def plane_z(model,xy):return xy[...,0]*model['a']+xy[...,1]*model['b']+model['c']


def analytic_gable(first,second,across_bounds,longitudinal_bounds):
    delta=coefficients(first)-coefficients(second)
    if np.linalg.norm(delta[:2])<1e-6:raise ValueError('Opposed distinct planes required')
    n=delta[:2]/np.linalg.norm(delta[:2]);d=np.array([-n[1],n[0]])
    u=-delta[2]/np.linalg.norm(delta[:2]);u0,u1=across_bounds;v0,v1=longitudinal_bounds
    if not u0<u<u1 or not 0<v1-v0<30 or not 0<u1-u0<30:raise ValueError('Finite supported gable bounds required')
    first_polygon=bounds_polygon(n,d,u0,u,v0,v1);second_polygon=bounds_polygon(n,d,u,u1,v0,v1)
    return first_polygon,second_polygon,{'normal':n.tolist(),'longitudinal_axis':d.tolist(),'ridge_across_m':float(u),'ridge_endpoints':[(n*u+d*v).tolist() for v in (v0,v1)]}


def cut_parent_surface(parent,footprint,children):
    """Child footprint occludes parent even where child geometry is unresolved."""
    footprint=footprint.buffer(0)
    visible_parent=parent.difference(footprint)
    visible_children=[p.intersection(footprint) for p in children]
    return visible_parent,visible_children


def dominant_pair(groups,priors):
    choices=[]
    for i,j in itertools.combinations(range(len(groups)),2):
        a,b=coefficients(groups[i]['plane_model']),coefficients(groups[j]['plane_model'])
        slope0,slope1=a[:2],b[:2]
        opposition=float(slope0@slope1/max(1e-8,np.linalg.norm(slope0)*np.linalg.norm(slope1)))
        distance=float(ndi.distance_transform_edt(~priors[i])[priors[j]].min())
        if opposition<-.8 and distance<=4:
            choices.append((float(priors[i].sum()+priors[j].sum()),i,j,opposition))
    if not choices:raise ValueError('No supported opposed dominant plane pair')
    _,i,j,opposition=max(choices)
    # Positive across normal follows the first plane's uphill direction.
    if coefficients(groups[i]['plane_model'])[0]<coefficients(groups[j]['plane_model'])[0]:i,j=j,i
    return i,j,opposition


def weighted_median(values,weights):
    order=np.argsort(values);v=np.asarray(values)[order];w=np.asarray(weights)[order]
    return float(v[np.searchsorted(np.cumsum(w),w.sum()/2)])


def structural_line_bounds(lines,n,d,estimated):
    support={k:[] for k in ('west','east','bottom','top')}
    for line in lines:
        if not line.get('classical_context_selected'):continue
        xy=np.asarray(line['local_xy_m'],float)
        delta=xy[1]-xy[0];length=float(np.linalg.norm(delta))
        if length<.8:continue
        along=abs(delta@d)/length;cross=abs(delta@n)/length
        uv=np.c_[xy@n,xy@d];mean=uv.mean(0)
        names=('west','east') if along>np.cos(np.deg2rad(12)) else (('bottom','top') if cross>np.cos(np.deg2rad(12)) else ())
        for key in names:
            axis=0 if key in ('west','east') else 1
            if abs(mean[axis]-estimated[key])>.8:continue
            # Finite source support in the other direction, not remote line extensions.
            if axis==0 and (mean[1]<estimated['bottom']-.5 or mean[1]>estimated['top']+.5):continue
            if axis==1 and (mean[0]<estimated['west']-.5 or mean[0]>estimated['east']+.5):continue
            support[key].append({'id':line['id'],'coordinate_m':float(mean[axis]),'length_m':length,
                                 'classical':True,'learned_agreement':bool(line.get('learned_filtered_selected')),
                                 'height_fold_or_step':bool(line.get('dsm_evidence',{}).get('fold_or_step_evidence'))})
    fitted={k:weighted_median([p['coordinate_m'] for p in v],[p['length_m'] for p in v]) if v else estimated[k] for k,v in support.items()}
    return fitted,support


def clip_halfplane(geometry,normal,offset,positive):
    """Finite clipping rectangle around existing bounds; never extends geometry."""
    normal=np.asarray(normal,float);norm=np.linalg.norm(normal)
    if norm<1e-8:return geometry
    normal=normal/norm;offset=offset/norm;direction=np.array([-normal[1],normal[0]])
    bounds=geometry.bounds
    corners=np.array([(bounds[0],bounds[1]),(bounds[2],bounds[1]),(bounds[2],bounds[3]),(bounds[0],bounds[3])])
    p0,p1=(corners@direction).min()-1,(corners@direction).max()+1
    q0,q1=(corners@normal).min()-1,(corners@normal).max()+1
    q0=max(q0,-offset) if positive else q0;q1=q1 if positive else min(q1,-offset)
    if q1<=q0:return Polygon()
    return geometry.intersection(bounds_polygon(normal,direction,q0,q1,p0,p1))


def source_exclusions(raw):
    """Established source holes/separate outlines; unverified obstructions are markers."""
    return [Polygon(ring) for ring in raw['roof_outline'].get('holes',[])]


def raster(geom,shape_,transform):
    if geom.is_empty:return np.zeros(shape_,bool)
    return rasterize([(mapping(geom),1)],out_shape=shape_,transform=transform).astype(bool)


def evaluate_faces(faces,xy,dsm,valid,transform,roof_mask,source_footprint,pixel):
    assigned=np.zeros(roof_mask.shape,bool);errors=[];interior_errors=[];per_face=[]
    for face in faces:
        geom=part_geometry(face['parts']);mask=raster(geom,roof_mask.shape,transform)
        finite=mask&valid;residual=dsm-plane_z(face['plane_model'],xy)
        interior=finite&(ndi.distance_transform_edt(mask)*pixel>.300001)
        errors.extend(residual[finite].tolist());interior_errors.extend(residual[interior].tolist())
        per_face.append({'id':face['id'],'horizontal_area_m2':float(geom.area),
                         'sloped_physical_area_m2':float(geom.area*np.sqrt(1+face['plane_model']['a']**2+face['plane_model']['b']**2)),
                         'full_height_residuals':residual_stats(residual[finite]),'interior_height_residuals':residual_stats(residual[interior]),
                         'area_usability':'unknown; structural capacity, AHJ setbacks, fire access, obstructions, and system design not assessed'})
        assigned|=mask
    roof_valid=roof_mask&valid
    geoms=[part_geometry(f['parts']) for f in faces]
    return {'assigned_horizontal_area_m2':float(unary_union(geoms).area) if geoms else 0.,
            'assigned_target_mask_pixels':int((assigned&roof_mask).sum()),
            'unexplained_target_mask_pixels':int((roof_mask&~assigned).sum()),
            'unexplained_target_mask_horizontal_area_m2':float((roof_mask&~assigned).sum()*pixel**2),
            'coverage_of_cached_target_roof_mask':float((assigned&roof_mask).sum()/max(1,roof_mask.sum())),
            'coverage_of_source_face_footprint':float((assigned&source_footprint).sum()/max(1,source_footprint.sum())),
            'assigned_outside_target_mask_horizontal_area_m2':float((assigned&~roof_mask).sum()*pixel**2),
            'visible_face_overlap_area_m2':float(max(0,sum(g.area for g in geoms)-unary_union(geoms).area)) if geoms else 0.,
            'full_height_residuals':residual_stats(errors),'interior_height_residuals':residual_stats(interior_errors),'per_face':per_face}


def make_face(identifier,group_ids,model,geom,role,level,status='candidate'):
    face={'id':identifier,'source_group_ids':group_ids,'plane_model':model,'parts':parts(geom),
          'role':role,'level_id':level,'hypothesis_status':status,'usable_area_status':'unknown'}
    if role=='main_roof':
        face['supporting_parts']=parts(geom)
        face['supporting_parts_purpose']='Uncut primitive body footprint for wall presentation only; hidden roof surface is excluded from parts and all exposed-area calculations.'
    return face


def main_candidates(groups,priors,xy,lines,dsm,valid,transform,roof_mask,pixel):
    i,j,opposition=dominant_pair(groups,priors)
    first,second=groups[i],groups[j];delta=coefficients(first['plane_model'])-coefficients(second['plane_model'])
    n=delta[:2]/np.linalg.norm(delta[:2]);d=np.array([-n[1],n[0]])
    points=xy[priors[i]|priors[j]];uv=np.c_[points@n,points@d]
    row_bounds=[]
    bins=np.floor(uv[:,1]/.3)
    for value in np.unique(bins):
        row=uv[bins==value]
        if len(row)<20:continue
        row_bounds.append([row[:,0].min(),row[:,0].max()])
    rows=np.asarray(row_bounds)
    estimated={'west':float(np.quantile(rows[:,0],.25)),'east':float(np.median(rows[:,1])),
               'bottom':float(np.quantile(uv[:,1],.001)-pixel/2),'top':float(np.quantile(uv[:,1],.999)+pixel/2)}
    detected,line_support=structural_line_bounds(lines,n,d,estimated)
    # Support and image evidence are alternatives; no fit assumes either is truth.
    proposals=[('support_rectangle',estimated),('detected_edge_rectangle',detected),
               ('blended_supported_rectangle',{k:(estimated[k]+detected[k])/2 for k in estimated})]
    records=[];all_candidates=[];pairmask=priors[i]|priors[j]
    for identifier,bounds in proposals:
        left,right,frame=analytic_gable(first['plane_model'],second['plane_model'],(bounds['west'],bounds['east']),(bounds['bottom'],bounds['top']))
        faces=[make_face('main-'+first['id'],[first['id']],first['plane_model'],left,'main_roof','main-level'),
               make_face('main-'+second['id'],[second['id']],second['plane_model'],right,'main_roof','main-level')]
        quality=evaluate_faces(faces,xy,dsm,valid,transform,roof_mask,pairmask,pixel)
        footprint=left.union(right);mask=raster(footprint,roof_mask.shape,transform)
        coverage=float((mask&pairmask).sum()/pairmask.sum())
        # DSM compare on reliable source interiors: child/occluded regions remain
        # separately reported in full coverage, not used to force contour edges.
        source_errors=[]
        for index,geom in [(i,left),(j,right)]:
            reliable=priors[index]&(ndi.distance_transform_edt(priors[index])*pixel>.300001)&valid&raster(geom,roof_mask.shape,transform)
            source_errors.extend((dsm-plane_z(groups[index]['plane_model'],xy))[reliable].tolist())
        interior=residual_stats(source_errors).get('rmse_m',1.)
        line_offsets=[]
        for key,evidence in line_support.items():
            for line in evidence:line_offsets.extend([abs(bounds[key]-line['coordinate_m'])]*max(1,round(line['length_m'])))
        line_error=float(np.mean(line_offsets)) if line_offsets else 0.
        spill=float((mask&~roof_mask).sum()/max(1,mask.sum()))
        score=4*(1-coverage)+spill+2*interior+.25*line_error
        record={'id':identifier,'description':'Finite analytic gable with common ridge and straight parallel eaves/cross eaves.',
                'bounds_in_ridge_frame_m':bounds,'scores':{'lower_is_better':score,'source_pair_coverage':coverage,
                 'outside_cached_roof_mask_fraction':spill,'reliable_source_interior_rmse_m':interior,'mean_supported_line_offset_m':line_error,
                 'all_candidate_surface_full_height_rmse_m':quality['full_height_residuals'].get('rmse_m')},
                'assumptions':['Two dominant opposed source models describe one upper gable.','A common rectangular plan is a structural hypothesis; dormer cutouts and lower roofs are separate.'],
                'selected':False,'roof_face_ids':[f['id'] for f in faces],'roof_faces':faces}
        records.append(record);all_candidates.append((score,faces,frame))
    selected=int(np.argmin([x[0] for x in all_candidates]));records[selected]['selected']=True
    return all_candidates[selected][1],records,all_candidates[selected][2],(i,j),line_support


def lower_primitives(groups,priors,xy,lines,excluded_indices,main_faces,dsm,valid,transform,pixel):
    main_geom=unary_union([part_geometry(f['parts']) for f in main_faces]);accepted=[];evidence=[]
    for i,group in enumerate(groups):
        if i in excluded_indices:continue
        source=priors[i];points=xy[source];interior=source&(ndi.distance_transform_edt(source)*pixel>.300001)
        reliable=xy[interior&valid]
        if len(reliable)<30:
            evidence.append({'source_group_id':group['id'],'status':'unresolved_insufficient_interior'});continue
        # Primitive directions come from actual selected photo lines near support,
        # plus principal support direction. No contour is traced or simplified.
        centered=reliable-reliable.mean(0);_,vectors=np.linalg.eigh(centered.T@centered)
        directions=[vectors[:,-1]]
        for line in lines:
            if not line.get('classical_context_selected') or line['length_m']<1.:continue
            p=np.asarray(line['local_xy_m']);mid=p.mean(0)
            if np.linalg.norm(reliable-mid,axis=1).min()>.8:continue
            v=p[1]-p[0];directions.append(v/np.linalg.norm(v))
        choices=[]
        for direction in directions:
            direction=direction/np.linalg.norm(direction);cross=np.array([-direction[1],direction[0]])
            uv=np.c_[points@cross,points@direction]
            lo=np.quantile(uv,.005,axis=0)-pixel/2;hi=np.quantile(uv,.995,axis=0)+pixel/2
            box=bounds_polygon(cross,direction,lo[0],hi[0],lo[1],hi[1])
            if box.area>2.5*source.sum()*pixel**2 or box.area<.5:continue
            # Adjacent distinct planes only propose finite separating cuts when a
            # detected height-supported fold agrees with their analytic seam.
            cuts=[]
            for j,other in enumerate(groups):
                if j==i or j in excluded_indices:continue
                distance=ndi.distance_transform_edt(~priors[j])*pixel
                if distance[source].min()>.35:continue
                delta=coefficients(group['plane_model'])-coefficients(other['plane_model'])
                if np.linalg.norm(delta[:2])<.1:continue
                seam_normal=delta[:2]/np.linalg.norm(delta[:2]);seam_offset=delta[2]/np.linalg.norm(delta[:2])
                line_ids=[]
                for line in lines:
                    if not line.get('classical_context_selected') or not line.get('dsm_evidence',{}).get('fold_or_step_evidence'):continue
                    lp=np.asarray(line['local_xy_m']);v=lp[1]-lp[0]
                    if abs(v@seam_normal)/np.linalg.norm(v)>.15:continue
                    if np.max(abs(lp@seam_normal+seam_offset))>.2:continue
                    if np.linalg.norm(reliable-lp.mean(0),axis=1).min()>1.5:continue
                    line_ids.append(line['id'])
                boundary_support=source&(distance<=.35)&valid
                boundary_model_difference=np.abs(plane_z(group['plane_model'],xy)-plane_z(other['plane_model'],xy))[boundary_support]
                c0,c1=coefficients(group['plane_model']),coefficients(other['plane_model'])
                normals=[np.r_[-c[:2],1.] for c in (c0,c1)]
                fold_angle=np.degrees(np.arccos(np.clip(np.dot(*normals)/(np.linalg.norm(normals[0])*np.linalg.norm(normals[1])),-1,1)))
                dsm_fold_supported=len(boundary_model_difference)>=10 and np.median(boundary_model_difference)<.25 and fold_angle>8
                if not line_ids and not dsm_fold_supported:continue
                signed=reliable@seam_normal+seam_offset
                if max(np.mean(signed>=0),np.mean(signed<=0))<.8:continue
                cuts.append((seam_normal,seam_offset,np.median(signed)>=0,line_ids,other['id'],float(np.median(boundary_model_difference)) if len(boundary_model_difference) else None))
            candidates=[(box,[])]
            for cut in cuts:
                for existing,ids in list(candidates):
                    clipped=clip_halfplane(existing,*cut[:3])
                    if not clipped.is_empty and clipped.area>=.35*source.sum()*pixel**2:candidates.append((clipped,ids+[{'other_group_id':cut[4],'line_ids':cut[3],'adjacent_source_model_height_difference_median_m':cut[5]}]))
            for candidate,cuts_used in candidates:
                # Upper roof occludes lower roofs; retain height step, never weld.
                candidate=candidate.difference(main_geom)
                if candidate.is_empty:continue
                mask=raster(candidate,source.shape,transform)
                recall=float((mask&source).sum()/source.sum())
                spill=float((mask&~source).sum()/max(1,mask.sum()))
                valid_interior=mask&valid&(ndi.distance_transform_edt(mask)*pixel>.300001)
                error=residual_stats((dsm-plane_z(group['plane_model'],xy))[valid_interior]).get('rmse_m',2.)
                if recall<.55 or spill>.5:continue
                score=3*(1-recall)+1.5*spill+min(error,2)*2+.015*sum(len(p.exterior.coords)-1 for p in polygons(candidate))
                choices.append((score,candidate,{'source_recall':recall,'outside_source_fraction':spill,'interior_rmse_m':error,'supported_analytic_cuts':cuts_used}))
        if not choices:
            evidence.append({'source_group_id':group['id'],'status':'unresolved_no_simple_supported_primitive'});continue
        score,geom,metrics=min(choices,key=lambda item:item[0])
        # Preserve visible assignment without double-counting overlapping lower
        # hypotheses. Height steps remain separate surfaces and levels.
        if geom.is_empty:continue
        role='lower_roof' if metrics['interior_rmse_m']<.2 else 'unresolved_context'
        status='partial_structural_candidate' if role=='lower_roof' else 'unresolved_height_conflict'
        face=make_face('lower-'+group['id'],[group['id']],group['plane_model'],geom,role,'lower-'+group['id'],status)
        face['candidate_evidence']=metrics;face['primitive_score']=score;accepted.append(face)
        evidence.append({'source_group_id':group['id'],'status':status,'primitive_score':score,**metrics})
    visible=[];occupied=Polygon()
    # Better-supported primitives retain their source support before uncertain
    # contexts. No plane heights are averaged to make these seams continuous.
    for face in sorted(accepted,key=lambda f:f['primitive_score']):
        geometry=part_geometry(face['parts']).difference(occupied)
        if geometry.is_empty:continue
        face['parts']=parts(geometry);occupied=occupied.union(geometry);visible.append(face)
    return visible,evidence


def structural_child_primitives(record,parent):
    """Use support as finite bounds, never as exported child contour vertices.

    The two roof models share their exact analytic ridge. Their parent equality
    lines clip finite planes into valleys. A support hull seam is never a ridge.
    """
    planes=record.get('roof_planes',record.get('roof_faces',[]))
    if len(planes)!=2 or parent is None:return None
    samples=[]
    for plane in planes:
        polygon=plane.get('support_polygon',plane.get('polygon'))
        if polygon is None and plane.get('parts'):polygon=plane['parts'][0]['polygon']
        if not polygon or not plane.get('plane_model'):return None
        samples.append(np.asarray(polygon,float))
    delta=coefficients(planes[0]['plane_model'])-coefficients(planes[1]['plane_model'])
    if np.linalg.norm(delta[:2])<.15:return None
    n=delta[:2]/np.linalg.norm(delta[:2]);d=np.array([-n[1],n[0]])
    ridge=-delta[2]/np.linalg.norm(delta[:2])
    coordinates=np.concatenate(samples);uv=np.c_[coordinates@n,coordinates@d]
    lo=np.quantile(uv,.01,axis=0)-.05;hi=np.quantile(uv,.99,axis=0)+.05
    if not lo[0]<ridge<hi[0] or max(hi-lo)>8:return None
    # Keep this bounded at the actual observed source support. Models cannot
    # create an arbitrarily large gable by a remote intersection.
    raw_footprint=Polygon(record['footprint'])
    if (hi[0]-lo[0])*(hi[1]-lo[1])>max(1.,raw_footprint.area)*2.5:return None
    low_side=int(np.argmin([np.median(p@n) for p in samples]))
    geometries=[]
    for i,plane in enumerate(planes):
        u0,u1=(lo[0],ridge) if i==low_side else (ridge,hi[0])
        geom=bounds_polygon(n,d,u0,u1,lo[1],hi[1])
        difference=coefficients(plane['plane_model'])-coefficients(parent['plane_model'])
        geom=clip_halfplane(geom,difference[:2],difference[2],True)
        if geom.is_empty or geom.area<.1:return None
        geometries.append(geom)
    footprint=unary_union(geometries)
    if footprint.geom_type!='Polygon':return None
    shared=geometries[0].boundary.intersection(geometries[1].boundary)
    if shared.length<.15:return None
    joined_points=[]
    if shared.geom_type=='LineString':joined_points=list(shared.coords)
    else:
        for item in getattr(shared,'geoms',[]):
            if item.geom_type=='LineString':joined_points.extend(item.coords)
    errors=[abs(plane_z(planes[0]['plane_model'],np.asarray(p))-plane_z(planes[1]['plane_model'],np.asarray(p))) for p in joined_points]
    return footprint,[(plane['plane_model'],geom) for plane,geom in zip(planes,geometries)],{
        'method':'Finite common ridge-frame gable bounds from support projections, exact analytic ridge, z_child>=z_parent valley clips.',
        'continuous_ridge_length_m':float(shared.length),'continuous_ridge_max_z_disagreement_m':float(max(errors,default=0)),
        'support_footprint_area_m2':float(raw_footprint.area),'primitive_footprint_area_m2':float(footprint.area),
        'footprint_corner_count':len(primitive_ring(footprint.exterior.coords))-1}


def apply_features(base_faces,feature_data):
    """Explicit with/without child candidates; no blind obstruction cutouts."""
    faces=json.loads(json.dumps(base_faces));features=[];alternatives=[]
    for record in feature_data.get('features',[]):
        identifier=record.get('id',f'feature-{len(features)+1}')
        parent_group=record.get('parent_group_id','')
        parent_group=parent_group.replace('west','').replace('east','')
        parent=next((f for f in faces if parent_group in f.get('source_group_ids',[])),None)
        footprint_record=record.get('footprint')
        if isinstance(footprint_record,dict):footprint=shape(footprint_record)
        elif footprint_record:footprint=Polygon(footprint_record)
        else:continue
        roof_planes=record.get('roof_planes',record.get('roof_faces',[]));child_faces=[]
        for index,plane in enumerate(roof_planes):
            poly=plane.get('support_polygon',plane.get('polygon'))
            geom=part_geometry(plane['parts']) if plane.get('parts') else (Polygon(poly) if poly else Polygon())
            if geom.is_empty or not plane.get('plane_model'):continue
            child_faces.append(make_face(f'{identifier}-roof-{index+1}',record.get('source_group_ids',[]),plane['plane_model'],geom,
                                         'dormer_roof','feature-'+identifier,record.get('hypothesis_status','unconfirmed_candidate')))
        kind=record.get('type','unknown')
        if child_faces and (parent is None or part_geometry(parent['parts']).intersection(footprint).area<.05):
            # A supplied parent hint cannot attach a distant child to the main
            # roof. Prefer a finite overlapping lower plane below the child.
            possibilities=[]
            for possible in faces:
                overlap=part_geometry(possible['parts']).intersection(footprint)
                if overlap.area<.1:continue
                center=np.asarray(overlap.representative_point().coords[0])
                child_height=max(plane_z(c['plane_model'],center) for c in child_faces)
                difference=child_height-plane_z(possible['plane_model'],center)
                if .1<difference<3:possibilities.append((overlap.area,possible))
            parent=max(possibilities,key=lambda p:p[0])[1] if possibilities else None
        primitive_evidence=None
        if kind=='dormer_candidate' and parent is not None:
            structural=structural_child_primitives(record,parent)
            if structural:
                footprint,primitive_planes,primitive_evidence=structural
                child_faces=[make_face(f'{identifier}-roof-{i+1}',record.get('source_group_ids',[]),model,geom,'dormer_roof','feature-'+identifier,record.get('hypothesis_status','unconfirmed_candidate')) for i,(model,geom) in enumerate(primitive_planes)]
            else:
                # A disconnected/unsupported child pair is retained as evidence,
                # not exported as a false continuous structural roof.
                child_faces=[]
        is_child=parent is not None and kind=='dormer_candidate' and child_faces and footprint.area>=.2
        if is_child:
            parent_geom=part_geometry(parent['parts']);before=parts(parent_geom)
            # A candidate cannot erase a remote or implausibly large parent area.
            intersection=parent_geom.intersection(footprint)
            if intersection.area>.05 and intersection.area<parent_geom.area*.35:
                remaining,children=cut_parent_surface(parent_geom,footprint,[part_geometry(c['parts']) for c in child_faces])
                # Every hidden source surface is removed only inside the
                # actual child footprint. Source IDs may describe a subset; a
                # feature never deletes an entire broad source roof by ID.
                for existing in faces:
                    existing['parts']=parts(part_geometry(existing['parts']).difference(footprint))
                faces=[f for f in faces if f['parts']]
                for face,geom in zip(child_faces,children):face['parts']=parts(geom);face['parent_face_id']=parent['id']
                for child in child_faces:
                    geom=part_geometry(child['parts'])
                    other=unary_union([part_geometry(f['parts']) for f in faces])
                    child['parts']=parts(geom.difference(other))
                    if child['parts']:faces.append(child)
                alternatives.append({'id':identifier+'-without-child','selected':False,'description':'Parent surface before candidate dormer occlusion; alternative only, never concurrent usable area.',
                                     'parent_face_id':parent['id'],'parent_parts':before,'excluded_feature_ids':[identifier]})
                alternatives.append({'id':identifier+'-with-child','selected':True,'description':'Candidate child roofs replace occluded parent footprint.',
                                     'parent_face_id':parent['id'],'occluded_parent_area_m2':float(intersection.area),'feature_ids':[identifier]})
            else:is_child=False
        features.append({'id':identifier,'type':kind if kind in ('dormer_candidate','obstruction_candidate','unknown') else 'unknown',
                         'parent_face_id':parent['id'] if parent else None,'footprint':primitive_ring(footprint.exterior.coords),
                         'roof_face_ids':[c['id'] for c in child_faces if any(f['id']==c['id'] for f in faces)] if is_child else [],
                         'confidence_basis':record.get('confidence_basis',record.get('evidence',{})),
                         'hypothesis_status':record.get('hypothesis_status','unconfirmed_candidate'),
                         'parent_cutout_applied':bool(is_child),'structural_primitive_evidence':primitive_evidence,'source_feature_record':record})
    return faces,features,alternatives


def main():
    start=time.perf_counter();data=pickle.load(open(ROOT/'data/inputs.pkl','rb'));archive=np.load(ROOT/'outputs/sam-masks.npz')
    priors=archive['face_priors'];ids=archive['face_ids'].tolist();raw,aligned=data['raw'],data['aligned'];transform=aligned['transform'];pixel=float(aligned['pixel_size_m'])
    source={g['id']:g for g in raw['refinement']['face_groups']};groups=[source[i] for i in ids]
    dsm,full_mask=warp_cached(data);valid=np.isfinite(dsm)&np.asarray(aligned['valid'],bool)
    yy,xx=np.indices(dsm.shape);xy=np.stack([transform.a*(xx+.5)+transform.b*(yy+.5)+transform.c,transform.d*(xx+.5)+transform.e*(yy+.5)+transform.f],axis=-1)
    components,_=ndi.label(full_mask);target=max(range(1,components.max()+1),key=lambda i:int(np.count_nonzero((components==i)&priors.any(0))))
    roof_mask=components==target
    lines=json.load(open(ROOT/'outputs/lines.json'))['lines']
    main_faces,candidates,frame,pair_indices,line_support=main_candidates(groups,priors,xy,lines,dsm,valid,transform,roof_mask,pixel)
    feature_path=ROOT/'outputs/phase2-features.json';feature_data=json.load(open(feature_path)) if feature_path.exists() else {}
    excluded=set(pair_indices)
    lower_faces,lower_evidence=lower_primitives(groups,priors,xy,lines,excluded,main_faces,dsm,valid,transform,pixel)
    base=main_faces+lower_faces
    for exclusion in source_exclusions(raw):
        for f in base:f['parts']=parts(part_geometry(f['parts']).difference(exclusion))
    final_faces,features,feature_alternatives=apply_features(base,feature_data)
    child_source_ids={i for f in features if f.get('parent_cutout_applied') for i in f.get('source_feature_record',{}).get('source_group_ids',[])}
    for face in final_faces:
        if face['role']!='dormer_roof' and face['source_group_ids'] and set(face['source_group_ids']).issubset(child_source_ids) and part_geometry(face['parts']).area<1.5:
            face['role']='unresolved_context';face['hypothesis_status']='unresolved_source_feature_remainder'
    # Raw algorithmic obstruction records remain hypotheses; no unverified hole.
    for index,obstruction in enumerate(raw.get('obstruction_candidates',[]),1):
        features.append({'id':f'cached-obstruction-{index}','type':'unknown','parent_face_id':None,
                         'footprint':obstruction['polygon'],'roof_face_ids':[],
                         'hypothesis_status':'unverified_cached_obstruction_or_edge_artifact',
                         'confidence_basis':'Cached algorithm output only; not carved and not interpreted as confirmed physical obstruction.'})
    ground=feature_data.get('ground_z_m',feature_data.get('ground',{}).get('estimated_z_m'))
    if isinstance(ground,dict):ground=ground.get('value_m',ground.get('z_m'))
    if ground is None:
        terrain=dsm[valid&~ndi.binary_dilation(roof_mask,iterations=5)]
        ground=float(np.quantile(terrain,.2)) if len(terrain) else float(np.nanquantile(dsm,.1))
    quality=evaluate_faces(final_faces,xy,dsm,valid,transform,roof_mask,priors.any(0),pixel)
    quality.update({'source_footprint_horizontal_area_m2':float(priors.any(0).sum()*pixel**2),
                    'cached_target_roof_mask_horizontal_area_m2':float(roof_mask.sum()*pixel**2),'main_gable_frame':frame,
                    'outer_primitive_corner_count':sum(len(p['polygon'])-1 for f in final_faces for p in f['parts']),
                    'accounted_source_group_ids':sorted({i for f in final_faces for i in f['source_group_ids']}),
                    'accounting_note':'Accounted means source evidence is represented, not that all source area has a valid structural explanation.',
                    'unresolved_source_group_ids':sorted((set(ids)-{i for f in final_faces for i in f['source_group_ids']})|{i for f in final_faces if f['role']=='unresolved_context' for i in f['source_group_ids']}),
                    'level_heights_are_not_welded':True,'interior_exclusion_m':.3,'lower_primitive_evidence':lower_evidence,
                    'physical_surface_area_m2':sum(f['sloped_physical_area_m2'] for f in quality['per_face']),
                    'usable_array_area_m2':None,'usable_array_area_status':'unknown_without_AHJ_and_structure_review'})
    levels=[]
    for level_id in dict.fromkeys(f['level_id'] for f in final_faces):
        level_faces=[f for f in final_faces if f['level_id']==level_id];heights=[]
        for f in level_faces:
            for p in f['parts']:heights.extend(plane_z(f['plane_model'],np.asarray(p['polygon'])).tolist())
        levels.append({'id':level_id,'roof_face_ids':[f['id'] for f in level_faces],'roof_z_min_m':float(min(heights)),'roof_z_max_m':float(max(heights)),
                       'ground_z_m':ground,'wall_base_status':'Unknown floor/eave-wall geometry; roof height intervals are evidence, not measured story counts.'})
    # Export complete, independently renderable hypotheses, never scores alone.
    selected_primitive=next(c for c in candidates if c['selected'])
    model_records=[]
    for primitive in (selected_primitive,next(c for c in candidates if c['id']=='detected_edge_rectangle')):
        if primitive is selected_primitive:
            alternative_faces,alternative_features=final_faces,features
        else:
            alt_main=primitive['roof_faces']
            alt_lower,_=lower_primitives(groups,priors,xy,lines,excluded,alt_main,dsm,valid,transform,pixel)
            alternative_faces,alternative_features,_=apply_features(alt_main+alt_lower,feature_data)
        model_records.append({**primitive,'roof_faces':alternative_faces,'features':alternative_features,
                              'scores':{**primitive['scores'],'complete_model':evaluate_faces(alternative_faces,xy,dsm,valid,transform,roof_mask,priors.any(0),pixel)}})
    model_records.append({'id':selected_primitive['id']+'-without-child-features','description':'Same structural main/lower roof primitives without candidate child replacements; alternative hypothesis only.',
                          'selected':False,'roof_faces':base,'features':[],
                          'scores':evaluate_faces(base,xy,dsm,valid,transform,roof_mask,priors.any(0),pixel),
                          'assumptions':['Source evidence does not establish every dormer; parent without child is retained as an explicit alternative.']})
    result={'algorithm_version':'phase2-finite-structural-primitives-v1','status':'experimental_structural_hypotheses','design_ready':False,
            'ground_z_m':float(ground),'ground_height_status':'DSM terrain estimate, not surveyed foundation datum',
            'roof_faces':final_faces,'features':features,'levels':levels,'candidate_models':model_records,'feature_alternatives':feature_alternatives,
            'edges':[{'id':'main-analytic-ridge','kind':'ridge_candidate','face_ids':[f['id'] for f in main_faces],
                      'coordinates':frame['ridge_endpoints'],'z_m':[float(plane_z(main_faces[0]['plane_model'],np.asarray(p))) for p in frame['ridge_endpoints']],
                      'evidence':'Analytic equality of the two dominant opposed cached models; finite endpoints from selected structural primitive.'}],
            'quality':quality,'main_boundary_line_evidence':line_support,
            'unknowns':['Structural primitives are hypotheses, not a completed or verified roof plan.','No exact source face count is imposed; unresolved source groups remain explicit.',
                        'Source lower-roof fragments may belong to hips, additions, or height steps; no continuity or story label is forced.',
                        'Dormer candidates include with/without alternatives; selected child footprints occlude parent area even where child roof is partial.',
                        'Cached obstruction candidates are unverified; no obstruction height or physical hole is invented.',
                        'No calibrated probabilities, AHJ compliance, usable array area, structural capacity, or solar design readiness.',
                        'RGB/DSM alignment and capture dates differ or remain uncertain; no manual reference coordinates were used.'],
            'provenance':{'inputs':['data/inputs.pkl','outputs/sam-masks.npz:face_priors,face_ids','outputs/lines.json']+(['outputs/phase2-features.json'] if feature_path.exists() else []),
                          'source_expires_at':data['expires_at'],'source_fetched_at':data['source_fetched_at'],
                          'network_used':False,'model_runs':False,'manual_reference_coordinates_used':False,'production_changes':False,
                          'attribution':'Includes solar data from Google.'},'elapsed_seconds':time.perf_counter()-start}
    (ROOT/'outputs/phase2-structure.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'main_candidate_scores':[{k:c[k] for k in ('id','scores','selected')} for c in candidates],
                      'roof_faces':[(f['id'],f['role'],sum(Polygon(p['polygon'],p.get('holes',[])).area for p in f['parts'])) for f in final_faces],
                      'features':[(f['id'],f.get('parent_cutout_applied')) for f in features],
                      'quality':{k:v for k,v in quality.items() if k not in ('per_face','lower_primitive_evidence')},'elapsed_seconds':result['elapsed_seconds']},indent=2))

if __name__=='__main__':main()
