from __future__ import annotations

from io import BytesIO
import math

import numpy as np
import pytest
import rasterio
from affine import Affine
from pyproj import Geod, Transformer
from shapely.geometry import Polygon

import backend.roof_geometry as roof_geometry
from backend.roof_geometry import reconstruct


CRS = "EPSG:32613"
TRANSFORM = Affine(1, 0, 500000, 0, -1, 4420000)
NODATA = -9999.0


def _tif(array, transform=TRANSFORM, crs=CRS, nodata=None):
    stream = BytesIO()
    with rasterio.open(
        stream, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype=array.dtype, transform=transform, crs=crs, nodata=nodata,
    ) as ds:
        ds.write(array, 1)
    return stream.getvalue()


def _assert_output_polygons_valid(result):
    if "roof_outline" in result:
        assert Polygon(result["roof_outline"]["polygon"], result["roof_outline"]["holes"]).is_valid
    for face in result["faces"]:
        assert Polygon(face["polygon"], face["holes"]).is_valid
    for candidate in result["obstruction_candidates"]:
        assert Polygon(candidate["polygon"], candidate["holes"]).is_valid


def _fixture(pitch=20.0, azimuth=180.0, bump=False, adjacent=False, bad_plane=False, no_mask=False,
             missing_data=False, transform=TRANSFORM, thin_hole=False, diagonal_pixel=False):
    h = w = 30
    yy, xx = np.indices((h, w), dtype=float)
    xx += transform.c + 0.5
    yy = transform.f - yy - 0.5
    to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    to_grid = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    center_x, center_y = transform.c + 15.0, transform.f - 15.0
    lon, lat = to_wgs.transform(center_x, center_y)
    lon2, lat2, _ = Geod(ellps="WGS84").fwd(lon, lat, azimuth, 1.0)
    direction_x, direction_y = to_grid.transform(lon2, lat2)
    grid_angle = math.atan2(direction_x - center_x, direction_y - center_y)
    grid_scale = math.hypot(direction_x - center_x, direction_y - center_y)
    slope = math.tan(math.radians(pitch))
    dsm = 10.0 - slope * ((xx - center_x) * math.sin(grid_angle) + (yy - center_y) * math.cos(grid_angle)) / grid_scale
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[5:25, 5:25] = 1
    mask[12:16, 12:16] = 0  # roof courtyard / void
    if thin_hole:
        mask[10:20, 18] = 0
    if diagonal_pixel:
        mask[4, 4] = 1
    if adjacent:
        mask[5:9, 27:29] = 1
        dsm[5:9, 27:29] = 16.0
    if bump:
        dsm[8:11, 8:11] += 1.5
    if missing_data:
        dsm[5:7, 5:10] = NODATA
    plane_height = 20.0 if bad_plane else 10.0
    insights = {
        "center": {"latitude": lat, "longitude": lon},
        "solarPotential": {"roofSegmentStats": [{
            "pitchDegrees": pitch,
            "azimuthDegrees": azimuth,
            "planeHeightAtCenterMeters": plane_height,
            "center": {"latitude": lat, "longitude": lon},
        }]},
    }
    parcel = {
        "type": "Polygon",
        "coordinates": [[
            [-105.0001, 39.9], [-104.9, 39.9], [-104.9, 40.0], [-105.0001, 40.0], [-105.0001, 39.9]
        ]],
    }
    # Use a parcel enclosing the raster in the raster's own WGS84 bounds.
    corners = [to_wgs.transform(*p) for p in [
        (transform.c, transform.f), (transform.c + 30, transform.f),
        (transform.c + 30, transform.f - 30), (transform.c, transform.f - 30)]]
    parcel["coordinates"] = [[*corners, corners[0]]]
    inputs = {"insights": insights, "dsm": _tif(dsm.astype("float32"), transform=transform, nodata=NODATA),
              "mask": _tif(np.zeros_like(mask) if no_mask else mask, transform=transform), "fetched_at": "2026-10-15T00:00:00Z",
              "expires_at": "2026-10-16T00:00:00Z"}
    return inputs, {"parcel": parcel}


@pytest.mark.parametrize("pitch,azimuth", [(0.0, 0.0), (17.0, 90.0), (31.0, 225.0)])
def test_assigns_google_plane_pitch_and_azimuth(pitch, azimuth):
    inputs, home = _fixture(pitch, azimuth)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["design_ready"] is False
    assert result["ahj"]["status"] == "pending_rules"
    assert result["quality"]["assigned_fraction"] > 0.95
    assert result["faces"][0]["pitch_degrees"] == pytest.approx(pitch, abs=0.2)
    delta = abs((result["faces"][0]["azimuth_degrees"] - azimuth + 180) % 360 - 180)
    assert delta < 0.5


