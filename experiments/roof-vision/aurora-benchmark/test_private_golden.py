"""Benchmark real houses kept in the ignored private/ folder; skipped when none are present.

Each private/<house>/ holds design.dxf, result.json (from export_result.py) and, once
accepted, baseline.json (from benchmark.py --write-baseline). Never commit these.
"""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
import aurora_dxf
import benchmark
import metrics
import ours

PRIVATE = Path(__file__).parent / 'private'
HOUSES = sorted(p for p in PRIVATE.glob('*/') if (p / 'design.dxf').exists() and (p / 'result.json').exists())


RAW_TOLERANCE = .03   # fitting may not leave large faces this far below the raw stage it starts from
MAX_ABSORBED_FRACTION = .03   # share of the roof: unreproduced Aurora faces swallowed by neighbouring faces (fit-1: 7.6%, fit-4: 4.1% on the human design)
STRAIGHT_VERTEX_SHARE = .4          # straightened faces keep under this share of the fit's vertices (real houses: 8-25%)
STRAIGHT_LONG_EDGE_SHARE = .75      # and at least this share of their edge length lies in straight runs of 1 m or more (real houses: 79-92%)
STRAIGHT_MIN_FACE_OVERLAP = .8      # every face still overlaps its fitted face this much (real houses: 0.86 or more)
STRAIGHT_IOU_SLACK = .01            # straightening may not cost more than this in large-face IoU against the reference
LARGE_FACE_M2 = 10.   # a face this big that is not reproduced at IoU >= 0.5 is a defect, not noise


def _scored(house):
    roof = ours.load(house / 'result.json')
    expires = (roof.meta.get('export') or {}).get('expires_at')
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise unittest.SkipTest(f'{house.name}: source data expired {expires}; delete this folder')
    return benchmark.build_report(aurora_dxf.load(house / 'design.dxf'), roof)


@unittest.skipUnless(HOUSES, 'no private houses in aurora-benchmark/private/')
class PrivateGoldenTests(unittest.TestCase):
    def test_each_house_is_sane_and_has_not_regressed(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                report = _scored(house)
                self.assertGreater(report['registration']['fit_iou'], .8)
                self.assertGreater(report['outline']['iou'], .8)
                baseline = house / 'baseline.json'
                if baseline.exists():
                    self.assertEqual(benchmark.compare_to_baseline(report, json.loads(baseline.read_text())), [])

    def test_large_aurora_faces_survive_fitting(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                faces = _scored(house)['stages']['fitted']['faces']
                lost = [(r['id'], round(r['area_m2'], 1), round(r['best_iou'], 2)) for r in faces
                        if r['area_m2'] >= LARGE_FACE_M2 and r['best_iou'] < metrics.MATCH_IOU]
                self.assertEqual(lost, [], 'large Aurora faces not reproduced after fitting')

    def test_fitted_faces_do_not_swallow_unmodeled_areas(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                report = _scored(house)
                area = report['outline']['aurora_area_m2']
                share = report['stages']['fitted']['absorbed_m2'] / area
                # A reference split the heights cannot see (two coplanar faces) is swallowed by the raw stage already;
                # fitting may not add to that, but it is not held to a limit the raw stage itself breaks.
                allowed = max(MAX_ABSORBED_FRACTION, report['stages']['raw']['absorbed_m2'] / area)
                self.assertLessEqual(share, allowed, 'fitted faces claim area that no fitted plane explains')

    def test_fitting_stays_close_to_the_raw_stage_it_starts_from(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                stages = _scored(house)['stages']
                raw, fitted = stages['raw']['large_area_weighted_best_iou'], stages['fitted']['large_area_weighted_best_iou']
                self.assertGreaterEqual(fitted, raw - RAW_TOLERANCE, 'fitting made the large faces clearly worse than the raw stage')

    def test_the_plausibility_report_finds_no_lost_part_of_the_roof(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                report = json.loads((house / 'result.json').read_text())['fitting'].get('plausibility')
                if not report:
                    self.skipTest(f'{house.name}: result.json predates the plausibility report; re-export it')
                for stage in ('fitted', 'straightened'):
                    self.assertIsNotNone(report[stage], f'no {stage} report: {report.get("error")}')
                    lost = [f['kind'] for f in report[stage]['flags'] if f['kind'] in ('raw_coverage_low', 'outline_coverage_low')]
                    self.assertEqual(lost, [], 'faces cover too little of the roof: the pipeline lost part of it')

    def test_straightened_faces_are_straighter_and_no_less_accurate(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                straight = json.loads((house / 'result.json').read_text())['fitting'].get('straightened') or {}
                if 'status' not in straight:
                    self.skipTest(f'{house.name}: result.json predates the straightened stage; re-export it')
                self.assertEqual(straight['status'], 'ok', straight.get('reason'))
                quality = straight['quality']
                self.assertLess(quality['vertex_count'], STRAIGHT_VERTEX_SHARE * quality['source_vertex_count'])
                self.assertGreaterEqual(quality['long_edge_share'], STRAIGHT_LONG_EDGE_SHARE)
                self.assertGreater(quality['min_face_overlap'], STRAIGHT_MIN_FACE_OVERLAP)
                stages = _scored(house)['stages']
                self.assertGreaterEqual(stages['straightened']['large_area_weighted_best_iou'],
                                        stages['fitted']['large_area_weighted_best_iou'] - STRAIGHT_IOU_SLACK,
                                        'straightening made the large faces worse than the fit it was made from')


if __name__ == '__main__':
    unittest.main()
