from __future__ import annotations

from copy import deepcopy

import pytest
from shapely.geometry import Polygon

from backend.roof_refinement import refine


def _face(face_id, polygon, model, pitch=20, azimuth=180, rmse=0.02, plane_id="plane-1", holes=None):
    return {"id": face_id, "source_plane_id": plane_id, "polygon": polygon, "holes": holes or [],
            "pitch_degrees": pitch, "azimuth_degrees": azimuth, "area_m2": Polygon(polygon, holes or []).area,
            "fit_rmse_m": rmse, "plane_model": dict(zip(("a", "b", "c"), model))}


def _raw(faces, outline=None, holes=None, obstructions=None, pixel=0.1):
    return {"status":"needs_review","roof_outline": {"polygon": outline or [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                             "holes": holes or []},
            "faces": faces, "obstruction_candidates": obstructions or [],
            "quality": {"pixel_size_m": pixel}}


def _parts(result):
    return [Polygon(part["polygon"], part["holes"]) for group in result["face_groups"] for part in group["parts"]]


def test_gable_proposes_plane_intersection_ridge_without_overlapping_faces():
    left = _face("left", [[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], (0.2, 0, 0), azimuth=270)
    right = _face("right", [[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]], (-0.2, 0, 2), azimuth=90,
                  plane_id="plane-2")
    result = refine(_raw([left, right]), {}, {})

    assert result["algorithm_version"] == "refine-1"
    assert result["status"] == "experimental"
    assert result["design_ready"] is False
    assert len(result["edges"]) == 1
    assert result["edges"][0]["kind"] == "ridge"
    assert result["edges"][0]["coordinates"][0][0] == pytest.approx(5)
    parts = _parts(result)
    assert parts[0].intersection(parts[1]).area == pytest.approx(0)


def test_valley_edge_classification_uses_height_profile():
    left = _face("left", [[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], (-0.2, 0, 2), azimuth=90)
    right = _face("right", [[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]], (0.2, 0, 0), azimuth=270,
                  plane_id="plane-2")
    assert refine(_raw([left, right]), {}, {})["edges"][0]["kind"] == "valley"


def test_mixed_height_profiles_are_unknown_not_a_hip():
    left = _face("left", [[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], (0.1, 0, 0), pitch=6)
    right = _face("right", [[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]], (0.2, 0, -0.5), pitch=11,
                  plane_id="plane-2")
    result = refine(_raw([left, right]), {}, {})
    assert result["edges"][0]["kind"] == "unknown"


def test_compatible_disconnected_regions_remain_parts_without_convex_hull():
    first = _face("a", [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]], (0, 0, 1))
    second = _face("b", [[7, 7], [9, 7], [9, 9], [7, 9], [7, 7]], (0, 0, 1))
    result = refine(_raw([first, second]), {}, {})

    assert len(result["face_groups"]) == 1
    assert len(result["face_groups"][0]["parts"]) == 2
    assert result["face_groups"][0]["largest_contiguous_area_m2"] == pytest.approx(4)


def test_distinct_height_garage_stays_separate_group():
    first = _face("house", [[1, 1], [4, 1], [4, 4], [1, 4], [1, 1]], (0, 0, 1))
    second = _face("garage", [[6, 1], [9, 1], [9, 4], [6, 4], [6, 1]], (0, 0, 3), plane_id="plane-2")
    result = refine(_raw([first, second]), {}, {})
    assert len(result["face_groups"]) == 2


def test_courtyard_hole_is_preserved_in_refined_part():
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    roof = [[1, 1], [9, 1], [9, 9], [1, 9], [1, 1]]
    face = _face("courtyard", roof, (0, 0, 1), holes=[hole])
    result = refine(_raw([face], holes=[hole]), {}, {})
    part = _parts(result)[0]
    assert len(part.interiors) == 1
    assert not part.covers(Polygon(hole).representative_point())


def test_flat_coplanar_faces_do_not_create_a_fake_edge():
    left = _face("left", [[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], (0, 0, 1), pitch=0)
    right = _face("right", [[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]], (0, 0, 1), pitch=0,
                  plane_id="plane-2")
    result = refine(_raw([left, right]), {}, {})
    assert result["edges"] == []


def test_small_supported_gap_can_be_bridged_with_bounded_addition():
    left = _face("left", [[1, 1], [4.95, 1], [4.95, 5], [1, 5], [1, 1]], (0, 0, 1))
    right = _face("right", [[5.05, 1], [9, 1], [9, 5], [5.05, 5], [5.05, 1]], (0, 0, 1))
    raw = _raw([left, right], pixel=0.5)
    inputs=_evidence_inputs(raw)
    before = deepcopy(raw)
    result = refine(raw, inputs, {})

    assert raw == before
    assert len(result["face_groups"]) == 1
    assert result["inferred_regions"]
    assert 0 < result["quality"]["added_area_m2"] <= 0.04
    assert result["quality"]["max_boundary_deviation_m"] <= 0.3


def test_gap_is_not_bridged_across_obstruction_candidate_buffer():
    left = _face("left", [[1, 1], [4.95, 1], [4.95, 5], [1, 5], [1, 1]], (0, 0, 1))
    right = _face("right", [[5.05, 1], [9, 1], [9, 5], [5.05, 5], [5.05, 1]], (0, 0, 1))
    obstacle = {"polygon": [[4.99, 2], [5.01, 2], [5.01, 4], [4.99, 4], [4.99, 2]], "holes": []}
    result = refine(_raw([left, right], obstructions=[obstacle], pixel=0.5), {}, {})

    assert result["inferred_regions"] == []
    assert len(result["face_groups"][0]["parts"]) == 2


def test_large_gap_is_refused_and_raw_polygons_are_retained():
    left = _face("left", [[1, 1], [4, 1], [4, 5], [1, 5], [1, 1]], (0, 0, 1))
    right = _face("right", [[6, 1], [9, 1], [9, 5], [6, 5], [6, 1]], (0, 0, 1))
    raw = _raw([left, right])
    before_polygons = deepcopy([f["polygon"] for f in raw["faces"]])
    result = refine(raw, {}, {})
    assert result["inferred_regions"] == []
    assert [f["polygon"] for f in raw["faces"]] == before_polygons
    assert [part.area for part in _parts(result)] == pytest.approx([12, 12])


def test_refined_parts_stay_inside_roof_outline_and_coverage_is_measured():
    face = _face("f", [[-1, 1], [5, 1], [5, 5], [-1, 5], [-1, 1]], (0, 0, 1))
    result = refine(_raw([face]), {}, {})
    outline = Polygon(_raw([face])["roof_outline"]["polygon"])
    assert all(outline.covers(part) for part in _parts(result))
    assert result["quality"]["coverage_fraction"] == pytest.approx(20 / 100)



def _evidence_inputs(raw, height=1.0):
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    from pyproj import Transformer
    ox,oy=500000.0,3700000.0
    lon,lat=Transformer.from_crs('EPSG:32612','EPSG:4326',always_xy=True).transform(ox,oy)
    raw['origin']={'longitude':lon,'latitude':lat,'crs':'EPSG:32612'}
    with MemoryFile() as memory:
        with memory.open(driver='GTiff',height=100,width=100,count=1,dtype='float32',
                crs='EPSG:32612',transform=from_origin(ox,oy+10,0.1,0.1),nodata=-9999) as ds:
            ds.write(np.full((100,100),height,dtype='float32'),1)
        return {'dsm':memory.read()}


def test_missing_height_evidence_never_fills_seams():
    a=_face('a',[[1,1],[4.95,1],[4.95,5],[1,5],[1,1]],(0,0,1))
    b=_face('b',[[5.05,1],[9,1],[9,5],[5.05,5],[5.05,1]],(0,0,1))
    result=refine(_raw([a,b],pixel=.5),{}, {})
    assert result['quality']['added_area_m2']==0
    assert result['inferred_regions']==[]


def test_contradictory_height_evidence_never_fills_seams():
    a=_face('a',[[1,1],[4.95,1],[4.95,5],[1,5],[1,1]],(0,0,1))
    b=_face('b',[[5.05,1],[9,1],[9,5],[5.05,5],[5.05,1]],(0,0,1))
    raw=_raw([a,b],pixel=.5)
    result=refine(raw,_evidence_inputs(raw,height=3),{})
    assert result['quality']['added_area_m2']==0


def test_unavailable_raw_cannot_be_promoted_to_a_refined_roof():
    raw=_raw([_face('a',[[1,1],[4,1],[4,5],[1,5],[1,1]],(0,0,1))])
    raw['status']='unavailable'
    assert refine(raw,{}, {})['face_groups']==[]


def test_overlapping_same_plane_parts_are_unioned_without_inflated_area():
    a=_face('a',[[0,0],[5,0],[5,5],[0,5],[0,0]],(0,0,1))
    b=_face('b',[[3,3],[8,3],[8,8],[3,8],[3,3]],(0,0,1))
    result=refine(_raw([a,b]),{}, {})
    assert len(result['face_groups'][0]['parts'])==1
    assert result['face_groups'][0]['area_m2']==pytest.approx(46)


def test_near_angle_planes_diverging_away_from_midpoint_stay_separate():
    a=_face('a',[[0,0],[5,0],[5,10],[0,10],[0,0]],(0,0,1),pitch=0)
    b=_face('b',[[5,0],[10,0],[10,10],[5,10],[5,0]],(.06,0,.7),pitch=3,plane_id='plane-2')
    assert len(refine(_raw([a,b]),{}, {})['face_groups'])==2


def test_convex_sloping_intersection_is_hip():
    a=_face('a',[[0,0],[5,0],[5,10],[0,10],[0,0]],(.2,.15,0),azimuth=240)
    b=_face('b',[[5,0],[10,0],[10,10],[5,10],[5,0]],(-.2,.15,2),azimuth=120,plane_id='plane-2')
    result=refine(_raw([a,b]),{}, {})
    assert result['edges'][0]['kind']=='hip'
    assert set(result['edges'][0]['face_ids'])=={g['id'] for g in result['face_groups']}


def test_shallow_planes_intersection_reaches_supported_boundary_extent():
    from backend.roof_refinement import _plane_intersection
    line=_plane_intersection((.001,0,0),(-.001,0,.01),Polygon([[0,0],[10,0],[10,10],[0,10],[0,0]]))
    assert line.length==pytest.approx(10)


def test_dominant_edge_cleanup_is_bounded_and_preserves_holes():
    coords=[[1,1],[9,1],[9.02,2],[8.98,3],[9.02,4],[8.98,5],[9,9],[1,9],[1,1]]
    hole=[[3,3],[4,3],[4,4],[3,4],[3,3]]
    raw=_raw([_face('a',coords,(0,0,1),pitch=0,holes=[hole])])
    result=refine(raw,_evidence_inputs(raw),{})
    part=_parts(result)[0]
    assert part.is_valid and not part.intersects(Polygon(hole).buffer(-.001))
    assert result['quality']['max_boundary_deviation_m']<=.15
    assert len(part.exterior.coords)<len(coords)
