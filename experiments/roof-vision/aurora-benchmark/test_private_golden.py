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
import ours

PRIVATE = Path(__file__).parent / 'private'
HOUSES = sorted(p for p in PRIVATE.glob('*/') if (p / 'design.dxf').exists() and (p / 'result.json').exists())


@unittest.skipUnless(HOUSES, 'no private houses in aurora-benchmark/private/')
class PrivateGoldenTests(unittest.TestCase):
    def test_each_house_is_sane_and_has_not_regressed(self):
        for house in HOUSES:
            with self.subTest(house=house.name):
                roof = ours.load(house / 'result.json')
                expires = (roof.meta.get('export') or {}).get('expires_at')
                if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
                    self.skipTest(f'{house.name}: source data expired {expires}; delete this folder')
                report = benchmark.build_report(aurora_dxf.load(house / 'design.dxf'), roof)
                self.assertGreater(report['registration']['fit_iou'], .8)
                self.assertGreater(report['outline']['iou'], .8)
                baseline = house / 'baseline.json'
                if baseline.exists():
                    self.assertEqual(benchmark.compare_to_baseline(report, json.loads(baseline.read_text())), [])


if __name__ == '__main__':
    unittest.main()
