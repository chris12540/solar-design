"""Loader tests for the saved reconstruction result."""
import json
import tempfile
import unittest
from pathlib import Path
import ours
from fixtures import result_dict

SQ = [(0, 0), (10, 0), (10, 10), (0, 10)]
HALF_A = [(0, 0), (5, 0), (5, 10), (0, 10)]
HALF_B = [(5, 0), (10, 0), (10, 10), (5, 10)]


class LoaderTests(unittest.TestCase):
    def test_stages_outline_obstructions_and_orientation(self):
        data = result_dict(SQ, {'g1': (HALF_A, 90, 22), 'g2': (HALF_B, 270, 23)},
                           obstructions=[[(1, 1), (2, 1), (2, 2), (1, 2)]])
        roof = ours.from_result(data)
        self.assertEqual(set(roof.stages), {'raw', 'refined', 'fitted'})
        self.assertEqual(sorted(roof.polygons('fitted')), ['g1', 'g2'])
        self.assertAlmostEqual(roof.outline.area, 100.)
        self.assertEqual(roof.orientation('fitted')['g2'], (270., 23.))
        self.assertAlmostEqual(roof.obstructions[0].area, 1.)
        self.assertEqual(roof.meta['height_rmse_m'], .3)

    def test_api_payload_wrapper_is_accepted(self):
        data = result_dict(SQ, {'g1': (SQ, 90, 22)})
        roof = ours.from_result({'status': 'needs_review', 'result': data})
        self.assertEqual(list(roof.stages['fitted']), ['g1'])

    def test_raw_regions_merge_by_source_plane(self):
        data = result_dict(SQ, {'g1': (SQ, 90, 22)})
        data['faces'] = [{'id': 'r1', 'source_plane_id': 'plane-1', 'polygon': HALF_A, 'holes': [], 'azimuth_degrees': 90, 'pitch_degrees': 22},
                         {'id': 'r2', 'source_plane_id': 'plane-1', 'polygon': HALF_B, 'holes': [], 'azimuth_degrees': 90, 'pitch_degrees': 22}]
        roof = ours.from_result(data)
        self.assertEqual(list(roof.stages['raw']), ['plane-1'])
        self.assertAlmostEqual(roof.stages['raw']['plane-1'].polygon.area, 100.)

    def test_holes_are_respected(self):
        hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
        data = result_dict(SQ, {'g1': (SQ, 90, 22)}, holes=[hole])
        self.assertAlmostEqual(ours.from_result(data).outline.area, 96.)

    def test_outline_falls_back_to_fitted_faces(self):
        data = result_dict(SQ, {'g1': (HALF_A, 90, 22), 'g2': (HALF_B, 270, 22)})
        del data['roof_outline']
        self.assertAlmostEqual(ours.from_result(data).outline.area, 100.)

    def test_missing_sections_raise_a_format_error(self):
        data = result_dict(SQ, {'g1': (SQ, 90, 22)})
        del data['fitting']
        with self.assertRaises(ours.ResultFormatError):
            ours.from_result(data)
        bad = result_dict(SQ, {'g1': (SQ, 90, 22)})
        bad['fitting']['face_groups'][0]['parts'] = [{'polygon': 'nope'}]
        with self.assertRaises(ours.ResultFormatError):
            ours.from_result(bad)

    def test_load_reads_export_metadata(self):
        data = result_dict(SQ, {'g1': (SQ, 90, 22)})
        data['_export'] = {'expires_at': '2099-01-01T00:00:00+00:00'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.json'
            path.write_text(json.dumps(data))
            self.assertEqual(ours.load(path).meta['export']['expires_at'], '2099-01-01T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
