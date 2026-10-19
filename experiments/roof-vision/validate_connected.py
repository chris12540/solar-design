"""Independent diagnostics for experimental connected roof output."""
from pathlib import Path
import json
import pickle
import numpy as np
from affine import Affine
from pyproj import Transformer
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from rasterio.io import MemoryFile
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling

ROOT=Path(__file__).resolve().parent


def validate():
    result=json.loads((ROOT/'outputs/connected-roof.json').read_text())
    source=pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    raw=source['raw'];aligned=source['aligned'];h,w=aligned['rgb'].shape[:2]
    groups=result['face_groups']
    shapes=[]
    for face in groups:
        parts=[Polygon(p['polygon'],p.get('holes',[])) for p in face['parts']]
        if not all(p.is_valid and not p.is_empty for p in parts):
            raise ValueError(f'Invalid output geometry: {face["id"]}')
        shapes.append(unary_union(parts))
    roof=unary_union(shapes)
    overlap=sum(p.area for p in shapes)-roof.area
    if overlap > 1e-6:
        raise ValueError(f'Overlapping roof faces: {overlap}')
    outline=Polygon(raw['roof_outline']['polygon'],raw['roof_outline'].get('holes',[]))
    protected=[Polygon(hole) for hole in raw['roof_outline'].get('holes',[])]
    protected.extend(Polygon(o['polygon'],o.get('holes',[])) for o in raw.get('obstruction_candidates',[]))
    protected_area=roof.intersection(unary_union(protected)).area if protected else 0.
    represented={p for g in groups for p in g.get('source_plane_ids',[])}
    expected={p for g in raw['refinement']['face_groups'] for p in g['source_plane_ids']}
    model_by_plane={p:g['plane_model'] for g in raw['refinement']['face_groups'] for p in g['source_plane_ids']}
    local=aligned['transform'];origin=raw['origin']
    ox,oy=Transformer.from_crs(4326,origin['crs'],always_xy=True).transform(origin['longitude'],origin['latitude'])
    world=Affine.translation(ox,oy)*local
    dsm=np.full((h,w),np.nan,np.float32)
    with MemoryFile(source['inputs']['dsm']) as mem,mem.open() as src:
        reproject(src.read(1),dsm,src_transform=src.transform,src_crs=src.crs,
            dst_transform=world,dst_crs=origin['crs'],src_nodata=src.nodata,dst_nodata=np.nan,
            resampling=Resampling.bilinear)
    rr,cc=np.indices((h,w));xx=local.a*(cc+.5)+local.b*(rr+.5)+local.c
    yy=local.d*(cc+.5)+local.e*(rr+.5)+local.f
    per_face=[];all_errors=[];interior_errors=[]
    for face,shape in zip(groups,shapes):
        ids=face.get('source_plane_ids',[])
        model=face.get('plane_model') or model_by_plane[ids[0]]
        residual=dsm-(model['a']*xx+model['b']*yy+model['c'])
        mask=rasterize([(shape,1)],out_shape=(h,w),transform=local,dtype='uint8').astype(bool)
        interior=shape.buffer(-.3)
        imask=rasterize([(interior,1)],out_shape=(h,w),transform=local,dtype='uint8').astype(bool) if not interior.is_empty else np.zeros((h,w),bool)
        valid=np.isfinite(dsm)&(dsm!=-9999)
        errors=residual[mask&valid];ie=residual[imask&valid]
        all_errors.extend(errors.tolist());interior_errors.extend(ie.tolist())
        per_face.append({'id':face['id'],'area_m2':shape.area,
            'all_point_height_rmse_m':float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            'interior_height_rmse_m':float(np.sqrt(np.mean(ie**2))) if len(ie) else None,
            'interior_exclusion_m':.3})
    shared=[]
    for i,a in enumerate(shapes):
        for j,b in enumerate(shapes[i+1:],i+1):
            length=a.boundary.intersection(b.boundary).length
            if length>.05: shared.append({'faces':[groups[i]['id'],groups[j]['id']],'length_m':length})
    by_id={face['id']:shape for face,shape in zip(groups,shapes)}
    phantom_length=0.
    declared={identifier:[] for identifier in by_id}
    for edge in result.get('edges',[]):
        line=LineString(edge['coordinates'])
        for identifier in edge['face_ids']:
            phantom_length+=line.difference(by_id[identifier].boundary.buffer(1e-7)).length
            declared[identifier].append(line)
    undeclared_length=sum(shape.boundary.difference(unary_union(declared[identifier]).buffer(1e-7)).length
                          for identifier,shape in by_id.items())
    report={'faces':len(groups),'valid_geometry':True,'overlap_area_m2':overlap,
        'declared_edge_off_boundary_length_m':phantom_length,
        'undeclared_boundary_length_m':undeclared_length,
        'protected_area_filled_m2':protected_area,'missing_source_planes':sorted(expected-represented),
        'outline_iou':roof.intersection(outline).area/roof.union(outline).area,
        'coverage_fraction':roof.intersection(outline).area/outline.area,
        'all_point_height_rmse_m':float(np.sqrt(np.mean(np.array(all_errors)**2))) if all_errors else None,
        'interior_height_rmse_m':float(np.sqrt(np.mean(np.array(interior_errors)**2))) if interior_errors else None,
        'interior_exclusion_m':.3,'per_face':per_face,'shared_boundaries':shared,
        'design_ready':False,'source_expires_at':source['expires_at'],
        'limitations':['Independent diagnostic code, but same source data; not independent accuracy validation.',
            'Interior errors exclude a 0.3m band; all-point error remains reported.',
            'Source plane fits do not establish true roof heights or permit compliance.']}
    (ROOT/'outputs/connected-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_face','shared_boundaries','limitations')},indent=2))
    failures=[]
    if protected_area>1e-6: failures.append('Protected exclusions filled')
    if expected-represented: failures.append('Source planes missing')
    if phantom_length>1e-6 or undeclared_length>1e-6: failures.append('Declared edges differ from final boundaries')
    if failures: raise ValueError('; '.join(failures))


if __name__=='__main__':
    validate()
