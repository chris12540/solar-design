"""Photo-line proposals + measured roof-plane evidence; no roof-type template."""
from dataclasses import dataclass, asdict
import math
import numpy as np
from scipy import ndimage as ndi
from scipy.linalg import qr
from scipy.optimize import minimize, LinearConstraint, Bounds
from rasterio.features import rasterize, shapes
from shapely.geometry import LineString, Polygon, Point, shape
from shapely.ops import polygonize, unary_union


@dataclass(frozen=True)
class Settings:
    line_score: float = .50
    minimum_face_area_m2: float = .30
    minimum_samples: int = 18
    large_face_erosion_m: float = .20
    small_face_erosion_m: float = .10
    google_rmse_limit_m: float = .12
    new_plane_rmse_limit_m: float = .10
    spatial_cv_limit_m: float = .18
    minimum_xy_eigenvalue_m2: float = .0025
    continuous_edge_max_initial_gap_m: float = .30
    step_min_initial_gap_m: float = .35
    minimum_shared_edge_m: float = .25
    maximum_joint_height_rmse_m: float = .15
    maximum_rmse_increase_m: float = .04


def evaluate(coeff,xy):
    return xy@np.asarray(coeff[:2])+coeff[2]


def robust_fit(xy,z):
    if len(z)<8:
        return None
    center=xy.mean(0);design=np.c_[xy-center,np.ones(len(z))]
    if np.linalg.matrix_rank(design)<3:
        return None
    c=np.linalg.lstsq(design,z,rcond=None)[0]
    for _ in range(12):
        e=z-design@c;scale=max(.015,1.4826*np.median(abs(e-np.median(e))))
        w=np.minimum(1.,1.345*scale/np.maximum(abs(e),1e-9))
        updated=np.linalg.lstsq(design*w[:,None]**.5,z*w**.5,rcond=None)[0]
        if np.linalg.norm(updated-c)<1e-9:
            c=updated;break
        c=updated
    return np.r_[c[:2],c[2]-c[:2]@center]


def rmse(coeff,xy,z):
    return float(np.sqrt(np.mean((z-evaluate(coeff,xy))**2)))


def crossvalidate(xy,z):
    errors=[]
    for axis in [0,1]:
        low=xy[:,axis]<=np.median(xy[:,axis])
        for selected in [low,~low]:
            if min(selected.sum(),(~selected).sum())<8:
                continue
            c=robust_fit(xy[selected],z[selected])
            if c is not None:
                errors.append(rmse(c,xy[~selected],z[~selected]))
    return max(errors) if errors else None


def parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type=='Polygon':
        return [geometry]
    return [p for g in geometry.geoms for p in parts(g)] if hasattr(geometry,'geoms') else []


def sample_face(geometry,xy,dsm,target,transform,settings):
    mask=rasterize([(geometry,1)],out_shape=dsm.shape,transform=transform).astype(bool)
    erosion=settings.large_face_erosion_m if geometry.area>=2 else settings.small_face_erosion_m
    selected=(ndi.distance_transform_edt(mask)*abs(transform.a)>erosion+1e-8)&target&np.isfinite(dsm)
    return xy[selected],dsm[selected],float(np.count_nonzero(mask&target)/max(1,mask.sum()))


