"""Straight-edged copy of the fitted roof faces.

The fit traces faces from a 10 cm height raster, so its edges stair-step. Here every edge shared by
two faces (or by a face and the outside) is rebuilt as a few straight segments: edges that run along
the roof's own axes or at 45 degrees are made exactly so, corners are placed where lines meet, and
every shared edge stays a single line so neighbouring faces still tile. The fit itself is not changed.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import shapely
from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, polygonize, unary_union

from .roof_refinement import _polygons, _record

SIMPLIFY_M = .25         # an edge is replaced by segments that stay within this of it
DIRECTIONS = (0., 45., 90., 135., 180.)   # degrees from the roof's dominant direction
SNAP_DEG = 10.           # a segment this close to one of those directions is made exactly parallel to it
SNAP_MIN_M = 1.          # shorter segments are too short to tell a direction from noise
STEP_M = .5              # two parallel segments this close, joined by a short jog, become one line
NODE_REACH_M = .7        # a junction, or a corner meeting point, may move this far
CHAMFER_M = 1.6          # a corner cut shorter than this, between two long edges, is squared
CORNER_REACH_M = 1.1     # ... if the squared corner lies this close to the cut
MIN_PIECE_M2 = .3        # smaller pieces of rebuilt linework are not faces
HOLE_MIN_M2 = .15        # holes at least this big are kept open
MIN_FACE_IOU = .6        # a straightened face must still overlap its fitted face this much
MAX_AREA_CHANGE = .03    # the faces together may gain or lose at most this share of their area
LONG_EDGE_M = 1.         # for the report: edge length in straight runs at least this long


def _valid(geometry):
    return geometry if geometry.is_valid else geometry.buffer(0)


def _turn(geometry, angle):
    """Rotate about the origin and snap to a 1 um grid so exactly shared edges stay exactly shared."""
    moved = rotate(_valid(geometry), angle, origin=(0, 0), use_radians=True)
    try:
        moved = shapely.set_precision(moved, 1e-6)
    except shapely.errors.GEOSException:
        moved = moved.buffer(0)
    return _valid(moved)


def _douglas_peucker(points, tolerance):
    """Indices of the points kept by Douglas-Peucker on an (n, 2) array."""
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        start, end = points[first], points[last]
        along = end - start
        length = float(np.hypot(*along))
        between = points[first + 1:last]
        if length < 1e-12:
            distance = np.hypot(*(between - start).T)
        else:
            distance = np.abs(along[0]*(between[:, 1]-start[1]) - along[1]*(between[:, 0]-start[0])) / length
        worst = int(np.argmax(distance))
        if distance[worst] > tolerance:
            middle = first + 1 + worst
            keep[middle] = True
            stack += [(first, middle), (middle, last)]
    return np.flatnonzero(keep)


def _meeting(first, second):
    """Where two (point, unit direction) lines cross, or None if they are nearly parallel."""
    (p, u), (q, v) = first, second
    determinant = u[0]*v[1] - u[1]*v[0]
    if abs(determinant) < math.sin(math.radians(8.)):
        return None
    t = ((q[0]-p[0])*v[1] - (q[1]-p[1])*v[0]) / determinant
    return p + t*u


def _segments(points):
    """Straight segments fitted to one chain of an edge: dicts with 'line' (point, unit direction), dense index range 'a'..'b' and length."""
    kept = _douglas_peucker(points, SIMPLIFY_M)
    segments = []
    for a, b in zip(kept, kept[1:]):
        chord = points[b] - points[a]
        length = float(np.hypot(*chord))
        angle = math.degrees(math.atan2(chord[1], chord[0])) % 180.
        target = min(DIRECTIONS, key=lambda t: abs(angle - t))
        snapped = length >= SNAP_MIN_M and abs(angle - target) <= SNAP_DEG
        if snapped:
            u = np.array([math.cos(math.radians(target)), math.sin(math.radians(target))])
            normal = np.array([-u[1], u[0]])
            dense = points[a:b+1]
            line = (normal*float(np.median(dense @ normal)) + u*float(np.median(dense @ u)), u)
        else:
            line = (points[a].copy(), chord/length if length > 1e-12 else np.array([1., 0.]))
        segments.append(dict(line=line, a=a, b=b, length=length, theta=target if snapped else None))
    changed = True
    while changed and len(segments) >= 3:           # a short jog between two parallel, nearly collinear segments is a step in the raster
        changed = False
        for i in range(1, len(segments) - 1):
            before, jog, after = segments[i-1], segments[i], segments[i+1]
            if jog['length'] < SNAP_MIN_M and before['theta'] is not None and before['theta'] == after['theta']:
                normal = np.array([-before['line'][1][1], before['line'][1][0]])
                if abs(float(before['line'][0] @ normal) - float(after['line'][0] @ normal)) <= STEP_M:
                    u = before['line'][1]
                    dense = points[before['a']:after['b']+1]
                    segments[i-1:i+2] = [dict(line=(normal*float(np.median(dense @ normal)) + u*float(np.median(dense @ u)), u),
                                              a=before['a'], b=after['b'], theta=before['theta'],
                                              length=before['length'] + jog['length'] + after['length'])]
                    changed = True
                    break
    i = 1
    while i < len(segments) - 1:                    # square a rounded or chamfered corner: drop the short run of segments between two long edges
        end, total = i, 0.
        while end < len(segments) - 1 and total + segments[end]['length'] <= CHAMFER_M and (end == i or segments[end]['length'] < SNAP_MIN_M):
            total += segments[end]['length']
            end += 1
        before, after = segments[i-1], segments[end]
        if end > i and before['length'] >= SNAP_MIN_M and after['length'] >= SNAP_MIN_M:
            corner = _meeting(before['line'], after['line'])
            middle = points[(segments[i]['a'] + segments[end-1]['b']) // 2]
            if corner is not None and math.dist(corner, middle) <= CORNER_REACH_M:
                before['cut_middle'] = middle
                del segments[i:end]
                continue
        i += 1
    return segments


def _from_a_corner(points):
    """A closed ring rolled to start at its vertex farthest from the centre, which is a corner, so no corner straddles the start."""
    if len(points) < 4 or not np.allclose(points[0], points[-1]):
        return points
    ring = points[:-1]
    start = int(np.argmax(np.hypot(*(ring - ring.mean(axis=0)).T)))
    rolled = np.roll(ring, -start, axis=0)
    return np.vstack([rolled, rolled[:1]])


def _chains(shapes):
    """The edges of `shapes` as chains that run from junction to junction (a lone ring is one chain)."""
    lines = unary_union([g.boundary for g in shapes])
    if lines.geom_type == 'LineString':
        return [lines]
    merged = linemerge(lines)
    return list(merged.geoms) if hasattr(merged, 'geoms') else [merged]


def _straighten_in_frame(faces, holes):
    """`faces` {id: geometry} with the roof's dominant direction along x. Returns {id: geometry}."""
    key = lambda p: (round(float(p[0]), 4), round(float(p[1]), 4))
    chains, junction_ends = [], {}
    for chain in _chains(faces.values()):
        points = _from_a_corner(np.array(chain.coords))
        segments = _segments(points)
        chains.append((points, segments))
        junction_ends.setdefault(key(points[0]), []).append(segments[0])
        junction_ends.setdefault(key(points[-1]), []).append(segments[-1])
    for ends in junction_ends.values():                    # two collinear edges meeting at a junction are one straight line
        for i, first in enumerate(ends):
            for second in ends[i+1:]:
                if first['theta'] is not None and first['theta'] == second['theta']:
                    u = first['line'][1]
                    normal = np.array([-u[1], u[0]])
                    offsets = [float(first['line'][0] @ normal), float(second['line'][0] @ normal)]
                    if abs(offsets[0] - offsets[1]) <= STEP_M:
                        along = (float(first['line'][0] @ u) + float(second['line'][0] @ u)) / 2
                        shared = (normal*(sum(offsets)/2) + u*along, u)
                        first['line'] = second['line'] = shared
    moved = {}
    for where, ends in junction_ends.items():              # one position per junction: closest point to every edge that ends there
        lines = [end['line'] for end in ends]
        if len(lines) < 2:
            continue
        a, b = np.zeros((2, 2)), np.zeros(2)
        for p, u in lines:
            away = np.eye(2) - np.outer(u, u)
            a += away
            b += away @ p
        try:
            best = np.linalg.solve(a, b)
        except np.linalg.LinAlgError:
            continue
        if math.dist(best, where) <= NODE_REACH_M:
            moved[where] = best
    rebuilt = []
    for points, segments in chains:
        vertices = [moved.get(key(points[0]), points[0])]
        for before, after in zip(segments, segments[1:]):
            corner = _meeting(before['line'], after['line'])
            anchor = before.get('cut_middle')
            origin = anchor if anchor is not None else points[before['b']]
            if corner is None or math.dist(corner, origin) > (CORNER_REACH_M if anchor is not None else NODE_REACH_M):
                corner = origin
            vertices.append(corner)
        vertices.append(moved.get(key(points[-1]), points[-1]))
        clean = [vertices[0]]
        for vertex in vertices[1:]:
            if math.dist(vertex, clean[-1]) > 1e-9:
                clean.append(vertex)
        rebuilt.append(LineString(clean) if len(clean) >= 2 else LineString(points))
    pieces = [p for p in polygonize(unary_union(rebuilt)) if p.area >= MIN_PIECE_M2]
    owned = {name: [] for name in faces}
    for piece in pieces:
        name, original = max(faces.items(), key=lambda item: piece.intersection(item[1]).area)
        if piece.intersection(original).area >= .5 * piece.area:
            owned[name].append(piece)
    out = {name: unary_union(parts) for name, parts in owned.items() if parts}
    for hole in holes:                                       # an opening the rebuilt faces now cover goes back, as a simpler outline
        if hole.area >= HOLE_MIN_M2 and unary_union(list(out.values())).intersection(hole).area > .3 * hole.area:
            simple = hole.simplify(.3, preserve_topology=True).buffer(0)
            out = {name: shape.difference(simple) for name, shape in out.items()}
            out = {name: shape for name, shape in out.items() if not shape.is_empty}
    return out


