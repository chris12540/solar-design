"""DSM-only child-roof feature hypotheses on the cached local metric grid.

No reference geometry, hand annotation, or visual tracing enters this detector.
Source face priors define broad parent supports; child candidates require an
independent positive DSM residual and a robust planar fit.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from scipy import ndimage


ALGORITHM_VERSION = "phase2-dsm-child-planes-v1"
MAIN_PAIR_SLOPE_DOT_MAX = -0.35
POSITIVE_RESIDUAL_M = 0.24
PLANE_INLIER_M = 0.075
MIN_CHILD_SUPPORT_M2 = 0.45
MIN_CHILD_POINTS = 45


def _grid_xy(shape: tuple[int, int], transform: Any, pixel_size_m: float):
    rows, cols = np.indices(shape, dtype=float)
    if transform is not None and hasattr(transform, "__mul__"):
        x, y = transform * (cols + 0.5, rows + 0.5)
        return np.asarray(x), np.asarray(y)
    if transform is None:
        return (cols + 0.5) * pixel_size_m, (rows + 0.5) * pixel_size_m
    a, b, c, d, e, f = transform
    return a * (cols + 0.5) + b * (rows + 0.5) + c, d * (cols + 0.5) + e * (rows + 0.5) + f


def _fit_plane(points: np.ndarray, threshold: float, rng: np.random.Generator,
               iterations: int = 180) -> tuple[np.ndarray | None, np.ndarray]:
    """Deterministic RANSAC plane fit; points are columns x,y,z."""
    n = len(points)
    if n < 3:
        return None, np.zeros(n, dtype=bool)
    # Bound work on broad supports while retaining deterministic coverage.
    if n > 5000:
        sample = np.sort(rng.choice(n, 5000, replace=False))
        fit_points = points[sample]
    else:
        sample = np.arange(n)
        fit_points = points
    design = np.column_stack((fit_points[:, 0], fit_points[:, 1], np.ones(len(fit_points))))
    best = np.zeros(len(fit_points), dtype=bool)
    for _ in range(iterations):
        inds = rng.choice(len(fit_points), 3, replace=False)
        tri = design[inds]
        if abs(np.linalg.det(tri)) < 1e-8:
            continue
        model = np.linalg.solve(tri, fit_points[inds, 2])
        inliers = np.abs(fit_points[:, 2] - design @ model) <= threshold
        if inliers.sum() > best.sum():
            best = inliers
    if best.sum() < 3:
        return None, np.zeros(n, dtype=bool)
    model = np.linalg.lstsq(design[best], fit_points[best, 2], rcond=None)[0]
    # Return inliers against the complete input set.
    all_design = np.column_stack((points[:, 0], points[:, 1], np.ones(n)))
    for _ in range(3):
        inliers = np.abs(points[:, 2] - all_design @ model) <= threshold
        if inliers.sum() < 3:
            break
        model = np.linalg.lstsq(all_design[inliers], points[inliers, 2], rcond=None)[0]
    inliers = np.abs(points[:, 2] - all_design @ model) <= threshold
    return model, inliers


def _convex_hull(points: np.ndarray) -> list[list[float]]:
    unique = sorted(set((float(x), float(y)) for x, y in points))
    if len(unique) < 3:
        return []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return []
    hull = _simplify_hull(hull, tolerance=0.12, max_vertices=8)
    hull.append(hull[0])
    return [[round(x, 4), round(y, 4)] for x, y in hull]


def _simplify_hull(points, tolerance=0.12, max_vertices=8):
    points = list(points)
    while len(points) > 3:
        distances = []
        for i, p in enumerate(points):
            a, b = points[i - 1], points[(i + 1) % len(points)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = np.hypot(dx, dy)
            dist = np.hypot(p[0] - a[0], p[1] - a[1]) if length == 0 else abs(dx * (a[1] - p[1]) - (a[0] - p[0]) * dy) / length
            distances.append(dist)
        index = int(np.argmin(distances))
        if distances[index] <= tolerance or len(points) > max_vertices:
            points.pop(index)
        else:
            break
    return points


def _clip_polygon_halfplane(polygon, line, keep_positive):
    """Clip an XY polygon to one side of an analytic plane-intersection line."""
    if len(polygon) < 4:
        return polygon
    a, b, c = line
    pts = [tuple(p) for p in polygon[:-1]]
    result = []
    def value(p): return a * p[0] + b * p[1] + c
    def inside(v): return v >= -1e-8 if keep_positive else v <= 1e-8
    for i, current in enumerate(pts):
        previous = pts[i - 1]
        vc, vp = value(current), value(previous)
        ic, ip = inside(vc), inside(vp)
        if ic != ip and abs(vp - vc) > 1e-12:
            t = vp / (vp - vc)
            result.append((previous[0] + t * (current[0] - previous[0]),
                           previous[1] + t * (current[1] - previous[1])))
        if ic:
            result.append(current)
    if len(result) < 3:
        return polygon
    result.append(result[0])
    return [[round(float(x), 6), round(float(y), 6)] for x, y in result]


def _enforce_shared_ridges(roof_planes, candidates):
    """Split overlapping candidate support hulls at their exact fitted plane ridge."""
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            mi, mj = candidates[i]["model"], candidates[j]["model"]
            line = np.asarray(mi) - np.asarray(mj)
            if np.hypot(line[0], line[1]) < 1e-8:
                continue
            pi = np.mean(candidates[i]["points"][:, :2], axis=0)
            pj = np.mean(candidates[j]["points"][:, :2], axis=0)
            side_i = float(line[0] * pi[0] + line[1] * pi[1] + line[2]) >= 0
            roof_planes[i]["support_polygon"] = _clip_polygon_halfplane(
                roof_planes[i]["support_polygon"], line, side_i)
            roof_planes[j]["support_polygon"] = _clip_polygon_halfplane(
                roof_planes[j]["support_polygon"], line, not side_i)
    return roof_planes


def _polygon_area(poly: list[list[float]]) -> float:
    if len(poly) < 4:
        return 0.0
    return abs(sum(poly[i][0] * poly[i + 1][1] - poly[i + 1][0] * poly[i][1]
                   for i in range(len(poly) - 1))) / 2.0


def _source_id(index: int) -> str:
    return f"group-{index + 1}"


def _plane_stats(dsm, mask, priors, x, y, rng, pixel_area):
    stats = []
    for i, prior in enumerate(priors):
        support = prior & mask & np.isfinite(dsm)
        rr, cc = np.where(support)
        points = np.column_stack((x[rr, cc], y[rr, cc], dsm[rr, cc]))
        if len(points) < 3:
            continue
        model, inliers = _fit_plane(points, PLANE_INLIER_M, rng, iterations=220)
        if model is None:
            continue
        residual = points[inliers, 2] - (points[inliers, 0] * model[0] +
                                           points[inliers, 1] * model[1] + model[2])
        stats.append({
            "index": i, "group_id": _source_id(i), "model": model,
            "support": support, "points": points, "inliers": inliers,
            "count": int(inliers.sum()), "area_m2": float(inliers.sum() * pixel_area),
            "rmse_m": float(np.sqrt(np.mean(residual ** 2))),
            "slope": model[:2] / np.sqrt(1 + model[0] ** 2 + model[1] ** 2),
        })
    return stats


def estimate_ground(dsm_m: np.ndarray, roof_mask: np.ndarray,
                    pixel_size_m: float = 0.1) -> dict[str, Any]:
    """Estimate terrain from a 0.3–2.0 m exterior ring; this is not measured ground."""
    valid = np.isfinite(dsm_m)
    outside_distance = ndimage.distance_transform_edt(~roof_mask, sampling=pixel_size_m)
    ring = (~roof_mask) & (outside_distance >= 0.3) & (outside_distance <= 2.0) & valid
    values = dsm_m[ring]
    if len(values) < 30:
        values = dsm_m[(~roof_mask) & valid]
    if len(values) < 10:
        return {"estimated_z_m": None, "method": "insufficient exterior DSM support",
                "uncertainty_m": None, "support_pixels": int(len(values))}
    q10, q25, q75 = np.quantile(values, [0.10, 0.25, 0.75])
    # A lower exterior quantile resists nearby eaves, trees, and wall returns.
    return {
        "estimated_z_m": round(float(q10), 3),
        "method": "10th percentile of valid DSM samples in a 0.3–2.0 m exterior roof-mask ring",
        "uncertainty_m": round(float(max(0.05, q75 - q25)), 3),
        "support_pixels": int(len(values)),
        "interpretation": "estimated local terrain; not a surveyed elevation",
    }


def _child_planes(component_mask, dsm, x, y, main_models, main_group_ids,
                  parent_assignment, priors, interior_mask, pixel_area, rng,
                  all_models, all_group_ids, all_parent_distances,
                  main_envelope_distance):
    rr, cc = np.where(component_mask)
    remaining = np.arange(len(rr))
    found = []
    while len(remaining) >= MIN_CHILD_POINTS:
        pts = np.column_stack((x[rr[remaining], cc[remaining]],
                               y[rr[remaining], cc[remaining]],
                               dsm[rr[remaining], cc[remaining]]))
        model, inliers = _fit_plane(pts, PLANE_INLIER_M, rng, iterations=250)
        if model is None or int(inliers.sum()) < MIN_CHILD_POINTS:
            break
        chosen = remaining[inliers]
        ipts = np.column_stack((x[rr[chosen], cc[chosen]],
                                y[rr[chosen], cc[chosen]],
                                dsm[rr[chosen], cc[chosen]]))
        residual = ipts[:, 2] - (ipts[:, 0] * model[0] + ipts[:, 1] * model[1] + model[2])
        area = len(chosen) * pixel_area
        hull = _convex_hull(ipts[:, :2])
        hull_area = _polygon_area(hull)
        # Associate the child to the nearest other source-supported plane in XY,
        # excluding priors that support the child itself. This distinguishes a
        # raised eave feature from a lower adjacent roof plane.
        source_groups = []
        child_rc = set(zip(rr[chosen].tolist(), cc[chosen].tolist()))
        for pi, prior in enumerate(priors):
            overlap = sum(bool(prior[r, c]) for r, c in child_rc)
            if overlap >= max(15, int(0.15 * len(chosen))):
                source_groups.append(_source_id(pi))
        source_groups = [g for g in source_groups if g not in main_group_ids]
        eligible_parent = [i for i, gid in enumerate(all_group_ids) if gid not in source_groups]
        if not eligible_parent:
            eligible_parent = list(range(len(all_group_ids)))
        dists = all_parent_distances[eligible_parent][:, rr[chosen], cc[chosen]]
        local_idx = np.argmin(dists, axis=0)
        parent_idx = np.asarray(eligible_parent, dtype=int)[local_idx]
        projected = np.stack([ipts[:, 0] * all_models[i][0] +
                              ipts[:, 1] * all_models[i][1] + all_models[i][2]
                              for i in parent_idx])
        parent_z = projected[np.arange(len(ipts)), np.arange(len(ipts))]
        height = ipts[:, 2] - parent_z
        parent_counts = Counter(all_group_ids[int(i)] for i in parent_idx)
        parent_group = parent_counts.most_common(1)[0][0]
        support_interior = float(np.mean(interior_mask[rr[chosen], cc[chosen]]))
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        med_height = float(np.median(height))
        p10_height = float(np.quantile(height, 0.10))
        candidate = {
            "model": model, "points": ipts, "indices": chosen, "hull": hull,
            "area_m2": area, "hull_area_m2": hull_area, "rmse_m": rmse,
            "height_m": med_height, "height_p10_m": p10_height,
            "parent_group_id": parent_group, "source_group_ids": source_groups,
            "interior_fraction": support_interior,
            "main_envelope_distance_m": float(np.median(
                main_envelope_distance[rr[chosen], cc[chosen]])),
        }
        found.append(candidate)
        remaining = remaining[~inliers]
    return found


def extract_features(
    dsm_m: np.ndarray,
    roof_mask: np.ndarray,
    face_priors: np.ndarray,
    transform: Any = None,
    *,
    pixel_size_m: float = 0.1,
    source_expires_at: str | None = None,
    source_obstruction_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return conservative child-roof hypotheses in local metric coordinates."""
    dsm = np.asarray(dsm_m, dtype=float)
    mask = np.asarray(roof_mask, dtype=bool)
    priors = np.asarray(face_priors, dtype=bool)
    if dsm.ndim != 2 or mask.shape != dsm.shape:
        raise ValueError("dsm_m and roof_mask must be matching 2D arrays")
    if priors.ndim != 3 or priors.shape[1:] != dsm.shape:
        raise ValueError("face_priors must have shape (groups, rows, columns)")
    valid_mask = mask & np.isfinite(dsm)
    if not valid_mask.any():
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "ground": estimate_ground(dsm, mask, pixel_size_m),
            "primary_group_ids": [],
            "features": [],
            "obstruction_candidates": _preserve_obstructions(source_obstruction_candidates),
            "unknowns": ["No valid DSM samples inside the roof mask."],
            "provenance": {"source_expires_at": source_expires_at},
        }

    x, y = _grid_xy(dsm.shape, transform, pixel_size_m)
    pixel_area = pixel_size_m ** 2
    rng = np.random.default_rng(2041)
    plane_stats = _plane_stats(dsm, valid_mask, priors, x, y, rng, pixel_area)
    if not plane_stats:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "ground": estimate_ground(dsm, mask, pixel_size_m),
            "primary_group_ids": [],
            "features": [],
            "obstruction_candidates": _preserve_obstructions(source_obstruction_candidates),
            "unknowns": ["Source priors do not contain enough planar DSM support to estimate the main roof."],
            "provenance": {"source_expires_at": source_expires_at},
        }

    # Select the largest opposed pair, so unrelated coplanar/smaller planes do not
    # silently become the main roof.
    pairs = []
    for i, first in enumerate(plane_stats):
        for second in plane_stats[i + 1:]:
            dot = float(np.dot(first["slope"], second["slope"]))
            if dot <= MAIN_PAIR_SLOPE_DOT_MAX:
                pairs.append((first["area_m2"] + second["area_m2"], dot, first, second))
    if pairs:
        _, _, main_a, main_b = max(pairs, key=lambda v: v[0])
    else:
        ranked = sorted(plane_stats, key=lambda x: x["area_m2"], reverse=True)
        main_a = ranked[0]
        main_b = ranked[1] if len(ranked) > 1 else ranked[0]
    main_stats = [main_a, main_b]
    main_models = [s["model"] for s in main_stats]
    main_ids = [s["group_id"] for s in main_stats]
    all_models = [s["model"] for s in plane_stats]
    all_ids = [s["group_id"] for s in plane_stats]
    all_parent_distances = np.stack([
        ndimage.distance_transform_edt(~(s["support"] & valid_mask), sampling=pixel_size_m)
        for s in plane_stats
    ])
    prediction = np.stack([m[0] * x + m[1] * y + m[2] for m in main_models])
    # Extend each primary plane from its own robust source support. Using height
    # proximity alone would compare a west feature to the extrapolated east plane.
    parent_distances = np.stack([
        ndimage.distance_transform_edt(~(s["support"] & valid_mask), sampling=pixel_size_m)
        for s in main_stats
    ])
    nearest = np.argmin(parent_distances, axis=0)
    parent_z = np.take_along_axis(prediction, nearest[None, :, :], axis=0)[0]
    residual = dsm - parent_z

    # The parent envelope is the union of robust inlier supports. Its eroded
    # interior guards against eave/ground returns masquerading as elevated features.
    parent_support = np.zeros(mask.shape, bool)
    for s in main_stats:
        parent_support |= s["support"] & valid_mask
    main_envelope_distance = ndimage.distance_transform_edt(
        ~parent_support, sampling=pixel_size_m)
    interior = ndimage.binary_erosion(valid_mask, structure=np.ones((3, 3)))
    parent_interior = interior & valid_mask
    positive = valid_mask & (residual >= POSITIVE_RESIDUAL_M)
    labels, nlabels = ndimage.label(positive, structure=np.ones((3, 3)))
    features = []
    unknowns = []
    for label_id in range(1, nlabels + 1):
        component = labels == label_id
        count = int(component.sum())
        if count < MIN_CHILD_POINTS:
            continue
        child_candidates = _child_planes(
            component, dsm, x, y, main_models, main_ids, nearest, priors,
            parent_interior, pixel_area, rng, all_models, all_ids,
            all_parent_distances, main_envelope_distance)
        supported = []
        for cand in child_candidates:
            support_ok = (cand["area_m2"] >= MIN_CHILD_SUPPORT_M2 and
                          cand["height_p10_m"] >= 0.10 and
                          cand["height_m"] >= POSITIVE_RESIDUAL_M and
                          cand["rmse_m"] <= 0.06 and
                          cand["interior_fraction"] >= 0.85 and
                          cand["hull_area_m2"] <= max(1.8 * cand["area_m2"], 0.7))
            child_source_ids = [g for g in cand["source_group_ids"] if g not in main_ids]
            if support_ok and child_source_ids:
                cand["source_group_ids"] = child_source_ids
                supported.append(cand)
            else:
                unknowns.append({
                    "type": "unknown",
                    "parent_group_id": cand["parent_group_id"],
                    "footprint": cand["hull"],
                    "support_pixels": len(cand["indices"]),
                    "support_area_m2": round(cand["area_m2"], 2),
                    "height_above_parent_m": round(cand["height_m"], 2),
                    "plane_rmse_m": round(cand["rmse_m"], 3),
                    "source_group_ids": cand["source_group_ids"],
                    "reason": "Elevated planar DSM support did not meet every dormer-candidate criterion.",
                })
        if not supported:
            continue
        # RANSAC can split one connected dormer roof into several planar facets.
        # Keep them as one feature hypothesis to prevent duplicate footprints.
        union_points = np.concatenate([c["points"][:, :2] for c in supported], axis=0)
        footprint = _convex_hull(union_points)
        if not footprint:
            continue
        feature_id = f"child-{len(features) + 1}"
        main_distance = float(np.median([c["main_envelope_distance_m"] for c in supported]))
        is_dormer_candidate = main_distance <= 2.0
        parent_counts = Counter(c["parent_group_id"] for c in supported)
        parent_group = parent_counts.most_common(1)[0][0]
        source_groups = sorted({g for c in supported for g in c["source_group_ids"]})
        roof_planes = []
        for pi, cand in enumerate(supported, start=1):
            model = cand["model"]
            roof_planes.append({
                "id": f"{feature_id}-plane-{pi}",
                "plane_model": {"a": round(float(model[0]), 6),
                                "b": round(float(model[1]), 6),
                                "c": round(float(model[2]), 4)},
                "support_polygon": cand["hull"],
                "support_pixels": len(cand["indices"]),
                "support_area_m2": round(cand["area_m2"], 2),
                "support_rmse_m": round(cand["rmse_m"], 3),
                "height_above_parent_m": round(cand["height_m"], 2),
                "height_p10_above_parent_m": round(cand["height_p10_m"], 2),
            })
        roof_planes = _enforce_shared_ridges(roof_planes, supported)
        features.append({
            "id": feature_id,
            "type": "dormer_candidate" if is_dormer_candidate else "unknown",
            "parent_group_id": parent_group,
            "footprint": footprint,
            "roof_planes": roof_planes,
            "source_group_ids": source_groups,
            "hypothesis_status": "candidate_unconfirmed" if is_dormer_candidate else "context_unresolved",
            "confidence_basis": {
                "positive_residual_threshold_m": POSITIVE_RESIDUAL_M,
                "planar_inlier_threshold_m": PLANE_INLIER_M,
                "minimum_interior_support_fraction": 0.85,
                "parent_plane_support": parent_group,
                "merged_plane_count": len(roof_planes),
                "median_distance_to_main_envelope_m": round(main_distance, 2),
            },
            "alternative_explanations": ([
                "A raised roof transition or non-dormer rooftop structure could produce a similar DSM patch.",
                "Source imagery is not survey-registered and may represent a different capture date.",
            ] if is_dormer_candidate else [
                "This elevated plane lies outside the dominant main-roof support envelope and may be an adjacent lower-roof hip or step.",
                "A dormer interpretation remains possible but is unresolved from these cached DSM samples.",
            ]),
            "support": {
                "pixels": sum(len(c["indices"]) for c in supported),
                "area_m2": round(sum(c["area_m2"] for c in supported), 2),
                "rmse_m": round(float(np.sqrt(np.average(
                    [c["rmse_m"] ** 2 for c in supported],
                    weights=[max(1, len(c["indices"])) for c in supported]))), 3),
            },
            **({} if is_dormer_candidate else {
                "reason": "Raised planar support is coherent but too far outside the dominant main-roof envelope to call a dormer candidate."
            }),
        })
    if not features:
        unknowns.append({
            "type": "unknown",
            "reason": "No DSM-supported raised child roof met the minimum support, elevation, planarity, interior, and source-prior criteria.",
        })

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "ground": estimate_ground(dsm, mask, pixel_size_m),
        "primary_group_ids": main_ids,
        "features": features,
        "obstruction_candidates": _preserve_obstructions(source_obstruction_candidates),
        "unknowns": unknowns,
        "provenance": {
            "source_expires_at": source_expires_at,
            "coordinate_frame": "cached local metric frame",
            "source_inputs": ["aligned DSM", "roof mask", "face_priors"],
            "reference_geometry_used": False,
        },
    }


