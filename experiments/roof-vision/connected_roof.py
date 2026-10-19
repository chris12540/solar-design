"""Joint, bounded polygonization of cached roof detectors. No reference or network.

Each interface is fitted once and reused by both incident faces. Finite chains
retain their junctions; no infinite half-plane intersections are constructed.
"""
from pathlib import Path
from collections import defaultdict
import json, pickle, time, copy
import numpy as np
import cv2
from scipy import ndimage as ndi
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import polygonize, unary_union, linemerge
from rasterio.features import rasterize
from affine import Affine

ROOT = Path(__file__).resolve().parent


def fuse_labels(priors, masks):
    """Conservative footprint; detector masks resolve face ownership only.

    Larger prior voids and disconnected footprints survive. Reassignment is bounded
    to two pixels from each source region; unsupported source faces are retained.
    """
    footprint = priors.any(axis=0)
    # Enclosed <=4-cell voids are sub-resolution label noise, not confirmed
    # courtyards. Larger voids and all separate footprints remain protected.
    holes=ndi.binary_fill_holes(footprint)&~footprint
    hole_labels,_=ndi.label(holes)
    sizes=np.bincount(hole_labels.ravel())
    tiny=(hole_labels>0)&(sizes[hole_labels]<=4)
    footprint |= tiny
    distance = np.stack([ndi.distance_transform_edt(~m) for m in priors])
    sam_distance = np.stack([ndi.distance_transform_edt(~m) if m.any()
                            else np.full(m.shape, 100.) for m in masks])
    scores = distance + .55 * np.minimum(sam_distance, 5.)
    scores[distance > 2.] = 1e6
    labels = scores.argmin(axis=0).astype(np.int32) + 1
    labels[~footprint] = 0
    for i, prior in enumerate(priors, 1):
        if not (labels == i).any() and prior.any():
            # Preserve the entire unsupported face rather than inventing a seed.
            labels[prior] = i
    return labels


def boundary_chains(labels):
    """Raster cell-edge graph, partitioned at every common junction."""
    h, w = labels.shape
    padded = np.pad(labels, 1)
    adjacency = defaultdict(list)
    edge_pairs = {}
    def add(a, b, left, right):
        if left == right:
            return
        key = tuple(sorted((a, b)))
        edge_pairs[key] = tuple(sorted((int(left), int(right))))
        adjacency[a].append(b); adjacency[b].append(a)
    for y in range(h + 1):
        for x in range(w):
            add((x,y), (x+1,y), padded[y,x+1], padded[y+1,x+1])
    for y in range(h):
        for x in range(w + 1):
            add((x,y), (x,y+1), padded[y+1,x], padded[y+1,x+1])
    def junction(v):
        pairs = {edge_pairs[tuple(sorted((v,n)))] for n in adjacency[v]}
        return len(adjacency[v]) != 2 or len(pairs) != 1
    seen = set(); result = []
    for start in sorted(adjacency, key=lambda v: (not junction(v),v)):
        for nxt in adjacency[start]:
            edge = tuple(sorted((start,nxt)))
            if edge in seen:
                continue
            points = [start, nxt]; seen.add(edge); previous, current = start, nxt
            while current != start and not junction(current):
                candidates = [v for v in adjacency[current] if v != previous]
                target = candidates[0]
                key = tuple(sorted((current,target)))
                if key in seen:
                    break
                seen.add(key); points.append(target)
                previous, current = current, target
            result.append({'pair':edge_pairs[edge], 'raw':np.asarray(points,float)})
    background, _ = ndi.label(labels == 0)
    external = set(np.concatenate([background[0],background[-1],background[:,0],background[:,-1]]))
    for chain in result:
        chain['protected_void'] = False
        if 0 not in chain['pair']: continue
        a,b = chain['raw'][:2]; mid=(a+b)/2; delta=b-a
        normal=np.array([-delta[1],delta[0]])*.25
        for point in (mid+normal,mid-normal):
            x,y=np.floor(point).astype(int)
            if 0<=x<w and 0<=y<h and labels[y,x]==0 and background[y,x] not in external:
                chain['protected_void']=True
    return result