def fit_face(geometry,xy,dsm,target,transform,google,settings):
    points,z,mask_fraction=sample_face(geometry,xy,dsm,target,transform,settings)
    info={'area_horizontal_m2':geometry.area,'interior_samples':len(z),'target_mask_fraction':mask_fraction,
          'state':'unresolved','source':'none','initial_coefficients':None}
    if geometry.area<settings.minimum_face_area_m2 or len(z)<settings.minimum_samples or mask_fraction<.7:
        return info,points,z
    eigen=float(np.linalg.eigvalsh(np.cov(points.T)).min())
    info['minimum_xy_eigenvalue_m2']=eigen
    if eigen<settings.minimum_xy_eigenvalue_m2:
        info['reason']='narrow_height_support';return info,points,z
    candidates=[]
    for plane in google:
        if plane['bounds'].buffer(.35).intersection(geometry).area/max(geometry.area,1e-9)<.6:
            continue
        candidates.append((rmse(plane['coefficients'],points,z),plane))
    candidates.sort(key=lambda pair:pair[0])
    fit=robust_fit(points,z)
    fitted_error=rmse(fit,points,z) if fit is not None else None
    info['independent_dsm_fit_rmse_m']=fitted_error
    info['best_google_segment_index']=candidates[0][1]['google_segment_index'] if candidates else None
    info['best_google_rmse_m']=candidates[0][0] if candidates else None
    if candidates and candidates[0][0]<=settings.google_rmse_limit_m:
        error,plane=candidates[0]
        info.update(state='google_supported',source='google_plane',google_segment_index=plane['google_segment_index'],
                    initial_coefficients=list(plane['coefficients']),initial_rmse_m=error)
    elif fit is not None and fitted_error<=settings.new_plane_rmse_limit_m:
        cv=crossvalidate(points,z);pitch=float(np.degrees(np.arctan(np.linalg.norm(fit[:2]))))
        info['spatial_cv_max_rmse_m']=cv
        if cv is not None and cv<=settings.spatial_cv_limit_m and pitch<=60:
            info.update(state='new_plane_provisional',source='dsm_fit_to_image_face',
                        initial_coefficients=fit.tolist(),initial_rmse_m=fitted_error)
        else:
            info['reason']='new_plane_not_spatially_stable'
    else:
        info['reason']='mixed_or_unsupported_height_surface'
    return info,points,z


def build_edges(faces,settings):
    edges=[]
    for i,a in enumerate(faces):
        for j,b in enumerate(faces):
            if j<=i:
                continue
            shared=a['geometry'].boundary.intersection(b['geometry'].boundary)
            if shared.length<settings.minimum_shared_edge_m:
                continue
            entry={'faces':[i,j],'geometry':shared,'length_m':shared.length,'kind':'unresolved','joint_enforced':False}
            if a['initial_coefficients'] is not None and b['initial_coefficients'] is not None:
                points=np.array([[p.x,p.y] for p in [shared.interpolate(t,normalized=True) for t in np.linspace(0,1,7)]])
                gap=evaluate(a['initial_coefficients'],points)-evaluate(b['initial_coefficients'],points)
                entry.update(initial_max_gap_m=float(abs(gap).max()),initial_min_gap_m=float(abs(gap).min()))
                if abs(gap).max()<=settings.continuous_edge_max_initial_gap_m:
                    entry['kind']='continuous_candidate'
                elif abs(gap).min()>=settings.step_min_initial_gap_m and (np.all(gap>0) or np.all(gap<0)):
                    entry['kind']='height_step'
            edges.append(entry)
    return edges


