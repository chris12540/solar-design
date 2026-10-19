"""Conservative 2D roof boundaries from unchanged Google Solar planes.

No inferred roof primitives, learned model, reference labels or photo annotation.
All geometry is local projected meters; plane heights remain source ASL meters.
"""
from dataclasses import dataclass, asdict
import math
import time

import numpy as np
from pyproj import Geod, Transformer
from rasterio.features import rasterize, shapes
from scipy import ndimage as ndi
from shapely import coverage_is_valid, make_valid, set_precision
from shapely.geometry import LineString, Point, Polygon, shape, mapping
from shapely.ops import split, unary_union, polygonize


@dataclass(frozen=True)
class Settings:
    height_tolerance_m: float = .20
    bounding_box_margin_m: float = .30
    minimum_island_area_m2: float = .10
    maximum_seed_distance_m: float = .75
    simplification_tolerance_m: float = .16
    max_boundary_displacement_m: float = .20
    max_component_area_change_fraction: float = .04
    strong_height_tolerance_m: float = .08
    strong_margin_m: float = .04
    max_strong_support_loss_fraction: float = .02
    seam_minimum_length_m: float = .80
    seam_maximum_displacement_m: float = .15
    seam_minimum_normal_angle_degrees: float = 8.


def google_planes(insights, crs):
    """Convert true-north slope to grid coordinates, retaining source measurements."""
    tf = Transformer.from_crs(4326, crs, always_xy=True)
    origin = np.array(tf.transform(insights['center']['longitude'], insights['center']['latitude']))
    geod = Geod(ellps='WGS84')
    planes = []
    for i, segment in enumerate(insights['solarPotential']['roofSegmentStats']):
        lat, lon = segment['center']['latitude'], segment['center']['longitude']
        cx, cy = tf.transform(lon, lat)
        lon2, lat2, _ = geod.fwd(lon, lat, segment['azimuthDegrees'], 1.)
        ex, ey = tf.transform(lon2, lat2)
        direction = np.array([ex-cx, ey-cy])
        scale = np.linalg.norm(direction)
        direction /= scale
        slope = math.tan(math.radians(segment['pitchDegrees']))
        a, b = -slope*direction/scale
        center = np.array([cx, cy])-origin
        c = segment['planeHeightAtCenterMeters'] - a*center[0] - b*center[1]
        box = segment['boundingBox']
        sw, ne = box['sw'], box['ne']
        bounds = Polygon([np.array(tf.transform(x, y))-origin for x, y in [
            (sw['longitude'],sw['latitude']), (ne['longitude'],sw['latitude']),
            (ne['longitude'],ne['latitude']), (sw['longitude'],ne['latitude'])]])
        planes.append({'id': i+1, 'google_segment_index': i,
                       'source_pitch_degrees': segment['pitchDegrees'],
                       'source_azimuth_degrees': segment['azimuthDegrees'],
                       'source_height_at_center_m': segment['planeHeightAtCenterMeters'],
                       'center_xy': center.tolist(), 'coefficients': [float(a),float(b),float(c)],
                       'bounds': bounds})
    return planes, origin


def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    if hasattr(geometry, 'geoms'):
        return [p for g in geometry.geoms for p in polygons(g)]
    return []


def records_from_grid(labels, target, transform):
    records = []
    for geom, value in shapes(labels.astype('int32'), mask=target, transform=transform, connectivity=4):
        source = shape(geom)
        # Pixel polygons can touch at a point; make_valid only splits that
        # contact. It does not fit or expand the source assignment.
        # A micrometer grid removes floating arithmetic differences along the
        # same raster edge (the source pixels are 0.1m), not roof-detail evidence.
        for part in polygons(set_precision(make_valid(source),1e-6)):
            records.append({'label': int(value), 'geometry': part})
    # Raster tracing omits collinear vertices at T-junctions on one side.
    # Node the complete boundary network once, then rebuild shared cells.
    network=unary_union([r['geometry'].boundary for r in records])
    inverse=~transform
    noded=[]
    for part in polygonize(network):
        point=part.representative_point()
        col,row=inverse*(point.x,point.y)
        row,col=int(math.floor(row)),int(math.floor(col))
        if 0<=row<labels.shape[0] and 0<=col<labels.shape[1] and target[row,col]:
            noded.append({'label':int(labels[row,col]),'geometry':part})
    return noded


