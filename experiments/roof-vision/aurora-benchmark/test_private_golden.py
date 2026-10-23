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


MAX_ABSORBED_FRACTION = .05   # share of the roof: unreproduced Aurora faces swallowed by neighbouring faces (original fit-1: 7.6%)
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
                share = report['stages']['fitted']['absorbed_m2'] / report['outline']['aurora_area_m2']
                self.assertLessEqual(share, MAX_ABSORBED_FRACTION, 'fitted faces claim area that no fitted plane explains')


if __name__ == '__main__':
    unittest.main()