def _fit_chain(chain, tolerance, evidence):
    pts = chain['raw']; closed = np.array_equal(pts[0],pts[-1])
    effective_tolerance = 0. if chain.get('protected_void') or (0 in chain['pair'] and len(pts) <= 10) else tolerance
    simple = cv2.approxPolyDP(pts.astype(np.float32), effective_tolerance, closed).reshape(-1,2).astype(float)
    if closed:
        simple = np.vstack([simple, simple[0]])
    else:
        simple[0], simple[-1] = pts[0], pts[-1]
    if len(simple) < (4 if closed else 2):
        simple = pts.copy()
    support=[]; snapped_vertices=0
    # A finite, already simplified segment can be attracted to a nearby detector
    # only when endpoints and the original chain remain within the bound.
    for k in range(len(simple)-1) if effective_tolerance else []:
        a,b = simple[k:k+2]; delta=b-a; length=np.linalg.norm(delta)
        if length < 5:
            continue
        direction = delta/length
        candidates=[]
        for record in evidence:
            if not(record.get('classical_context_selected') or record.get('learned_filtered_selected')):
                continue
            p,q=np.asarray(record['pixel_xy'],float)+.5
            v=q-p; vl=np.linalg.norm(v)
            if vl < 5 or abs(np.dot(v/vl,direction)) < np.cos(np.deg2rad(9)):
                continue
            n=np.array([-v[1],v[0]])/vl
            distances=np.abs((np.array([a,b])-p)@n)
            overlap=min(np.dot(q-a,direction),length)-max(np.dot(p-a,direction),0) if np.dot(v,direction)>0 else min(np.dot(p-a,direction),length)-max(np.dot(q-a,direction),0)
            if max(distances) <= tolerance and overlap > min(4,length*.3):
                strength=(2 if record.get('dsm_evidence',{}).get('fold_or_step_evidence') else 1) + .15*float(record.get('learned_inlier_fraction',0))
                candidates.append((strength*overlap/(1+distances.mean()),record,p,q,n))
        if candidates:
            _,record,p,q,n=max(candidates,key=lambda v:v[0])
            support.append({'segment_index':k,'line_id':record['id'],
                            'classical':bool(record.get('classical_context_selected')),
                            'learned':bool(record.get('learned_filtered_selected')),
                            'height_fold_or_step':bool(record.get('dsm_evidence',{}).get('fold_or_step_evidence'))})
            # Only move non-junction internal vertices; common endpoints remain
            # exactly shared. Connected topology takes priority over line fit.
            proposed=simple.copy()
            for ix in (k,k+1):
                if ix not in (0,len(simple)-1):
                    proposed[ix] -= np.dot(proposed[ix]-p,n)*n
            candidate=LineString(proposed)
            if candidate.is_simple and candidate.hausdorff_distance(LineString(pts)) <= tolerance:
                snapped_vertices+=int(np.count_nonzero(np.linalg.norm(proposed-simple,axis=1)>1e-7))
                simple=proposed
    if LineString(simple).hausdorff_distance(LineString(pts)) > tolerance+1e-5:
        simple=pts.copy()
    return {**chain,'points':simple,'line_support':support,'snapped_vertex_count':snapped_vertices}


def _pieces(chains, labels):
    network=unary_union([LineString(c['points']) for c in chains])
    groups=defaultdict(list)
    for poly in polygonize(network):
        minx,miny,maxx,maxy=poly.bounds
        x0,y0=max(0,int(minx)),max(0,int(miny))
        x1,y1=min(labels.shape[1],int(np.ceil(maxx))),min(labels.shape[0],int(np.ceil(maxy)))
        if x1<=x0 or y1<=y0: continue
        inside=rasterize([(mapping(poly),1)],out_shape=(y1-y0,x1-x0),transform=Affine.translation(x0,y0)).astype(bool)
        counts=np.bincount(labels[y0:y1,x0:x1][inside],minlength=int(labels.max())+1)
        if not counts.size or counts.argmax()==0: continue
        groups[int(counts.argmax())].append(poly)
    return {i:unary_union(parts) for i,parts in groups.items()}


