"""Experimental straight-line, jointly partitioned roof proposals.

The source reconstruction is never edited. A line arrangement gives every face
one shared topology; plane intersections are preferred over raster stair steps.
Photo gradients can move a proposed line only inside its geometric uncertainty.
They never supply height or authorize a roof outside DSM support. A face never
claims pixels its own plane does not explain; those become unmodeled regions.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from rasterio import Affine, band
from rasterio.features import rasterize, shapes
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds, Window
from rasterio.enums import Resampling
from rasterio.warp import reproject
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry import shape as geometry_of
from shapely import union_all
from shapely.ops import polygonize, unary_union

from .roof_cleanup import straighten_fit
from .roof_refinement import _model, _poly, _polygons, _record, _plane_intersection, _edge_kind

ALGORITHM_VERSION = "fit-7"
MAX_FACES = 128
MAX_CELLS = 4096
RETENTION_MIN = .5   # a plane group keeping less of its source area than this is reported as degraded
UNMODELED_RESIDUAL_M = .35   # same limit the raw stage uses to assign a pixel to a plane
MIN_UNMODELED_M2 = .5
UNMODELED_OPEN_PX = 1        # opening radius that drops seam noise thinner than this
KIND_RESIDUAL_M = .5         # mean residual beyond which an unmodeled region is raised or recessed
RIDGE_REACH_M = 1.5          # how far past its supported span a ridge may run to meet another line
MIXED_CELL_M2 = .5           # a cell is mixed when two sources each have at least this much in it ...
MIXED_SHARE = .15            # ... and at least this share of their own area (a sliver of a big face is just edge noise)
PIECE_FLOOR_M2 = .1          # smallest source overlap that becomes its own piece
SLOPE_RADIUS_PX = 2          # local slope is a least-squares plane over a (2r+1)^2 pixel window
TILT_SEED_GAP = .5           # slope vector differing from the owning face by more than this seeds a tilt region ...
TILT_GROW_GAP = .3           # ... which then grows over pixels differing by more than this
TILT_MAX_DISPERSION = .4     # a real facet has one coherent slope; a smoothed crease blends many
TILT_PITCH_DEG = (8., 45.)   # slope of a plausible facet
TILT_MIN_SEED_M2 = .5
TILT_MIN_WIDTH_M = .6        # smoothed creases are long bands only a few pixels wide
TILT_MIN_REGION_M2 = .8
TILT_REACH_M = 1.            # how far from its seed a tilt region may grow
TILT_MAX_TOTAL_FRACTION = .15  # more than this carved as tilt means the height model is unreliable
MAX_CARVE_FRACTION = .4      # a plane unexplained over more of its area than this is a bad fit, not a few unmodeled regions


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


def _contact_lines(sources, skip, reach, tolerance, minimum):
    """Source-label boundaries between touching plane groups whose ridge was not accepted.

    A rejected ridge candidate means the plane intersection disagrees with the
    source labels, so the label boundary is the only evidence separating the two
    groups. Without it a neighbouring ridge's replacement buffer can erase the
    boundary, leaving one arrangement cell that mixes both groups, and the whole
    cell then goes to whichever plane has the lower residual over the mixture.
    """
    lines = []
    for i, a in enumerate(sources):
        for j in range(i+1, len(sources)):
            if (i, j) in skip:
                continue
            shared = a.boundary.intersection(sources[j].buffer(reach))
            for part in getattr(shared, 'geoms', [shared]):
                if part.geom_type == 'LineString' and part.length >= minimum:
                    lines.append(part.simplify(tolerance, preserve_topology=False))
    return lines


def _retention(source_areas, fitted_areas):
    """Fitted area as a fraction of each group's source area (1 when the source has none)."""
    return [fitted/source if source > 0 else 1. for source, fitted in zip(source_areas, fitted_areas)]


def _parts(geometry):
    return list(geometry.geoms) if hasattr(geometry, 'geoms') else [geometry]


def _ridge_junctions(ridges, index, reach):
    """Points where ridge `index` crosses another accepted ridge, with evidence of both within `reach`.

    Hips and the ridge they climb to meet at one point, but each supported span stops where its
    two faces stop touching, a little short of it. `ridges` holds (line, supported, ...) tuples.
    """
    line, supported = ridges[index][:2]
    points = []
    for other, (candidate, span, *_) in enumerate(ridges):
        if other == index:
            continue
        hit = line.intersection(candidate)
        if hit.geom_type == 'Point' and not hit.is_empty and supported.distance(hit) <= reach and span.distance(hit) <= reach:
            points.append(hit)
    return points