def test_true_north_azimuth_is_converted_to_grid_direction_off_central_meridian():
    off_center_transform = Affine(1, 0, 700000, 0, -1, 4420000)
    inputs, home = _fixture(pitch=24.0, azimuth=135.0, transform=off_center_transform)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["quality"]["assigned_fraction"] > 0.95
    assert result["faces"][0]["pitch_degrees"] == pytest.approx(24.0, abs=0.2)
    delta = abs((result["faces"][0]["azimuth_degrees"] - 135.0 + 180) % 360 - 180)
    assert delta < 0.5
    _assert_output_polygons_valid(result)


def test_polygonizes_roof_hole_and_selects_center_component():
    inputs, home = _fixture(adjacent=True)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert len(result["faces"]) == 1
    assert len(result["faces"][0]["holes"]) == 1
    assert len(result["roof_outline"]["holes"]) == 1
    assert result["quality"]["valid_pixel_count"] == 384
    assert result["faces"][0]["area_m2"] == pytest.approx(384.0)
    _assert_output_polygons_valid(result)


def test_thin_hole_survives_polygon_serialization():
    inputs, home = _fixture(thin_hole=True)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert len(result["roof_outline"]["holes"]) == 2
    assert sum(len(face["holes"]) for face in result["faces"]) == 2
    _assert_output_polygons_valid(result)


def test_diagonal_mask_pixel_does_not_create_self_touching_ring():
    inputs, home = _fixture(diagonal_pixel=True)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["quality"]["valid_pixel_count"] == 384
    _assert_output_polygons_valid(result)


def test_positive_residual_is_proposed_as_obstruction_candidate():
    inputs, home = _fixture(bump=True)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["obstruction_candidates"]
    assert result["obstruction_candidates"][0]["height_m"] == pytest.approx(1.5, abs=0.2)
    _assert_output_polygons_valid(result)


def test_missing_masked_dsm_data_is_excluded():
    inputs, home = _fixture(missing_data=True)
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["quality"]["valid_pixel_count"] == 374
    assert result["quality"]["assigned_fraction"] > 0.99
    assert result["quality"]["source_height_coverage_fraction"] == pytest.approx(374 / 384, abs=0.0001)
    assert result["quality"]["polygon_coverage_fraction"] == pytest.approx(374 / 384, abs=0.0001)


def test_zero_nodata_marker_counts_as_missing_source_height():
    inputs, home = _fixture()
    with rasterio.io.MemoryFile(inputs["dsm"]) as mem:
        with mem.open() as ds:
            dsm = ds.read(1)
            transform, crs = ds.transform, ds.crs
    dsm[8, 8:11] = 0
    inputs["dsm"] = _tif(dsm, transform=transform, crs=crs, nodata=0)
    result = reconstruct(inputs, home)
    assert result["status"] == "needs_review"
    assert result["quality"]["source_height_coverage_fraction"] == pytest.approx(381 / 384, abs=0.0001)


def _gable_fixture():
    h = w = 30
    row, col = np.indices((h, w), dtype=float)
    x = TRANSFORM.c + col + 0.5
    y = TRANSFORM.f - row - 0.5
    center_x, center_y = 500015.0, 4419985.0
    to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    to_grid = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    lon, lat = to_wgs.transform(center_x, center_y)
    pitch = 20.0
    slope = math.tan(math.radians(pitch))
    dsm = np.full((h, w), NODATA, dtype="float32")
    mask = np.zeros((h, w), dtype="uint8")
    mask[5:25, 5:25] = 1

    def plane_z(azimuth):
        lon2, lat2, _ = Geod(ellps="WGS84").fwd(lon, lat, azimuth, 1.0)
        dir_x, dir_y = to_grid.transform(lon2, lat2)
        dx, dy = dir_x - center_x, dir_y - center_y
        scale = math.hypot(dx, dy)
        return 10 - slope * ((x - center_x) * dx / scale + (y - center_y) * dy / scale)

    left = np.arange(5, 15)
    right = np.arange(15, 25)
    dsm[5:25, left] = plane_z(270)[5:25, left].astype("float32")
    dsm[5:25, right] = plane_z(90)[5:25, right].astype("float32")
    # These ridge-adjacent pixels slightly favor the opposite extrapolated plane;
    # the Google segment bounding boxes must keep assignments on their own side.
    dsm[10, 14] = dsm[10, 15] = 10.05
    dsm[10:13, 18:21] += 1.5

    def bounds_box(xmin, xmax):
        sw_lon, sw_lat = to_wgs.transform(xmin, 4419975)
        ne_lon, ne_lat = to_wgs.transform(xmax, 4419995)
        return {"sw": {"longitude": sw_lon, "latitude": sw_lat},
                "ne": {"longitude": ne_lon, "latitude": ne_lat}}

    planes = [
        {"pitchDegrees": pitch, "azimuthDegrees": 270, "planeHeightAtCenterMeters": 10,
         "center": {"latitude": lat, "longitude": lon}, "boundingBox": bounds_box(500005, 500015)},
        {"pitchDegrees": pitch, "azimuthDegrees": 90, "planeHeightAtCenterMeters": 10,
         "center": {"latitude": lat, "longitude": lon}, "boundingBox": bounds_box(500015, 500025)},
    ]
    to_wgs_corners = [to_wgs.transform(*point) for point in (
        (500000, 4420000), (500030, 4420000), (500030, 4419970), (500000, 4419970))]
    home = {"parcel": {"type": "Polygon", "coordinates": [[*to_wgs_corners, to_wgs_corners[0]]]}}
    inputs = {"insights": {"center": {"latitude": lat, "longitude": lon},
                            "solarPotential": {"roofSegmentStats": planes}},
              "dsm": _tif(dsm, nodata=NODATA), "mask": _tif(mask)}
    return inputs, home