def straighten(faces: dict[str, Any], angle: float) -> dict[str, Any]:
    """Straight-edged copy of `faces` ({id: shapely geometry}) in the fit's local frame; `angle` is the roof's dominant direction in radians."""
    turned = {name: _turn(shape, -angle) for name, shape in faces.items()}
    union = unary_union(list(turned.values()))
    holes = [Polygon(ring) for part in _polygons(union) for ring in part.interiors]
    straight = _straighten_in_frame(turned, holes)
    return {name: _turn(shape, angle) for name, shape in straight.items()}


def _vertex_count(shapes):
    return sum(len(part.exterior.coords) - 1 for shape in shapes for part in _polygons(shape))


def _long_edge_share(shapes, angle):
    """Share of the faces' edge length lying in straight runs of LONG_EDGE_M or more (shared edges counted once)."""
    total = long = 0.
    for chain in _chains([_turn(s, -angle) for s in shapes]):
        points = list(chain.coords)
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            total += length
            long += length if length >= LONG_EDGE_M else 0.
    return long / total if total else 0.


def _problem(faces, straight):
    """Why a straightened result must not be used, or None."""
    if set(straight) != set(faces):
        return 'faces were lost: ' + ', '.join(sorted(set(faces) - set(straight)))
    for name, shape in faces.items():
        new = straight[name]
        overlap = new.intersection(shape).area / max(new.union(shape).area, 1e-9)
        if overlap < MIN_FACE_IOU:
            return f'{name} changed too much (overlap with the fitted face {overlap:.2f})'
    before, after = sum(s.area for s in faces.values()), sum(s.area for s in straight.values())
    if abs(after - before) > MAX_AREA_CHANGE * before:
        return f'the faces changed area by {after - before:+.1f} m2'
    shapes = list(straight.values())
    shared = sum(a.intersection(b).area for i, a in enumerate(shapes) for b in shapes[i+1:])
    if shared > 1e-6 * after:
        return f'straightened faces overlap by {shared:.2f} m2'
    if not all(s.is_valid for s in shapes):
        return 'a straightened face is not a valid polygon'
    return None


