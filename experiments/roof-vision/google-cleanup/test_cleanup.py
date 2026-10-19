"""Synthetic physical counterexamples; no coordinates from the user's drawing."""
import copy
import math
import unittest

from affine import Affine
import numpy as np
from pyproj import Geod, Transformer
from shapely.geometry import Polygon
from shapely.ops import unary_union
from cleanup import google_planes, reconstruct, coverage_valid


def fixture(azimuths=(81.,261.), heights=(380.,380.)):
    crs='EPSG:32612'
    center={'latitude':33.6554,'longitude':-112.2131}
    project=Transformer.from_crs(4326,crs,always_xy=True)
    inverse=Transformer.from_crs(crs,4326,always_xy=True)
    ox,oy=project.transform(center['longitude'],center['latitude'])
    sw=inverse.transform(ox-6,oy-8);ne=inverse.transform(ox+6,oy+8)
    insights={'center':center,'solarPotential':{'roofSegmentStats':[
        {'center':dict(center),'pitchDegrees':22.,'azimuthDegrees':az,'planeHeightAtCenterMeters':h,
         'boundingBox':{'sw':{'longitude':sw[0],'latitude':sw[1]},
                        'ne':{'longitude':ne[0],'latitude':ne[1]}}}
        for az,h in zip(azimuths,heights)]}}
    transform=Affine(.1,0,ox-6,0,-.1,oy+8)
    yy,xx=np.indices((160,120));x=(xx+.5)*.1-6;y=8-(yy+.5)*.1
    planes,_=google_planes(insights,crs)
    surfaces=np.array([p['coefficients'][0]*x+p['coefficients'][1]*y+p['coefficients'][2] for p in planes])
    dsm=surfaces.min(0)
    mask=(abs(x)<5)&(abs(y)<7)
    return insights,dsm,mask,transform,crs,x,y,surfaces


class CleanupTests(unittest.TestCase):
    def test_google_center_height_and_true_north_direction(self):
        insights,_,_,_,crs,*_=fixture((90.,),(380.,))
        planes,origin=google_planes(insights,crs)
        a,b,c=planes[0]['coefficients']
        self.assertAlmostEqual(c,380.,places=8)
        point=insights['center'];geod=Geod(ellps='WGS84')
        lon,lat,_=geod.fwd(point['longitude'],point['latitude'],90.,10.)
        ex,ey=Transformer.from_crs(4326,crs,always_xy=True).transform(lon,lat)
        self.assertAlmostEqual(a*(ex-origin[0])+b*(ey-origin[1])+c,
                               380.-math.tan(math.radians(22.))*10.,places=5)

    def test_gable_shared_ridge_is_exact_and_no_overlap(self):
        inputs=fixture();result=reconstruct(*inputs[:5])
        self.assertTrue(coverage_valid(result['records']))
        proposals=result['diagnostics']['seam_proposals']
        self.assertTrue(any(p['accepted'] for p in proposals))
        groups=[unary_union([r['geometry'] for r in result['records'] if r['label']==k]) for k in [1,2]]
        self.assertLess(groups[0].intersection(groups[1]).area,1e-8)
        shared=groups[0].boundary.intersection(groups[1].boundary)
        self.assertGreater(shared.length,10.)
        ca,cb=[np.array(p['coefficients']) for p in result['models']]
        for f in np.linspace(.05,.95,15):
            point=shared.interpolate(f,normalized=True)
            self.assertLess(abs((ca-cb)@np.array([point.x,point.y,1.])),2e-5)

    def test_parallel_roofs_at_different_stories_do_not_join(self):
        insights,dsm,mask,transform,crs,x,y,surfaces=fixture((90.,90.),(380.,377.))
        dsm=np.where(x<0,surfaces[0],surfaces[1])
        result=reconstruct(insights,dsm,mask,transform,crs)
        self.assertTrue(np.any(result['cleaned_labels']==1))
        self.assertTrue(np.any(result['cleaned_labels']==2))
        self.assertFalse(any(p['accepted'] for p in result['diagnostics']['seam_proposals']))
        self.assertTrue(any(p['reason']=='parallel_or_near_parallel_planes'
                            for p in result['diagnostics']['seam_proposals']))

    def test_unmodeled_dormer_stays_excluded_without_invented_plane(self):
        insights,dsm,mask,transform,crs,x,y,_=fixture()
        bump=(x>1)&(x<2)&(y>1)&(y<2)
        dsm=dsm.copy();dsm[bump]+=1.5
        original=copy.deepcopy(insights)
        result=reconstruct(insights,dsm,mask,transform,crs)
        self.assertEqual(insights,original)
        self.assertEqual(len(result['models']),2)
        self.assertTrue(np.all(result['cleaned_labels'][bump]==0))
        self.assertEqual(result['diagnostics']['unresolved_pixels_assigned'],0)
        self.assertAlmostEqual(result['diagnostics']['effective_support_overlap_with_exclusions_m2'],0.)
        bump_polygon=Polygon([(1,1),(2,1),(2,2),(1,2)])
        effective=unary_union([r['geometry'] for r in result['effective_records']])
        self.assertLess(effective.intersection(bump_polygon).area,1e-6)

    def test_no_roof_support_is_returned_as_unresolved(self):
        insights,dsm,mask,transform,crs,*_=fixture()
        result=reconstruct(insights,dsm+20,mask,transform,crs)
        self.assertEqual(result['effective_records'],[])
        self.assertFalse(np.any(result['cleaned_labels']>0))


if __name__=='__main__':
    unittest.main()
