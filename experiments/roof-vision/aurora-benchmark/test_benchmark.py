"""End to end: synthetic Aurora design vs a synthetic result that is a known transform of it."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from shapely.geometry import Point
import aurora_dxf
import benchmark
import ours
from fixtures import FT, HIP, dxf_text, result_dict, rect
from registration import Transform

KNOWN = Transform(1.5, 12., -7.)
VENT_FT = (20., 5., .3)          # inside the lower trapezoid


def coords(poly):
    return [tuple(p) for p in list(poly.exterior.coords)[:-1]]


def design():
    return aurora_dxf.parse(dxf_text(buildings=HIP, vents=[VENT_FT], modules=[rect(5, 2, 8.6, 7.5)]))


def square_around(point, half=.15):
    return [(point.x - half, point.y - half), (point.x + half, point.y - half),
            (point.x + half, point.y + half), (point.x - half, point.y + half)]


def result_for(design_, drop=(), extra_obstructions=()):
    """A saved result equal to the design moved by KNOWN; `drop` indexes faces to omit from the fitted stage."""
    moved = [KNOWN.apply(f) for f in design_.faces]
    spec = {f'g{i}': (coords(p), 90. + 10 * i, 22.) for i, p in enumerate(moved)}
    fitted = {k: v for i, (k, v) in enumerate(spec.items()) if i not in drop}
    vent = KNOWN.apply(Point(VENT_FT[0] * FT, VENT_FT[1] * FT))
    return result_dict(coords(KNOWN.apply(design_.roof_outline)), fitted, refined=spec, raw=spec,
                       obstructions=[square_around(vent)] + list(extra_obstructions))


class BenchmarkTests(unittest.TestCase):
    def report(self, result):
        return benchmark.build_report(design(), ours.from_result(result))

    def test_perfect_result_scores_perfectly_and_recovers_the_transform(self):
        r = self.report(result_for(design()))
        self.assertAlmostEqual(r['registration']['rotation_deg'], KNOWN.rotation_deg, delta=.25)
        self.assertGreater(r['outline']['iou'], .995)
        self.assertLess(r['outline']['boundary']['p90_m'], .05)
        for stage in ('raw', 'refined', 'fitted'):
            self.assertGreater(r['stages'][stage]['area_weighted_best_iou'], .99, stage)
            self.assertEqual(r['stages'][stage]['unmatched_ids'], [])
        self.assertEqual((r['obstructions']['found'], r['obstructions']['false_positives']), (1, 0))
        self.assertAlmostEqual(r['obstructions']['recall'], 1.)
        self.assertEqual(r['panels']['count'], 1)

    def test_dropping_small_faces_is_visible_only_in_the_fitted_stage(self):
        d = design()
        small = [i for i, f in enumerate(d.faces) if f.area < 20]
        self.assertEqual(len(small), 2)
        r = self.report(result_for(d, drop=small))
        self.assertGreater(r['stages']['refined']['face_recall'], .99)
        self.assertLess(r['stages']['fitted']['face_recall'], .85)
        self.assertEqual(len(r['stages']['fitted']['unmatched_ids']), 2)
        self.assertEqual(r['stages']['fitted']['n_ours'], 2)

    def test_false_positive_on_a_roof_face_is_explained(self):
        off_vent = KNOWN.apply(Point(5 * FT, 15 * FT))     # a point on the upper trapezoid, far from the vent
        r = self.report(result_for(design(), extra_obstructions=[square_around(off_vent, .6)]))
        self.assertEqual(r['obstructions']['false_positives'], 1)
        self.assertIsNotNone(r['obstructions']['false_positive_detail'][0]['mostly_on_aurora_face'])
        self.assertIn('likely a roof step', benchmark.summarize(r))

    def test_orientation_reference_is_scored_when_given(self):
        d = design()
        reference = {fid: {'azimuth_deg': 90. + 10 * i, 'pitch_deg': 22.} for i, fid in enumerate(d.face_ids)}
        r = benchmark.build_report(d, ours.from_result(result_for(d)), reference)
        self.assertAlmostEqual(r['orientation']['fitted']['azimuth_within_tol'], 1.)
        self.assertAlmostEqual(r['orientation']['fitted']['pitch_within_tol'], 1.)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.report = benchmark.build_report(design(), ours.from_result(result_for(design())))
        self.baseline = benchmark.baseline_of(self.report)

    def test_same_report_passes_its_own_baseline(self):
        self.assertEqual(benchmark.compare_to_baseline(self.report, self.baseline), [])

    def test_regression_beyond_slack_is_flagged_and_within_slack_is_not(self):
        worse = copy.deepcopy(self.report)
        worse['stages']['fitted']['area_weighted_best_iou'] -= .05
        worse['outline']['iou'] -= .005
        bad = benchmark.compare_to_baseline(worse, self.baseline)
        self.assertEqual([b['metric'] for b in bad], ['stages.fitted.area_weighted_best_iou'])

    def test_lower_is_better_metrics(self):
        worse = copy.deepcopy(self.report)
        worse['outline']['boundary']['p90_m'] += .5
        worse['obstructions']['false_positives'] += 1
        names = {b['metric'] for b in benchmark.compare_to_baseline(worse, self.baseline)}
        self.assertEqual(names, {'outline.boundary.p90_m', 'obstructions.false_positives'})

    def test_improvements_and_missing_metrics_are_ignored(self):
        better = copy.deepcopy(self.report)
        better['outline']['iou'] = 1.
        self.assertEqual(benchmark.compare_to_baseline(better, {**self.baseline, 'orientation.fitted.azimuth_within_tol': .9}), [])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = benchmark.main(list(args))
        return code, out.getvalue()

    def test_write_baseline_then_gate_passes_and_a_degraded_result_fails(self):
        d = design()
        small = [i for i, f in enumerate(d.faces) if f.area < 20]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'd.dxf').write_text(dxf_text(buildings=HIP, vents=[VENT_FT], modules=[rect(5, 2, 8.6, 7.5)]))
            (tmp / 'good.json').write_text(json.dumps(result_for(d)))
            (tmp / 'bad.json').write_text(json.dumps(result_for(d, drop=small)))
            code, text = self.run_cli('--dxf', str(tmp / 'd.dxf'), '--result', str(tmp / 'good.json'),
                                      '--write-baseline', str(tmp / 'base.json'), '--out', str(tmp / 'report.json'))
            self.assertEqual(code, 0)
            self.assertIn('outline: IoU', text)
            self.assertIn('stages', json.loads((tmp / 'report.json').read_text()))
            self.assertEqual(self.run_cli('--dxf', str(tmp / 'd.dxf'), '--result', str(tmp / 'good.json'),
                                          '--baseline', str(tmp / 'base.json'))[0], 0)
            code, text = self.run_cli('--dxf', str(tmp / 'd.dxf'), '--result', str(tmp / 'bad.json'),
                                      '--baseline', str(tmp / 'base.json'))
            self.assertEqual(code, 1)
            self.assertIn('REGRESSION stages.fitted.face_recall', text)


if __name__ == '__main__':
    unittest.main()