def _solve_joint_groups(faces,edges,settings):
    """Constrained linear plane fitting: shared image edges get one height.

    Pixel ownership and XY graph are fixed in this first prototype. Roof steps
    have no equality constraint. Infeasible or height-degrading groups roll back.
    """
    adjacency={i:set() for i,f in enumerate(faces) if f['initial_coefficients'] is not None}
    for edge in edges:
        if edge['kind']=='continuous_candidate':
            i,j=edge['faces'];adjacency[i].add(j);adjacency[j].add(i)
    unseen=set(adjacency);logs=[]
    while unseen:
        stack=[min(unseen)];component=[]
        while stack:
            i=stack.pop()
            if i not in unseen:
                continue
            unseen.remove(i);component.append(i);stack.extend(adjacency[i])
        if len(component)<2:
            continue
        component.sort();lookup={k:i for i,k in enumerate(component)}
        initial=[];lower=[];upper=[];centers=[];A=[];B=[]
        for i in component:
            f=faces[i];points=f['_xy'];z=f['_z'];center=points.mean(0);centers.append(center)
            c=np.array(f['initial_coefficients']);p=np.r_[c[:2],evaluate(c,center)]
            initial.extend(p)
            slope_bound=.05 if f['source']=='google_plane' else .12
            limits=np.array([slope_bound,slope_bound,.2]);lower.extend(p-limits);upper.extend(p+limits)
            sample=np.arange(len(z))[::max(1,len(z)//250)]
            block=np.zeros((len(sample),len(component)*3));k=lookup[i]*3
            block[:,k:k+3]=np.c_[points[sample]-center,np.ones(len(sample))]/(.07*np.sqrt(len(sample)))
            A.append(block);B.extend(z[sample]/(.07*np.sqrt(len(sample))))
            prior=np.zeros((3,len(component)*3));prior[:,k:k+3]=np.diag([1/.04,1/.04,1/.10])
            A.append(prior);B.extend(p/np.array([.04,.04,.10]))
        equations=[];used=[]
        for edge in edges:
            if edge['kind']!='continuous_candidate' or not set(edge['faces']).issubset(component):
                continue
            used.append(edge)
            i,j=edge['faces']
            # Each straight segment's endpoints enforce continuity everywhere
            # along it. Multi-segment seams can make the constraints infeasible.
            segments=[edge['geometry']] if edge['geometry'].geom_type=='LineString' else list(edge['geometry'].geoms)
            for segment in segments:
                for point in [np.array(segment.coords[0]),np.array(segment.coords[-1])]:
                    row=np.zeros(len(component)*3)
                    for identifier,sign in [(i,1),(j,-1)]:
                        k=lookup[identifier];row[k*3:k*3+3]=sign*np.r_[point-centers[k],1.]
                    equations.append(row)
        E=np.array(equations)
        _,R,pivot=qr(E.T,pivoting=True,mode='economic')
        rank=int(np.linalg.matrix_rank(R,tol=1e-9));E=E[pivot[:rank]]
        A=np.vstack(A);B=np.array(B);initial=np.array(initial)
        Q=A.T@A;v=A.T@B
        result=minimize(lambda p:float(np.sum((A@p-B)**2)),initial,
                        jac=lambda p:2*(Q@p-v),method='SLSQP',
                        bounds=Bounds(lower,upper),constraints=[LinearConstraint(E,0.,0.)],
                        options={'maxiter':150,'ftol':1e-10})
        candidates={}
        for i in component:
            k=lookup[i];p=result.x[k*3:k*3+3];center=centers[k]
            candidates[i]=np.r_[p[:2],p[2]-p[:2]@center]
        errors={i:rmse(candidates[i],faces[i]['_xy'],faces[i]['_z']) for i in component}
        good=result.success and max(abs(E@result.x),default=0)<1e-6 and all(
            errors[i]<=settings.maximum_joint_height_rmse_m and
            errors[i]<=faces[i]['initial_rmse_m']+settings.maximum_rmse_increase_m for i in component)
        logs.append({'faces':component,'accepted':bool(good),'optimizer_success':bool(result.success),
                     'reason':str(result.message),'max_constraint_gap_m':float(max(abs(E@result.x),default=0)),
                     'candidate_rmse_m':{str(i):errors[i] for i in component}})
        if good:
            for i in component:
                faces[i]['coefficients']=candidates[i].tolist();faces[i]['joint_fit_applied']=True
            for edge in used:
                edge['joint_enforced']=True;edge['kind']='continuous'
        else:
            for edge in used:
                edge['kind']='unresolved_connection'
    return logs


def joint_fit(faces,edges,settings):
    """Add strongest measured connections first; reject only conflicting joins."""
    candidate_indices=[i for i,e in enumerate(edges) if e['kind']=='continuous_candidate']
    priority=lambda i:edges[i]['length_m']*math.sqrt(min(len(faces[k]['_z']) for k in edges[i]['faces']))
    selected=[];attempts=[]
    for index in sorted(candidate_indices,key=priority,reverse=True):
        trial_faces=[dict(f,coefficients=f['initial_coefficients'],joint_fit_applied=False) for f in faces]
        active=selected+[index]
        trial_edges=[dict(e,kind='continuous_candidate' if i in active else 'deferred') for i,e in enumerate(edges)]
        logs=_solve_joint_groups(trial_faces,trial_edges,settings)
        accepted=bool(logs) and all(log['accepted'] for log in logs)
        attempts.append({'edge_faces':edges[index]['faces'],'accepted':accepted,'group_diagnostics':logs})
        if accepted:
            selected.append(index)
    final_edges=[dict(e,kind='continuous_candidate' if i in selected else 'deferred') for i,e in enumerate(edges)]
    final_logs=_solve_joint_groups(faces,final_edges,settings)
    for i in candidate_indices:
        if i in selected:
            edges[i]['kind']='continuous';edges[i]['joint_enforced']=True
        else:
            edges[i]['kind']='unresolved_connection'
    return {'incremental_connections':attempts,'final_groups':final_logs}


def fuse(lines_yx,scores,google,dsm,target,transform,settings=Settings()):
    yy,xx=np.indices(dsm.shape);x,y=transform*(xx+.5,yy+.5);xy=np.stack([x,y],-1)
    lines=[LineString([transform*(p[1],p[0]) for p in line]) for line,score in zip(lines_yx,scores) if score>=settings.line_score]
    cells=sorted(polygonize(unary_union(lines)),key=lambda p:(-p.area,p.centroid.x,p.centroid.y))
    faces=[]
    for cell in cells:
        if cell.area<settings.minimum_face_area_m2:
            continue
        info,points,z=fit_face(cell,xy,dsm,target,transform,google,settings)
        faces.append({**info,'id':f'F{len(faces)+1}','geometry':cell,'_xy':points,'_z':z,
                      'coefficients':info['initial_coefficients'],'joint_fit_applied':False,
                      'boundary_source':'roofmapnet_lines','source_cell_count':1})
    # Eliminate artificial subdivisions only when their union supports the same
    # supplied Google plane. No merging across stories or unknown faces.
    merged=[]
    for face in faces:
        partner=next((f for f in merged if f['source']=='google_plane' and face['source']=='google_plane'
                      and f['google_segment_index']==face['google_segment_index']
                      and f['geometry'].boundary.intersection(face['geometry'].boundary).length>.05),None)
        if partner:
            union=partner['geometry'].union(face['geometry'])
            if union.geom_type=='Polygon':
                info,points,z=fit_face(union,xy,dsm,target,transform,google,settings)
                if info['source']=='google_plane' and info['google_segment_index']==face['google_segment_index']:
                    partner.update(info,geometry=union,_xy=points,_z=z,coefficients=info['initial_coefficients'],
                                   source_cell_count=partner['source_cell_count']+1)
                    continue
        merged.append(face)
    faces=merged
    for i,f in enumerate(faces):
        f['id']=f'F{i+1}'
    edges=build_edges(faces,settings);joint=joint_fit(faces,edges,settings)
    for f in faces:
        if f['coefficients'] is not None:
            c=f['coefficients'];f['final_rmse_m']=rmse(c,f['_xy'],f['_z'])
            f['pitch_degrees']=float(np.degrees(np.arctan(np.linalg.norm(c[:2]))))
            f['azimuth_grid_degrees']=float(np.degrees(np.arctan2(-c[0],-c[1]))%360)
            f['roof_area_m2']=float(f['geometry'].area*np.sqrt(1+c[0]**2+c[1]**2))
            f['xyz_rings']=[[[float(a),float(b),float(evaluate(c,np.array([a,b])))] for a,b in ring.coords]
                            for ring in [f['geometry'].exterior,*f['geometry'].interiors]]
    for edge in edges:
        i,j=edge['faces'];a,b=faces[i],faces[j]
        if a['coefficients'] is not None and b['coefficients'] is not None:
            points=np.array([[p.x,p.y] for p in [edge['geometry'].interpolate(t,normalized=True) for t in np.linspace(0,1,7)]])
            edge['final_max_gap_m']=float(np.max(abs(evaluate(a['coefficients'],points)-evaluate(b['coefficients'],points))))
    supported=[f['geometry'] for f in faces if f['coefficients'] is not None]
    grid=rasterize([(g,1) for g in supported],out_shape=dsm.shape,transform=transform).astype(bool) if supported else np.zeros(dsm.shape,bool)
    unknown=target&~grid
    unknown_geoms=[shape(g) for g,v in shapes(unknown.astype('uint8'),mask=unknown,transform=transform)]
    return {'faces':faces,'edges':edges,'unknown_geometries':unknown_geoms,'joint_groups':joint,
            'raw_lines_local':lines,'settings':asdict(settings),'raw_cell_count':len(cells),
            'coverage_fraction':float(np.count_nonzero(grid&target)/max(1,target.sum())),
            'unsupported_area_m2':float(unknown.sum()*abs(transform.a*transform.e)),
            'overlap_m2':max(0.,sum(g.area for g in supported)-unary_union(supported).area)}