def fit_connected(labels, evidence=(), tolerance=2.25, height_squared_errors=None):
    """Fit all boundary chains once; globally validate each finite-chain replacement.

    A candidate must preserve every source label and every background component
    and hole, retain each face's sampled area, and stay inside its movement bound.
    """
    original=boundary_chains(labels)
    raw_groups=_pieces([{**c,'points':c['raw']} for c in original],labels)
    raw_union=unary_union(list(raw_groups.values()))
    original_voids=sum(len(p.interiors) for p in _polygons(raw_union))
    protected_void_geometry=unary_union([Polygon(r) for p in _polygons(raw_union) for r in p.interiors])
    original_components=ndi.label(labels>0)[1]
    if height_squared_errors is not None:
        base_height={i:float(np.nanmean(height_squared_errors[i-1][labels==i]))**.5 for i in raw_groups}
        base_interior_height={i:float(np.nanmean(height_squared_errors[i-1][ndi.binary_erosion(labels==i,iterations=3)]))**.5 for i in raw_groups}
        baseline=np.concatenate([height_squared_errors[i-1][labels==i] for i in raw_groups])
        total_height_limit=float(np.nanmean(baseline))**.5+.04
    def validate(groups, tol, exterior_evidence=False, current_labels=None):
        if set(groups)!=set(raw_groups): return False
        u=unary_union(list(groups.values()))
        if len(_polygons(u))!=original_components: return False
        if sum(len(p.interiors) for p in _polygons(u))!=original_voids: return False
        if u.intersection(protected_void_geometry).area > 1e-7: return False
        for i,raw in raw_groups.items():
            p=groups[i]
            if not p.is_valid or not .8*raw.area <= p.area <= 1.2*raw.area: return False
            if raw.boundary.hausdorff_distance(p.boundary)>tol+1e-4: return False
        if height_squared_errors is not None:
            assigned=rasterize([(mapping(p),i) for i,p in groups.items()],out_shape=labels.shape,transform=Affine.identity(),dtype='int32')
            residuals=[]
            for i in groups:
                values=height_squared_errors[i-1][assigned==i]
                if not exterior_evidence:
                    current_values=height_squared_errors[i-1][current_labels==i] if current_labels is not None else height_squared_errors[i-1][labels==i]
                    if float(np.nanmean(values))**.5>float(np.nanmean(current_values))**.5+.06:return False
                if exterior_evidence:
                    interior=ndi.binary_erosion(assigned==i,iterations=3)
                    interior_values=height_squared_errors[i-1][interior]
                    if interior_values.size and float(np.nanmean(interior_values))**.5>base_interior_height[i]+.04:return False
                residuals.extend(values.tolist())
            current_total=np.concatenate([height_squared_errors[i-1][current_labels==i] for i in groups]) if current_labels is not None else baseline
            height_limit=.35 if exterior_evidence else min(.35,float(np.nanmean(current_total))**.5+.04)
            if float(np.nanmean(residuals))**.5>height_limit:return False
        return sum(p.area for p in groups.values())-u.area<1e-6
    # A local bad chain must not force every good roof edge back to stair steps.
    # Greedily accept the longest finite interfaces under the same GLOBAL checks.
    fitted=[_fit_chain(c,0.,()) for c in original]
    accepted=[]; rejected=[]
    for index in sorted(range(len(original)),key=lambda i:-LineString(original[i]['raw']).length):
        found=False
        current_groups=_pieces(fitted,labels)
        current_labels=rasterize([(mapping(p),i) for i,p in current_groups.items()],out_shape=labels.shape,transform=Affine.identity(),dtype='int32') if height_squared_errors is not None else None
        for local_tolerance in [tolerance,tolerance*.75,tolerance*.5,tolerance*.25]:
            proposed=_fit_chain(original[index],local_tolerance,evidence)
            candidate=fitted.copy();candidate[index]=proposed
            groups=_pieces(candidate,labels)
            exterior_evidence=0 in original[index]['pair'] and any(s['classical'] for s in proposed['line_support'])
            if 0 in original[index]['pair'] and local_tolerance>2.25 and not exterior_evidence:continue
            if validate(groups,tolerance,exterior_evidence=exterior_evidence,current_labels=current_labels):
                fitted=candidate;accepted.append(index);found=True;break
        if not found: rejected.append(index)
    groups=_pieces(fitted,labels)
    if not validate(groups,tolerance,exterior_evidence=True): raise RuntimeError('Exact raster graph failed validation')
    return groups,fitted,{'accepted_tolerance_px':tolerance,
                          'accepted_chain_count':len(accepted),'conservative_chain_fallback_count':len(rejected),
                          'conservative_chain_fallback_indices':rejected,
                          'unsupported_labels':[int(i) for i in sorted(raw_groups) if not any(c['line_support'] for c in fitted if i in c['pair'])],
                          'protected_footprint_void_count':original_voids,
                          'raw_boundary_vertices':sum(len(c['raw'])-1 for c in original),
                          'fitted_boundary_vertices':sum(len(c['points'])-1 for c in fitted),
                          'detector_snapped_vertex_count':sum(c.get('snapped_vertex_count',0) for c in fitted)}


