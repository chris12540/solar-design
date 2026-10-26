"""Score a saved roof reconstruction against an Aurora DXF design.

    .venv/bin/python experiments/roof-vision/aurora-benchmark/benchmark.py \
        --dxf design.dxf --result result.json [--baseline baseline.json | --write-baseline baseline.json]

Exit code 1 means a gated metric regressed against the baseline.
"""
import argparse
import json
import sys
from pathlib import Path
from shapely.geometry import Point
from shapely.ops import unary_union
import aurora_dxf
import metrics
import ours
import registration

# (dotted path in the report, direction that is better, allowed slack)
GATES = (
    ('outline.iou', 'higher', .01),
    ('outline.boundary.p90_m', 'lower', .03),
    ('stages.fitted.area_weighted_best_iou', 'higher', .02),
    ('stages.fitted.face_recall', 'higher', .02),
    ('stages.fitted.large_area_weighted_best_iou', 'higher', .02),
    ('stages.fitted.absorbed_m2', 'lower', .5),
    ('stages.straightened.large_area_weighted_best_iou', 'higher', .02),
    ('stages.straightened.face_recall', 'higher', .02),
    ('stages.straightened.absorbed_m2', 'lower', .5),
    ('plausibility.straightened.edges.consistent', 'higher', .05),
    ('plausibility.straightened.edges.inconsistent', 'lower', .05),
    ('obstructions.recall', 'higher', 0.),
    ('obstructions.false_positives', 'lower', 0),
    ('orientation.fitted.azimuth_within_tol', 'higher', .02),
    ('orientation.fitted.pitch_within_tol', 'higher', .02),
)


def dig(data, path):
    for key in path.split('.'):
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def build_report(design, roof, reference=None, reference_panel_count=None, any_orientation=False):
    transform, fit_iou = registration.register(design.roof_outline, roof.outline, any_orientation=any_orientation)
    aurora_faces = {k: transform.apply(f) for k, f in design.faces_by_id.items()}
    aurora_outline = transform.apply(design.roof_outline)
    report = {
        'meta': {'dxf': {'units_to_m': design.units_to_m, 'faces': len(design.faces), 'modules': len(design.modules),
                         'vents': len(design.vents), 'obstruction_polygons': len(design.obstruction_polygons),
                         'layers': design.counts, 'warnings': design.warnings},
                 'result': roof.meta},
        'registration': {'rotation_deg': transform.rotation_deg, 'dx_m': transform.dx, 'dy_m': transform.dy,
                         'fit_iou': fit_iou},
        'outline': metrics.outline_report(aurora_outline, roof.outline),
        'stages': {}, 'orientation': {},
        'plausibility': roof.meta.get('plausibility'),
    }
    for stage in ours.STAGES:
        polys = roof.polygons(stage)
        if not polys:
            continue
        summary = metrics.match_faces(aurora_faces, polys)
        summary['union_iou'] = metrics.iou(aurora_outline, unary_union(list(polys.values())))
        report['stages'][stage] = summary
        if reference:
            report['orientation'][stage] = metrics.orientation_errors(
                summary['faces'], roof.orientation(stage), reference)
    vents = []
    for x, y, radius in design.vents:
        moved = transform.apply(Point(x, y))
        vents.append((moved.x, moved.y, radius))
    report['obstructions'] = metrics.obstruction_report(
        vents, [transform.apply(p) for p in design.obstruction_polygons], roof.obstructions, aurora_faces=aurora_faces)
    report['panels'] = metrics.panel_report([transform.apply(m) for m in design.modules], aurora_faces,
                                            reference_panel_count)
    return report


