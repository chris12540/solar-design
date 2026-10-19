"""Heuristic priority signals for automated roof-face candidate selection.

Scores support inexpensive candidate prioritization. They are not production
estimates, panel counts, usable-area estimates, or code findings.
"""

from __future__ import annotations

import math
import re
from typing import Any

from shapely.geometry import Polygon
from shapely.ops import unary_union


ALGORITHM_VERSION = "rank-1"
OBSTRUCTION_BUFFER_M = 0.5


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _ring_polygon(part: Any) -> Polygon | None:
    if not isinstance(part, dict):
        return None
    exterior = part.get("polygon")
    holes = part.get("holes") or []
    try:
        if not isinstance(exterior, (list, tuple)) or len(exterior) < 4:
            return None
        polygon = Polygon(exterior, holes)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            return None
        if not math.isfinite(polygon.area):
            return None
        return polygon
    except (TypeError, ValueError, OverflowError):
        return None


def _obstruction_geometries(raw: Any) -> list[Any]:
    candidates = _get(raw, "obstruction_candidates", []) or []
    usable = []
    for candidate in candidates:
        polygon = _ring_polygon(candidate)
        if polygon is not None:
            usable.append(polygon.buffer(OBSTRUCTION_BUFFER_M))
    return usable


def _source_plane_indices(group: Any) -> set[int]:
    """Map only explicit `plane-N` IDs to zero-based Google segment indices."""
    result: set[int] = set()
    for source_id in _get(group, "source_plane_ids", []) or []:
        match = re.fullmatch(r"plane-(\d+)", str(source_id).strip(), flags=re.IGNORECASE)
        if match:
            one_based = int(match.group(1))
            if one_based > 0:
                result.add(one_based - 1)
    return result


