"""Geometry scores for comparing a fitted roof with an Aurora design.

All inputs are shapely geometries in one metric frame (register first). Scores
measure agreement with Aurora, which is a reference, not surveyed ground truth.
"""
import math
from shapely.geometry import Point
from shapely.ops import unary_union

MATCH_IOU = .5     # a face counts as reproduced at or above this IoU
SMALL_M2 = 3.      # faces below this are "small" (hips, facets)
SPAN_FRAC = .15    # share of a face that makes an overlap count for merge/split


def iou(a, b):
    inter = a.intersection(b).area
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.


def _parts(geom):
    return list(geom.geoms) if hasattr(geom, 'geoms') else [geom]


def _samples(geom, n):
    lines = [p for p in _parts(geom.boundary) if p.length > 0]
    total = sum(p.length for p in lines)
    out = []
    for line in lines:
        k = max(2, round(n * line.length / total))
        out += [line.interpolate(line.length * i / k) for i in range(k)]
    return out


def _stats(ds):
    ds = sorted(ds)
    return {'mean_m': sum(ds) / len(ds), 'median_m': ds[len(ds) // 2],
            'p90_m': ds[min(len(ds) - 1, int(.9 * len(ds)))], 'max_m': ds[-1]}


def boundary_distance(a, b, n=400):
    """Distances from samples on each outline to the other outline."""
    return {'a_to_b': _stats([p.distance(b.boundary) for p in _samples(a, n)]),
            'b_to_a': _stats([p.distance(a.boundary) for p in _samples(b, n)])}


def _regions(geom, min_m2):
    out = [g for g in _parts(geom) if g.area >= min_m2]
    return [{'area_m2': g.area, 'x': g.centroid.x, 'y': g.centroid.y} for g in sorted(out, key=lambda g: -g.area)]


def outline_report(aurora, ours, min_region_m2=.15):
    """`aurora` and `ours` are outline polygons. 'missing' is Aurora-only, 'extra' is ours-only."""
    dist = boundary_distance(aurora, ours)
    missing, extra = aurora.difference(ours), ours.difference(aurora)
    return {'iou': iou(aurora, ours), 'aurora_area_m2': aurora.area, 'ours_area_m2': ours.area,
            'area_ratio': ours.area / aurora.area if aurora.area else None,
            'missing_m2': missing.area, 'extra_m2': extra.area,
            'missing_fraction': missing.area / aurora.area if aurora.area else None,
            'extra_fraction': extra.area / ours.area if ours.area else None,
            'boundary': {'p90_m': max(dist['a_to_b']['p90_m'], dist['b_to_a']['p90_m']),
                         'max_m': max(dist['a_to_b']['max_m'], dist['b_to_a']['max_m']),
                         'mean_m': (dist['a_to_b']['mean_m'] + dist['b_to_a']['mean_m']) / 2,
                         **dist},
            'missing_regions': _regions(missing, min_region_m2), 'extra_regions': _regions(extra, min_region_m2)}


def match_faces(aurora, ours, small_m2=SMALL_M2, match_iou=MATCH_IOU, span_frac=SPAN_FRAC):
    """Score `ours` ({id: polygon}) against `aurora` ({id: polygon})."""
    inter = {(a, o): ap.intersection(op).area for a, ap in aurora.items() for o, op in ours.items()}
    rows = []
    for aid, ap in aurora.items():
        scored = []
        for oid, op in ours.items():
            i = inter[(aid, oid)]
            u = ap.area + op.area - i
            scored.append((i / u if u > 0 else 0., oid, i / ap.area))
        scored.sort(reverse=True)
        best = scored[0] if scored else (0., None, 0.)
        cover = ap.intersection(unary_union(list(ours.values()))).area / ap.area if ours else 0.
        rows.append({'id': aid, 'area_m2': ap.area, 'x': ap.centroid.x, 'y': ap.centroid.y,
                     'best_id': best[1], 'best_iou': best[0], 'coverage': cover,
                     'covered_by': [(oid, share) for _, oid, share in sorted(scored, key=lambda s: -s[2])[:3] if share > .02]})
    total = sum(r['area_m2'] for r in rows) or 1.
    large = [r for r in rows if r['area_m2'] >= small_m2]
    large_total = sum(r['area_m2'] for r in large) or 1.
    unmatched = [r for r in rows if r['best_iou'] < match_iou]
    spans = {oid: [aid for aid in aurora if inter[(aid, oid)] / op.area >= span_frac]
             for oid, op in ours.items()}
    splits = {aid: [oid for oid in ours if inter[(aid, oid)] / ap.area >= span_frac]
              for aid, ap in aurora.items()}
    return {'faces': rows,
            'n_aurora': len(aurora), 'n_aurora_large': len(large), 'n_ours': len(ours),
            'area_weighted_best_iou': sum(r['best_iou'] * r['area_m2'] for r in rows) / total,
            'large_area_weighted_best_iou': sum(r['best_iou'] * r['area_m2'] for r in large) / large_total,
            'face_recall': 1 - sum(r['area_m2'] for r in unmatched) / total,
            'unmatched_area_m2': sum(r['area_m2'] for r in unmatched),
            'unmatched_ids': [r['id'] for r in unmatched],
            'merged_ours': {oid: ids for oid, ids in spans.items() if len(ids) >= 2},
            'split_aurora': {aid: ids for aid, ids in splits.items() if len(ids) >= 2}}


def obstruction_report(vents, polygons, ours, tolerance_m=.5, aurora_faces=None):
    """Recall of Aurora obstructions and false positives among our candidates.

    `vents` are (x, y, radius); `polygons` are Aurora obstruction polygons; `ours` are candidate polygons.
    """
    truth = [Point(x, y).buffer(r) for x, y, r in vents] + list(polygons)
    found = [t for t in truth if any(t.distance(o) <= tolerance_m for o in ours)]
    false_pos = []
    for k, o in enumerate(ours):
        if not any(t.distance(o) <= tolerance_m for t in truth):
            row = {'index': k, 'area_m2': o.area, 'x': o.centroid.x, 'y': o.centroid.y}
            if aurora_faces:
                share = {fid: o.intersection(f).area / o.area for fid, f in aurora_faces.items() if o.area}
                fid, frac = max(share.items(), key=lambda kv: kv[1], default=(None, 0.))
                row.update({'mostly_on_aurora_face': fid if frac >= .5 else None, 'on_face_fraction': frac})
            false_pos.append(row)
    return {'aurora_count': len(truth), 'found': len(found),
            'recall': len(found) / len(truth) if truth else None,
            'ours_count': len(ours), 'false_positives': len(false_pos), 'false_positive_detail': false_pos}


def panel_report(modules, faces=None, reference_count=None):
    """Aurora module layout summary; `reference_count` is e.g. Google's max panel count."""
    dims = []
    for m in modules:
        pts = list(m.minimum_rotated_rectangle.exterior.coords)
        dims.append(sorted([math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])]))
    dims.sort()
    mid = dims[len(dims) // 2] if dims else None
    per_face = {}
    for m in modules:
        for fid, f in (faces or {}).items():
            if f.contains(m.centroid):
                per_face[fid] = per_face.get(fid, 0) + 1
                break
    return {'count': len(modules), 'median_dims_m': mid,
            'total_area_m2': sum(m.area for m in modules), 'per_face': per_face,
            'reference_count': reference_count,
            'count_vs_reference': len(modules) / reference_count if reference_count else None}


def angle_diff(a, b):
    return abs((a - b + 180.) % 360. - 180.)


def orientation_errors(face_rows, our_orientation, reference, az_tol=10., pitch_tol=3.):
    """Azimuth/pitch error for Aurora faces with a reference value.

    `face_rows` come from match_faces()['faces']; `our_orientation` is {our_id: (azimuth, pitch)};
    `reference` is {aurora_id: {'azimuth_deg', 'pitch_deg'}}. Faces without a best match count as failures.
    """
    out, total, ok_az, ok_pitch = [], 0., 0., 0.
    for r in face_rows:
        ref = reference.get(r['id'])
        if ref is None:
            continue
        total += r['area_m2']
        mine = our_orientation.get(r['best_id']) if r['best_iou'] >= MATCH_IOU else None
        row = {'id': r['id'], 'area_m2': r['area_m2'], 'matched': mine is not None}
        if mine is not None:
            row['azimuth_error_deg'] = angle_diff(mine[0], ref['azimuth_deg'])
            row['pitch_error_deg'] = abs(mine[1] - ref['pitch_deg'])
            ok_az += r['area_m2'] * (row['azimuth_error_deg'] <= az_tol)
            ok_pitch += r['area_m2'] * (row['pitch_error_deg'] <= pitch_tol)
        out.append(row)
    return {'faces': out, 'reference_area_m2': total,
            'azimuth_within_tol': ok_az / total if total else None,
            'pitch_within_tol': ok_pitch / total if total else None}
