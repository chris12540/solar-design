"""Experimental straight-line, jointly partitioned roof proposals.

The source reconstruction is never edited. A line arrangement gives every face
one shared topology; plane intersections are preferred over raster stair steps.
Photo gradients can move a proposed line only inside its geometric uncertainty.
They never supply height or authorize a roof outside DSM support.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from rasterio import Affine, band
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds, Window
from rasterio.enums import Resampling
from rasterio.warp import reproject
from shapely.geometry import LineString, Point, Polygon
from shapely import union_all
from shapely.ops import polygonize, unary_union

from .roof_refinement import _model, _poly, _polygons, _record, _plane_intersection, _edge_kind

ALGORITHM_VERSION = "fit-1"
MAX_FACES = 128
MAX_CELLS = 4096


def _raster(raw, inputs):
    try:
        with MemoryFile(inputs['dsm']) as memory, memory.open() as ds:
            if not ds.crs or CRS.from_user_input(ds.crs) != CRS.from_user_input(raw['origin']['crs']):
                return None
            origin = raw['origin']
            ox, oy = Transformer.from_crs('EPSG:4326', ds.crs, always_xy=True).transform(
                origin['longitude'], origin['latitude'])
            bounds = _poly(raw['roof_outline']).bounds
            window = from_bounds(bounds[0]+ox-2, bounds[1]+oy-2, bounds[2]+ox+2, bounds[3]+oy+2, ds.transform).round_offsets().round_lengths()
            window = window.intersection(Window(0, 0, ds.width, ds.height))
            scale = max(1., window.width/512, window.height/512)
            shape = (max(1, int(window.height/scale)), max(1, int(window.width/scale)))
            transform = (Affine.translation(-ox, -oy) * ds.window_transform(window)
                         * Affine.scale(window.width/shape[1], window.height/shape[0]))
            data = ds.read(1, window=window, out_shape=shape, resampling=Resampling.nearest).astype(float)
            valid = np.isfinite(data) & (data != -9999)
            if ds.nodata is not None:
                valid &= data != ds.nodata
            return data, valid, transform
    except (KeyError, ValueError, TypeError, OSError):
        return None


def _mask(raw, inputs, raster):
    """Read the cached roof mask on the bounded DSM crop."""
    if not inputs.get('mask'):
        return None
    try:
        data, _, local = raster
        origin = raw['origin']
        crs = origin['crs']
        ox, oy = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(
            origin['longitude'], origin['latitude'])
        destination = np.zeros(data.shape, dtype='uint8')
        with MemoryFile(inputs['mask']) as memory, memory.open() as ds:
            if not ds.crs:
                return None
            reproject(source=band(ds, 1), destination=destination,
                      src_transform=ds.transform, src_crs=ds.crs,
                      dst_transform=Affine.translation(ox, oy)*local, dst_crs=crs,
                      resampling=Resampling.nearest)
        return destination > 0
    except (KeyError, ValueError, TypeError, OSError):
        return None


def _photo(raw, inputs, home):
    if not inputs.get('rgb'):
        return None
    try:
        from .roof_photo import aligned_rgb
        evidence = aligned_rgb(inputs, raw, home)
        if not evidence:
            return None
        gray = np.asarray(evidence['rgb'], dtype=float).mean(axis=2) / 255.
        gy, gx = np.gradient(gray)
        evidence = dict(evidence)
        evidence['gradient'] = np.hypot(gx, gy)
        return evidence
    except (ImportError, KeyError, ValueError, TypeError, OSError):
        return None


def _direction(outline, tolerance):
    """Length-weighted fourfold orientation; no axis or sample is hardcoded."""
    segments = []
    for part in _polygons(outline):
        coords = list(part.simplify(tolerance, preserve_topology=True).exterior.coords)
        for p, q in zip(coords, coords[1:]):
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dy)
            if length > tolerance * 2:
                segments.append((length, math.atan2(dy, dx)))
    if not segments:
        return 0.
    return math.atan2(sum(w * math.sin(4*a) for w, a in segments),
                      sum(w * math.cos(4*a) for w, a in segments)) / 4


def _straight_outline(poly, angle, tolerance):
    simple = poly.simplify(tolerance, preserve_topology=True)
    coords = list(simple.exterior.coords)[:-1]
    lines = []
    for p, q in zip(coords, coords[1:] + coords[:1]):
        dx, dy = q[0]-p[0], q[1]-p[1]
        a = math.atan2(dy, dx)
        target = angle + round((a-angle)/(math.pi/2)) * math.pi/2
        if abs(math.atan2(math.sin(a-target), math.cos(a-target))) < math.radians(15):
            a = target
        lines.append((np.array([(p[0]+q[0])/2, (p[1]+q[1])/2]),
                      np.array([math.cos(a), math.sin(a)])))
    corners = []
    for i, p in enumerate(coords):
        a, u = lines[i-1]
        b, v = lines[i]
        determinant = u[0]*v[1]-u[1]*v[0]
        if abs(determinant) < .05:
            corners.append(p)
            continue
        t = ((b[0]-a[0])*v[1]-(b[1]-a[1])*v[0])/determinant
        corners.append(tuple(a+t*u))
    candidate = Polygon(corners, [list(r.coords) for r in poly.interiors])
    if (candidate.is_valid and not candidate.is_empty
            and candidate.boundary.hausdorff_distance(poly.boundary) <= tolerance*1.8
            and candidate.symmetric_difference(poly).area <= poly.area*.12):
        return candidate
    # Even a nonorthogonal roof gets a small, straight segmented outline.
    return Polygon(simple.exterior.coords, [list(r.coords) for r in poly.interiors])


def _shift_photo(line, evidence, bound):
    if evidence is None or line.length < .5:
        return line, False
    coords = list(line.coords)
    first, last = np.array(coords[0]), np.array(coords[-1])
    direction = (last-first)/max(np.linalg.norm(last-first), 1e-9)
    normal = np.array([-direction[1], direction[0]])
    points = np.linspace(first, last, min(160, max(10, int(line.length/.12))))
    inverse = ~evidence['transform']
    gradient, valid = evidence['gradient'], evidence['valid']
    def score(offset):
        probe = points + offset*normal
        cols = np.floor(inverse.a*probe[:,0]+inverse.b*probe[:,1]+inverse.c).astype(int)
        rows = np.floor(inverse.d*probe[:,0]+inverse.e*probe[:,1]+inverse.f).astype(int)
        inside = (rows >= 0) & (cols >= 0) & (rows < gradient.shape[0]) & (cols < gradient.shape[1])
        rows, cols = rows[inside], cols[inside]
        selected = valid[rows, cols]
        if selected.sum() < len(points)*.6:
            return 0.
        # Require evidence along the line, not a single high-contrast object.
        values = gradient[rows[selected], cols[selected]]
        return float(np.quantile(values, .4))
    offsets = np.linspace(-bound, bound, 9)
    scores = [score(float(offset)) for offset in offsets]
    best = int(np.argmax(scores))
    baseline = score(0.)
    if scores[best] > max(.025, baseline*1.25):
        delta = float(offsets[best])*normal
        return LineString([tuple(first+delta), tuple(last+delta)]), True
    return line, False


def _groups(faces, shapes, tolerance):
    groups = []
    for index, face in enumerate(faces):
        model = _model(face)
        assigned = False
        for group in groups:
            anchor = _model(faces[group[0]])
            # Compare full local support, not just intercepts or azimuths.
            vertices = list(shapes[index].envelope.exterior.coords)
            vertices += list(shapes[group[0]].envelope.exterior.coords)
            angle = np.dot([*model[:2], -1], [*anchor[:2], -1]) / (
                np.linalg.norm([*model[:2], -1])*np.linalg.norm([*anchor[:2], -1]))
            delta = max(abs((model[0]-anchor[0])*x+(model[1]-anchor[1])*y+model[2]-anchor[2]) for x,y in vertices)
            if angle > math.cos(math.radians(4)) and delta <= tolerance:
                group.append(index)
                assigned = True
                break
        if not assigned:
            groups.append([index])
    return groups


def fit(raw: dict[str, Any], inputs: dict[str, Any], home: dict[str, Any]) -> dict[str, Any]:
    """Fit an evidence-scored line arrangement in source local projected meters."""
    warnings = []
    result = dict(algorithm_version=ALGORITHM_VERSION, status='unavailable', face_groups=[],
                  edges=[], warnings=warnings, design_ready=False, quality={
                      'coverage_fraction': 0., 'height_rmse_m': None, 'outline_iou': 0.,
                      'max_boundary_deviation_m': 0., 'overlap_area_m2': 0.,
                      'unexplained_fraction': 1., 'checks_passed': False})
    if raw.get('status') != 'needs_review':
        warnings.append('A successful raw reconstruction is required for fitting.')
        return result
    try:
        outline = _poly(raw.get('roof_outline') or {})
        faces, shapes = [], []
        for face in (raw.get('faces') or [])[:MAX_FACES]:
            shape = _poly(face)
            if shape.is_valid and shape.area > .01 and _model(face) is not None:
                shape = shape.intersection(outline)
                if not shape.is_empty:
                    faces.append(face)
                    shapes.append(shape)
        if not outline.is_valid or outline.is_empty or not faces:
            warnings.append('Valid outline and modeled raw faces are required.')
            return result
        pixel = float((raw.get('quality') or {}).get('pixel_size_m') or .1)
        tolerance = min(.65, max(.35, pixel*2.5))
        raster = _raster(raw, inputs)
        photo = _photo(raw, inputs, home)
        if raster is None:
            warnings.append('DSM evidence is unavailable; no geometry was fitted.')
            return result
        angle = _direction(outline, tolerance)
        # Keep every explicit hole and obstruction; they are never cell-filled.
        source_union = unary_union(shapes)
        holes = [Polygon(ring) for shape in [outline, source_union, *shapes] for p in _polygons(shape) for ring in p.interiors]
        obstructions = [_poly(item) for item in raw.get('obstruction_candidates', [])]
        protected = unary_union([p for p in holes+obstructions if p.is_valid and not p.is_empty])
        domain = unary_union([_straight_outline(p, angle, tolerance) for p in _polygons(outline)])
        # Reject outline expansion where no modeled DSM support exists.
        data, valid, transform = raster
        rows, cols = np.indices(data.shape)
        xx = transform.a*(cols+.5)+transform.b*(rows+.5)+transform.c
        yy = transform.d*(cols+.5)+transform.e*(rows+.5)+transform.f
        added = domain.difference(outline)
        if not added.is_empty:
            addition = rasterize([(added, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool)
            if addition.any():
                residual = np.full(data.shape, np.inf)
                for face in faces:
                    m = _model(face)
                    np.minimum(residual, np.abs(data-(m[0]*xx+m[1]*yy+m[2])), out=residual)
                if np.mean(valid[addition] & (residual[addition] <= .75)) < .65:
                    domain = outline.simplify(tolerance*.5, preserve_topology=True)
        domain = domain.difference(protected)
        groups = _groups(faces, shapes, .15)
        sources = [unary_union([shapes[i] for i in group]) for group in groups]
        models = [_model(faces[group[0]]) for group in groups]
        lines = [domain.boundary]
        replacements = [[] for _ in groups]
        plane_lines, snapped = 0, 0
        for i, a in enumerate(sources):
            for j in range(i+1, len(sources)):
                b = sources[j]
                if a.distance(b) > tolerance*2:
                    continue
                candidate = _plane_intersection(models[i], models[j], domain.envelope.buffer(2))
                if candidate is None:
                    continue
                near = a.boundary.buffer(tolerance*2).intersection(b.boundary.buffer(tolerance*2))
                supported = candidate.intersection(near)
                if supported.length < max(.7, pixel*3):
                    continue
                # A useful intersection must account for a meaningful boundary,
                # not merely touch two unrelated regions at a vertex.
                common = a.boundary.intersection(b.buffer(tolerance))
                if common.length > .5 and supported.length < common.length*.35:
                    continue
                shifted, used = _shift_photo(candidate, photo, min(.12, pixel*.6))
                # Photo is secondary: a shifted ridge must still agree in height.
                p = shifted.interpolate(.5, normalized=True)
                delta = abs((models[i][0]-models[j][0])*p.x+(models[i][1]-models[j][1])*p.y+models[i][2]-models[j][2])
                if delta > .12:
                    shifted, used = candidate, False
                # Extend through the connected outline to reach arrangement nodes;
                # source support restricts ownership so unrelated wings cannot
                # be claimed by this plane merely because a line crosses them.
                components = [p for p in _polygons(domain) if p.distance(a) <= tolerance and p.distance(b) <= tolerance]
                lines.append(shifted.intersection(unary_union(components)))
                replacements[i].append(near.buffer(tolerance))
                replacements[j].append(near.buffer(tolerance))
                plane_lines += 1
                snapped += int(used)
        for i, source in enumerate(sources):
            # Keep unsupported breaks, but replace stair-stepped shared ridges as
            # a whole rather than separately simplifying their two sides.
            boundary = source.simplify(tolerance, preserve_topology=True).boundary
            if replacements[i]:
                boundary = boundary.difference(unary_union(replacements[i]))
            lines.append(boundary.intersection(domain))
        cells = [cell for cell in polygonize(union_all(lines,grid_size=1e-7))
                 if domain.covers(cell.representative_point()) and cell.area > 1e-7]
        if len(cells) > MAX_CELLS or len(cells)*data.size > 40_000_000:
            warnings.append('The line arrangement exceeded the bounded complexity limit.')
            return result
        assigned = [[] for _ in groups]
        errors, absolute_errors, sampled = [], [], 0
        for cell in cells:
            mask = rasterize([(cell, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & valid
            eligible = [i for i, source in enumerate(sources) if source.distance(cell) <= tolerance*2]
            if not eligible:
                continue
            support = {i: cell.intersection(sources[i]).area / cell.area for i in eligible}
            residuals = {i: float(np.mean(np.abs(data[mask]-(models[i][0]*xx[mask]+models[i][1]*yy[mask]+models[i][2])))) if mask.any() else None for i in eligible}
            # Cell ownership uses source labels and independent height evidence.
            scores = {i: support[i] - .65*min(2., residuals[i] if residuals[i] is not None else 1.) for i in eligible}
            winner = max(eligible, key=lambda i: (scores[i], support[i], -i))
            if support[winner] < .03:
                continue
            assigned[winner].append(cell)
            if mask.any():
                m = models[winner]
                residual = data[mask]-(m[0]*xx[mask]+m[1]*yy[mask]+m[2])
                errors.append(float(np.square(residual).sum()))
                absolute_errors.append(np.abs(residual))
                sampled += len(residual)
        emitted = []
        for index, group in enumerate(groups):
            # Zero-tolerance removes only redundant collinear nodes; independent
            # positive-tolerance simplification would tear shared topology.
            shape = unary_union(assigned[index]).simplify(1e-9, preserve_topology=True)
            parts = _polygons(shape)
            if not parts:
                continue
            representative = faces[group[0]]
            emitted.append(shape)
            result['face_groups'].append(dict(
                id=f'group-{len(emitted)}', parts=[_record(p) for p in parts],
                source_region_ids=[str(faces[i].get('id', f'region-{i+1}')) for i in group],
                source_plane_ids=sorted({str(faces[i].get('source_plane_id', faces[i].get('id', f'plane-{i+1}'))) for i in group}),
                plane_model=dict(representative['plane_model']),
                pitch_degrees=float(representative.get('pitch_degrees') or 0),
                azimuth_degrees=float(representative.get('azimuth_degrees') or 0),
                area_m2=float(shape.area), largest_contiguous_area_m2=max(p.area for p in parts),
                fit_rmse_m=max(float(faces[i].get('fit_rmse_m') or 0) for i in group),
                design_ready=False))
        for i, first in enumerate(emitted):
            for j in range(i+1, len(emitted)):
                shared = first.boundary.intersection(emitted[j].boundary)
                segments = [shared] if shared.geom_type == 'LineString' else list(getattr(shared, 'geoms', []))
                for edge in segments:
                    if edge.geom_type != 'LineString' or edge.length < max(.2, pixel*2):
                        continue
                    edge = edge.simplify(1e-7)
                    pair = [result['face_groups'][i], result['face_groups'][j]]
                    result['edges'].append(dict(id=f"edge-{len(result['edges'])+1}",
                        face_ids=[f['id'] for f in pair],
                        coordinates=[[float(x),float(y)] for x,y in edge.coords],
                        kind=_edge_kind(edge,pair,[first,emitted[j]]), inferred=True))
        output = unary_union(emitted)
        overlap = sum(g.area for g in emitted)-output.area
        iou = output.intersection(outline).area/output.union(outline).area if not output.is_empty else 0.
        coverage = output.intersection(outline).area/outline.area
        outer_output = unary_union([p.exterior for p in _polygons(output)])
        outer_source = unary_union([p.exterior for p in _polygons(outline)])
        deviation = outer_output.hausdorff_distance(outer_source) if not output.is_empty else 0.
        rmse = math.sqrt(sum(errors)/sampled) if sampled else None
        result['quality']['checks_passed'] = bool(coverage >= .9 and rmse is not None and rmse <= .35 and overlap <= 1e-6)
        roof_mask = _mask(raw, inputs, raster)
        output_pixels = rasterize([(output, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) if not output.is_empty else np.zeros(data.shape, dtype=bool)
        mask_support = float(np.mean(roof_mask[output_pixels])) if roof_mask is not None and output_pixels.any() else None
        absolutes = np.concatenate(absolute_errors) if absolute_errors else None
        photo_support = None
        if photo is not None:
            boundary = unary_union([g.boundary for g in emitted])
            count = max(1, min(8000, int(boundary.length/max(.1, pixel))))
            points = [boundary.interpolate(i/count, normalized=True) for i in range(count)]
            inv = ~photo['transform']
            hits = []
            for point in points:
                col = inv.a*point.x + inv.b*point.y + inv.c
                row = inv.d*point.x + inv.e*point.y + inv.f
                row, col = math.floor(row), math.floor(col)
                if (0 <= row < photo['gradient'].shape[0] and 0 <= col < photo['gradient'].shape[1]
                        and photo['valid'][row, col]):
                    hits.append(photo['gradient'][row, col] >= .04)
            if hits:
                photo_support = float(np.mean(hits))
        result['quality'].update(coverage_fraction=coverage, height_rmse_m=rmse, outline_iou=iou,
                                 max_boundary_deviation_m=deviation, overlap_area_m2=max(0., overlap),
                                 unexplained_fraction=max(0., 1-coverage),
                                 height_median_absolute_error_m=float(np.median(absolutes)) if absolutes is not None else None,
                                 height_p90_absolute_error_m=float(np.percentile(absolutes,90)) if absolutes is not None else None,
                                 roof_mask_support_fraction=mask_support,
                                 source_vertex_count=sum(len(p.exterior.coords)-1 for s in shapes for p in _polygons(s)),
                                 fitted_vertex_count=sum(len(p.exterior.coords)-1 for s in emitted for p in _polygons(s)),
                                 arrangement_cell_count=len(cells), plane_intersection_count=plane_lines,
                                 photo_evidence_available=photo is not None, photo_evidence_used=photo is not None,
                                 photo_geometry_adjusted=snapped > 0, photo_snapped_line_count=snapped,
                                 photo_edge_support=photo_support, photo_gradient_threshold=.04,
                                 checks={'coverage': coverage >= .9, 'height': rmse is not None and rmse <= .35,
                                         'no_overlap': overlap <= 1e-6, 'design_validation': False})
        represented = {plane for group in result['face_groups'] for plane in group['source_plane_ids']}
        source_planes = {str(face.get('source_plane_id',face.get('id'))) for face in faces}
        missing_planes = sorted(source_planes-represented)
        result['quality']['unrepresented_source_planes'] = missing_planes
        result['quality']['checks']['source_planes_retained'] = not missing_planes
        result['quality']['checks_passed'] = result['quality']['checks_passed'] and not missing_planes
        if missing_planes:
            warnings.append('Some source planes were not retained by the fitted topology: '+', '.join(missing_planes)+'. Their connections remain unresolved.')
        if rmse is None or rmse > .35:
            warnings.append(f'Height fit failed the development check (RMSE {rmse:.2f} m; limit 0.35 m).' if rmse is not None else 'Height fit could not be measured.')
        warnings.append('Experimental automatic fitting requires roof and obstruction review; design validation has not passed.')
        if photo is None:
            warnings.append('Aligned RGB evidence was unavailable; photo boundaries were not checked.')
        result['status'] = 'experimental' if emitted else 'unavailable'
        return result
    except Exception as exc:
        result['face_groups'] = []
        warnings.append(f'Fitting was withheld after a geometry error ({type(exc).__name__}).')
        return result
