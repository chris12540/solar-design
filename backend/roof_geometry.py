"""Conservative reconstruction of roof faces from Google Solar rasters.

The returned geometry is a review aid.  It does not establish code compliance,
structural suitability, or design readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Any

import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.io import MemoryFile
from rasterio.warp import Resampling, reproject
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform as transform_geometry


ALGORITHM_VERSION = "roof-5"
MAX_FACES = 32
MAX_CANDIDATES = 32
MAX_RING_VERTICES = 1200
MAX_HOLES_PER_FACE = 16
MAX_HOLE_VERTICES = 128
MAX_RASTER_PIXELS = 4_000_000
MAX_PLANES = 64
MAX_SELECTED_PIXELS = 500_000
MAX_PLANE_PIXEL_CELLS = 8_000_000
ASSIGNMENT_TOLERANCE_M = 0.35


@dataclass
class _Plane:
    index: int
    center_x: float
    center_y: float
    height: float
    pitch: float
    azimuth: float
    grid_azimuth: float
    grid_scale: float
    polygon: Any = None
    bounds: Any = None

    def z_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        angle = math.radians(self.grid_azimuth)
        slope = math.tan(math.radians(self.pitch))
        projected_distance = ((x - self.center_x) * math.sin(angle) + (y - self.center_y) * math.cos(angle))
        return self.height - slope * projected_distance / self.grid_scale


def _unavailable(warning: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "algorithm_version": ALGORITHM_VERSION,
        "faces": [],
        "obstruction_candidates": [],
        "bounds": None,
        "quality": {
            "assigned_fraction": 0.0,
            "unassigned_fraction": 1.0,
            "valid_pixel_count": 0,
            "plane_count": 0,
        },
        "warnings": [warning],
        "ahj": {"status": "pending_rules"},
        "design_ready": False,
    }


def _bytes_dataset(content: bytes) -> Any:
    with MemoryFile(content) as memory:
        with memory.open() as src:
            if src.width * src.height > MAX_RASTER_PIXELS:
                raise ValueError("raster exceeds pixel limit")
            data = src.read(1)
            return data, src.transform, src.crs, src.nodata, src.width, src.height


def _wgs84_xy(lon: float, lat: float, target: CRS) -> tuple[float, float]:
    return Transformer.from_crs("EPSG:4326", target, always_xy=True).transform(lon, lat)


def _projected_direction(lon: float, lat: float, azimuth: float, crs: CRS) -> tuple[float, float]:
    """Return the projected grid bearing and map scale for a true-north bearing."""
    geod = Geod(ellps="WGS84")
    lon2, lat2, _ = geod.fwd(lon, lat, azimuth, 1.0)
    x1, y1 = _wgs84_xy(lon, lat, crs)
    x2, y2 = _wgs84_xy(lon2, lat2, crs)
    dx, dy = x2 - x1, y2 - y1
    scale = math.hypot(dx, dy)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("could not derive projected direction")
    return math.degrees(math.atan2(dx, dy)) % 360.0, scale


def _coordinates(geometry: Any, src_crs: CRS, target: CRS) -> Any:
    return transform_geometry(Transformer.from_crs(src_crs, target, always_xy=True).transform, geometry)


def _raster_valid(data: np.ndarray, nodata: float | None) -> np.ndarray:
    valid = np.isfinite(data)
    if nodata is not None:
        if math.isnan(float(nodata)):
            valid &= ~np.isnan(data)
        else:
            valid &= data != nodata
    return valid


def _make_planes(insights: dict[str, Any], crs: CRS) -> tuple[list[_Plane], tuple[float, float]]:
    center = insights.get("center") or {}
    lon, lat = float(center["longitude"]), float(center["latitude"])
    origin = _wgs84_xy(lon, lat, crs)
    planes: list[_Plane] = []
    solar_potential = insights.get("solarPotential") or {}
    segments = solar_potential.get("roofSegmentStats") or insights.get("roofSegmentStats") or []
    for i, item in enumerate(segments[:MAX_PLANES]):
        try:
            pc = item.get("center") or center
            plane_lon, plane_lat = float(pc["longitude"]), float(pc["latitude"])
            cx, cy = _wgs84_xy(plane_lon, plane_lat, crs)
            pitch = float(item["pitchDegrees"])
            azimuth = float(item["azimuthDegrees"]) % 360.0
            grid_azimuth, grid_scale = _projected_direction(plane_lon, plane_lat, azimuth, crs)
            height = float(item["planeHeightAtCenterMeters"])
            if not all(math.isfinite(v) for v in (cx, cy, pitch, azimuth, height)) or not (0 <= pitch < 90):
                continue
            poly = item.get("polygon")
            polygon = None
            if poly:
                wgs_poly = shape({"type": "Polygon", "coordinates": [[(float(p["longitude"]), float(p["latitude"])) for p in poly]]})
                polygon = _coordinates(wgs_poly, CRS.from_epsg(4326), crs)
            bbox = item.get("boundingBox")
            bounds = None
            if bbox:
                sw, ne = bbox.get("sw") or {}, bbox.get("ne") or {}
                west, south = float(sw["longitude"]), float(sw["latitude"])
                east, north = float(ne["longitude"]), float(ne["latitude"])
                if east <= west or north <= south:
                    continue
                wgs_bounds = shape({"type": "Polygon", "coordinates": [[
                    (west, south), (east, south), (east, north), (west, north), (west, south)
                ]]})
                bounds = _coordinates(wgs_bounds, CRS.from_epsg(4326), crs)
            planes.append(_Plane(i, cx, cy, height, pitch, azimuth, grid_azimuth, grid_scale, polygon, bounds))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return planes, origin


def _local_polygon(poly: Any, origin: tuple[float, float], tolerance: float) -> tuple[list[list[float]], list[list[list[float]]]] | None:
    if poly.geom_type != "Polygon" or not poly.is_valid or len(poly.interiors) > MAX_HOLES_PER_FACE:
        return None

    source_holes = len(poly.interiors)
    candidate = poly
    simplify_tolerance = 0.0
    for _ in range(16):
        exterior_coords = list(candidate.exterior.coords)
        hole_coords = [list(ring.coords) for ring in candidate.interiors]
        bounded = (len(exterior_coords) <= MAX_RING_VERTICES
                   and len(hole_coords) <= MAX_HOLES_PER_FACE
                   and all(len(ring) <= MAX_HOLE_VERTICES for ring in hole_coords))
        if bounded and len(candidate.interiors) == source_holes:
            exterior = [[float(x - origin[0]), float(y - origin[1])] for x, y in exterior_coords]
            holes = [[[float(x - origin[0]), float(y - origin[1])] for x, y in ring] for ring in hole_coords]
            local_poly = Polygon(exterior, holes)
            if local_poly.is_valid and local_poly.area > 0:
                return exterior, holes
            return None
        simplify_tolerance = max(tolerance, 0.01) if simplify_tolerance == 0 else simplify_tolerance * 2
        candidate = candidate.simplify(simplify_tolerance, preserve_topology=True)
        if (candidate.geom_type != "Polygon" or not candidate.is_valid
                or len(candidate.interiors) != source_holes):
            return None
    return None


def _polygon_records(label_grid: np.ndarray, transform: Any, origin: tuple[float, float], tolerance: float,
                     valid_mask: np.ndarray | None = None) -> list[tuple[int, Any]]:
    from shapely.geometry import shape as make_shape

    mask = valid_mask if valid_mask is not None else label_grid > 0
    return [(int(value), make_shape(geom)) for geom, value in shapes(label_grid.astype("int32"), mask=mask, transform=transform, connectivity=4) if int(value) > 0]


def reconstruct(inputs: dict[str, Any], home: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct reviewable roof faces from DSM, roof mask, parcel, and planes."""
    warnings: list[str] = [
        "Experimental geometry has not passed accuracy validation.",
        "Obstruction detection is incomplete; trees and other positive residuals may be included.",
    ]
    try:
        insights = inputs.get("insights") or {}
        if isinstance(insights, dict) and isinstance(insights.get("buildingInsights"), dict):
            insights = insights["buildingInsights"]
        if not inputs.get("dsm") or not inputs.get("mask"):
            return _unavailable("DSM and roof mask rasters are both required.")
        dsm, transform, raster_crs_value, nodata, width, height = _bytes_dataset(inputs["dsm"])
        if raster_crs_value is None:
            return _unavailable("DSM raster has no coordinate reference system.")
        crs = CRS.from_user_input(raster_crs_value)
        if not crs.is_projected:
            return _unavailable("DSM coordinates must use a projected CRS.")
        factors = [axis.unit_conversion_factor for axis in crs.axis_info[:2]]
        if len(factors) < 2 or any(f is None or abs(float(f) - 1.0) > 1e-8 for f in factors):
            return _unavailable("DSM projected coordinates must use meters.")
        mask_data, mask_transform, mask_crs_value, mask_nodata, _, _ = _bytes_dataset(inputs["mask"])
        if mask_crs_value is None:
            return _unavailable("Roof mask raster has no coordinate reference system.")
        aligned_mask = np.zeros((height, width), dtype=np.uint8)
        reproject(
            source=mask_data,
            destination=aligned_mask,
            src_transform=mask_transform,
            src_crs=mask_crs_value,
            # Google building masks use zero for background. Treat it as source
            # nodata during warp so destination initialization cannot turn it on.
            src_nodata=mask_nodata if mask_nodata is not None else 0,
            dst_transform=transform,
            dst_crs=crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        valid = _raster_valid(dsm, nodata)
        footprint_mask = aligned_mask > 0
        if not (footprint_mask & valid).any():
            return _unavailable("The roof mask has no valid DSM pixels.")

        parcel_geo = (home or {}).get("parcel") or (home or {}).get("geometry")
        if isinstance(parcel_geo, dict) and "geometry" in parcel_geo and "type" not in parcel_geo:
            parcel_geo = parcel_geo["geometry"]
        if isinstance(parcel_geo, dict) and parcel_geo.get("type") == "Feature":
            parcel_geo = parcel_geo.get("geometry")
        if not isinstance(parcel_geo, dict):
            return _unavailable("Home parcel GeoJSON geometry is required.")
        parcel = shape(parcel_geo)
        if parcel.is_empty or not parcel.is_valid:
            return _unavailable("Home parcel geometry is empty or invalid.")
        parcel_projected = _coordinates(parcel, CRS.from_epsg(4326), crs)
        parcel_grid = rasterize([(parcel_projected, 1)], out_shape=(height, width), transform=transform,
                                fill=0, all_touched=False, dtype="uint8").astype(bool)
        footprint_candidate = footprint_mask & parcel_grid
        candidate = footprint_candidate & valid
        if not candidate.any():
            return _unavailable("No valid roof-mask pixels fall inside the home parcel.")

        planes, origin = _make_planes(insights, crs)
        if not planes:
            return _unavailable("No usable Google roof plane measurements were supplied.")
        segments = (insights.get("solarPotential") or {}).get("roofSegmentStats") or insights.get("roofSegmentStats") or []
        if len(segments) > MAX_PLANES:
            warnings.append("Plane count exceeded the processing limit; extra planes were ignored.")
        center = insights.get("center") or {}
        center_xy = _wgs84_xy(float(center["longitude"]), float(center["latitude"]), crs)
        # Polygonize the footprint to separate nearby masked structures. Keep only
        # the connected component containing, or plausibly nearest to, the insight center.
        # Four-connectivity keeps diagonal-only pixel contacts as separate valid
        # polygons instead of a self-touching ring.
        polygons = list(shapes(footprint_candidate.astype("uint8"), mask=footprint_candidate, transform=transform, connectivity=4))
        components = [(shape(geom), int(value)) for geom, value in polygons if int(value) == 1]
        if not components:
            return _unavailable("No connected roof component could be found in the parcel.")
        center_point = Point(center_xy)
        covering = [p for p, _ in components if p.buffer(max(abs(transform.a), abs(transform.e)) * 0.75).covers(center_point)]
        if covering:
            selected = max(covering, key=lambda p: p.area)
        else:
            selected = min((p for p, _ in components), key=lambda p: p.distance(center_point))
            if selected.distance(center_point) > 30.0:
                return _unavailable("No plausible masked building component is near the Google insight center.")
            warnings.append("The selected roof component is near, but does not contain, the Google insight center.")
        selected_component = rasterize([(selected, 1)], out_shape=(height, width), transform=transform,
                                       fill=0, all_touched=False, dtype="uint8").astype(bool) & footprint_candidate
        selected_total_count = int(selected_component.sum())
        selected_grid = selected_component & valid
        if not selected_grid.any():
            return _unavailable("The selected roof component has no valid DSM height samples.")

        rows, cols = np.nonzero(selected_grid)
        if len(rows) > MAX_SELECTED_PIXELS or len(rows) * len(planes) > MAX_PLANE_PIXEL_CELLS:
            return _unavailable("Selected roof component exceeds the plane-fitting memory limit.")
        xs, ys = rasterio.transform.xy(transform, rows, cols, offset="center")
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
        z = dsm[rows, cols].astype(float)
        predicted = np.vstack([p.z_at(x, y) for p in planes])
        residual = z[None, :] - predicted
        eligible = np.ones(residual.shape, dtype=bool)
        for pi, plane in enumerate(planes):
            if plane.bounds is not None:
                bounds_grid = rasterize([(plane.bounds, 1)], out_shape=(height, width), transform=transform,
                                        fill=0, all_touched=False, dtype="uint8")
                eligible[pi] = bounds_grid[rows, cols].astype(bool)
        has_plane = eligible.any(axis=0)
        abs_residual = np.abs(residual)
        abs_residual[~eligible] = np.inf
        choice = np.argmin(abs_residual, axis=0)
        best_abs = abs_residual[choice, np.arange(len(rows))]
        assigned = has_plane & (best_abs <= ASSIGNMENT_TOLERANCE_M)
        labels = np.zeros((height, width), dtype=np.int32)
        labels[rows[assigned], cols[assigned]] = choice[assigned] + 1
        valid_count = int(selected_grid.sum())
        assigned_count = int(assigned.sum())
        if assigned_count == 0:
            return _unavailable("No roof pixels match any supplied Google plane within 0.35 m.")

        # Fit a robust local plane only when the samples span a stable 2D region.
        # Store pitch, true-north azimuth, fit RMSE, fitted center height, and
        # local-coordinate plane coefficients. Coefficients are in projected
        # meter coordinates and preserve the raster fit's grid rotation/scale.
        refined: dict[int, tuple[float, float, float, float, float, float, float]] = {}
        excessive_shifts = 0
        for pi, plane in enumerate(planes):
            take = assigned & (choice == pi)
            if int(take.sum()) < 12:
                continue
            xx, yy, zz = x[take], y[take], z[take]
            design = np.column_stack((xx - plane.center_x, yy - plane.center_y, np.ones(len(xx))))
            if np.linalg.matrix_rank(design) < 3:
                continue
            keep = np.ones(len(xx), dtype=bool)
            coeff = np.linalg.lstsq(design, zz, rcond=None)[0]
            for _ in range(3):
                err = zz - design @ coeff
                med = np.median(err[keep])
                mad = np.median(np.abs(err[keep] - med))
                new_keep = np.abs(err - med) <= max(0.12, 3.0 * 1.4826 * mad)
                if new_keep.sum() < 12 or new_keep.sum() == keep.sum():
                    break
                keep = new_keep
                coeff = np.linalg.lstsq(design[keep], zz[keep], rcond=None)[0]
            rmse = float(np.sqrt(np.mean((zz[keep] - design[keep] @ coeff) ** 2)))
            gx, gy, intercept = map(float, coeff)
            fit_pitch = math.degrees(math.atan(math.hypot(gx, gy) * plane.grid_scale))
            fit_grid_azimuth = math.degrees(math.atan2(-gx, -gy)) % 360.0
            grid_rotation = (plane.grid_azimuth - plane.azimuth + 180.0) % 360.0 - 180.0
            fit_azimuth = (fit_grid_azimuth - grid_rotation) % 360.0
            az_delta = abs((fit_azimuth - plane.azimuth + 180.0) % 360.0 - 180.0)
            height_delta = abs(intercept - plane.height)
            pitch_delta = abs(fit_pitch - plane.pitch)
            angle_ok = pitch_delta <= 3.0 and (max(fit_pitch, plane.pitch) < 1.0 or az_delta <= 12.0)
            if angle_ok and height_delta <= 0.5:
                refined[pi] = (fit_pitch, plane.azimuth if fit_pitch < 1.0 else fit_azimuth,
                               rmse, intercept, gx, gy, intercept - gx * plane.center_x - gy * plane.center_y)
            else:
                excessive_shifts += 1
                angle = math.radians(plane.grid_azimuth)
                slope = math.tan(math.radians(plane.pitch))
                gx = -slope * math.sin(angle) / plane.grid_scale
                gy = -slope * math.cos(angle) / plane.grid_scale
                refined[pi] = (plane.pitch, plane.azimuth, rmse, plane.height,
                               gx, gy, plane.height - gx * plane.center_x - gy * plane.center_y)
        if excessive_shifts:
            warnings.append("One or more raster fits differed too much from the supplied plane measurements; original plane angles were retained.")

        pixel_area = abs(float(transform.a * transform.e - transform.b * transform.d))
        tolerance = min(0.2, max(0.03, math.sqrt(pixel_area) * 0.2))
        outline_rings = _local_polygon(selected, origin, tolerance)
        if outline_rings is None:
            return _unavailable("Roof outline has too many holes or vertices to represent safely.")
        roof_outline_polygon = Polygon(outline_rings[0], outline_rings[1])
        if roof_outline_polygon.is_empty or not roof_outline_polygon.is_valid or roof_outline_polygon.area <= 0:
            return _unavailable("Roof outline is invalid after coordinate conversion.")
        faces: list[dict[str, Any]] = []
        emitted_face_polygons: list[Polygon] = []
        invalid_geometry_withheld = False
        bounds_values: list[tuple[float, float]] = [(px, py) for px, py in outline_rings[0]]
        pieces = []
        for geom, label in shapes(labels, mask=labels > 0, transform=transform, connectivity=4):
            poly = shape(geom)
            if not poly.is_empty and poly.area >= pixel_area * 0.5:
                pieces.append((poly, label))
        if len(pieces) > MAX_FACES:
            # The scan runs top to bottom, so cutting it off would drop whatever lies below the first
            # fragments. A roof turned off the pixel grid leaves hundreds of one-pixel stair steps
            # along its hips and ridges, enough to use every slot before the main planes are reached.
            keep = set(sorted(range(len(pieces)), key=lambda i: (-pieces[i][0].area, i))[:MAX_FACES])
            dropped = sum(p.area for i, (p, _) in enumerate(pieces) if i not in keep)
            warnings.append(f"Output face count was capped: {len(pieces) - MAX_FACES} smaller face(s) totalling {dropped:.1f} m2 were dropped.")
            pieces = [piece for i, piece in enumerate(pieces) if i in keep]
        for poly, label in pieces:
            plane_idx = int(label) - 1
            rings = _local_polygon(poly, origin, tolerance)
            if rings is None:
                return _unavailable("A roof face has too many holes or vertices to represent safely.")
            exterior, holes = rings
            output_polygon = Polygon(exterior, holes)
            if output_polygon.is_empty or not output_polygon.is_valid or output_polygon.area <= 0:
                invalid_geometry_withheld = True
                warnings.append("An invalid roof polygon was withheld from output.")
                continue
            if any(output_polygon.intersection(previous).area > 0.001 for previous in emitted_face_polygons):
                invalid_geometry_withheld = True
                warnings.append("An overlapping roof polygon was withheld from output.")
                continue
            model = refined.get(plane_idx)
            if model is None:
                plane = planes[plane_idx]
                angle = math.radians(plane.grid_azimuth)
                slope = math.tan(math.radians(plane.pitch))
                gx = -slope * math.sin(angle) / plane.grid_scale
                gy = -slope * math.cos(angle) / plane.grid_scale
                model = (plane.pitch, plane.azimuth, None, plane.height, gx, gy,
                         plane.height - gx * plane.center_x - gy * plane.center_y)
            pitch, azimuth, rmse = model[:3]
            faces.append({
                "id": f"plane-{planes[plane_idx].index + 1}-face-{len(faces) + 1}",
                "source_plane_id": f"plane-{planes[plane_idx].index + 1}",
                "polygon": exterior,
                "holes": holes,
                "pitch_degrees": round(float(pitch), 1),
                "azimuth_degrees": round(float(azimuth), 1),
                "area_m2": round(float(poly.area), 1),
                "area_basis": "horizontal",
                "fit_rmse_m": None if rmse is None else round(float(rmse), 2),
                # Face coordinates are serialized relative to the insight
                # center, so shift the intercept into that same local frame.
                "plane_model": {"a": float(model[4]), "b": float(model[5]),
                                "c": float(model[6] + model[4] * origin[0] + model[5] * origin[1])},
                "pixel_count": int(round(poly.area / pixel_area)),
            })
            emitted_face_polygons.append(output_polygon)
            bounds_values.extend((float(a - origin[0]), float(b - origin[1])) for a, b in poly.exterior.coords)

        candidates: list[dict[str, Any]] = []
        obstruction_grid = np.zeros((height, width), dtype=np.uint8)
        unassigned_indices = np.flatnonzero(~assigned)
        high = np.zeros(len(rows), dtype=bool)
        high[unassigned_indices] = has_plane[unassigned_indices] & (residual[choice[unassigned_indices], unassigned_indices] >= 0.75)
        obstruction_grid[rows[high], cols[high]] = 1
        for geom, value in shapes(obstruction_grid, mask=obstruction_grid > 0, transform=transform, connectivity=4):
            poly = shape(geom)
            if poly.area < max(0.5, pixel_area * 4):
                continue
            if len(candidates) >= MAX_CANDIDATES:
                warnings.append("Output obstruction-candidate count was capped.")
                break
            # Estimate height from positive residual pixels within this candidate polygon.
            within = np.asarray([poly.covers(Point(px, py)) for px, py in zip(x[high], y[high])], dtype=bool)
            residual_values = residual[choice, np.arange(len(rows))][high]
            height_est = float(np.mean(residual_values[within])) if within.any() else 0.75
            rings = _local_polygon(poly, origin, tolerance)
            if rings is None:
                warnings.append("A complex obstruction proposal was omitted to keep output geometry bounded.")
                continue
            output_polygon = Polygon(rings[0], rings[1])
            if output_polygon.is_empty or not output_polygon.is_valid or output_polygon.area <= 0:
                warnings.append("An invalid obstruction proposal was withheld from output.")
                continue
            candidates.append({
                "polygon": rings[0],
                "holes": rings[1],
                "area_m2": round(float(poly.area), 1),
                "area_basis": "horizontal",
                "height_m": round(height_est, 1),
            })

        if not faces:
            if invalid_geometry_withheld:
                return _unavailable("No valid roof polygons remained after geometry checks.")
            return _unavailable("Plane assignment produced no usable roof polygons.")
        assigned_fraction = assigned_count / valid_count if valid_count else 0.0
        if assigned_fraction < 0.65:
            warnings.append("A large share of roof-mask pixels could not be assigned confidently to supplied planes.")
        elif assigned_fraction < 0.9:
            warnings.append("Some roof-mask pixels remain unassigned.")
        if inputs.get("rgb"):
            warnings.append("Raw reconstruction uses heights and mask only; fitted roof evaluates photo evidence separately.")
        return {
            "status": "needs_review",
            "algorithm_version": ALGORITHM_VERSION,
            "origin": {"latitude": float(center["latitude"]), "longitude": float(center["longitude"]), "crs": crs.to_string()},
            "roof_outline": {"polygon": outline_rings[0], "holes": outline_rings[1]},
            "faces": faces,
            "obstruction_candidates": candidates,
            "bounds": None if not bounds_values else {
                "min_x": round(min(a for a, _ in bounds_values), 2),
                "min_y": round(min(b for _, b in bounds_values), 2),
                "max_x": round(max(a for a, _ in bounds_values), 2),
                "max_y": round(max(b for _, b in bounds_values), 2),
            },
            "quality": {
                "assigned_fraction": round(float(assigned_fraction), 4),
                "polygon_coverage_fraction": round(min(1.0, sum(face["pixel_count"] for face in faces) / selected_total_count), 4) if selected_total_count else 0.0,
                "unassigned_fraction": round(float(1.0 - assigned_fraction), 4),
                "valid_pixel_count": valid_count,
                "source_height_coverage_fraction": round(float(valid_count / selected_total_count), 4) if selected_total_count else 0.0,
                "assigned_pixel_count": assigned_count,
                "plane_count": len(planes),
                "pixel_size_m": round(math.sqrt(pixel_area), 4),
                "refined_plane_count": len(refined) - excessive_shifts,
                "excessive_fit_shift_count": excessive_shifts,
            },
            "warnings": warnings,
            "ahj": {"status": "pending_rules"},
            "design_ready": False,
        }
    except Exception as exc:
        # Convert malformed or unsupported inputs into a bounded, JSON-safe result.
        if isinstance(exc, ValueError) and "pixel limit" in str(exc):
            return _unavailable("Raster exceeds the 4-million-pixel processing limit.")
        return _unavailable(f"Roof reconstruction could not process the supplied geometry: {type(exc).__name__}.")
