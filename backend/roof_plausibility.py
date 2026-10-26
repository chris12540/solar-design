"""Would this roof stand? The fitted faces checked against how pitched roofs are built.

Read-only: it reports what holds and flags what needs a second look, and never changes a face.
The checks use each face's plane, so they say something the outline alone cannot:

- faces that share an edge should meet there at the same height, or the edge is misplaced or a real step
- the main faces of a house share one framing pitch, normally a standard n:12 ratio
- faces face along the roof's axes (a hip or gable end faces away from its eave)
- a face under about 2:12 is not a shingle or tile roof: patio cover, porch or flat roof
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, unary_union

STANDARD_RATIOS = {n: math.degrees(math.atan(n/12)) for n in range(1, 13)}   # rise : 12 run
LOW_SLOPE_DEG = STANDARD_RATIOS[2]       # under 2:12 is below the usual shingle (2:12) and tile (2.5:12) minimum
MAIN_FACE_M2 = 10.                       # faces this big and pitched set the framing pitch and the roof's axes
SMALL_FACE_M2 = 2.
PITCH_SPREAD_DEG = 3.                    # a pitched face this far from the framing pitch is worth a note ...
PITCH_REVIEW_DEG = 5.                    # ... and this far, a review (small hip faces measure a few degrees off)
PITCH_OFF_STANDARD_DEG = 1.5             # the framing pitch this far from every n:12 is worth a note
AXIS_OFFSET_DEG = 5.                     # a pitched face facing this far off the roof's axes is worth a note
AXIS_MIN_PITCH_DEG = 6.                  # flatter faces have no meaningful azimuth
CONTINUOUS_GAP_M = .15                   # planes this close on average along an edge meet there (raster edges wobble, so not the maximum)
CORRECTABLE_M = .8                       # a plane intersection this near a misplaced edge says where the edge belongs
PARALLEL_SLOPE = .15                     # planes whose slopes differ by less than this have no well-placed line of meeting: a gap between them is a step
MIN_EDGE_M = .2
OUTLINE_COVERAGE_MIN = .9
RAW_COVERAGE_MIN = .8                    # below this the raw stage lost part of the roof (a capped or failed face list)
EDGE_FLAG_M = 2.                         # inconsistent edge length between two faces worth a flag


def _plane(group):
    m = group['plane_model']
    return float(m['a']), float(m['b']), float(m['c'])


def _pitch(plane):
    return math.degrees(math.atan(math.hypot(plane[0], plane[1])))


def _densify(coords, step=.25):
    points = []
    for a, b in zip(coords, coords[1:]):
        k = max(1, int(math.dist(a, b) / step))
        points += [(a[0] + (b[0]-a[0])*i/k, a[1] + (b[1]-a[1])*i/k) for i in range(k)]
    points.append(tuple(coords[-1]))
    return np.array(points)


def _shape(group):
    return unary_union([Polygon(p['polygon'], p.get('holes') or None).buffer(0) for p in group['parts']])


def _shared_edges(shapes):
    """{(i, j): [coordinate lists]} for every pair of faces that touch along a line."""
    found = {}
    names = list(shapes)
    for n, i in enumerate(names):
        for j in names[n+1:]:
            meet = shapes[i].boundary.intersection(shapes[j].boundary)
            parts = [g for g in getattr(meet, 'geoms', [meet]) if g.geom_type in ('LineString', 'MultiLineString')]
            if not parts:
                continue
            joined = unary_union(parts)
            merged = joined if joined.geom_type == 'LineString' else linemerge(joined)       # linemerge wants several lines
            lines = [g for g in getattr(merged, 'geoms', [merged]) if g.geom_type == 'LineString' and g.length >= MIN_EDGE_M]
            if lines:
                found[(i, j)] = [list(line.coords) for line in lines]
    return found


def edge_class(first, second, points):
    """How two planes relate along an edge: 'consistent' (they meet there), 'correctable' (their intersection passes within
    CORRECTABLE_M, so the edge is misplaced), 'step' (near-parallel planes a constant height apart) or 'inconsistent'."""
    da, db, dc = (first[t] - second[t] for t in range(3))
    gap = np.abs(da*points[:, 0] + db*points[:, 1] + dc)
    if gap.mean() <= CONTINUOUS_GAP_M:
        return 'consistent'
    slope = math.hypot(da, db)
    if slope < PARALLEL_SLOPE:
        return 'step'
    return 'correctable' if float(np.median(gap)) / slope <= CORRECTABLE_M else 'inconsistent'


def _axis_bearing(groups):
    """Compass bearing, mod 90, of the roof's axes from the azimuths of its main pitched faces, or None."""
    s = c = 0.
    for g in groups:
        plane = _plane(g)
        if g['area_m2'] >= MAIN_FACE_M2 and _pitch(plane) >= LOW_SLOPE_DEG:
            azimuth = math.radians(4 * (math.degrees(math.atan2(-plane[0], -plane[1])) % 360))
            s += g['area_m2'] * math.sin(azimuth)
            c += g['area_m2'] * math.cos(azimuth)
    return (math.degrees(math.atan2(s, c)) / 4) % 90 if s or c else None