def _trim_ridge(line, supported, network, reach, junctions=()):
    """The stretch of a plane-intersection line that carries evidence, or None.

    `line` is the full intersection of two planes; only `supported` (where the two faces meet)
    is evidence of a ridge, hip or valley. Each end then runs on, up to `reach`, to the first
    line in `network` or the first of `junctions` (points on `line` where another ridge crosses
    it), so the ridge still meets the boundary or the next ridge. Beyond that the line is
    dropped: planes intersect forever, faces do not.
    """
    start, end = np.array(line.coords[0]), np.array(line.coords[-1])
    length = float(np.linalg.norm(end-start))
    if length < 1e-9 or supported.is_empty:
        return None
    axis = (end-start)/length
    spans = [float(np.dot(np.array(p)-start, axis)) for g in _parts(supported) if not g.is_empty for p in g.coords]
    low, high = max(min(spans), 0.), min(max(spans), length)
    if high-low < 1e-6:
        return None
    meeting = [float(np.dot(np.array(p.coords[0])-start, axis)) for p in junctions]

    def extend(t, sign):
        origin = start+axis*t
        hit = LineString([tuple(origin), tuple(origin+sign*axis*reach)]).intersection(network)
        steps = [float(np.dot(np.array(p)-origin, sign*axis)) for g in _parts(hit) if not g.is_empty for p in g.coords]
        steps += [(s-t)*sign for s in meeting if 0 <= (s-t)*sign <= reach]
        steps = [d for d in steps if d >= -1e-9]
        return t+sign*min(steps) if steps else t
    return LineString([tuple(start+axis*extend(low, -1)), tuple(start+axis*extend(high, 1))])


def _split_mixed(cells, sources, minimum, share, floor):
    """Split cells that straddle faces, or hold a source plus unclaimed area, into one piece per owner.

    A cell goes whole to one plane. A cell straddling two faces gives the smaller one away, and
    a cell holding one face plus area no plane claims would absorb that area into the face.
    A source counts as straddled only if the cell holds `minimum` m2 of it and `share` of its
    area, so edge noise around a correctly straight ridge does not undo the ridge. A cell is also
    split when `minimum` m2 or more of it is claimed by no source. Pieces keep each source's own
    area; the unclaimed rest becomes a separate piece that the support rule then leaves empty.
    """
    pieces = []
    for cell in cells:
        overlap = [(cell.intersection(source), k) for k, source in enumerate(sources)]
        claimed = [part for part, _ in overlap if part.area >= floor]
        straddled = sum(1 for part, k in overlap if part.area >= minimum and part.area >= share*sources[k].area) >= 2
        remainder = cell.difference(unary_union(claimed)) if claimed else cell
        if not claimed or not (straddled or remainder.area >= minimum):
            pieces.append(cell)
            continue
        for geometry in [*claimed, remainder]:
            pieces += [g for g in _parts(geometry) if g.geom_type == 'Polygon' and g.area > 1e-7]
    return pieces


def _shift(mask, dy, dx):
    out = np.zeros_like(mask)
    h, w = mask.shape
    out[max(dy, 0):h+min(dy, 0), max(dx, 0):w+min(dx, 0)] = mask[max(-dy, 0):h+min(-dy, 0), max(-dx, 0):w+min(-dx, 0)]
    return out


def _open_mask(mask, radius):
    """Binary opening with a 3 x 3 element, `radius` times; removes features thinner than 2*radius+1 pixels."""
    offsets = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    for _ in range(radius):
        mask = mask & np.all([_shift(mask, dy, dx) for dy, dx in offsets], axis=0)
    for _ in range(radius):
        mask = mask | np.any([_shift(mask, dy, dx) for dy, dx in offsets], axis=0)
    return mask


def _kind(mean_residual):
    if mean_residual >= KIND_RESIDUAL_M:
        return 'raised'
    return 'recessed' if mean_residual <= -KIND_RESIDUAL_M else 'uneven'


