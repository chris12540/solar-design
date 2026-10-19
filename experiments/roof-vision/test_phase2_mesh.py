import unittest
import numpy as np
from shapely.geometry import Point, Polygon
from phase2_mesh import build_mesh


def face(identifier, ring, a=0., b=0., c=5., holes=(), **extra):
    return {'id':identifier, 'plane_model':{'a':a,'b':b,'c':c},
            'parts':[{'polygon':ring,'holes':list(holes)}], 'role':'main_roof', 'level_id':'upper', **extra}


class PresentationMeshTests(unittest.TestCase):
    def test_hole_is_not_triangulated_or_extruded_to_ground(self):
        ring=[[-2,-2],[2,-2],[2,2],[-2,2]]
        hole=[[-1,-1],[-1,1],[1,1],[1,-1]]
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[face('parent',ring,holes=[hole])]})
        self.assertAlmostEqual(mesh['quality']['roof_projected_area_m2'],12.)
        self.assertAlmostEqual(mesh['quality']['triangulated_roof_projected_area_m2'],12.)
        self.assertTrue(all(max(abs(w['xy'][0][0]),abs(w['xy'][0][1]))>=1.99 for w in mesh['wall_records']))

    def test_shared_gable_ridge_does_not_become_internal_wall(self):
        west=face('west',[[-2,-1],[0,-1],[0,1],[-2,1]],a=.5)
        east=face('east',[[0,-1],[2,-1],[2,1],[0,1]],a=-.5)
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[west,east]})
        bad=[w for w in mesh['wall_records'] if all(abs(p[0])<1e-9 for p in w['xy'])]
        self.assertEqual(bad,[])
        self.assertAlmostEqual(mesh['quality']['roof_projected_area_m2'],8.)

    def test_dormer_walls_stop_at_parent_plane(self):
        hole=[[-.5,-.5],[-.5,.5],[.5,.5],[.5,-.5]]
        parent=face('parent',[[-2,-2],[2,-2],[2,2],[-2,2]],a=.1,c=3.,holes=[hole])
        child=face('child',hole,c=4.,parent_face_id='parent')
        child['role']='dormer_roof'
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[parent,child]})
        cheeks=[w for w in mesh['wall_records'] if w['kind']=='dormer_cheek']
        self.assertTrue(cheeks)
        for wall in cheeks:
            for point,z in zip(wall['xy'],wall['base_source_z_m']):
                self.assertAlmostEqual(z,.1*point[0]+3.)
        self.assertAlmostEqual(mesh['quality']['roof_projected_area_m2'],16.)

    def test_dormer_sibling_ridge_does_not_descend_to_parent(self):
        cut=[[-1,-1],[-1,1],[1,1],[1,-1]]
        parent=face('parent',[[-3,-3],[3,-3],[3,3],[-3,3]],c=3.,holes=[cut])
        west=face('west',[[-1,-1],[0,-1],[0,1],[-1,1]],a=.5,c=5.,parent_face_id='parent')
        east=face('east',[[0,-1],[1,-1],[1,1],[0,1]],a=-.5,c=5.,parent_face_id='parent')
        west['role']=east['role']='dormer_roof'
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[parent,west,east]})
        self.assertFalse(any(all(abs(p[0])<1e-9 for p in wall['xy']) for wall in mesh['wall_records']))

    def test_step_wall_stops_at_lower_sibling_not_parent(self):
        cut=[[-1,-1],[-1,1],[1,1],[1,-1]]
        parent=face('parent',[[-3,-3],[3,-3],[3,3],[-3,3]],c=3.,holes=[cut])
        west=face('west',[[-1,-1],[0,-1],[0,1],[-1,1]],c=5.,parent_face_id='parent')
        east=face('east',[[0,-1],[1,-1],[1,1],[0,1]],c=4.5,parent_face_id='parent')
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[parent,west,east]})
        shared=[wall for wall in mesh['wall_records'] if all(abs(p[0])<1e-9 for p in wall['xy'])]
        self.assertTrue(shared)
        self.assertTrue(all(w['face_id']=='west' and w['base_source_z_m']==[4.5,4.5] for w in shared))

    def test_roof_normals_up_and_wall_normals_outward_for_clockwise_input(self):
        ring=[[-2,-1],[-2,1],[2,1],[2,-1]]
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[face('box',ring)]})
        polygon=Polygon(ring)
        for indices,surface in zip(mesh['triangles'],mesh['surfaces']):
            points=np.asarray([mesh['vertices'][i] for i in indices])
            normal=np.cross(points[1]-points[0],points[2]-points[0])
            if surface['kind']=='roof':
                self.assertGreater(normal[2],0.)
            else:
                center=points.mean(axis=0);normal/=np.linalg.norm(normal)
                self.assertFalse(polygon.contains(Point(center[:2]+normal[:2]*.01)))

    def test_dormer_cut_does_not_remove_body_wall_or_add_hidden_roof_area(self):
        base=Polygon([[-2,-2],[2,-2],[2,2],[-2,2]])
        footprint=Polygon([[-3,-.5],[-1,-.5],[-1,.5],[-3,.5]])
        exposed=base.difference(footprint)
        parent=face('parent',list(exposed.exterior.coords),c=3.)
        parent['supporting_parts']=[{'polygon':list(base.exterior.coords),'holes':[]}]
        child=face('child',list(footprint.exterior.coords),c=4.,parent_face_id='parent')
        mesh=build_mesh({'ground_z_m':0.,'roof_faces':[parent,child]})
        self.assertAlmostEqual(mesh['quality']['roof_projected_area_m2'],17.)
        self.assertTrue(any(w['face_id']=='parent' and all(abs(p[0]+2)<1e-9 for p in w['xy'])
                            and abs(sum(p[1] for p in w['xy'])/2)<.5 for w in mesh['wall_records']))


if __name__=='__main__':unittest.main()