def actual_edges(groups):
    """Export only interfaces present in final clipped geometry."""
    def lines(geom):
        if geom.is_empty: return []
        if geom.geom_type in ('LineString','LinearRing'): return [LineString(geom)]
        if hasattr(geom,'geoms'): return [line for item in geom.geoms for line in lines(item)]
        return []
    result=[]
    for i,g in groups.items():
        shared=[]
        for j,h in groups.items():
            if j==i:continue
            geometry=g.boundary.intersection(h.boundary)
            if geometry.geom_type=='MultiLineString':geometry=linemerge(geometry)
            shared.append(geometry)
            if j>i:
                result.extend(((i,j),line) for line in lines(geometry))
        exterior=g.boundary.difference(unary_union(shared))
        if exterior.geom_type=='MultiLineString':exterior=linemerge(exterior)
        result.extend(((0,i),line) for line in lines(exterior))
    return result


def _polygons(geom):
    return [geom] if geom.geom_type=='Polygon' else list(geom.geoms)


def main():
    started=time.perf_counter()
    data=pickle.load(open(ROOT/'data/inputs.pkl','rb'))
    archive=np.load(ROOT/'outputs/sam-masks.npz')
    detected=json.load(open(ROOT/'outputs/lines.json'))
    raw,aligned=data['raw'],data['aligned']; ids=archive['face_ids'].tolist()
    labels=fuse_labels(archive['face_priors'],archive['faces'])
    from line_experiment import context
    _,dsm=context(data)
    transform=aligned['transform']
    yy,xx=np.indices(labels.shape); xm=transform.a*(xx+.5)+transform.c; ym=transform.e*(yy+.5)+transform.f
    source={g['id']:g for g in raw['refinement']['face_groups']}
    errors=[]
    for identifier in ids:
        p=source[identifier]['plane_model']
        errors.append((dsm-(p['a']*xm+p['b']*ym+p['c']))**2)
    groups,chains,quality=fit_connected(labels,detected['lines'],tolerance=4.,height_squared_errors=np.stack(errors))
    quality['height_acceptance_limits']='Internal chains: aggregate all-pixel RMSE <= preceding partition + 0.04m and each face <= preceding partition + 0.06m; aggregate ceiling 0.35m. Classical-line-supported exterior chains: 0.30m-eroded per-face interior RMSE <= initial interior + 0.04m; aggregate all-pixel RMSE <= 0.35m. Both metrics reported without inlier trimming.'
    # Apply exactly the same exclusion geometry to the complete partition.
    inverse=~aligned['transform']
    obstruction_polygons=[]
    for obstruction in raw.get('obstruction_candidates',[]):
        obstruction_polygons.append(Polygon([inverse*tuple(p) for p in obstruction['polygon']],
                                           [[inverse*tuple(p) for p in ring] for ring in obstruction.get('holes',[])]))
    obstruction_union=unary_union(obstruction_polygons)
    groups={i:g.difference(obstruction_union).simplify(0) for i,g in groups.items()}
    quality['obstruction_exclusions_exact']=True
    quality['subresolution_label_void_pixels_reassigned']=int(((labels>0)&~archive['face_priors'].any(0)).sum())
    transform=aligned['transform']; pixel=float(aligned['pixel_size_m'])
    source={g['id']:g for g in raw['refinement']['face_groups']}
    def local(ring): return [list(transform*tuple(p)) for p in ring]
    output_groups=[]
    for number,identifier in enumerate(ids,1):
        original=source[identifier]; geom=groups[number]; parts=[]
        for poly in _polygons(geom):
            parts.append({'polygon':local(poly.exterior.coords),'holes':[local(r.coords) for r in poly.interiors],
                          'area_m2':float(poly.area*pixel**2),'area_basis':'horizontal'})
        supported=sum(len(c['line_support']) for c in chains if number in c['pair'])
        metadata=copy.deepcopy(original)
        metadata['source_fit_rmse_m']=metadata.pop('fit_rmse_m',None)
        metadata['source_largest_contiguous_area_m2']=metadata.pop('largest_contiguous_area_m2',None)
        metadata['largest_contiguous_area_m2']=float(max(p.area for p in _polygons(geom))*pixel**2)
        output_groups.append({**metadata,'parts':parts,'area_m2':float(geom.area*pixel**2),
                              'boundary_evidence_segments':supported,'unsupported_boundary':supported==0,
                              'status':'experimental_review_required'})
    edges=[]
    for pair,geometry in actual_edges(groups):
        faces=[ids[i-1] for i in pair if i]
        support=[]
        for c in chains:
            if set(c['pair'])==set(pair) and geometry.intersection(LineString(c['points']).buffer(.05)).length>geometry.length*.5:
                support.extend(c['line_support'])
        edges.append({'id':f'connected-edge-{len(edges)+1}','kind':'unknown','face_ids':faces,
                      'coordinates':local(geometry.coords),'inferred':True,'line_support':support,
                      'uncertain_junctions':True})
    # Height errors use cached DSM reprojected once above.
    final_labels=rasterize([(mapping(g),i) for i,g in groups.items()],out_shape=labels.shape,transform=Affine.identity(),dtype='int32')
    yy,xx=np.indices(labels.shape); xm=transform.a*(xx+.5)+transform.c; ym=transform.e*(yy+.5)+transform.f
    square=[]; interior_square=[];perface=[]
    for i,identifier in enumerate(ids,1):
        p=source[identifier]['plane_model']; valid=(final_labels==i)&np.isfinite(dsm)
        residual=dsm[valid]-(p['a']*xm[valid]+p['b']*ym[valid]+p['c'])
        square.extend((residual**2).tolist())
        output_groups[i-1]['all_point_height_rmse_m']=float(np.sqrt(np.mean(residual**2))) if len(residual) else None
        interior=ndi.binary_erosion(final_labels==i,iterations=3)&np.isfinite(dsm)
        interior_residual=dsm[interior]-(p['a']*xm[interior]+p['b']*ym[interior]+p['c'])
        interior_square.extend((interior_residual**2).tolist())
        output_groups[i-1]['interior_height_rmse_m']=float(np.sqrt(np.mean(interior_residual**2))) if len(interior_residual) else None
        perface.append({'id':identifier,'interior_point_count':int(interior.sum()),'interior_height_rmse_m':output_groups[i-1]['interior_height_rmse_m'],'all_point_count':int(valid.sum()),'all_point_height_rmse_m':float(np.sqrt(np.mean(residual**2))) if len(residual) else None})
    def corners(group): return sum(len(p.exterior.coords)-1 for p in _polygons(group))
    footprint=labels>0; final=final_labels>0
    quality.update({'source_face_count':len(ids),'retained_source_face_count':len(output_groups),
                    'lost_source_face_ids':[],'all_point_height_rmse_m':float(np.sqrt(np.mean(square))),
                    'interior_height_rmse_m':float(np.sqrt(np.mean(interior_square))),
                    'interior_erosion_m':.3,
                    'height_scope':'Every finite cached DSM pixel assigned to output; original source plane coefficients, no inlier trimming or refit.',
                    'height_per_face':perface,'coverage_fraction':float((footprint&final).sum()/footprint.sum()),
                    'footprint_iou':float((footprint&final).sum()/(footprint|final).sum()),
                    'outer_corner_count':sum(corners(g) for g in groups.values()),
                    'hole_count':sum(len(p.interiors) for g in groups.values() for p in _polygons(g)),
                    'max_boundary_displacement_m':float(max(LineString(c['raw']).hausdorff_distance(LineString(c['points'])) for c in chains)*pixel),
                    'overlap_area_m2':float((sum(g.area for g in groups.values())-unary_union(list(groups.values())).area)*pixel**2),
                    'source_footprint_components':ndi.label(footprint)[1],'output_footprint_components':ndi.label(final)[1],
                    'raw_sam_overlap_pixels':int((archive['faces'].sum(0)>1).sum()),
                    'source_prior_pixels':int(footprint.sum()),'changed_assignment_pixels':int((labels!=final_labels).sum())})
    result={'algorithm_version':'cached-detector-shared-chains-v1','status':'experimental','design_ready':False,
            'face_groups':output_groups,'edges':edges,'quality':quality,
            'obstruction_candidates':copy.deepcopy(raw.get('obstruction_candidates',[])),
            'automatic_candidates':{'count':int(len(np.load(ROOT/'outputs/sam-automatic-masks.npz')['masks'])),
                                    'used_as_geometry':False,'reason':'Generic automatic masks lack obstruction/roof semantics; retained only as candidate evidence.'},
            'unknowns':['All junction positions and edge semantic types require review.','Source priors determine footprint and larger voids; <=4-pixel enclosed label voids are reassigned as uncertain noise. SAM resolves ownership near priors.',
                        'Separate source footprints are preserved, including narrow source gaps; these may be segmentation artifacts.',
                        'Source obstruction candidates retained without claiming confirmed obstructions.','Image/DSM registration and source capture dates are unverified.',
                        'Exterior eave fitting uses 0.30m-eroded interior DSM consistency because boundary cells can mix roof and ground. All-point RMSE is reported separately and capped at 0.35m during fitting; this does not establish true boundary accuracy.'],
            'photo_evidence':{'image_size_xy':[int(aligned['rgb'].shape[1]),int(aligned['rgb'].shape[0])],
                              'pixel_to_local_affine':list(transform)[:6], 'coordinate_convention':'Raster cell corners; detector coordinates shifted +0.5 from pixel centers.',
                              'classical_supported_segments':sum(s['classical'] for c in chains for s in c['line_support']),
                              'learned_supported_segments':sum(s['learned'] for c in chains for s in c['line_support'])},
            'provenance':{'inputs':['data/inputs.pkl','outputs/sam-masks.npz','outputs/lines.json','outputs/sam-automatic-masks.npz'],
                          'manual_reference_used':False,'network_used':False,'models_rerun':False,
                          'attribution':'Includes solar data from Google. Google-derived geometry and image are source priors, not independent truth.',
                          'source_fetched_at':data['source_fetched_at'],'expires_at':data['expires_at']}}
    result['elapsed_seconds']=time.perf_counter()-started
    (ROOT/'outputs/connected-roof.json').write_text(json.dumps(result,indent=2))
    comparison(aligned['rgb'],archive['faces'],groups,ids,ROOT/'outputs/connected-roof-comparison.png')
    print(json.dumps({'quality':quality,'elapsed_seconds':result['elapsed_seconds']},indent=2))


