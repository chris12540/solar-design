"""Independent coordinate/sign regressions for Phase 1 diagnostics."""
import unittest
import numpy as np
from affine import Affine
from scipy import ndimage as ndi
from phase1_evidence import line_check
from phase1_alignment import shifted_score


class EvidenceCoordinateTests(unittest.TestCase):
    def test_pixel_centers_place_known_plane_intersection_correctly(self):
        priors = np.zeros((2, 12, 12), dtype=bool)
        priors[0, :, :5] = True
        priors[1, :, 5:] = True
        archive = {'face_priors': priors, 'face_ids': ['west', 'east']}
        groups = {'west': {'plane_model': {'a': 1., 'b': 0., 'c': 0.}},
                  'east': {'plane_model': {'a': -1., 'b': 0., 'c': 0.}}}
        # Native image x=4.5 lies between pixel centers 4 and 5. The corner
        # affine places that boundary at local x=0 only after the +0.5 shift.
        line = {'id': 'known-ridge', 'label': 'Known ridge',
                'xy': [[4.5, 1.], [4.5, 10.]]}
        report = line_check(line, archive, groups, Affine(1, 0, -5, 0, -1, 12))
        self.assertAlmostEqual(report['distance_from_visible_seam_to_analytic_intersection_m']['max'], 0.)
        self.assertAlmostEqual(report['plane_height_disagreement_on_visible_seam_m']['max_absolute'], 0.)

    def test_same_source_ownership_does_not_invent_join(self):
        archive = {'face_priors': np.ones((1, 12, 12), dtype=bool), 'face_ids': ['one']}
        groups = {'one': {'plane_model': {'a': .3, 'b': .1, 'c': 3.}}}
        report = line_check({'id':'texture', 'label':'Texture seam', 'xy':[[5, 1], [5, 10]]},
                            archive, groups, Affine.identity())
        self.assertEqual(report['intersection_status'], 'source_ownership_ambiguous_or_same_on_both_sides')
        self.assertNotIn('distance_from_visible_seam_to_analytic_intersection_m', report)

    def test_east_north_translation_signs(self):
        nonedge = np.ones((12, 12), dtype=bool)
        nonedge[3:5, 6] = False
        distance = ndi.distance_transform_edt(nonedge)*.1
        evidence = np.array([[5., 4.], [6., 4.]])
        self.assertAlmostEqual(shifted_score(evidence, distance, .2, .2, .1), 0.)
        self.assertGreater(shifted_score(evidence, distance, .2, -.2, .1), .2)


if __name__ == '__main__':
    unittest.main()
