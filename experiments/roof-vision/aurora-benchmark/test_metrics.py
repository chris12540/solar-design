"""Metric tests on constructed shapes with hand-computable answers."""
import unittest
from shapely.geometry import box
import metrics


class OutlineTests(unittest.TestCase):
    def test_iou_of_half_overlapping_squares(self):
        self.assertAlmostEqual(metrics.iou(box(0, 0, 1, 1), box(.5, 0, 1.5, 1)), 1 / 3)
        self.assertEqual(metrics.iou(box(0, 0, 1, 1), box(5, 5, 6, 6)), 0.)

    def test_distance_is_measured_in_both_directions(self):
        # Inner square: every edge is exactly 1 m from the outer one. The outer square's corners
        # are sqrt(2) m from the inner one, which is why both directions are reported.
        d = metrics.boundary_distance(box(0, 0, 10, 10), box(-1, -1, 11, 11))
        self.assertAlmostEqual(d['a_to_b']['mean_m'], 1., places=6)
        self.assertAlmostEqual(d['a_to_b']['max_m'], 1., places=6)
        self.assertAlmostEqual(d['b_to_a']['max_m'], 2 ** .5, places=2)
        self.assertGreater(d['b_to_a']['mean_m'], 1.)

    def test_identical_outlines_have_zero_gap(self):
        r = metrics.outline_report(box(0, 0, 10, 10), box(0, 0, 10, 10))
        self.assertAlmostEqual(r['iou'], 1.)
        self.assertAlmostEqual(r['boundary']['max_m'], 0., places=9)
        self.assertEqual((r['missing_m2'], r['extra_m2']), (0., 0.))

    def test_extra_and_missing_area_and_regions(self):
        aurora = box(0, 0, 10, 10).union(box(0, 10, 1, 13))          # 100 + 3
        ours = box(0, 0, 10, 10).union(box(10, 0, 12, 1))            # 100 + 2
        r = metrics.outline_report(aurora, ours)
        self.assertAlmostEqual(r['missing_m2'], 3.)
        self.assertAlmostEqual(r['extra_m2'], 2.)
        self.assertAlmostEqual(r['iou'], 100 / 105)
        self.assertEqual(len(r['missing_regions']), 1)
        self.assertAlmostEqual(r['missing_regions'][0]['y'], 11.5)
        self.assertAlmostEqual(r['extra_regions'][0]['x'], 11.)

    def test_multipart_outline_is_handled(self):
        two = box(0, 0, 4, 4).union(box(10, 0, 14, 4))
        r = metrics.outline_report(two, two)
        self.assertAlmostEqual(r['boundary']['max_m'], 0., places=9)


class FaceMatchTests(unittest.TestCase):
    AURORA = {'A0': box(0, 0, 10, 10), 'A1': box(10, 0, 14, 10), 'A2': box(14, 0, 15, 2)}  # 100, 40, 2 m2

    def test_perfect_match(self):
        m = metrics.match_faces(self.AURORA, dict(self.AURORA))
        self.assertAlmostEqual(m['area_weighted_best_iou'], 1.)
        self.assertAlmostEqual(m['face_recall'], 1.)
        self.assertEqual((m['merged_ours'], m['split_aurora'], m['unmatched_ids']), ({}, {}, []))
        self.assertEqual((m['n_aurora'], m['n_aurora_large'], m['n_ours']), (3, 2, 3))

    def test_merged_faces_are_detected(self):
        ours = {'m': box(0, 0, 14, 10), 'n': box(14, 0, 15, 2)}
        m = metrics.match_faces(self.AURORA, ours)
        self.assertEqual(m['merged_ours'], {'m': ['A0', 'A1']})
        self.assertEqual(m['unmatched_ids'], ['A1'])       # 40 / 140 < 0.5
        self.assertAlmostEqual(m['unmatched_area_m2'], 40.)
        rows = {r['id']: r for r in m['faces']}
        self.assertAlmostEqual(rows['A0']['best_iou'], 100 / 140)
        self.assertAlmostEqual(rows['A1']['coverage'], 1.)  # covered, but not as its own face

    def test_split_face_is_detected(self):
        ours = {'s0': box(0, 0, 6, 10), 's1': box(6, 0, 10, 10)}
        m = metrics.match_faces({'A0': box(0, 0, 10, 10)}, ours)
        self.assertEqual(m['split_aurora'], {'A0': ['s0', 's1']})
        self.assertAlmostEqual(m['faces'][0]['best_iou'], .6)

    def test_missing_small_face_hurts_all_but_not_large_score(self):
        m = metrics.match_faces(self.AURORA, {k: v for k, v in self.AURORA.items() if k != 'A2'})
        self.assertEqual(m['unmatched_ids'], ['A2'])
        self.assertAlmostEqual(m['large_area_weighted_best_iou'], 1.)
        self.assertAlmostEqual(m['area_weighted_best_iou'], 140 / 142)
        self.assertAlmostEqual(m['face_recall'], 140 / 142)

    def test_no_faces_of_ours(self):
        m = metrics.match_faces(self.AURORA, {})
        self.assertEqual(m['area_weighted_best_iou'], 0.)
        self.assertEqual(len(m['unmatched_ids']), 3)


