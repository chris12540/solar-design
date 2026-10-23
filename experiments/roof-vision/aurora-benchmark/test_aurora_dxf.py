"""DXF reader tests on synthetic layouts with known areas."""
import tempfile
import unittest
from pathlib import Path
import aurora_dxf
from fixtures import FT, GABLE, HIP, dxf_text, rect, ring_lines

FT2 = FT * FT


class DxfReaderTests(unittest.TestCase):
    def test_gable_gives_two_equal_faces_in_metres(self):
        design = aurora_dxf.parse(dxf_text(buildings=GABLE))
        self.assertEqual(len(design.faces), 2)
        for face in design.faces:
            self.assertAlmostEqual(face.area, 600 * FT2, delta=.01)
        self.assertAlmostEqual(design.roof_outline.area, 1200 * FT2, delta=.05)
        self.assertEqual(design.face_ids, ['A0', 'A1'])

    def test_hip_gives_four_faces_largest_first(self):
        design = aurora_dxf.parse(dxf_text(buildings=HIP))
        areas = [f.area / FT2 for f in design.faces]
        self.assertEqual(len(areas), 4)
        self.assertEqual(areas, sorted(areas, reverse=True))
        for got, want in zip(areas, (300, 300, 100, 100)):
            self.assertAlmostEqual(got, want, delta=.5)

    def test_units_header_and_override(self):
        metres = aurora_dxf.parse(dxf_text(buildings=GABLE, units=6))
        self.assertAlmostEqual(metres.faces[0].area, 600, delta=.01)
        forced = aurora_dxf.parse(dxf_text(buildings=GABLE, units=None), units=FT)
        self.assertAlmostEqual(forced.faces[0].area, 600 * FT2, delta=.01)

    def test_missing_or_unsupported_units_raise(self):
        with self.assertRaises(aurora_dxf.DxfError):
            aurora_dxf.parse(dxf_text(buildings=GABLE, units=None))
        with self.assertRaises(aurora_dxf.DxfError):
            aurora_dxf.parse(dxf_text(buildings=GABLE, units=99))

    def test_modules_vents_and_skylight(self):
        mods = [rect(2, 2, 5.6, 7.5), rect(6, 2, 9.6, 7.5)]
        sky = ring_lines(rect(10, 10, 12, 14))
        design = aurora_dxf.parse(dxf_text(buildings=GABLE, modules=mods, obstruction_lines=sky, vents=[(5, 5, .3)]))
        self.assertEqual(len(design.modules), 2)
        self.assertAlmostEqual(design.modules[0].area, 3.6 * 5.5 * FT2, delta=.01)
        self.assertEqual(len(design.vents), 1)
        self.assertAlmostEqual(design.vents[0][2], .3 * FT, delta=1e-6)
        self.assertEqual(len(design.obstruction_polygons), 1)
        self.assertAlmostEqual(design.obstruction_polygons[0].area, 8 * FT2, delta=.01)

    def test_no_optional_layers_is_fine(self):
        design = aurora_dxf.parse(dxf_text(buildings=GABLE))
        self.assertEqual((design.modules, design.vents, design.obstruction_polygons), ([], [], []))

    def test_tiny_slivers_are_dropped_with_a_warning(self):
        lines = GABLE + [((0, 0), (.3, .1)), ((.3, .1), (.3, 0))]  # a ~0.015 ft2 triangle at the corner
        design = aurora_dxf.parse(dxf_text(buildings=lines))
        self.assertEqual(len(design.faces), 2)
        self.assertTrue(any('sliver' in w for w in design.warnings))

    def test_malformed_input_raises_cleanly(self):
        with self.assertRaises(aurora_dxf.DxfError):
            aurora_dxf.parse('abc\nSECTION\n')
        bad = dxf_text(buildings=GABLE).replace('\n10\n0.0\n', '\n10\nnot-a-number\n', 1)
        with self.assertRaises(aurora_dxf.DxfError):
            aurora_dxf.parse(bad)

    def test_entities_outside_known_layers_are_counted_not_used(self):
        text = dxf_text(buildings=GABLE).replace('LINE\n8\nBuildings', 'LINE\n8\nSetbacks')
        design = aurora_dxf.parse(text)
        self.assertEqual(design.counts.get('Setbacks'), len(GABLE))
        self.assertEqual(len(design.faces), 0)
        self.assertTrue(any('no roof faces' in w for w in design.warnings))

    def test_neighbouring_structures_are_ignored_by_default(self):
        neighbour = ring_lines(rect(100, 0, 110, 20)) + [((100, 10), (110, 10))]    # 200 ft2, far from the house
        design = aurora_dxf.parse(dxf_text(buildings=GABLE + neighbour))
        self.assertEqual(len(design.faces), 2)
        self.assertAlmostEqual(design.roof_outline.area, 1200 * FT2, delta=.1)
        self.assertTrue(any('other structure' in w for w in design.warnings))
        everything = aurora_dxf.parse(dxf_text(buildings=GABLE + neighbour), primary_only=False)
        self.assertEqual(len(everything.faces), 4)

    def test_faces_of_one_building_are_never_split_apart(self):
        for lines, count in ((GABLE, 2), (HIP, 4)):
            design = aurora_dxf.parse(dxf_text(buildings=lines))
            self.assertEqual(len(design.faces), count)
            self.assertFalse(any('other structure' in w for w in design.warnings))

    def test_file_size_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.dxf'
            path.write_text(dxf_text(buildings=GABLE))
            self.assertEqual(len(aurora_dxf.load(path).faces), 2)
            original = aurora_dxf.MAX_BYTES
            aurora_dxf.MAX_BYTES = 10
            try:
                with self.assertRaises(aurora_dxf.DxfError):
                    aurora_dxf.load(path)
            finally:
                aurora_dxf.MAX_BYTES = original


if __name__ == '__main__':
    unittest.main()