def grid_from_records(records, transform, size):
    return rasterize([(r['geometry'], r['label']) for r in records], out_shape=size,
                     transform=transform, fill=-1, dtype='int32')


def coverage_valid(records):
    return bool(records) and all(r['geometry'].is_valid for r in records) and bool(
        coverage_is_valid([r['geometry'] for r in records]))


def simplify_shared_network(records,tolerance):
    """Simplify each shared chain exactly once with bounded-distance DP.

    Junctions are fixed. Short/closed small details are preserved, and long
    chains retain any corner required by the distance tolerance. No assumed
    rectangle or required roof shape is introduced.
    """
    owners={}
    for record in records:
        for ring in [record['geometry'].exterior,*record['geometry'].interiors]:
            points=[tuple(p) for p in ring.coords]
            for a,b in zip(points,points[1:]):
                if a!=b:
                    edge=tuple(sorted([a,b]))
                    owners.setdefault(edge,set()).add(record['label'])
    global_adj={}
    by_pair={}
    for edge,labels in owners.items():
        pair=tuple(sorted(labels)) if len(labels)>1 else (-1,next(iter(labels)))
        by_pair.setdefault(pair,[]).append(edge)
        for vertex in edge:
            global_adj.setdefault(vertex,set()).add(edge)
    lines=[]
    for pair,edges in by_pair.items():
        adj={}
        for edge in edges:
            for vertex in edge:
                adj.setdefault(vertex,[]).append(edge)
        stops={v for v in adj if len(adj[v])!=2 or len(global_adj[v])!=2}
        unused=set(edges)
        while unused:
            edge=next((e for e in unused if e[0] in stops or e[1] in stops),next(iter(unused)))
            start=edge[0] if edge[0] in stops else edge[1] if edge[1] in stops else edge[0]
            chain=[start]
            vertex=start
            current=edge
            while current in unused:
                unused.remove(current)
                other=current[1] if current[0]==vertex else current[0]
                chain.append(other)
                if other in stops or other==start:
                    break
                next_edges=[e for e in adj[other] if e in unused]
                if len(next_edges)!=1:
                    break
                vertex=other;current=next_edges[0]
            line=LineString(chain)
            # Preserve small holes/projections instead of simplifying them away.
            if line.length>=1. and (not line.is_ring or Polygon(chain).area>=1.):
                candidate=line.simplify(tolerance,preserve_topology=True)
                if candidate.hausdorff_distance(line)<=tolerance+1e-8:
                    line=candidate
            lines.append(line)
    network=unary_union(lines)
    candidate=[]
    for part in polygonize(network):
        # Area ownership is robust to a representative point falling into the
        # narrow boundary strip moved by simplification.
        overlaps=[part.intersection(r['geometry']).area for r in records]
        winner=int(np.argmax(overlaps))
        if overlaps[winner]>0:
            candidate.append({'label':records[winner]['label'],'geometry':part})
    return candidate