def _sunshine_by_segment(inputs: Any) -> dict[int, float]:
    """Read Google Solar API's nested roofSegmentStats.stats.sunshineQuantiles."""
    insights = _get(inputs, "insights", {}) or {}
    solar = _get(insights, "solarPotential", {}) or {}
    segments = _get(solar, "roofSegmentStats", []) or []
    if not isinstance(segments, (list, tuple)):
        return {}
    values: dict[int, float] = {}
    for index, segment in enumerate(segments):
        stats = _get(segment, "stats", {}) or {}
        quantiles = _get(stats, "sunshineQuantiles", None)
        if not isinstance(quantiles, (list, tuple)) or not quantiles:
            continue
        # The middle quantile is a stable summary of the segment's source data.
        median = _finite_number(quantiles[len(quantiles) // 2])
        if median is not None and median >= 0:
            values[index] = median
    return values


def _orientation_factor(azimuth: float | None, pitch: float | None) -> float:
    if pitch is not None and abs(pitch) < 2.0:
        return 1.0
    if azimuth is None:
        return 0.82
    # In the northern hemisphere, south-facing planes generally receive more
    # annual sun. East and west retain substantial value; north is discounted.
    south_alignment = math.cos(math.radians((azimuth - 180.0) % 360.0))
    return 0.58 + 0.42 * ((south_alignment + 1.0) / 2.0)


def _pitch_factor(pitch: float | None) -> float:
    if pitch is None:
        return 0.88
    # Broad preference for moderate pitches; this is a ranking heuristic only.
    return max(0.72, 1.0 - abs(pitch - 25.0) / 125.0)


def rank_candidates(refinement: Any, raw: Any, inputs: Any) -> list[dict[str, Any]]:
    """Return a deterministic heuristic ranking of reconstructed roof faces.

    Invalid or unavailable refinement results and groups without valid polygon
    geometry produce no candidates. Obstruction candidates are subtracted with
    a conservative buffer in local metres. No AHJ rules are inferred.
    """
    # Refinement is intentionally marked experimental while the raw geometry
    # reconstruction uses needs_review. Both are review-only inputs.
    if _get(refinement, "status") != "experimental":
        return []
    groups = _get(refinement, "face_groups", []) or []
    if not isinstance(groups, (list, tuple)) or not groups:
        return []

    obstructions = _obstruction_geometries(raw)
    obstruction_union = unary_union(obstructions) if obstructions else None
    sunshine = _sunshine_by_segment(inputs)
    preliminary: list[dict[str, Any]] = []

    for group in groups:
        face_id = str(_get(group, "id", "") or "")
        parts = _get(group, "parts", []) or []
        if not face_id or not isinstance(parts, (list, tuple)) or not parts:
            continue
        polygons = [_ring_polygon(part) for part in parts]
        polygons = [polygon for polygon in polygons if polygon is not None]
        if not polygons:
            continue
        try:
            merged = unary_union(polygons)
            if obstruction_union is not None:
                merged = merged.difference(obstruction_union)
            # Only polygon components count. Their areas remain horizontal area.
            components = []
            if merged.geom_type == "Polygon":
                components = [merged]
            elif merged.geom_type == "MultiPolygon":
                components = list(merged.geoms)
            else:
                components = [geom for geom in getattr(merged, "geoms", [])
                              if geom.geom_type == "Polygon"]
            components = [geom for geom in components if not geom.is_empty and geom.area > 0]
            area = sum(float(geom.area) for geom in components)
            contiguous = max((float(geom.area) for geom in components), default=0.0)
        except Exception:
            continue
        if area <= 0:
            continue

        pitch = _finite_number(_get(group, "pitch_degrees"))
        azimuth = _finite_number(_get(group, "azimuth_degrees"))
        source_indices = _source_plane_indices(group)
        matched_sun = [sunshine[index] for index in source_indices if index in sunshine]
        sun_value = (sum(matched_sun) / len(matched_sun)
                     if source_indices and len(matched_sun) == len(source_indices) else None)
        preliminary.append({
            "face_id": face_id,
            "area_m2": area,
            "contiguous_area_m2": contiguous,
            "pitch_degrees": pitch,
            "azimuth_degrees": azimuth,
            "sunshine": sun_value,
            "source_plane_count": len(source_indices),
            "reasons": [],
            "unknown_checks": [
                "AHJ setbacks, fire access, and other code rules have not been applied.",
                "Structural capacity and final obstruction review are unknown.",
            ],
        })

    if not preliminary:
        return []

    observed_sun = [item["sunshine"] for item in preliminary if item["sunshine"] is not None]
    min_sun = min(observed_sun) if observed_sun else None
    max_sun = max(observed_sun) if observed_sun else None
    max_effective = max((item["contiguous_area_m2"] for item in preliminary), default=0.0)

    for item in preliminary:
        contiguous = item["contiguous_area_m2"]
        orientation = _orientation_factor(item["azimuth_degrees"], item["pitch_degrees"])
        pitch = _pitch_factor(item["pitch_degrees"])
        if item["sunshine"] is None or min_sun is None or max_sun is None:
            # Missing source exposure is neutral within the 0.75–1.0 relative
            # sunshine range, and cannot receive the maximum factor by default.
            sun_factor = 0.875
            shading_status = "unknown"
            if item["source_plane_count"]:
                item["unknown_checks"].append("Matching Google sunshine quantiles are missing for one or more source planes.")
            else:
                item["unknown_checks"].append("Matching Google sunshine quantiles are unavailable.")
        else:
            relative_sun = 1.0 if max_sun == min_sun else (
                (item["sunshine"] - min_sun) / (max_sun - min_sun)
            )
            sun_factor = 0.875 if max_sun == min_sun else 0.75 + 0.25 * relative_sun
            shading_status = "available"
            item["reasons"].append("Matching Google sunshine quantiles are available for this source plane.")

        if max_effective <= 0:
            area_factor = 0.0
        else:
            area_factor = contiguous / max_effective
        score = 100.0 * area_factor * orientation * pitch * sun_factor
        if contiguous > 0:
            item["reasons"].append("A larger single connected roof area improves this face's priority.")
        else:
            item["reasons"].append("No connected roof area remains after obstruction deductions.")
        if item["azimuth_degrees"] is not None:
            if orientation >= 0.9:
                item["reasons"].append("Southward orientation improves the heuristic priority.")
            elif orientation <= 0.7:
                item["reasons"].append("Northward orientation lowers the heuristic priority.")
        item["reasons"].append("Score is a review heuristic; it does not estimate production, panel count, or AHJ-usable area.")
        item["shading_status"] = shading_status
        item["score"] = round(score, 2)

    ordered = sorted(preliminary, key=lambda item: (-item["score"], item["face_id"]))
    result = []
    for rank, item in enumerate(ordered, start=1):
        result.append({
            "face_id": item["face_id"],
            "rank": rank,
            "score": item["score"],
            "area_m2": round(item["area_m2"], 2),
            "contiguous_area_m2": round(item["contiguous_area_m2"], 2),
            "reasons": item["reasons"],
            "unknown_checks": item["unknown_checks"],
            "shading_status": item["shading_status"],
        })
    return result
