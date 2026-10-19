"""Structural hypotheses: topology, height steps, and parent occlusion."""
import unittest
import numpy as np
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
from phase2_structure import analytic_gable,cut_parent_surface,make_face,apply_features,part_geometry,plane_z,source_exclusions,structural_child_primitives

class StructuralPrimitiveTests(unittest.TestCase):
    def test_gable_analytic_ridge_is_exact_and_finite(self):
        a={'a':.4,'b':0.,'c':12.};b={'a':-.4,'b':0.,'c':12.}
        left,right,frame=analytic_gable(a,b,(-4,4),(-6,6))
        ridge=LineString(frame['ridge_endpoints'])
        self.assertLess(left.intersection(right).area,1e-10)
        self.assertLess(left.boundary.intersection(right.boundary).symmetric_difference(ridge).length,1e-10)
        self.assertEqual(len(left.exterior.coords)-1,4)
        self.assertEqual(len(right.exterior.coords)-1,4)
        for p in frame['ridge_endpoints']:self.assertAlmostEqual(plane_z(a,np.asarray(p)),plane_z(b,np.asarray(p)))
        with self.assertRaises(ValueError):analytic_gable(a,{'a':.3999,'b':0.,'c':0.},(-4,4),(-6,6))

    def test_height_step_keeps_distinct_plane_heights_and_levels(self):
        a=make_face('upper',['source-a'],{'a':.1,'b':0.,'c':10.},Polygon([(0,0),(4,0),(4,4),(0,4)]),'lower_roof','upper-level')
        b=make_face('lower',['source-b'],{'a':.1,'b':0.,'c':8.},Polygon([(4,0),(7,0),(7,4),(4,4)]),'lower_roof','lower-level')
        faces,_,_=apply_features([a,b],{})
        self.assertEqual(len(faces),2)
        self.assertNotEqual(faces[0]['level_id'],faces[1]['level_id'])
        p=np.array([4.,2.]);self.assertAlmostEqual(plane_z(faces[0]['plane_model'],p)-plane_z(faces[1]['plane_model'],p),2.)
        self.assertEqual(part_geometry(faces[0]['parts']).intersection(part_geometry(faces[1]['parts'])).area,0.)

    def test_dormer_explicitly_removes_parent_and_never_double_counts(self):
        parent=Polygon([(0,0),(10,0),(10,8),(0,8)])
        footprint=Polygon([(2,2),(6,2),(6,5),(2,5)])
        child_a=Polygon([(2,2),(4,2),(4,5),(2,5)]);child_b=Polygon([(4,2),(6,2),(6,5),(4,5)])
        remaining,children=cut_parent_surface(parent,footprint,[child_a,child_b])
        self.assertEqual(remaining.intersection(footprint).area,0.)
        self.assertAlmostEqual(sum(p.area for p in children)+remaining.area,parent.area)
        self.assertAlmostEqual(unary_union([remaining]+children).area,parent.area)
        self.assertEqual(len(remaining.interiors),1)
        # A partial child must leave occluded unknown footprint unused as well.
        partial,_=cut_parent_surface(parent,footprint,[child_a])
        self.assertEqual(partial.intersection(footprint).area,0.)

    def test_wrong_remote_parent_hint_cannot_attach_child_to_main(self):
        main=make_face('main',['group-main'],{'a':0.,'b':0.,'c':15.},Polygon([(10,0),(18,0),(18,8),(10,8)]),'main_roof','upper')
        lower=make_face('wing',['group-wing'],{'a':0.,'b':0.,'c':10.},Polygon([(0,0),(8,0),(8,8),(0,8)]),'lower_roof','lower')
        footprint=[[2,2],[4,2],[4,4],[2,4],[2,2]]
        records={'features':[{'id':'candidate','type':'dormer_candidate','parent_group_id':'group-main','footprint':footprint,'roof_planes':[{'plane_model':{'a':.4,'b':0.,'c':9.8},'support_polygon':[[2,2],[3,2],[3,4],[2,4],[2,2]]},{'plane_model':{'a':-.4,'b':0.,'c':12.2},'support_polygon':[[3,2],[4,2],[4,4],[3,4],[3,2]]}]}]}
        faces,features,_=apply_features([main,lower],records)
        self.assertEqual(features[0]['parent_face_id'],'wing')
        self.assertTrue(features[0]['parent_cutout_applied'])
        self.assertAlmostEqual(part_geometry(next(f for f in faces if f['id']=='main')['parts']).area,64.)
        self.assertAlmostEqual(part_geometry(next(f for f in faces if f['id']=='main')['supporting_parts']).area,64.)
        self.assertEqual(part_geometry(next(f for f in faces if f['id']=='wing')['parts']).intersection(Polygon(footprint)).area,0.)
        geometries=[part_geometry(f['parts']) for f in faces]
        self.assertAlmostEqual(sum(p.area for p in geometries),unary_union(geometries).area)

    def test_main_supporting_parts_retain_body_after_dormer_cutout(self):
        parent=make_face('parent',['source'],{'a':.1,'b':0.,'c':9.5},Polygon([(0,0),(8,0),(8,8),(0,8)]),'main_roof','upper')
        feature={'id':'child','type':'dormer_candidate','parent_group_id':'source','footprint':[[2,2],[4,2],[4,5],[2,5],[2,2]],'roof_planes':[
            {'plane_model':{'a':.4,'b':0.,'c':9.8},'support_polygon':[[2,2],[3.2,2],[3.2,5],[2,5],[2,2]]},
            {'plane_model':{'a':-.4,'b':0.,'c':12.2},'support_polygon':[[2.8,2],[4,2],[4,5],[2.8,5],[2.8,2]]}]}
        faces,features,_=apply_features([parent],{'features':[feature]})
        cut_parent=next(f for f in faces if f['id']=='parent')
        support=part_geometry(cut_parent['supporting_parts']);visible=part_geometry(cut_parent['parts'])
        self.assertAlmostEqual(support.area,64.)
        self.assertLess(visible.area,support.area)
        self.assertAlmostEqual(visible.intersection(Polygon(features[0]['footprint'])).area,0.)
        self.assertEqual(parent['parts'],parent['supporting_parts'])
        self.assertNotEqual(cut_parent['parts'],cut_parent['supporting_parts'])

    def test_child_hull_seam_is_replaced_by_exact_analytic_ridge(self):
        parent=make_face('parent',['source'],{'a':.1,'b':0.,'c':9.5},Polygon([(0,0),(8,0),(8,8),(0,8)]),'main_roof','upper')
        feature={'footprint':[[2,2],[4,2],[4,5],[2,5],[2,2]],'roof_planes':[
            {'plane_model':{'a':.4,'b':0.,'c':9.8},'support_polygon':[[2,2],[3.2,2],[3.2,5],[2,5],[2,2]]},
            {'plane_model':{'a':-.4,'b':0.,'c':12.2},'support_polygon':[[2.8,2],[4,2],[4,5],[2.8,5],[2.8,2]]}]}
        footprint,planes,evidence=structural_child_primitives(feature,parent)
        shared=planes[0][1].boundary.intersection(planes[1][1].boundary)
        self.assertGreater(shared.length,2.)
        self.assertEqual(planes[0][1].intersection(planes[1][1]).area,0.)
        self.assertLess(evidence['continuous_ridge_max_z_disagreement_m'],1e-9)
        for point in shared.coords:
            self.assertAlmostEqual(point[0],3.)
            self.assertAlmostEqual(plane_z(planes[0][0],np.asarray(point)),plane_z(planes[1][0],np.asarray(point)))
        for model,geometry in planes:
            for point in geometry.exterior.coords:self.assertGreaterEqual(plane_z(model,np.asarray(point))-plane_z(parent['plane_model'],np.asarray(point)),-1e-9)

    def test_established_holes_and_separate_buildings_survive(self):
        raw={'roof_outline':{'holes':[[[2,2],[4,2],[4,4],[2,4],[2,2]]]}}
        first=Polygon([(0,0),(6,0),(6,6),(0,6)])
        second=Polygon([(10,0),(14,0),(14,4),(10,4)])
        for hole in source_exclusions(raw):first=first.difference(hole);second=second.difference(hole)
        union=first.union(second)
        self.assertEqual(len(union.geoms),2)
        self.assertEqual(len(first.interiors),1)
        self.assertEqual(first.intersection(Polygon(raw['roof_outline']['holes'][0])).area,0.)

if __name__=='__main__':unittest.main()