def jointly_simplify(records, transform, labels, strong, settings):
    source = [r['geometry'] for r in records]
    diagnostics = []
    # A fixed bounded fallback schedule, not house-specific parameter tuning.
    for tolerance in [settings.simplification_tolerance_m,
                      settings.simplification_tolerance_m*.75,
                      settings.simplification_tolerance_m/2, 0.]:
        candidate = records if tolerance==0 else simplify_shared_network(records,tolerance)
        old={k:unary_union([r['geometry'] for r in records if r['label']==k]) for k in set(r['label'] for r in records)}
        new={k:unary_union([r['geometry'] for r in candidate if r['label']==k]) for k in old}
        displacement=max((old[k].boundary.hausdorff_distance(new[k].boundary) for k in old if k>0),default=0.)
        area_changes=[abs(old[k].area-new[k].area)/old[k].area for k in old if k>0]
        signature=lambda g:(len(polygons(g)),sum(len(p.interiors) for p in polygons(g)))
        topology_retained=all(signature(old[k])==signature(new[k]) for k in old)
        raster = grid_from_records(candidate, transform, labels.shape)
        lost = int(np.count_nonzero(strong & (raster != labels)))
        loss = lost/max(1,int(strong.sum()))
        per_plane_loss=max((np.count_nonzero(strong&(labels==k)&(raster!=k))/
                            max(1,np.count_nonzero(strong&(labels==k))) for k in old if k>0),default=0.)
        # Geometry and exclusions are separate: a candidate outline may cross an
        # unresolved pixel, but the original exclusions are retained separately
        # and subtracted from every effective support geometry below.
        uncertainty_lost = int(np.count_nonzero((labels==0) & (raster>0)))
        accepted = (topology_retained and coverage_valid(candidate) and displacement <= settings.max_boundary_displacement_m+1e-8
                    and max(area_changes,default=0) <= settings.max_component_area_change_fraction
                    and per_plane_loss <= settings.max_strong_support_loss_fraction)
        diagnostics.append({'tolerance_m': tolerance, 'max_displacement_m': displacement,
                            'topology_retained':topology_retained,
                            'max_component_area_change_fraction': max(area_changes,default=0),
                            'strong_support_loss_fraction': loss,
                            'max_per_plane_strong_support_loss_fraction':float(per_plane_loss),
                            'candidate_outline_pixels_requiring_retained_exclusion': uncertainty_lost, 'accepted': bool(accepted)})
        if accepted:
            return candidate, diagnostics
    raise RuntimeError('Original pixel coverage failed its own consistency guards')


def snap_supported_seams(records, plane_models, transform, labels, strong, settings):
    groups = {k: unary_union([r['geometry'] for r in records if r['label']==k])
              for k in sorted(set(r['label'] for r in records))}
    models = {p['id']: np.array(p['coefficients']) for p in plane_models}
    proposals = []
    for a in sorted(models):
        for b in sorted(models):
            if a>=b or a not in groups or b not in groups:
                continue
            length = groups[a].boundary.intersection(groups[b].boundary).length
            if length >= settings.seam_minimum_length_m:
                proposals.append((length,a,b))
    logs = []
    for _, a, b in sorted(proposals, reverse=True):
        shared = groups[a].boundary.intersection(groups[b].boundary)
        ca, cb = models[a], models[b]
        na, nb = np.r_[-ca[:2],1.], np.r_[-cb[:2],1.]
        angle = float(np.degrees(np.arccos(np.clip(na@nb/(np.linalg.norm(na)*np.linalg.norm(nb)),-1,1))))
        normal = ca[:2]-cb[:2]
        norm = np.linalg.norm(normal)
        log = {'labels':[a,b], 'shared_length_m': shared.length, 'normal_angle_degrees':angle, 'accepted':False}
        if norm<1e-9 or angle < settings.seam_minimum_normal_angle_degrees:
            logs.append({**log,'reason':'parallel_or_near_parallel_planes'}); continue
        point = -(ca[2]-cb[2])*normal/(norm**2)
        tangent = np.array([-normal[1],normal[0]])/norm
        extent = max(100.,groups[a].union(groups[b]).length*2)
        line = LineString([point-tangent*extent,point+tangent*extent])
        # One-way sampled distance checks closeness to actual finite shared edge;
        # unrelated plane intersections never create adjacency.
        samples = [shared.interpolate(float(t)) for t in np.linspace(0,shared.length,max(10,int(shared.length/.05)))]
        distance = max((line.distance(p) for p in samples),default=float('inf'))
        log['max_existing_seam_distance_to_intersection_m'] = distance
        if distance > settings.seam_maximum_displacement_m:
            logs.append({**log,'reason':'height_step_or_unsupported_intersection'}); continue
        union = groups[a].union(groups[b])
        pieces = [p for part in polygons(union) for p in split(part,line).geoms if p.area>1e-8]
        new_a, new_b = [], []
        for piece in pieces:
            (new_a if piece.intersection(groups[a]).area >= piece.intersection(groups[b]).area else new_b).append(piece)
        if not new_a or not new_b:
            logs.append({**log,'reason':'intersection_does_not_separate_existing_faces'}); continue
        aa, bb = unary_union(new_a), unary_union(new_b)
        moved = max(groups[a].boundary.hausdorff_distance(aa.boundary),groups[b].boundary.hausdorff_distance(bb.boundary))
        area_change = max(abs(aa.area-groups[a].area)/groups[a].area,abs(bb.area-groups[b].area)/groups[b].area)
        candidate_groups = {**groups,a:aa,b:bb}
        candidate = [{'label':k,'geometry':p} for k,g in candidate_groups.items() for p in polygons(g)]
        # Insert all changed seam endpoints into the unchanged neighboring edges.
        # Original label ownership is retained by representative-point containment.
        noded=[]
        network=unary_union([set_precision(r['geometry'],1e-6).boundary for r in candidate])
        for part in polygonize(network):
            representative=part.representative_point()
            owners=[r for r in candidate if r['geometry'].covers(representative)]
            if owners:
                noded.append({'label':owners[0]['label'],'geometry':part})
        candidate=noded
        raster = grid_from_records(candidate,transform,labels.shape)
        loss = np.count_nonzero(strong & (raster!=labels))/max(1,int(strong.sum()))
        per_plane_loss=max((np.count_nonzero(strong&(labels==k)&(raster!=k))/
                            max(1,np.count_nonzero(strong&(labels==k))) for k in models),default=0.)
        unknown_lost = int(np.count_nonzero((labels==0)&(raster>0)))
        signature=lambda g:(len(polygons(g)),sum(len(p.interiors) for p in polygons(g)))
        topology_retained=signature(groups[a])==signature(aa) and signature(groups[b])==signature(bb)
        accepted = (coverage_valid(candidate) and moved <= settings.max_boundary_displacement_m
                    and area_change <= settings.max_component_area_change_fraction
                    and topology_retained and per_plane_loss <= settings.max_strong_support_loss_fraction)
        logs.append({**log, 'max_displacement_m':moved,'max_area_change_fraction':area_change,
                     'strong_support_loss_fraction':float(loss),'accepted':bool(accepted),
                     'topology_retained':topology_retained,
                     'max_per_plane_strong_support_loss_fraction':float(per_plane_loss),
                     'reason':'bounded_shared_plane_intersection' if accepted else 'consistency_guard_rejected'})
        if accepted:
            groups={k:unary_union([r['geometry'] for r in candidate if r['label']==k]) for k in candidate_groups}
    return [{'label':k,'geometry':p} for k,g in groups.items() for p in polygons(g)], logs