class ObstructionTests(unittest.TestCase):
    def test_recall_and_false_positive_on_roof_face(self):
        faces = {'A0': box(35, 35, 45, 45)}
        r = metrics.obstruction_report(
            [(5, 5, .1)], [box(20, 20, 21, 21)], [box(5.2, 5, 5.6, 5.4), box(38, 38, 39, 39)], aurora_faces=faces)
        self.assertEqual((r['aurora_count'], r['found']), (2, 1))
        self.assertAlmostEqual(r['recall'], .5)
        self.assertEqual(r['false_positives'], 1)
        self.assertEqual(r['false_positive_detail'][0]['mostly_on_aurora_face'], 'A0')

    def test_no_truth_means_no_recall_value(self):
        r = metrics.obstruction_report([], [], [box(0, 0, 1, 1)])
        self.assertIsNone(r['recall'])
        self.assertEqual(r['false_positives'], 1)


class PanelTests(unittest.TestCase):
    def test_counts_dims_and_per_face(self):
        mods = [box(0, 0, 1.1, 1.7), box(2, 0, 3.1, 1.7), box(12, 0, 13.1, 1.7)]
        faces = {'A0': box(0, 0, 10, 5), 'A1': box(10, 0, 20, 5)}
        r = metrics.panel_report(mods, faces, reference_count=6)
        self.assertEqual(r['count'], 3)
        self.assertEqual(r['per_face'], {'A0': 2, 'A1': 1})
        self.assertAlmostEqual(r['median_dims_m'][0], 1.1)
        self.assertAlmostEqual(r['median_dims_m'][1], 1.7)
        self.assertAlmostEqual(r['count_vs_reference'], .5)

    def test_empty_layout(self):
        r = metrics.panel_report([])
        self.assertEqual((r['count'], r['median_dims_m']), (0, None))


class OrientationTests(unittest.TestCase):
    def test_angle_difference_wraps(self):
        self.assertAlmostEqual(metrics.angle_diff(350, 10), 20)
        self.assertAlmostEqual(metrics.angle_diff(10, 350), 20)
        self.assertAlmostEqual(metrics.angle_diff(0, 180), 180)

    def test_area_weighted_tolerances_and_unmatched_faces(self):
        aurora = {'A0': box(0, 0, 10, 10), 'A1': box(10, 0, 14, 10), 'A2': box(14, 0, 18, 10)}
        ours = {'o0': box(0, 0, 10, 10), 'o1': box(10, 0, 14, 10)}
        rows = metrics.match_faces(aurora, ours)['faces']
        reference = {'A0': {'azimuth_deg': 95, 'pitch_deg': 23},
                     'A1': {'azimuth_deg': 90, 'pitch_deg': 20},
                     'A2': {'azimuth_deg': 10, 'pitch_deg': 20}}
        r = metrics.orientation_errors(rows, {'o0': (90, 22), 'o1': (270, 20)}, reference)
        self.assertAlmostEqual(r['reference_area_m2'], 180.)
        self.assertAlmostEqual(r['azimuth_within_tol'], 100 / 180)   # A0 only
        self.assertAlmostEqual(r['pitch_within_tol'], 140 / 180)     # A0 and A1; A2 has no match
        self.assertFalse([f for f in r['faces'] if f['id'] == 'A2'][0]['matched'])

    def test_no_reference_gives_none(self):
        r = metrics.orientation_errors([], {}, {})
        self.assertIsNone(r['azimuth_within_tol'])


if __name__ == '__main__':
    unittest.main()