def test_adjacent_gable_planes_use_bounding_boxes_and_detect_obstruction():
    inputs, home = _gable_fixture()
    result = reconstruct(inputs, home)

    assert result["status"] == "needs_review"
    assert result["quality"]["plane_count"] == 2
    assert result["quality"]["assigned_fraction"] > 0.95
    assert len(result["faces"]) == 2
    assert sorted(face["pixel_count"] for face in result["faces"]) == [191, 200]
    polygons = [pytest.importorskip("shapely.geometry").Polygon(face["polygon"], face["holes"]) for face in result["faces"]]
    _assert_output_polygons_valid(result)
    assert polygons[0].intersection(polygons[1]).area == pytest.approx(0.0)
    ridge_edges = sorted([polygons[0].bounds[2], polygons[1].bounds[0]])
    assert ridge_edges == pytest.approx([0.0, 0.0], abs=0.01)
    assert result["obstruction_candidates"]


def _smaller_face_scanned_first(monkeypatch):
    """Make the 191-pixel face of the gable fixture come before the 200-pixel one in the label scan."""
    real = roof_geometry.shapes

    def scan(source, *args, **kwargs):
        found = list(real(source, *args, **kwargs))
        return reversed(found) if np.asarray(source).max() > 1 else iter(found)   # only the plane-label scan, not masks
    monkeypatch.setattr(roof_geometry, "shapes", scan)


def test_face_cap_keeps_the_largest_faces_not_the_first_in_scan_order(monkeypatch):
    inputs, home = _gable_fixture()
    _smaller_face_scanned_first(monkeypatch)
    uncapped = reconstruct(inputs, home)
    assert [f["pixel_count"] for f in uncapped["faces"]] == [191, 200]
    assert not any("capped" in w for w in uncapped["warnings"])
    monkeypatch.setattr(roof_geometry, "MAX_FACES", 1)
    result = reconstruct(inputs, home)
    assert [f["pixel_count"] for f in result["faces"]] == [200]
    assert any("capped" in w and "1 smaller face(s)" in w for w in result["warnings"])
    _assert_output_polygons_valid(result)


def test_face_cap_leaves_the_scan_order_alone_when_nothing_is_dropped(monkeypatch):
    inputs, home = _gable_fixture()
    _smaller_face_scanned_first(monkeypatch)
    monkeypatch.setattr(roof_geometry, "MAX_FACES", 2)
    result = reconstruct(inputs, home)
    assert [f["pixel_count"] for f in result["faces"]] == [191, 200]
    assert not any("capped" in w for w in result["warnings"])


def test_invalid_serialized_face_is_withheld(monkeypatch):
    inputs, home = _fixture()
    original = roof_geometry._local_polygon
    calls = 0

    def invalid_face_after_outline(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(*args)
        return [[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]], []

    monkeypatch.setattr(roof_geometry, "_local_polygon", invalid_face_after_outline)
    result = reconstruct(inputs, home)

    assert result["status"] == "unavailable"
    assert result["faces"] == []
    assert "valid roof polygons" in result["warnings"][0]


def test_raster_dimensions_are_capped_before_reading_pixels():
    inputs, home = _fixture()
    large = np.zeros((2001, 2000), dtype="uint8")
    inputs["dsm"] = _tif(large, nodata=0)
    result = reconstruct(inputs, home)
    assert result["status"] == "unavailable"
    assert "processing limit" in result["warnings"][0]


def test_missing_mask_and_bad_planes_are_unavailable():
    inputs, home = _fixture(no_mask=True)
    assert reconstruct(inputs, home)["status"] == "unavailable"
    inputs, home = _fixture(bad_plane=True)
    result = reconstruct(inputs, home)
    assert result["status"] == "unavailable"
    assert result["faces"] == []


def test_geographic_dsm_crs_is_rejected():
    inputs, home = _fixture()
    array = np.zeros((30, 30), dtype="float32")
    inputs["dsm"] = _tif(array, transform=Affine(0.00001, 0, -105, 0, -0.00001, 40), crs="EPSG:4326", nodata=NODATA)
    assert reconstruct(inputs, home)["status"] == "unavailable"