def comparison(rgb,masks,groups,ids,path):
    from PIL import Image,ImageDraw
    palette=[(255,92,70),(60,200,255),(255,208,60),(175,100,255),(50,225,135),(255,120,210),(110,150,255),(215,245,70)]
    h,w=rgb.shape[:2];scale=3; panels=[]
    raw=rgb.astype(float).copy()
    for mask,col in zip(masks,palette):raw[mask]=raw[mask]*.5+np.asarray(col)*.5
    panels.append(Image.fromarray(raw.astype('uint8')).resize((w*scale,h*scale)))
    for photo in (False,True):
        panel=Image.fromarray(rgb).resize((w*scale,h*scale)) if photo else Image.new('RGB',(w*scale,h*scale),'#202630')
        draw=ImageDraw.Draw(panel)
        for i,geom in groups.items():
            col=palette[(i-1)%len(palette)]
            for poly in _polygons(geom):
                points=[(x*scale,y*scale) for x,y in poly.exterior.coords]
                if not photo:draw.polygon(points,fill=tuple(int(c*.5) for c in col))
                draw.line(points,fill=col,width=3)
                for hole in poly.interiors:
                    hp=[(x*scale,y*scale) for x,y in hole.coords]
                    if not photo:draw.polygon(hp,fill='#202630')
                    draw.line(hp,fill=col,width=2)
        panels.append(panel)
    canvas=Image.new('RGB',(w*scale*3,h*scale+100),'#141a23');draw=ImageDraw.Draw(canvas)
    for i,(p,title) in enumerate(zip(panels,['Raw SAM face masks (overlap blended)','Shared finite-chain polygons; source voids kept','Polygons on original 248 x 220 photo'])):
        canvas.paste(p,(i*w*scale,35));draw.text((i*w*scale+8,10),title,fill='white')
    draw.text((8,h*scale+45),'Includes solar data from Google. Source priors are not truth. All junctions uncertain; not design ready.',fill='white')
    draw.text((8,h*scale+65),'No manual reference, network, model rerun, or image resizing before fitting. Display enlarged 3x.',fill='white')
    canvas.save(path)

if __name__=='__main__': main()