def _carve_unmodeled(shape, model, raster, xx, yy):
    """Remove from `shape` the areas its plane does not explain; return (shape, regions).

    A region is a connected set of valid pixels more than UNMODELED_RESIDUAL_M off the
    plane (after dropping seam-width noise) and at least MIN_UNMODELED_M2 in area. Without
    this, a cell that mixes a plane with an adjacent raised section, recess or unmodeled
    facet gives the whole cell, mixture included, to that plane. If more than
    MAX_CARVE_FRACTION of the face would go, the plane itself is wrong: nothing is carved
    and the height error stays visible in the quality figures.
    """
    data, valid, transform = raster
    if shape.is_empty:
        return shape, []
    inside = rasterize([(shape, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & valid
    residual = data - (model[0]*xx + model[1]*yy + model[2])
    bad = _open_mask(inside & (np.abs(residual) > UNMODELED_RESIDUAL_M), UNMODELED_OPEN_PX)
    if not bad.any():
        return shape, []
    regions = []
    for geom, _ in shapes(bad.astype('uint8'), mask=bad, transform=transform, connectivity=8):
        polygon = geometry_of(geom)
        if polygon.area < MIN_UNMODELED_M2:
            continue
        pixels = rasterize([(polygon, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & bad
        mean = float(np.mean(residual[pixels]))
        regions.append(dict(geometry=polygon, area_m2=float(polygon.area), pixels=int(pixels.sum()),
                            mean_residual_m=mean, max_abs_residual_m=float(np.max(np.abs(residual[pixels]))),
                            kind=_kind(mean)))
    removed = unary_union([r['geometry'] for r in regions]) if regions else None
    if removed is None or removed.intersection(shape).area > MAX_CARVE_FRACTION*shape.area:
        return shape, []
    return shape.difference(removed), regions


def _box_sum(a, r):
    """Sum over every (2r+1) x (2r+1) window of `a` (valid positions only)."""
    k = 2*r+1
    c = np.cumsum(np.cumsum(np.pad(a, ((r+1, r), (r+1, r))), 0), 1)
    return c[k:, k:]-c[:-k, k:]-c[k:, :-k]+c[:-k, :-k]


def _local_slope(data, valid, transform, radius):
    """Surface slope (east, north), as rise per metre, from a least-squares plane in a window around each pixel.

    NaN where the window holds too little height data.
    """
    v = valid.astype(float)
    z = np.where(valid, data, 0.).astype(float)
    rows, cols = (g.astype(float) for g in np.indices(data.shape))
    n = _box_sum(v, radius)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = lambda q: _box_sum(v*q, radius)/n
        mc, mr, mz = mean(cols), mean(rows), mean(z)
        d_col = (mean(cols*z)-mc*mz)/(mean(cols*cols)-mc*mc)       # rise per pixel along columns
        d_row = (mean(rows*z)-mr*mz)/(mean(rows*rows)-mr*mr)
        det = transform.a*transform.e-transform.b*transform.d
        east = (d_col*transform.e-d_row*transform.d)/det           # solve [[a, d], [b, e]] . (east, north) = (d_col, d_row)
        north = (d_row*transform.a-d_col*transform.b)/det
    thin = n < .6*(2*radius+1)**2
    return np.where(thin, np.nan, east), np.where(thin, np.nan, north)


def _carve_tilt(shapes_, models_, raster, xx, yy):
    """Cut out compact areas whose slope disagrees with the face that owns them; return (shapes, regions).

    A hip or small facet next to larger faces fits their planes to within about 10 cm, so no
    height test sees it, but its tilt is plainly different, and in the smoothed height model that
    survives as one coherent slope. A region needs a seed (slope far from the owner, coherent, a
    plausible pitch, wide enough not to be a smoothed crease) and grows over pixels that also
    disagree. The result is reported as unmodeled, not as a face: the height model is too smooth to
    give such a facet a trustworthy plane.
    """
    data, valid, transform = raster
    east, north = _local_slope(data, valid, transform, SLOPE_RADIUS_PX)
    known = ~np.isnan(east)
    owner = np.full(data.shape, -1)
    gap = np.zeros(data.shape)
    owner_height = np.zeros(data.shape)
    for index, (shape, model) in enumerate(zip(shapes_, models_)):
        if shape.is_empty:
            continue
        mask = rasterize([(shape, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & valid
        owner[mask] = index
        owner_height[mask] = (model[0]*xx+model[1]*yy+model[2])[mask]
        use = mask & known
        gap[use] = np.hypot(east[use]-model[0], north[use]-model[1])
    owned = owner >= 0
    seeds = _open_mask((gap > TILT_SEED_GAP) & owned, 1)
    grown = _open_mask((gap > TILT_GROW_GAP) & owned, 1)
    regions = []
    for geometry, _ in shapes(seeds.astype('uint8'), mask=seeds, transform=transform, connectivity=8):
        seed = geometry_of(geometry)
        if seed.area < TILT_MIN_SEED_M2:
            continue
        rectangle = seed.minimum_rotated_rectangle
        if rectangle.geom_type != 'Polygon':
            continue
        corners = list(rectangle.exterior.coords)
        if min(math.dist(corners[0], corners[1]), math.dist(corners[1], corners[2])) < TILT_MIN_WIDTH_M:
            continue
        pixels = rasterize([(seed, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & seeds & known
        if not pixels.any():
            continue
        mid_e, mid_n = np.median(east[pixels]), np.median(north[pixels])
        dispersion = float(np.median(np.hypot(east[pixels]-mid_e, north[pixels]-mid_n)))
        pitch = math.degrees(math.atan(math.hypot(mid_e, mid_n)))
        if dispersion > TILT_MAX_DISPERSION or not TILT_PITCH_DEG[0] <= pitch <= TILT_PITCH_DEG[1]:
            continue
        near = rasterize([(seed.buffer(TILT_REACH_M), 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool)
        region = None
        for geometry, _ in shapes((grown & near).astype('uint8'), mask=grown & near, transform=transform, connectivity=8):
            piece = geometry_of(geometry)
            if piece.intersects(seed):
                region = piece if region is None else region.union(piece)
        if region is None or region.area < TILT_MIN_REGION_M2:
            continue
        inside = rasterize([(region, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & owned
        offset = (data-owner_height)[inside]
        regions.append(dict(geometry=region, area_m2=float(region.area), pixels=int(inside.sum()),
                            mean_residual_m=float(np.mean(offset)), max_abs_residual_m=float(np.max(np.abs(offset))), kind='tilt'))
    if not regions:
        return list(shapes_), []
    cut = unary_union([r['geometry'] for r in regions])
    if cut.intersection(unary_union(list(shapes_))).area > TILT_MAX_TOTAL_FRACTION*sum(s.area for s in shapes_):
        return list(shapes_), []
    return [s.difference(cut) for s in shapes_], regions


def _merge_unmodeled(pieces):
    """Join regions carved from neighbouring faces into one record per connected area."""
    if not pieces:
        return []
    merged = []
    for area in _polygons(unary_union([p['geometry'] for p in pieces])):
        members = [p for p in pieces if p['geometry'].intersects(area)]
        pixels = sum(p['pixels'] for p in members)
        mean = sum(p['mean_residual_m']*p['pixels'] for p in members)/pixels
        tilted = sum(p['area_m2'] for p in members if p['kind'] == 'tilt')
        kind = 'tilt' if tilted >= .5*sum(p['area_m2'] for p in members) else _kind(mean)
        merged.append(dict(geometry=area, area_m2=float(area.area), mean_residual_m=mean,
                           max_abs_residual_m=max(p['max_abs_residual_m'] for p in members), kind=kind))
    return sorted(merged, key=lambda r: -r['area_m2'])


def fit(raw: dict[str, Any], inputs: dict[str, Any], home: dict[str, Any]) -> dict[str, Any]:
    """Fit an evidence-scored line arrangement in source local projected meters."""
    warnings = []
    result = dict(algorithm_version=ALGORITHM_VERSION, status='unavailable', face_groups=[],
                  edges=[], unmodeled_regions=[], warnings=warnings, design_ready=False, quality={
                      'coverage_fraction': 0., 'height_rmse_m': None, 'outline_iou': 0.,
                      'max_boundary_deviation_m': 0., 'overlap_area_m2': 0.,
                      'unexplained_fraction': 1., 'unmodeled_area_m2': 0., 'checks_passed': False})
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
        accepted, ridges = set(), []
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
                # Kept for later: trimmed to its supported span once the other lines are known.
                components = [p for p in _polygons(domain) if p.distance(a) <= tolerance and p.distance(b) <= tolerance]
                ridges.append((shifted, supported, unary_union(components)))
                replacements[i].append(near.buffer(tolerance))
                replacements[j].append(near.buffer(tolerance))
                plane_lines += 1
                snapped += int(used)
                accepted.add((i, j))
        lines += _contact_lines(sources, accepted, tolerance*.5, tolerance, max(.5, pixel*3))
        for i, source in enumerate(sources):
            # Keep unsupported breaks, but replace stair-stepped shared ridges as
            # a whole rather than separately simplifying their two sides.
            boundary = source.simplify(tolerance, preserve_topology=True).boundary
            if replacements[i]:
                boundary = boundary.difference(unary_union(replacements[i]))
            lines.append(boundary.intersection(domain))
        network = unary_union(lines)
        for index, (ridge, span, allowed) in enumerate(ridges):
            kept = _trim_ridge(ridge, span, network, RIDGE_REACH_M, _ridge_junctions(ridges, index, RIDGE_REACH_M))
            if kept is not None:
                lines.append(kept.intersection(allowed))
        cells = [cell for cell in polygonize(union_all(lines,grid_size=1e-7))
                 if domain.covers(cell.representative_point()) and cell.area > 1e-7]
        cells = _split_mixed(cells, sources, MIXED_CELL_M2, MIXED_SHARE, PIECE_FLOOR_M2)
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
        emitted, degraded, carved = [], [], []
        # Pass one: each face as the cells gave it, minus areas its own plane cannot explain by height.
        drafts = []
        for index, group in enumerate(groups):
            # Zero-tolerance removes only redundant collinear nodes; independent
            # positive-tolerance simplification would tear shared topology.
            shape = unary_union(assigned[index]).simplify(1e-9, preserve_topology=True)
            shape, regions = _carve_unmodeled(shape, models[index], raster, xx, yy)
            carved += regions
            if _polygons(shape):
                drafts.append((index, group, shape))
        # Pass two: then minus areas whose tilt, not height, says they are a different facet.
        finals, tilt_regions = _carve_tilt([d[2] for d in drafts], [models[d[0]] for d in drafts], raster, xx, yy)
        carved += tilt_regions
        # Height error is measured over the faces as emitted, after unexplained areas are carved out.
        errors, absolute_errors, sampled = [], [], 0
        for (index, group, _), shape in zip(drafts, finals):
            parts = _polygons(shape)
            if not parts:
                continue
            representative = faces[group[0]]
            emitted.append(shape)
            face_pixels = rasterize([(shape, 1)], out_shape=data.shape, transform=transform, dtype='uint8').astype(bool) & valid
            if face_pixels.any():
                m = models[index]
                residual = data[face_pixels]-(m[0]*xx[face_pixels]+m[1]*yy[face_pixels]+m[2])
                errors.append(float(np.square(residual).sum()))
                absolute_errors.append(np.abs(residual))
                sampled += len(residual)
            retained = _retention([sources[index].area], [shape.area])[0]
            if retained < RETENTION_MIN:
                degraded += [str(faces[i].get('source_plane_id', faces[i].get('id', f'plane-{i+1}'))) for i in group]
            result['face_groups'].append(dict(
                source_retained_fraction=float(retained),
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
        unmodeled = _merge_unmodeled(carved)
        unmodeled_area = sum(r['area_m2'] for r in unmodeled)
        result['unmodeled_regions'] = [
            dict(id=f'unmodeled-{k+1}', **_record(r['geometry']), area_m2=r['area_m2'], kind=r['kind'],
                 mean_residual_m=r['mean_residual_m'], max_abs_residual_m=r['max_abs_residual_m'])
            for k, r in enumerate(unmodeled)]
        result['quality'].update(coverage_fraction=coverage, height_rmse_m=rmse, outline_iou=iou,
                                 unmodeled_area_m2=unmodeled_area, unmodeled_fraction=unmodeled_area/outline.area,
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
        degraded = sorted(set(degraded)-set(missing_planes))
        result['quality']['degraded_source_planes'] = degraded
        result['quality']['checks']['source_regions_retained'] = not degraded
        result['quality']['checks_passed'] = result['quality']['checks_passed'] and not missing_planes and not degraded
        if missing_planes:
            warnings.append('Some source planes were not retained by the fitted topology: '+', '.join(missing_planes)+'. Their connections remain unresolved.')
        if degraded:
            warnings.append('Some source planes kept under half of their original area after fitting: '+', '.join(degraded)+'. Their regions may have been assigned to a neighboring plane.')
        if unmodeled:
            kinds = ', '.join(sorted({r['kind'] for r in unmodeled}))
            warnings.append(f'{len(unmodeled)} unmodeled roof region(s) totalling {unmodeled_area:.1f} m2 ({kinds}) were left out of the faces: '
                            f'the DSM there is more than {UNMODELED_RESIDUAL_M} m off the neighboring plane. They may be raised sections, objects or facets that are not modeled.')
        if rmse is None or rmse > .35:
            warnings.append(f'Height fit failed the development check (RMSE {rmse:.2f} m; limit 0.35 m).' if rmse is not None else 'Height fit could not be measured.')
        warnings.append('Experimental automatic fitting requires roof and obstruction review; design validation has not passed.')
        if photo is None:
            warnings.append('Aligned RGB evidence was unavailable; photo boundaries were not checked.')
        result['status'] = 'experimental' if emitted else 'unavailable'
        result['straightened'] = straighten_fit(result['face_groups'], emitted, angle) if emitted else dict(status='skipped', reason='no faces were fitted', face_groups=[])
        return result
    except Exception as exc:
        result['face_groups'] = []
        warnings.append(f'Fitting was withheld after a geometry error ({type(exc).__name__}).')
        return result
