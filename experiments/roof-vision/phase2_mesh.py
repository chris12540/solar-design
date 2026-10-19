"""Create an illustrative 3D mesh from structural roof surfaces, not image pixels."""
from pathlib import Path
import json
import math
import re
import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon, Point
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent


def height(face, x, y):
    plane = face['plane_model']
    return plane['a']*x + plane['b']*y + plane['c']


def geometry(face):
    polygons = [Polygon(part['polygon'], part.get('holes', [])) for part in face['parts']]
    if any(not p.is_valid or p.is_empty for p in polygons):
        raise ValueError(f'Invalid roof geometry: {face["id"]}')
    return unary_union(polygons)


def build_mesh(model, wall_sample_m=.75):
    ground = float(model['ground_z_m'])
    if not math.isfinite(ground):
        raise ValueError('An explicit, finite estimated ground height is required')
    faces = model['roof_faces']
    by_id = {face['id']:face for face in faces}
    shapes = {face['id']:geometry(face) for face in faces}
    vertices, triangles, surfaces, walls = [], [], [], []
    skipped = []

    def triangle(points, face, kind):
        points = np.asarray(points, dtype=float)
        if not np.isfinite(points).all():
            raise ValueError('Nonfinite mesh coordinates')
        if np.linalg.norm(np.cross(points[1]-points[0], points[2]-points[0])) < 1e-9:
            return
        start = len(vertices)
        vertices.extend(points.tolist())
        triangles.append([start, start+1, start+2])
        surfaces.append({'face_id':face['id'], 'kind':kind,
                         'role':face.get('role', 'unresolved_context'),
                         'level_id':face.get('level_id'),
                         'hypothesis_status':face.get('hypothesis_status', 'unverified')})

    roof_area = 0.
    projected_triangle_area = 0.
    for face in faces:
        geom = shapes[face['id']]
        roof_area += geom.area
        polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        for poly in polygons:
            for part in constrained_delaunay_triangles(poly).geoms:
                if not poly.covers(part):
                    raise ValueError('Roof triangulation crossed a cutout')
                xy = list(part.exterior.coords)[:3]
                points = [[x, y, height(face, x, y)-ground] for x,y in xy]
                if np.cross(np.asarray(points[1])-points[0], np.asarray(points[2])-points[0])[2] < 0:
                    points[1], points[2] = points[2], points[1]
                triangle(points, face, 'roof')
                projected_triangle_area += part.area
    if abs(projected_triangle_area-roof_area) > 1e-6:
        raise ValueError('Roof triangles do not preserve exposed projected area')

    for face in faces:
        if face.get('role') == 'unresolved_context':
            continue
        geom = geometry({**face,'parts':face['supporting_parts']}) if face.get('supporting_parts') else shapes[face['id']]
        polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        for poly in polygons:
            # Interior rings represent roof cuts, not automatically courtyards.
            # Child roofs supply their own cheek walls; unknown objects get no
            # invented wall height or below-roof cavity.
            ring = list(orient(poly, sign=1.).exterior.coords)
            for begin, end in zip(ring[:-1], ring[1:]):
                a, b = np.asarray(begin), np.asarray(end)
                count = max(1, math.ceil(np.linalg.norm(b-a)/wall_sample_m))
                for index in range(count):
                    p = a+(b-a)*index/count
                    q = a+(b-a)*(index+1)/count
                    mid = (p+q)/2
                    top = np.array([height(face, *p), height(face, *q)])
                    parent = by_id.get(face.get('parent_face_id'))
                    base = np.array([ground, ground])
                    kind = 'exterior_wall'
                    neighbors = [other for other in faces if other['id'] != face['id']
                                 and other.get('parent_face_id') != face['id']
                                 and shapes[other['id']].buffer(.015).covers(Point(mid))]
                    continuous = [other for other in neighbors
                                  if max(abs(height(other,*p)-top[0]),abs(height(other,*q)-top[1]))<=.08]
                    above = [other for other in neighbors if height(other,*mid)>height(face,*mid)+.08]
                    if continuous or above:
                        continue
                    lower = [other for other in neighbors if height(other,*mid)<height(face,*mid)-.08]
                    if lower:
                        support = max(lower,key=lambda other:height(other,*mid))
                        base = np.array([height(support,*p),height(support,*q)])
                        kind = 'dormer_cheek' if parent is support else 'level_step_wall'
                    elif parent is not None:
                        base = np.array([height(parent, *p), height(parent, *q)])
                        kind = 'dormer_cheek'
                    if np.any(base > top+.08):
                        skipped.append({'face_id':face['id'], 'reason':'base_crosses_roof', 'xy':[p.tolist(),q.tolist()]})
                        continue
                    base = np.minimum(base, top)
                    if np.max(top-base) < .02:
                        continue
                    v = [[*p, top[0]-ground], [*q, top[1]-ground],
                         [*q, base[1]-ground], [*p, base[0]-ground]]
                    triangle([v[0],v[2],v[1]], face, kind)
                    triangle([v[0],v[3],v[2]], face, kind)
                    walls.append({'face_id':face['id'], 'kind':kind, 'xy':[p.tolist(),q.tolist()],
                                  'top_source_z_m':top.tolist(), 'base_source_z_m':base.tolist()})

    return {
        'algorithm_version':'structural-presentation-mesh-1',
        'coordinate_system':'Local projected x/y meters; z meters above estimated local ground',
        'ground_source_z_m':ground, 'vertices':vertices, 'triangles':triangles,
        'surfaces':surfaces, 'wall_records':walls,
        'quality':{'roof_projected_area_m2':roof_area,
                   'triangulated_roof_projected_area_m2':projected_triangle_area,
                   'roof_triangle_count':sum(s['kind']=='roof' for s in surfaces),
                   'wall_triangle_count':sum(s['kind']!='roof' for s in surfaces),
                   'omitted_inverted_wall_segments':skipped},
        'presentation_only':True, 'design_ready':False,
        'unknowns':['Ground elevation and wall positions are estimated, not measured architecture.',
                    'Roof eaves include overhangs; extruded walls are illustrative.',
                    'Unresolved roof hypotheses remain unresolved in this mesh.',
                    'No invented obstruction heights, panels, pathways or AHJ compliance.'],
        'source_expires_at':model.get('provenance',{}).get('source_expires_at')
                             or model.get('provenance',{}).get('expires_at')
    }


def export_obj(mesh, path):
    text = ['# Experimental structural roof presentation; not a design approval',
            f'# Source expiry: {mesh["source_expires_at"]}',
            '# z is above estimated ground; walls and ground are approximate']
    text.extend(f'v {x:.6f} {y:.6f} {z:.6f}' for x,y,z in mesh['vertices'])
    previous = None
    for tri, surface in zip(mesh['triangles'], mesh['surfaces']):
        group = re.sub(r'[^a-zA-Z0-9_-]', '_', surface['face_id']+'_'+surface['kind'])
        if group != previous:
            text.append('g '+group)
            previous = group
        text.append('f '+' '.join(str(i+1) for i in tri))
    path.write_text('\n'.join(text)+'\n')


def main():
    model = json.loads((ROOT/'outputs/phase2-structure.json').read_text())
    mesh = build_mesh(model)
    (ROOT/'outputs/phase2-house-mesh.json').write_text(json.dumps(mesh,indent=2))
    export_obj(mesh, ROOT/'outputs/phase2-house.obj')
    print(json.dumps({'vertices':len(mesh['vertices']), 'triangles':len(mesh['triangles']),
                      'quality':mesh['quality']},indent=2))


if __name__ == '__main__':
    main()