def assess(groups: list[dict[str, Any]], outline_area: float | None = None, raw_polygon_coverage: float | None = None) -> dict[str, Any]:
    """Checks of face groups (the fit's `face_groups`, or the straightened copy)."""
    flags = []
    planes = {g['id']: _plane(g) for g in groups}
    shapes = {g['id']: _shape(g) for g in groups}
    pitches = {k: _pitch(p) for k, p in planes.items()}
    area = {g['id']: g['area_m2'] for g in groups}

    main = [g['id'] for g in groups if area[g['id']] >= MAIN_FACE_M2 and pitches[g['id']] >= LOW_SLOPE_DEG]
    framing = None
    if main:
        weights = np.array([area[k] for k in main])
        values = np.array([pitches[k] for k in main])
        mean = float((weights * values).sum() / weights.sum())
        ratio, standard = min(STANDARD_RATIOS.items(), key=lambda item: abs(item[1] - mean))
        framing = dict(degrees=mean, ratio=ratio, standard_degrees=standard, spread_degrees=float(values.max() - values.min()), faces=len(main))
        if abs(mean - standard) > PITCH_OFF_STANDARD_DEG:
            flags.append(dict(kind='framing_pitch_off_standard', severity='note', face_ids=main,
                              message=f'The main faces average {mean:.1f} degrees, {abs(mean-standard):.1f} from the nearest standard pitch ({ratio}:12).'))
        for k in _by_size(groups):
            if pitches[k] >= LOW_SLOPE_DEG and area[k] >= 5 and abs(pitches[k] - mean) > PITCH_SPREAD_DEG:
                flags.append(dict(kind='pitch_off_framing', severity='review' if abs(pitches[k] - mean) > PITCH_REVIEW_DEG else 'note', face_ids=[k],
                                  message=f'{k} is {pitches[k]:.1f} degrees against a framing pitch of {mean:.1f}.'))

    low = [dict(id=k, area_m2=area[k], pitch_degrees=pitches[k]) for k in planes if pitches[k] < LOW_SLOPE_DEG and area[k] >= SMALL_FACE_M2]
    for item in low:
        flags.append(dict(kind='low_slope', severity='note', face_ids=[item['id']],
                          message=f"{item['id']} is {item['pitch_degrees']:.1f} degrees, under 2:12: a patio cover, porch or flat roof rather than shingle or tile."))
    for k in planes:
        if area[k] < SMALL_FACE_M2:
            flags.append(dict(kind='small_face', severity='note', face_ids=[k], message=f'{k} is only {area[k]:.1f} m2.'))

    axis = _axis_bearing(groups)
    offsets = {}
    if axis is not None:
        for k, plane in planes.items():
            if area[k] >= 5 and pitches[k] >= AXIS_MIN_PITCH_DEG:
                bearing = math.degrees(math.atan2(-plane[0], -plane[1])) % 360
                offsets[k] = abs((bearing - axis + 45) % 90 - 45)
                if offsets[k] > AXIS_OFFSET_DEG:
                    flags.append(dict(kind='azimuth_off_axis', severity='note', face_ids=[k],
                                      message=f'{k} faces {offsets[k]:.0f} degrees off the roof\'s axes.'))

    length = dict(consistent=0., correctable=0., step=0., inconsistent=0.)
    for (i, j), edges in _shared_edges(shapes).items():
        bad = 0.
        for coords in edges:
            kind = edge_class(planes[i], planes[j], _densify(coords))
            length[kind] += LineString(coords).length
            bad += LineString(coords).length if kind in ('inconsistent', 'step') else 0.
        if bad >= EDGE_FLAG_M:
            flags.append(dict(kind='edge_inconsistent', severity='note', face_ids=[i, j],
                              message=f'{i} and {j} are at different heights along {bad:.1f} m of their shared edge: a real step, or a misplaced edge.'))
    total = sum(length.values())
    edges = dict(length_m=total, **{k: (v / total if total else 0.) for k, v in length.items()})

    if raw_polygon_coverage is not None and raw_polygon_coverage < RAW_COVERAGE_MIN:
        flags.append(dict(kind='raw_coverage_low', severity='review', face_ids=[],
                          message=f'The raw stage covers only {raw_polygon_coverage:.0%} of the roof mask; part of the roof was lost before fitting.'))
    if outline_area:
        covered = sum(s.area for s in shapes.values()) / outline_area
        if covered < OUTLINE_COVERAGE_MIN:
            flags.append(dict(kind='outline_coverage_low', severity='review', face_ids=[],
                              message=f'The faces cover {covered:.0%} of the roof outline.'))
    return dict(status='review' if any(f['severity'] == 'review' for f in flags) else 'ok',
                framing_pitch=framing, edges=edges, low_slope_faces=low,
                axis=dict(bearing_degrees=axis, max_offset_degrees=max(offsets.values()) if offsets else None),
                flags=flags)


def _by_size(groups):
    return [g['id'] for g in sorted(groups, key=lambda g: -g['area_m2'])]
