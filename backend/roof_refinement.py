"""Experimental, bounded cleanup proposals for reconstructed roof faces.

This module never changes the source reconstruction. It groups compatible
regions, closes only tiny evidence-supported seams, and reports shared-edge
proposals where the fitted planes and existing boundaries agree.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely import affinity
from shapely.ops import split
from rasterio.io import MemoryFile
from pyproj import Transformer
import numpy as np
from shapely.ops import nearest_points, unary_union


ALGORITHM_VERSION = "refine-1"
MAX_GROUPS = 32
MAX_PARTS = 128
MAX_EDGES = 64
MAX_BRIDGES = 16
MAX_ANGLE_DELTA = 5.0
MAX_DEVIATION_M = 0.3


def _poly(record: dict[str, Any]) -> Polygon:
    return Polygon(record.get("polygon") or [], record.get("holes") or [])


def _model(face: dict[str, Any]) -> tuple[float, float, float] | None:
    raw = face.get("plane_model")
    if not isinstance(raw, dict):
        return None
    try:
        a, b, c = (float(raw[k]) for k in ("a", "b", "c"))
    except (KeyError, TypeError, ValueError):
        return None
    return (a, b, c) if all(math.isfinite(v) for v in (a, b, c)) else None


def _angle(face: dict[str, Any]) -> tuple[float, float]:
    return float(face.get("pitch_degrees") or 0.0), float(face.get("azimuth_degrees") or 0.0) % 360.0


def _angle_compatible(first: dict[str, Any], second: dict[str, Any]) -> bool:
    p1, a1 = _angle(first)
    p2, a2 = _angle(second)
    if abs(p1 - p2) > MAX_ANGLE_DELTA:
        return False
    if max(p1, p2) < 2.0:
        return True
    delta = abs((a1 - a2 + 180.0) % 360.0 - 180.0)
    return delta <= MAX_ANGLE_DELTA


def _height_compatible(first: dict[str, Any], second: dict[str, Any], sample: Point,
                       tolerance: float) -> bool:
    m1, m2 = _model(first), _model(second)
    if m1 is None or m2 is None:
        return False
    z1 = m1[0] * sample.x + m1[1] * sample.y + m1[2]
    z2 = m2[0] * sample.x + m2[1] * sample.y + m2[2]
    rmse = max(float(first.get("fit_rmse_m") or 0), float(second.get("fit_rmse_m") or 0))
    limit = min(MAX_DEVIATION_M, max(0.08, tolerance, 2.0 * rmse))
    return abs(z1 - z2) <= limit


def _z(model: tuple[float, float, float], x: float, y: float) -> float:
    return model[0] * x + model[1] * y + model[2]


def _plane_intersection(first: tuple[float, float, float], second: tuple[float, float, float],
                        clip: Polygon) -> LineString | None:
    da, db, dc = first[0] - second[0], first[1] - second[1], first[2] - second[2]
    norm2 = da * da + db * db
    if norm2 < 1e-12:
        return None
    # Point nearest the origin on da*x + db*y + dc = 0 and its direction.
    x0, y0 = -dc * da / norm2, -dc * db / norm2
    scale = max(1.0, clip.bounds[2] - clip.bounds[0], clip.bounds[3] - clip.bounds[1]) * 4
    norm = math.sqrt(norm2)
    line = LineString([(x0 - db / norm * scale, y0 + da / norm * scale), (x0 + db / norm * scale, y0 - da / norm * scale)])
    hit = line.intersection(clip)
    lines: list[LineString] = []
    if hit.geom_type == "LineString":
        lines = [hit]
    elif hasattr(hit, "geoms"):
        lines = [g for g in hit.geoms if g.geom_type == "LineString"]
    return max(lines, key=lambda g: g.length) if lines else None


def _edge_kind(edge: LineString, faces: list[dict[str, Any]], parts: list[Polygon]) -> str:
    if edge.length <= 0:
        return "unknown"
    m1, m2 = _model(faces[0]), _model(faces[1])
    if m1 is None or m2 is None:
        return "unknown"
    midpoint = edge.interpolate(0.5, normalized=True)
    coords = list(edge.coords)
    dx, dy = coords[-1][0] - coords[0][0], coords[-1][1] - coords[0][1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return "unknown"
    nx, ny = -dy / length, dx / length
    step = min(0.25, max(0.05, edge.length / 20.0))
    probe1 = Point(midpoint.x + nx * step, midpoint.y + ny * step)
    probe2 = Point(midpoint.x - nx * step, midpoint.y - ny * step)
    # Pick the inward probe for each face. Compare its height with the
    # plane-intersection height at the edge midpoint.
    probes = []
    for part in parts:
        if part.buffer(1e-6).covers(probe1):
            probes.append(probe1)
        elif part.buffer(1e-6).covers(probe2):
            probes.append(probe2)
        else:
            return "unknown"
    changes = [_z(m, p.x, p.y) - _z(m, midpoint.x, midpoint.y) for m, p in zip((m1, m2), probes)]
    eps = 0.015
    if all(value < -eps for value in changes):
        along_slope = abs(_z(m1, *coords[-1]) - _z(m1, *coords[0])) / length
        return "hip" if along_slope > 0.03 else "ridge"
    if all(value > eps for value in changes):
        return "valley"
    return "unknown"


def _record(poly: Polygon) -> dict[str, Any]:
    return {
        "polygon": [[float(x), float(y)] for x, y in poly.exterior.coords],
        "holes": [[[float(x), float(y)] for x, y in ring.coords] for ring in poly.interiors],
    }


def _polygons(geometry: Any) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [part for g in geometry.geoms for part in _polygons(g) if part.area > 1e-8]
    return []


def _inferred_edge(first: dict[str, Any], second: dict[str, Any], p1: Polygon, p2: Polygon,
                   outline: Polygon, tolerance: float) -> LineString | None:
    m1, m2 = _model(first), _model(second)
    if m1 is None or m2 is None or p1.distance(p2) > tolerance + 1e-6:
        return None
    shared_support = p1.boundary.buffer(tolerance).intersection(p2.boundary.buffer(tolerance))
    candidate = _plane_intersection(m1, m2, outline)
    if candidate is None or candidate.length < max(tolerance, 0.05):
        return None
    supported = candidate.intersection(shared_support)
    lines = [supported] if supported.geom_type == "LineString" else [g for g in getattr(supported, "geoms", []) if g.geom_type == "LineString"]
    if not lines:
        return None
    result = max(lines, key=lambda g: g.length)
    # A proposal must follow the observed boundaries closely along its length.
    if result.distance(p1.boundary) > tolerance or result.distance(p2.boundary) > tolerance:
        return None
    return result



def _hole_geometry(geometry):
    return unary_union([Polygon(ring) for part in _polygons(geometry) for ring in part.interiors])


def _evidence(raw, inputs):
    try:
        origin=raw['origin']
        with MemoryFile(inputs['dsm']) as memory:
            with memory.open() as ds:
                if ds.width*ds.height > 4_000_000 or not ds.crs:
                    return None
                data=ds.read(1)
                ox,oy=Transformer.from_crs('EPSG:4326',ds.crs,always_xy=True).transform(origin['longitude'],origin['latitude'])
                return data,~ds.transform,ds.nodata,ox,oy
    except Exception:
        return None


def _supported(geometry, model, evidence):
    if evidence is None or model is None or geometry.is_empty:
        return False
    data,inverse,nodata,ox,oy=evidence
    points=[]
    for part in _polygons(geometry):
        points.append(part.representative_point())
        count=max(4,min(2048,int(part.length/0.05)+1))
        if part.length/0.05>2048:
            return False
        points.extend(part.exterior.interpolate(i/count,normalized=True) for i in range(count))
    if not points:
        return False
    for point in points:
        px,py=point.x+ox,point.y+oy
        col,row=inverse.a*px+inverse.b*py+inverse.c,inverse.d*px+inverse.e*py+inverse.f
        row,col=math.floor(row),math.floor(col)
        if not (0<=row<data.shape[0] and 0<=col<data.shape[1]):
            return False
        value=float(data[row,col])
        if not math.isfinite(value) or value == -9999 or (nodata is not None and value==nodata):
            return False
        if abs(value-_z(model,point.x,point.y))>0.35:
            return False
    return True


def _fit_boundary(poly, model, limit):
    candidate=poly.simplify(limit,preserve_topology=True)
    if candidate.geom_type!='Polygon' or not candidate.is_valid:
        return poly
    if model and math.hypot(model[0],model[1])>1e-5:
        base=math.atan2(model[1],model[0])
    else:
        rectangle=list(poly.minimum_rotated_rectangle.exterior.coords)
        longest=max(zip(rectangle,rectangle[1:]),key=lambda pair:Point(pair[0]).distance(Point(pair[1])))
        base=math.atan2(longest[1][1]-longest[0][1],longest[1][0]-longest[0][0])
    ring=list(candidate.exterior.coords)[:-1]
    if len(ring)<3:
        return poly
    lines=[]
    for first,second in zip(ring,ring[1:]+ring[:1]):
        dx,dy=second[0]-first[0],second[1]-first[1]
        length=math.hypot(dx,dy)
        angle=math.atan2(dy,dx)
        target=base+round((angle-base)/(math.pi/4))*(math.pi/4)
        if length>=0.5 and abs(math.atan2(math.sin(target-angle),math.cos(target-angle)))<=math.radians(7):
            dx,dy=math.cos(target),math.sin(target)
        else:
            dx,dy=dx/max(length,1e-9),dy/max(length,1e-9)
        lines.append((((first[0]+second[0])/2,(first[1]+second[1])/2),(dx,dy)))
    fitted=[]
    for index,old in enumerate(ring):
        p,u=lines[index-1];q,v=lines[index]
        cross=u[0]*v[1]-u[1]*v[0]
        if abs(cross)<0.1:
            fitted.append(old);continue
        t=((q[0]-p[0])*v[1]-(q[1]-p[1])*v[0])/cross
        point=(p[0]+t*u[0],p[1]+t*u[1])
        fitted.append(point if Point(point).distance(Point(old))<=limit else old)
    out=Polygon(fitted,[list(r.coords) for r in poly.interiors])
    if (out.is_valid and out.hausdorff_distance(poly)<=limit+1e-8
            and len(out.interiors)==len(poly.interiors)):
        return out
    return candidate if candidate.hausdorff_distance(poly)<=limit+1e-8 else poly


def _partition_edge(a,b,first,second,line,outline,tolerance,evidence):
    if evidence is None:
        return None
    ma,mb=_model(first),_model(second)
    if ma is None or mb is None:
        return None
    pa,pb=a.representative_point(),b.representative_point()
    sign=lambda point:(_z(ma,point.x,point.y)-_z(mb,point.x,point.y))
    sa,sb=sign(pa),sign(pb)
    if sa*sb>=0:
        return None
    combined=a.union(b)
    full=_plane_intersection(ma,mb,combined.envelope.buffer(1))
    if full is None:
        return None
    pieces=_polygons(split(combined,full))
    half_a=unary_union([p for p in pieces if sign(p.representative_point())*sa>0])
    half_b=unary_union([p for p in pieces if sign(p.representative_point())*sb>0])
    if half_a.is_empty or half_b.is_empty:
        return None
    strip=line.buffer(tolerance).intersection(combined)
    aa=a.difference(strip).union(half_a.intersection(strip))
    bb=b.difference(strip).union(half_b.intersection(strip))
    if (not aa.is_valid or not bb.is_valid or aa.is_empty or bb.is_empty
            or aa.intersection(bb).area>1e-8
            or combined.symmetric_difference(aa.union(bb)).area>1e-6):
        return None
    deviation=max(a.hausdorff_distance(aa),b.hausdorff_distance(bb))
    if deviation>tolerance+1e-6:
        return None
    if ((not aa.difference(a).is_empty and not _supported(aa.difference(a),ma,evidence))
            or (not bb.difference(b).is_empty and not _supported(bb.difference(b),mb,evidence))):
        return None
    return aa,bb,deviation


def refine(raw: dict[str, Any], inputs: dict[str, Any], home: dict[str, Any]) -> dict[str, Any]:
    """Return an experimental face grouping and conservative seam proposals.

    ``raw`` remains untouched. All coordinates are local projected meters as
    emitted by :func:`backend.roof_geometry.reconstruct`.
    """
    del home
    warnings: list[str] = []
    empty = {"algorithm_version": ALGORITHM_VERSION, "status": "experimental", "face_groups": [],
             "edges": [], "inferred_regions": [], "quality": {"coverage_fraction": 0.0,
             "added_area_m2": 0.0, "max_boundary_deviation_m": 0.0}, "warnings": warnings,
             "design_ready": False}
    try:
        if raw.get("status") != "needs_review":
            warnings.append("Only a successful raw reconstruction can be refined.")
            return empty
        evidence = _evidence(raw, inputs)
        outline_record = raw.get("roof_outline") or {}
        outline = _poly(outline_record)
        faces = raw.get("faces") or []
        if outline.is_empty or not outline.is_valid or not faces:
            warnings.append("Valid roof outline and source faces are required for refinement.")
            return empty
        original = []
        valid_faces = []
        for face in faces[:MAX_PARTS]:
            poly = _poly(face)
            if poly.is_valid and not poly.is_empty and poly.area > 0 and _model(face) is not None:
                # A source face must stay inside the original outline.
                poly = poly.intersection(outline)
                if not poly.is_empty:
                    valid_faces.append(face)
                    original.append(poly)
        if not valid_faces:
            warnings.append("No valid source faces with plane models were available.")
            return empty

        pixel_size = float((raw.get("quality") or {}).get("pixel_size_m") or 0.1)
        rmse_values = [float(f.get("fit_rmse_m") or 0) for f in valid_faces]
        # Pixel quantization and fit error set the seam tolerance, capped at
        # 30 cm so coarse or noisy data cannot authorize broad filling.
        tolerance = min(MAX_DEVIATION_M, max(0.02, min(pixel_size * 0.2, 0.2),
                                              min(max(rmse_values, default=0) * 1.5, 0.2)))
        obstruction = unary_union([_poly(item) for item in (raw.get("obstruction_candidates") or [])
                                   if _poly(item).is_valid and not _poly(item).is_empty])
        if not obstruction.is_empty:
            obstruction = obstruction.buffer(max(tolerance, pixel_size * 0.5))

        # Greedy deterministic grouping. Geometry remains represented as parts;
        # disconnected components are never replaced by a convex hull.
        groups: list[list[int]] = []
        anchor_points = [poly.representative_point() for poly in original]
        for idx, face in enumerate(valid_faces):
            assigned = False
            for group in groups:
                compatible = True
                for member in group:
                    if (not _angle_compatible(face, valid_faces[member]) or
                            not all(_height_compatible(face, valid_faces[member],
                                                   point, tolerance)
                                for point in [anchor_points[idx], anchor_points[member],
                                    *[Point(x,y) for x,y in original[idx].envelope.exterior.coords],
                                    *[Point(x,y) for x,y in original[member].envelope.exterior.coords]])):
                        compatible = False
                        break
                if compatible:
                    group.append(idx)
                    assigned = True
                    break
            if not assigned:
                groups.append([idx])
        groups = groups[:MAX_GROUPS]

        inferred_regions: list[dict[str, Any]] = []
        added_area = 0.0
        max_deviation = 0.0
        face_groups: list[dict[str, Any]] = []
        emitted: list[list[Polygon]] = []
        for gi, members in enumerate(groups):
            parts = _polygons(unary_union([original[i] for i in members]))
            source_union = unary_union(parts)
            protected = _hole_geometry(source_union)
            other_source = unary_union([original[i] for i in range(len(original)) if i not in members])
            model = _model(valid_faces[members[0]])
            # Simplify an entire polygon, preserving its holes, then fit long
            # segments to the plane's dominant axes within the source tolerance.
            fitted_parts = []
            cleanup_limit = min(0.15, max(0.025, pixel_size * 0.75))
            for part in parts:
                fitted = _fit_boundary(part, model, cleanup_limit)
                fitted = fitted.intersection(outline).difference(protected).difference(other_source)
                added = fitted.difference(part)
                if (fitted.is_valid and not fitted.is_empty
                        and fitted.hausdorff_distance(part) <= cleanup_limit + 1e-6
                        and (added.is_empty or _supported(added, model, evidence))):
                    fitted_parts.extend(_polygons(fitted))
                    max_deviation = max(max_deviation, fitted.hausdorff_distance(part))
                else:
                    fitted_parts.append(part)
            parts = _polygons(unary_union(fitted_parts))
            # Bridge only the shortest tiny seam between parts in this group.
            candidates = []
            for pos, first in enumerate(members):
                for second in members[pos + 1:]:
                    a, b = original[first], original[second]
                    distance = a.distance(b)
                    if 1e-6 < distance <= tolerance and len(candidates) < MAX_BRIDGES:
                        pa, pb = nearest_points(a, b)
                        bridge = LineString([pa, pb]).buffer(max(0.005, tolerance * 0.35), cap_style=2)
                        if (outline.covers(bridge) and (obstruction.is_empty or not bridge.intersects(obstruction))):
                            candidates.append((distance, first, second, bridge))
            for gap_distance, first, second, bridge in sorted(candidates, key=lambda row: (row[0], row[1], row[2])):
                current = unary_union(parts)
                addition = bridge.difference(current)
                if (addition.is_empty or addition.area > max(0.01, tolerance * tolerance * 4)
                        or addition.intersects(protected) or addition.intersection(other_source).area > 1e-8
                        or not _supported(addition, model, evidence)):
                    continue
                merged = current.union(addition).intersection(outline)
                if not merged.is_valid or (not obstruction.is_empty and merged.intersection(obstruction).area > 1e-8):
                    continue
                before = _polygons(current)
                after = _polygons(merged)
                if not after or sum(p.area for p in after) + 1e-7 < sum(p.area for p in before):
                    continue
                parts = after
                inferred_regions.extend(_record(p) for p in _polygons(addition))
                added_area += float(addition.area)
                max_deviation = max(max_deviation, addition.hausdorff_distance(current))

            # Guard against any unexpected cross-group overlap.
            clean_parts = []
            for part in parts:
                if any(part.intersection(previous).area > 1e-7 for other in emitted for previous in other):
                    warnings.append("A proposed part overlapped another face group and was withheld.")
                    continue
                clean_parts.append(part)
            emitted.append(clean_parts)
            source_faces = [valid_faces[i] for i in members]
            largest_area = max((p.area for p in clean_parts), default=0.0)
            area = sum(p.area for p in clean_parts)
            representative = source_faces[0]
            face_groups.append({
                "id": f"group-{gi + 1}",
                "parts": [_record(p) for p in clean_parts],
                "source_region_ids": [str(f.get("id", f"region-{i + 1}")) for i, f in zip(members, source_faces)],
                "source_plane_ids": sorted({str(f.get("source_plane_id", f.get("id", f"plane-{i + 1}")))
                                             for i, f in zip(members, source_faces)}),
                "pitch_degrees": float(representative.get("pitch_degrees") or 0),
                "azimuth_degrees": float(representative.get("azimuth_degrees") or 0),
                "area_m2": float(area),
                "largest_contiguous_area_m2": float(largest_area),
                "plane_model": dict(representative["plane_model"]),
                "fit_rmse_m": max(float(f.get("fit_rmse_m") or 0) for f in source_faces),
            })

        # Partition only a narrow strip around an evidence-supported plane
        # intersection. Joint changes keep neighboring faces disjoint.
        edges: list[dict[str, Any]] = []
        for i in range(len(face_groups)):
            for j in range(i + 1,len(face_groups)):
                if len(edges) >= MAX_EDGES:
                    break
                a, b = unary_union(emitted[i]), unary_union(emitted[j])
                if a.is_empty or b.is_empty:
                    continue
                first, second = face_groups[i], face_groups[j]
                line = _inferred_edge(first,second,a,b,outline,tolerance)
                if line is None:
                    continue
                if not obstruction.is_empty:
                    segments = line.difference(obstruction)
                    lines = [segments] if segments.geom_type == "LineString" else [g for g in getattr(segments,'geoms',[]) if g.geom_type=='LineString']
                    if not lines:
                        continue
                    line = max(lines,key=lambda g:g.length)
                if line.length < max(0.25,pixel_size*2):
                    continue
                updated = _partition_edge(a,b,first,second,line,outline,tolerance,evidence)
                if updated is not None:
                    aa,bb,deviation = updated
                    # Never move a face into a third face group.
                    others = unary_union([p for k,group in enumerate(emitted) if k not in (i,j) for p in group])
                    if aa.intersection(others).area <= 1e-8 and bb.intersection(others).area <= 1e-8:
                        emitted[i],emitted[j] = _polygons(aa),_polygons(bb)
                        max_deviation = max(max_deviation,deviation)
                        a,b=aa,bb
                kind = _edge_kind(line,[first,second],[a,b])
                coords=list(line.coords)
                edges.append({'id':f'edge-{len(edges)+1}','face_ids':[first['id'],second['id']],
                    'kind':kind,'coordinates':[[float(x),float(y)] for x,y in (coords[0],coords[-1])],
                    'inferred':True})
        for index, group in enumerate(face_groups):
            group['parts'] = [_record(p) for p in emitted[index]]
            group['area_m2'] = sum(p.area for p in emitted[index])
            group['largest_contiguous_area_m2'] = max((p.area for p in emitted[index]),default=0.0)
        if not edges and len(valid_faces) > 1:
            warnings.append("No shared edge had enough boundary and plane-intersection evidence; no edge was inferred.")
        if not inferred_regions:
            warnings.append("No seam was closed; disconnected source regions remain separate.")
        # Report geometric change from the actual retained output, never a
        # clamp or a distance between unrelated points on the whole roof.
        source_all = unary_union(original)
        output_all = unary_union([p for group in emitted for p in group])
        added_area = output_all.difference(source_all).area
        max_deviation = max((unary_union(emitted[k]).hausdorff_distance(
            unary_union([original[i] for i in members])) for k,members in enumerate(groups)
            if emitted[k]), default=0.0)
        total_area = float(outline.area)
        retained_area = sum(sum(p.area for p in group) for group in emitted)
        empty.update({
            "face_groups": face_groups,
            "edges": edges,
            "inferred_regions": inferred_regions,
            "quality": {"coverage_fraction": min(1.0, retained_area / total_area) if total_area else 0.0,
                        "added_area_m2": added_area,
                        "max_boundary_deviation_m": max_deviation},
            "warnings": warnings,
        })
        return empty
    except Exception as exc:
        warnings.append(f"Refinement was withheld after a geometry error ({type(exc).__name__}).")
        return empty