def reconstruct(insights, dsm, mask, transform, crs, settings=Settings()):
    started = time.perf_counter()
    models, origin = google_planes(insights, crs)
    if not models:
        raise ValueError('Google supplied no roof planes; reconstruction withheld')
    yy,xx=np.indices(dsm.shape)
    x,y=transform*(xx+.5,yy+.5)
    x=x-origin[0]; y=y-origin[1]
    from affine import Affine
    local=Affine.translation(-origin[0],-origin[1])*transform
    cc,n=ndi.label(mask>0)
    cx,cy=~local*(0.,0.)
    r,c=int(np.clip(cy,0,dsm.shape[0]-1)),int(np.clip(cx,0,dsm.shape[1]-1))
    target_id=int(cc[r,c])
    if target_id==0:
        # Bounded nearest component, never choose a distant large neighbor.
        distance,indices=ndi.distance_transform_edt(cc==0,return_indices=True)
        if distance[r,c]*abs(local.a) > 3.:
            raise ValueError('No roof-mask component within 3m of Google building center')
        target_id=int(cc[indices[0,r,c],indices[1,r,c]])
    target=cc==target_id
    residual=[]
    for p in models:
        a,b,z=p['coefficients']
        error=abs(dsm-(a*x+b*y+z))
        # Preserve the true projected bounding polygon, not its axis-aligned envelope.
        domain=rasterize([(p['bounds'].buffer(settings.bounding_box_margin_m),1)],out_shape=dsm.shape,
                         transform=local,dtype='uint8').astype(bool)
        error[~domain | ~target | ~np.isfinite(dsm)]=np.inf
        residual.append(error)
    residual=np.array(residual)
    order=np.argsort(residual,axis=0)
    best=np.take_along_axis(residual,order[:1],axis=0)[0]
    second=np.take_along_axis(residual,order[1:2],axis=0)[0] if len(models)>1 else np.full(dsm.shape,np.inf)
    labels=np.where(target,np.where(best<=settings.height_tolerance_m,order[0]+1,0),-1).astype('int32')
    removed=[]
    pixel_area=abs(local.a*local.e-local.b*local.d)
    for identifier in range(1,len(models)+1):
        islands,count=ndi.label(labels==identifier)
        for k in range(1,count+1):
            selected=islands==k
            if selected.sum()*pixel_area < settings.minimum_island_area_m2:
                labels[selected]=0; removed.append({'label':identifier,'area_m2':float(selected.sum()*pixel_area)})
    disconnected=[]
    for p in models:
        components,count=ndi.label(labels==p['id'])
        if not count:
            continue
        cx,cy=p['center_xy']
        nearest=[]
        for identifier in range(1,count+1):
            selected=components==identifier
            distance=float(np.sqrt(((x[selected]-cx)**2+(y[selected]-cy)**2).min()))
            nearest.append((distance,identifier))
        seed_distance,seed_component=min(nearest)
        for distance,identifier in nearest:
            if identifier!=seed_component or seed_distance>settings.maximum_seed_distance_m:
                selected=components==identifier
                labels[selected]=0
                disconnected.append({'label':p['id'],'area_m2':float(selected.sum()*pixel_area),
                                     'distance_to_google_center_m':distance,
                                     'reason':'disconnected_from_google_center_support' if identifier!=seed_component else 'no_support_near_google_center'})
    with np.errstate(invalid='ignore'):
        margin=second-best
    strong=(labels>0)&(best<=settings.strong_height_tolerance_m)&(margin>=settings.strong_margin_m)
    original=records_from_grid(labels,target,local)
    if not coverage_valid(original):
        raise RuntimeError('Source assignment is not a valid edge-matched coverage')
    clean,simplification=jointly_simplify(original,local,labels,strong,settings)
    clean,seams=snap_supported_seams(clean,models,local,labels,strong,settings)
    candidate_grid=grid_from_records(clean,local,labels.shape)
    cleaned=candidate_grid.copy()
    cleaned[~target]=-1
    cleaned[target & (labels==0)]=0
    for p in models:
        a,b,c=p['coefficients']
        supported=np.isfinite(dsm)&(abs(dsm-(a*x+b*y+c))<=settings.height_tolerance_m)
        cleaned[(cleaned==p['id'])&~supported]=0
    exclusions=records_from_grid(np.where(target & (cleaned<=0),0,-1),target & (cleaned<=0),local)
    excluded=unary_union([r['geometry'] for r in exclusions])
    target_geometry=unary_union([r['geometry'] for r in original])
    effective=[]
    for r in clean:
        if r['label']>0:
            for part in polygons(r['geometry'].intersection(target_geometry).difference(excluded)):
                effective.append({'label':r['label'],'geometry':part})
    return {'models':models,'origin':origin,'local_transform':local,'labels':labels,
            'cleaned_labels':cleaned,'candidate_labels':candidate_grid,'target':target,'strong':strong,'residual_m':best,
            'raw_records':original,'records':clean,'exclusions':exclusions,'effective_records':effective,
            'diagnostics':{'settings':asdict(settings),'seconds':time.perf_counter()-started,
                           'removed_support_islands':removed,'simplification':simplification,'seam_proposals':seams,
                           'disconnected_support_withheld':disconnected,
                           'plane_measurements_changed':False,'inferred_planes':0,
                           'original_target_area_m2':float(target.sum()*pixel_area),
                           'raw_unresolved_area_m2':float(((labels==0)&target).sum()*pixel_area),
                           'cleaned_coverage_valid':coverage_valid(clean),
                           'unresolved_pixels_assigned':int(np.count_nonzero((labels==0)&target&(cleaned>0))),
                           'effective_support_overlap_with_exclusions_m2':sum(r['geometry'].intersection(excluded).area for r in effective),
                           'strong_support_pixels_changed':int(np.count_nonzero(strong&(labels!=cleaned)))}}
