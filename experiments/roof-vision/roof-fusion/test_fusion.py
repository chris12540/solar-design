"""Physical counterexamples for image/height fusion; no real-house annotation."""
import unittest
import numpy as np
from affine import Affine
from shapely.geometry import Polygon,LineString
from fusion import Settings,fuse,fit_face,joint_fit,evaluate


def fixture(step=0.):
    transform=Affine(.1,0,-4,0,-.1,4)
    yy,xx=np.indices((80,80));x,y=transform*(xx+.5,yy+.5);xy=np.stack([x,y],-1)
    target=(abs(x)<3)&(abs(y)<3)
    a=np.array([.25,.1,380.]);b=np.array([-.15,.1,380.-step])
    dsm=np.where(x<0,evaluate(a,xy),evaluate(b,xy))
    google=[{'coefficients':c.tolist(),'google_segment_index':k,
             'bounds':Polygon([(-3,-3),(3,-3),(3,3),(-3,3)])} for k,c in enumerate([a,b])]
    world_lines=[[(-3,-3),(3,-3)],[(3,-3),(3,3)],[(3,3),(-3,3)],[(-3,3),(-3,-3)],[(0,-3),(0,3)]]
    inverse=~transform
    lines=[]
    for line in world_lines:
        points=[inverse*point for point in line];lines.append([[p[1],p[0]] for p in points])
    return np.array(lines),np.ones(5),google,dsm,target,transform,xy


class FusionTests(unittest.TestCase):
    def test_sloping_ridge_faces_share_height_without_gable_template(self):
        data=fixture();result=fuse(*data[:6])
        self.assertEqual(len(result['faces']),2)
        self.assertLess(result['overlap_m2'],1e-8)
        continuous=[e for e in result['edges'] if e['kind']=='continuous']
        self.assertEqual(len(continuous),1)
        self.assertLess(continuous[0]['final_max_gap_m'],1e-6)
        self.assertTrue(all(f['final_rmse_m']<1e-6 for f in result['faces']))

    def test_separate_stories_do_not_weld(self):
        data=fixture(step=3.)
        result=fuse(*data[:6])
        self.assertEqual(len(result['faces']),2)
        self.assertEqual(result['edges'][0]['kind'],'height_step')
        self.assertFalse(result['edges'][0]['joint_enforced'])
        self.assertAlmostEqual(result['edges'][0]['final_max_gap_m'],3.,places=5)

    def test_curved_or_mixed_surface_is_not_forced_to_plane(self):
        _,_,google,dsm,target,transform,xy=fixture()
        curved=380.+.6*xy[...,0]**2+.4*xy[...,1]**2
        face=Polygon([(-2,-2),(2,-2),(2,2),(-2,2)])
        info,_,_=fit_face(face,xy,curved,target,transform,google,Settings())
        self.assertIsNone(info['initial_coefficients'])
        self.assertEqual(info['state'],'unresolved')

    def test_missing_google_plane_can_be_provisional_only_with_height_support(self):
        _,_,google,dsm,target,transform,xy=fixture()
        measured=381.+.3*xy[...,0]-.2*xy[...,1]
        face=Polygon([(-2,-2),(2,-2),(2,2),(-2,2)])
        info,_,_=fit_face(face,xy,measured,target,transform,google,Settings())
        self.assertEqual(info['state'],'new_plane_provisional')
        np.testing.assert_allclose(info['initial_coefficients'],[.3,-.2,381.],atol=1e-7)

    def test_one_bad_join_does_not_distort_supported_component(self):
        yy,xx=np.mgrid[-2:2:10j,-2:2:10j];points=np.c_[xx.ravel(),yy.ravel()]
        faces=[]
        for z in [380.,380.,380.25]:
            faces.append({'initial_coefficients':[0.,0.,z],'coefficients':[0.,0.,z],
                          'initial_rmse_m':0.,'source':'google_plane','_xy':points,'_z':np.full(len(points),z)})
        edges=[{'faces':[0,1],'geometry':LineString([(0,-3),(0,3)]),'length_m':6.,'kind':'continuous_candidate'},
               {'faces':[1,2],'geometry':LineString([(1,-1),(1,1)]),'length_m':2.,'kind':'continuous_candidate'}]
        joint_fit(faces,edges,Settings())
        self.assertEqual(edges[0]['kind'],'continuous')
        self.assertEqual(edges[1]['kind'],'unresolved_connection')
        self.assertAlmostEqual(faces[0]['coefficients'][2],380.,places=6)
        self.assertAlmostEqual(faces[1]['coefficients'][2],380.,places=6)
        self.assertAlmostEqual(faces[2]['coefficients'][2],380.25,places=6)


if __name__=='__main__':
    unittest.main()