def _preserve_obstructions(candidates):
    """Carry prior obstruction hypotheses separately without treating them as roof faces."""
    out = []
    for i, item in enumerate(candidates or []):
        out.append({
            "id": f"obstruction-source-{i + 1}",
            "type": "unknown",
            "status": "unverified_source_candidate",
            "footprint": item.get("polygon", []),
            "holes": item.get("holes", []),
            "area_m2": item.get("area_m2"),
            "height_m": item.get("height_m"),
            "area_basis": item.get("area_basis"),
            "alternative_explanations": [
                "Could be a rooftop obstruction, dormer-like feature, or edge/segmentation artifact.",
                "Not confirmed by independent imagery or field measurement.",
            ],
        })
    return out


def build_cached_output(experiment_dir=None):
    """Build the authorized local Phase 2 output from cached arrays only."""
    import json
    import pickle
    from pathlib import Path

    root = Path(experiment_dir) if experiment_dir else Path(__file__).parent
    with (root / "data/inputs.pkl").open("rb") as stream:
        cached = pickle.load(stream)
    with np.load(root / "outputs/phase1-alignment-fields.npz") as arrays:
        dsm = arrays["dsm_m"]
        rgb = arrays["rgb"]  # retained as approved evidence input; not used for fitting
        roof_mask = arrays["source_target_mask"]
    with np.load(root / "outputs/sam-masks.npz") as arrays:
        priors = arrays["face_priors"]
    if rgb.shape[:2] != dsm.shape:
        raise ValueError("Cached RGB and DSM grids do not align")
    result = extract_features(
        dsm, roof_mask, priors, cached.get("aligned", {}).get("transform"),
        pixel_size_m=0.1, source_expires_at=cached.get("expires_at"),
        source_obstruction_candidates=cached.get("raw", {}).get("obstruction_candidates", []),
    )
    output = root / "outputs/phase2-features.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    from pathlib import Path
    result = build_cached_output(Path(__file__).parent)
    print(f"Wrote {len(result['features'])} candidate feature(s); {len(result['unknowns'])} unresolved item(s).")