def straighten_fit(groups: list[dict[str, Any]], shapes: list[Any], angle: float) -> dict[str, Any]:
    """Straightened copy of a fit's face groups, with the quality it was accepted on, or why it was skipped."""
    faces = {group['id']: shape for group, shape in zip(groups, shapes)}
    try:
        straight = straighten(faces, angle)
        problem = _problem(faces, straight)
    except Exception as exc:       # the fit must never be lost to a cosmetic step
        return dict(status='skipped', reason=f'straightening failed ({type(exc).__name__})', face_groups=[])
    if problem:
        return dict(status='skipped', reason=problem, face_groups=[])
    out = []
    for group in groups:
        shape = straight[group['id']]
        parts = _polygons(shape)
        out.append(dict(group, parts=[_record(part) for part in parts], area_m2=float(shape.area),
                        largest_contiguous_area_m2=max(part.area for part in parts)))
    before, after = list(faces.values()), list(straight.values())
    return dict(status='ok', face_groups=out, quality=dict(
        vertex_count=_vertex_count(after), source_vertex_count=_vertex_count(before),
        long_edge_share=_long_edge_share(after, angle), source_long_edge_share=_long_edge_share(before, angle),
        area_change_m2=float(sum(s.area for s in after) - sum(s.area for s in before)),
        min_face_overlap=float(min(straight[name].intersection(shape).area / max(straight[name].union(shape).area, 1e-9) for name, shape in faces.items()))))
