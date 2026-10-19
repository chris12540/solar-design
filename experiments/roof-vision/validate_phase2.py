"""Independent invariants and source-consistency checks for structural output."""
from pathlib import Path
import hashlib
import json
import pickle
import numpy as np
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from rasterio.features import rasterize

ROOT=Path(__file__).resolve().parent


def shape(parts):
    return unary_union([Polygon(p['polygon'],p.get('holes',[])) for p in parts])


def main():
    source=pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    model=json.loads((ROOT/'outputs/phase2-structure.json').read_text())
    mesh=json.loads((ROOT/'outputs/phase2-house-mesh.json').read_text())
    fields=np.load(ROOT/'outputs/phase1-alignment-fields.npz')
    baseline=json.loads((ROOT/'outputs/phase1-alignment.json').read_text())
    faces=model['roof_faces'];by_id={f['id']:f for f in faces}
    shapes={f['id']:shape(f['parts']) for f in faces}
    assert all(g.is_valid and not g.is_empty for g in shapes.values())
    overlap=sum(g.area for g in shapes.values())-unary_union(list(shapes.values())).area
    assert overlap<1e-6
    candidates=[c for c in model['candidate_models'] if c.get('roof_faces')]
    selected=[c for c in candidates if c.get('selected')]
    assert len(selected)==1 and selected[0]['roof_faces']==faces
    for candidate in candidates:
        geoms=[shape(face['parts']) for face in candidate['roof_faces']]
        assert all(g.is_valid and not g.is_empty for g in geoms)
        assert sum(g.area for g in geoms)-unary_union(geoms).area<1e-6
    cuts=[];joins=[]
    for feature in model['features']:
        if feature.get('parent_cutout_applied'):
            assert by_id[feature['parent_face_id']].get('supporting_parts')
    for parent in faces:
        if not parent.get('supporting_parts'):continue
        children=[f for f in model['features'] if f.get('parent_face_id')==parent['id'] and f.get('parent_cutout_applied')]
        before=shape(parent['supporting_parts']);after=shapes[parent['id']]
        child_geometry=unary_union([Polygon(f['footprint']) for f in children])
        removed=before.difference(after)
        expected=before.intersection(child_geometry)
        assert removed.symmetric_difference(expected).area<1e-6
        assert after.intersection(child_geometry).area<1e-6
        cuts.append({'parent_id':parent['id'],'occluded_parent_projected_area_m2':removed.area})
    for feature in model['features']:
        identifiers=feature.get('roof_face_ids',[])
        if feature.get('parent_cutout_applied'):
            assert identifiers
            assert Polygon(feature['footprint']).symmetric_difference(unary_union([shapes[i] for i in identifiers])).area<1e-6
        for index,a in enumerate(identifiers):
            for b in identifiers[index+1:]:
                seam=shapes[a].boundary.intersection(shapes[b].boundary)
                if seam.length<1e-6:continue
                samples=[seam.interpolate(float(t),normalized=True) for t in np.linspace(0,1,25)]
                def z(face,p):
                    m=face['plane_model'];return m['a']*p.x+m['b']*p.y+m['c']
                discrepancy=max(abs(z(by_id[a],p)-z(by_id[b],p)) for p in samples)
                assert discrepancy<1e-5
                joins.append({'faces':[a,b],'length_m':seam.length,'max_height_disagreement_m':discrepancy})
    vertices=np.asarray(mesh['vertices'])
    assert np.isfinite(vertices).all() and np.max(np.abs(vertices))<1000
    roof_normals=[];inward=0
    for indices,surface in zip(mesh['triangles'],mesh['surfaces']):
        points=vertices[indices];normal=np.cross(points[1]-points[0],points[2]-points[0])
        if surface['kind']=='roof':roof_normals.append(float(normal[2]));continue
        face=by_id[surface['face_id']]
        domain=shape(face.get('supporting_parts') or face['parts'])
        probe=points.mean(axis=0)[:2]+normal[:2]/np.linalg.norm(normal)*.001
        inward+=int(domain.contains(Point(probe)))
    assert min(roof_normals)>0 and inward==0
    assert abs(mesh['quality']['roof_projected_area_m2']-sum(g.area for g in shapes.values()))<1e-6
    assert mesh['source_expires_at']==source['expires_at']
    input_hash=hashlib.sha256((ROOT/'data/inputs.pkl').read_bytes()).hexdigest()
    assert input_hash==baseline['source_input_sha256']

    dsm=fields['dsm_m'];local=source['aligned']['transform'];h,w=dsm.shape
    yy,xx=np.indices(dsm.shape);x=local.a*(xx+.5)+local.c;y=local.e*(yy+.5)+local.f
    all_errors=[];interior_errors=[]
    for face in faces:
        geom=shapes[face['id']];m=face['plane_model']
        residual=dsm-(m['a']*x+m['b']*y+m['c'])
        for domain,target in [(geom,all_errors),(geom.buffer(-.3),interior_errors)]:
            if domain.is_empty:continue
            mask=rasterize([(domain,1)],out_shape=(h,w),transform=local,dtype='uint8').astype(bool)
            target.extend(residual[mask&np.isfinite(dsm)].tolist())
    reference=json.loads((ROOT/'phase1-reference.json').read_text())
    main=[f for f in faces if f['role']=='main_roof']
    main_outline=unary_union([shapes[f['id']] for f in main]).boundary
    main_ridge=shapes[main[0]['id']].boundary.intersection(shapes[main[1]['id']].boundary)
    photo_checks=[]
    for line in reference['lines']:
        if line['id'] not in ('R1','E1','E2','E3'):continue
        a,b=np.asarray(line['xy'],float)
        samples=[Point(local*tuple(a+(b-a)*t+.5)) for t in np.linspace(.15,.85,50)]
        boundary=main_ridge if line['id']=='R1' else main_outline
        distances=[p.distance(boundary) for p in samples]
        photo_checks.append({'reference_id':line['id'],'median_distance_m':float(np.median(distances)),
                             'max_distance_m':max(distances),'scope':'Central70%ofdraftphotoannotation;notmeasuredaccuracy'})
    report={
        'valid_geometry':True,'visible_face_overlap_m2':overlap,'candidate_count':len(candidates),
        'selected_candidate_matches_export':True,'parent_cutouts':cuts,'child_ridges':joins,
        'roof_triangles_point_up':True,'inward_wall_triangle_count':inward,
        'projected_roof_area_preserved':True,'all_point_height_rmse_m':float(np.sqrt(np.mean(np.asarray(all_errors)**2))),
        'interior_height_rmse_m':float(np.sqrt(np.mean(np.asarray(interior_errors)**2))),
        'photo_reference_checks':photo_checks,'source_input_unchanged':True,'source_input_sha256':input_hash,
        'source_expires_at':source['expires_at'],'design_ready':False,
        'limits':['Checks use cached source data and draft photo annotations, not surveyed roof truth.',
                  'Walls and ground are approximate; a complete or watertight building is not claimed.',
                  'Small southern main-roof dormer and obstruction completeness remain unresolved.']}
    (ROOT/'outputs/phase2-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
