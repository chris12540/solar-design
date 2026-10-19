"""Synthetic invariants for the finite shared-boundary graph."""
import unittest
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from connected_roof import boundary_chains, fit_connected, fuse_labels, _pieces, _polygons


class ConnectedRoofTests(unittest.TestCase):
    def test_gable_exact_shared_ridge_and_no_overlap(self):
        labels=np.zeros((45,60),np.int32)
        for y in range(5,40):
            ridge=25+y//8
            labels[y,5:ridge]=1; labels[y,ridge:55]=2
        groups,chains,q=fit_connected(labels,tolerance=1.5)
        self.assertEqual(set(groups),{1,2})
        self.assertLess(groups[1].intersection(groups[2]).area,1e-9)
        shared=groups[1].boundary.intersection(groups[2].boundary)
        declared=unary_union([LineString(c['points']) for c in chains if c['pair']==(1,2)])
        self.assertLess(shared.symmetric_difference(declared).length,1e-8)
        self.assertLess(sum(len(c['points']) for c in chains if c['pair']==(1,2)),10)
        self.assertTrue(all(g.is_valid for g in groups.values()))

    def test_courtyard_and_separate_building_preserved(self):
        labels=np.zeros((60,90),np.int32)
        labels[5:50,5:55]=1;labels[5:50,30:55]=2
        labels[18:33,20:40]=0
        labels[15:42,68:83]=3
        groups,_,q=fit_connected(labels,tolerance=2.)
        union=unary_union(list(groups.values()))
        self.assertEqual(len(_polygons(union)),2)
        self.assertEqual(sum(len(p.interiors) for p in _polygons(union)),1)
        self.assertEqual(union.intersection(Polygon([(20,18),(40,18),(40,33),(20,33)])).area,0)
        self.assertEqual(q['protected_footprint_void_count'],1)

    def test_unsupported_face_retained_and_flagged(self):
        priors=np.zeros((3,40,55),bool)
        priors[0,5:35,5:25]=True;priors[1,5:35,25:48]=True
        priors[2,15:20,12:17]=True;priors[0,15:20,12:17]=False
        masks=priors.copy();masks[2]=False;masks[0,15:20,12:17]=True
        labels=fuse_labels(priors,masks)
        groups,_,q=fit_connected(labels,evidence=(),tolerance=1.5)
        self.assertEqual(set(groups),{1,2,3})
        self.assertGreater(groups[3].area,0)
        self.assertIn(3,q['unsupported_labels'])

    def test_changes_globally_bounded_and_deterministic(self):
        labels=np.zeros((55,70),np.int32)
        for y in range(5,45):
            edge=5+y//9;ridge=30+y//10
            labels[y,edge:ridge]=1;labels[y,ridge:60+y//15]=2
        original=_pieces([{**c,'points':c['raw']} for c in boundary_chains(labels)],labels)
        groups,chains,q=fit_connected(labels,tolerance=2.)
        again,_,_=fit_connected(labels,tolerance=2.)
        for i,g in groups.items():
            self.assertLessEqual(original[i].boundary.hausdorff_distance(g.boundary),2.00001)
            self.assertLessEqual(abs(g.area/original[i].area-1),.2)
            self.assertTrue(g.equals_exact(again[i],0))
        self.assertLess(q['fitted_boundary_vertices'],q['raw_boundary_vertices']*.5)
        for c in chains:
            self.assertLessEqual(LineString(c['raw']).hausdorff_distance(LineString(c['points'])),2.00001)


class ExportGeometryTests(unittest.TestCase):
    def test_exact_exclusion_and_declared_final_edges(self):
        from connected_roof import actual_edges
        labels=np.zeros((40,60),np.int32)
        labels[5:35,5:30]=1;labels[5:35,30:55]=2
        groups,_,_=fit_connected(labels,tolerance=2.)
        # Exclusion straddles an interface and uses non-grid coordinates.
        exclusion=Polygon([(27.3,15.2),(33.4,15.2),(33.4,22.7),(27.3,22.7)])
        groups={i:g.difference(exclusion).simplify(0) for i,g in groups.items()}
        edges=actual_edges(groups)
        for pair,line in edges:
            for i in pair:
                if i:self.assertLess(line.difference(groups[i].boundary).length,1e-8)
        for i,g in groups.items():
            declared=unary_union([line for pair,line in edges if i in pair])
            self.assertLess(g.boundary.symmetric_difference(declared).length,1e-8)
        self.assertLess(unary_union(list(groups.values())).intersection(exclusion).area,1e-9)
        self.assertLess(groups[1].intersection(groups[2]).area,1e-9)

    def test_tiny_label_void_noise_distinguished_from_courtyard(self):
        priors=np.zeros((1,40,50),bool);priors[0,5:35,5:45]=True
        priors[0,10,10]=False;priors[0,15:23,18:29]=False
        labels=fuse_labels(priors,priors)
        self.assertEqual(labels[10,10],1)
        self.assertTrue((labels[15:23,18:29]==0).all())

class HeightGuardTests(unittest.TestCase):
    def test_internal_ownership_cannot_hide_height_error_at_boundary(self):
        from rasterio.features import rasterize
        from shapely.geometry import mapping
        from affine import Affine
        labels=np.zeros((50,65),np.int32)
        for y in range(5,45):
            ridge=28+y//7
            labels[y,5:ridge]=1;labels[y,ridge:60]=2
        squared=np.stack([np.where(labels==i,0.,4.) for i in (1,2)])
        groups,_,_=fit_connected(labels,tolerance=4.,height_squared_errors=squared)
        assigned=rasterize([(mapping(p),i) for i,p in groups.items()],out_shape=labels.shape,transform=Affine.identity(),dtype='int32')
        for i in (1,2):
            self.assertLessEqual(float(np.mean(squared[i-1][assigned==i]))**.5,.060001)


if __name__=='__main__':unittest.main()