def summarize(report):
    o, r = report['outline'], report['registration']
    lines = [f"registration: rotation {r['rotation_deg']:.2f} deg, shift ({r['dx_m']:.2f}, {r['dy_m']:.2f}) m, fit IoU {r['fit_iou']:.3f}",
             f"outline: IoU {o['iou']:.3f}, area ours/Aurora {o['ours_area_m2']:.1f}/{o['aurora_area_m2']:.1f} m2, "
             f"edge gap mean {o['boundary']['mean_m']:.2f} p90 {o['boundary']['p90_m']:.2f} max {o['boundary']['max_m']:.2f} m"]
    for stage, s in report['stages'].items():
        lines.append(f"{stage}: {s['n_ours']} faces vs Aurora {s['n_aurora']} ({s['n_aurora_large']} large); "
                     f"face IoU (area-weighted) {s['area_weighted_best_iou']:.3f}, recall {s['face_recall']:.3f}, "
                     f"unmatched {s['unmatched_area_m2']:.1f} m2 {s['unmatched_ids']}")
        for aid, oids in s['split_aurora'].items():
            lines.append(f'    Aurora {aid} split across {oids}')
        for oid, aids in s['merged_ours'].items():
            lines.append(f'    ours {oid} spans Aurora {aids}')
    ob = report['obstructions']
    recall = 'n/a' if ob['recall'] is None else f"{ob['found']}/{ob['aurora_count']}"
    lines.append(f"obstructions: found {recall}, false positives {ob['false_positives']}")
    for fp in ob['false_positive_detail']:
        if fp.get('mostly_on_aurora_face'):
            lines.append(f"    candidate {fp['index']} sits on Aurora roof face {fp['mostly_on_aurora_face']} (likely a roof step)")
    p = report['panels']
    lines.append(f"Aurora modules: {p['count']} (median {p['median_dims_m'] and [round(d, 2) for d in p['median_dims_m']]} m), per face {p['per_face']}")
    plausible = (report.get('plausibility') or {}).get('straightened')
    if plausible:
        framing, edges = plausible.get('framing_pitch'), plausible['edges']
        lines.append('plausibility (straightened): %s; framing pitch %s; shared edges %.0f m: %.0f%% consistent, %.0f%% correctable, %.0f%% step, %.0f%% inconsistent; flags %s' % (
            plausible['status'], '%.1f deg (%d:12)' % (framing['degrees'], framing['ratio']) if framing else 'n/a', edges['length_m'],
            100*edges['consistent'], 100*edges['correctable'], 100*edges['step'], 100*edges['inconsistent'], sorted({f['kind'] for f in plausible['flags']}) or 'none'))
    for stage, orient in report['orientation'].items():
        lines.append(f"{stage} orientation: azimuth within tol {orient['azimuth_within_tol']}, pitch within tol {orient['pitch_within_tol']}")
    return '\n'.join(lines)


def baseline_of(report):
    return {path: dig(report, path) for path, _, _ in GATES if dig(report, path) is not None}


def compare_to_baseline(report, baseline):
    """Return the gated metrics that are worse than baseline by more than their slack."""
    bad = []
    for path, better, slack in GATES:
        old, new = baseline.get(path), dig(report, path)
        if old is None or new is None:
            continue
        delta = new - old if better == 'higher' else old - new
        if delta < -slack - 1e-12:
            bad.append({'metric': path, 'baseline': old, 'current': new, 'slack': slack})
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dxf', required=True)
    p.add_argument('--result', required=True)
    p.add_argument('--reference', help='JSON {"A0": {"azimuth_deg": .., "pitch_deg": ..}} (provisional format)')
    p.add_argument('--panel-reference', type=int, help='panel count to compare Aurora against (e.g. Google max)')
    p.add_argument('--units', type=float, help='metres per DXF unit (overrides $INSUNITS)')
    p.add_argument('--all-structures', action='store_true', help='keep every structure in the DXF, not just the largest building')
    p.add_argument('--any-orientation', action='store_true', help='also try 90/180/270 degree turns when registering')
    p.add_argument('--out', help='write the full JSON report here')
    p.add_argument('--baseline')
    p.add_argument('--write-baseline')
    args = p.parse_args(argv)
    design = aurora_dxf.load(args.dxf, args.units, primary_only=not args.all_structures)
    roof = ours.load(args.result)
    reference = json.loads(Path(args.reference).read_text()) if args.reference else None
    report = build_report(design, roof, reference, args.panel_reference, args.any_orientation)
    print(summarize(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1))
    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(baseline_of(report), indent=1))
        print(f'baseline written to {args.write_baseline}')
    if args.baseline:
        bad = compare_to_baseline(report, json.loads(Path(args.baseline).read_text()))
        for b in bad:
            print(f"REGRESSION {b['metric']}: {b['baseline']:.4f} -> {b['current']:.4f} (slack {b['slack']})")
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
