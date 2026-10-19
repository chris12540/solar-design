from backend.roof_ranking import rank_candidates
from backend.roof_refinement import refine


def _square(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height], [x, y]]


def _group(face_id, parts, azimuth=180, plane="plane-1", pitch=25):
    area = sum(abs((part["polygon"][1][0] - part["polygon"][0][0]) *
                   (part["polygon"][2][1] - part["polygon"][1][1])) for part in parts)
    return {
        "id": face_id,
        "parts": parts,
        "source_plane_ids": [plane] if plane else [],
        "pitch_degrees": pitch,
        "azimuth_degrees": azimuth,
        "area_m2": area,
        "largest_contiguous_area_m2": max(
            (abs((part["polygon"][1][0] - part["polygon"][0][0]) *
                 (part["polygon"][2][1] - part["polygon"][1][1])) for part in parts), default=0
        ),
    }


def _refinement(*groups):
    return {"status": "experimental", "face_groups": list(groups)}


def _part(x, y, width, height, holes=None):
    return {"polygon": _square(x, y, width, height), "holes": holes or []}


def _ids(result):
    return [item["face_id"] for item in result]


def test_large_contiguous_face_gets_strong_priority():
    result = rank_candidates(_refinement(
        _group("small", [_part(0, 0, 60, 60)]),
        _group("large", [_part(100, 0, 100, 100)]),
    ), {}, {})
    assert _ids(result)[0] == "large"
    assert result[0]["score"] > result[1]["score"]


def test_south_facing_face_outranks_equal_area_north_face():
    result = rank_candidates(_refinement(
        _group("north", [_part(0, 0, 50, 50)], azimuth=0),
        _group("south", [_part(60, 0, 50, 50)], azimuth=180),
    ), {}, {})
    assert _ids(result)[0] == "south"
    assert "Northward orientation" in " ".join(result[1]["reasons"])


def test_flat_faces_do_not_get_an_azimuth_penalty():
    result = rank_candidates(_refinement(
        _group("north-flat", [_part(0, 0, 50, 50)], azimuth=0, pitch=0),
        _group("south-flat", [_part(60, 0, 50, 50)], azimuth=180, pitch=0),
    ), {}, {})
    assert result[0]["score"] == result[1]["score"]


def test_disconnected_parts_do_not_count_as_one_large_contiguous_area():
    disconnected = _group("disconnected", [_part(0, 0, 75, 1), _part(0, 10, 75, 1)])
    single = _group("single", [_part(200, 0, 100, 1)])
    result = rank_candidates(_refinement(disconnected, single), {}, {})
    assert _ids(result)[0] == "single"
    disconnected_result = next(item for item in result if item["face_id"] == "disconnected")
    assert disconnected_result["area_m2"] == 150
    assert disconnected_result["contiguous_area_m2"] == 75


def test_obstruction_candidates_are_buffered_and_subtracted():
    refinement = _refinement(_group("face", [_part(0, 0, 10, 10)]))
    raw = {"obstruction_candidates": [{"polygon": _square(4, 4, 2, 2), "holes": []}]}
    result = rank_candidates(refinement, raw, {})
    # The 0.5 m buffer expands the obstruction and removes about 9 m².
    assert 91 < result[0]["area_m2"] < 92
    assert result[0]["contiguous_area_m2"] == result[0]["area_m2"]


def test_shading_is_explicitly_unknown_without_matching_google_quantiles():
    result = rank_candidates(_refinement(_group("face", [_part(0, 0, 20, 20)])), {}, {})
    assert result[0]["shading_status"] == "unknown"
    assert any("one or more source planes" in check for check in result[0]["unknown_checks"])


def test_nested_google_sunshine_contract_is_matched_by_plane_id():
    refinement = _refinement(
        _group("first", [_part(0, 0, 20, 20)], plane="plane-1"),
        _group("second", [_part(30, 0, 20, 20)], plane="plane-2"),
    )
    inputs = {"insights": {"solarPotential": {"roofSegmentStats": [
        {"stats": {"areaMeters2": 400, "sunshineQuantiles": [100, 120, 130]}},
        {"stats": {"areaMeters2": 400, "sunshineQuantiles": [100, 200, 300]}},
    ]}}}
    result = rank_candidates(refinement, {}, inputs)
    assert all(item["shading_status"] == "available" for item in result)
    assert _ids(result)[0] == "second"
    assert all(any("Google sunshine quantiles" in reason for reason in item["reasons"])
               for item in result)


def test_missing_sunshine_is_neutral_and_explicitly_unknown():
    refinement = _refinement(
        _group("known", [_part(0, 0, 20, 20)], plane="plane-1"),
        _group("unknown", [_part(30, 0, 20, 20)], plane=None),
    )
    inputs = {"insights": {"solarPotential": {"roofSegmentStats": [
        {"stats": {"sunshineQuantiles": [100, 100, 100]}},
    ]}}}
    result = rank_candidates(refinement, {}, inputs)
    known, unknown = {item["face_id"]: item for item in result}.values()
    assert known["score"] == unknown["score"]
    assert known["shading_status"] == "available"
    assert unknown["shading_status"] == "unknown"
    assert any("quantiles are unavailable" in check for check in unknown["unknown_checks"])


def test_partial_source_plane_sunshine_match_remains_unknown():
    refinement = _refinement(_group(
        "merged", [_part(0, 0, 20, 20)], plane="plane-1"
    ))
    refinement["face_groups"][0]["source_plane_ids"].append("plane-2")
    inputs = {"insights": {"solarPotential": {"roofSegmentStats": [
        {"stats": {"sunshineQuantiles": [100, 120, 130]}},
        {},
    ]}}}
    result = rank_candidates(refinement, {}, inputs)
    assert result[0]["shading_status"] == "unknown"
    assert any("one or more source planes" in check for check in result[0]["unknown_checks"])


def test_large_north_face_can_lose_to_smaller_better_oriented_face():
    result = rank_candidates(_refinement(
        _group("large-north", [_part(0, 0, 100, 100)], azimuth=0),
        _group("south", [_part(120, 0, 80, 100)], azimuth=180),
    ), {}, {})
    assert _ids(result)[0] == "south"


def test_larger_low_sun_face_can_lose_to_smaller_sunnier_face():
    refinement = _refinement(
        _group("large-shaded", [_part(0, 0, 100, 100)], plane="plane-1"),
        _group("smaller-sunny", [_part(120, 0, 80, 100)], plane="plane-2"),
    )
    inputs = {"insights": {"solarPotential": {"roofSegmentStats": [
        {"stats": {"sunshineQuantiles": [20, 30, 40]}},
        {"stats": {"sunshineQuantiles": [200, 300, 400]}},
    ]}}}
    result = rank_candidates(refinement, {}, inputs)
    assert _ids(result)[0] == "smaller-sunny"


def test_invalid_refinement_falls_back_to_no_candidates():
    assert rank_candidates({"status": "unavailable", "face_groups": []}, {}, {}) == []


def test_invalid_polygons_do_not_fall_back_to_area_metadata():
    group = _group("invalid", [], plane="plane-1")
    group["parts"] = [{"polygon": [[0, 0], [5, 5], [0, 5], [5, 0], [0, 0]], "holes": []}]
    group["area_m2"] = 10_000
    group["largest_contiguous_area_m2"] = 10_000
    assert rank_candidates(_refinement(group), {}, {}) == []


def test_results_do_not_claim_ahj_or_production_findings():
    result = rank_candidates(_refinement(_group("face", [_part(0, 0, 20, 20)])), {}, {})[0]
    assert any("AHJ" in check for check in result["unknown_checks"])
    assert any("does not estimate production" in reason for reason in result["reasons"])


def test_actual_refinement_output_can_be_ranked_without_status_mock():
    raw = {
        "status": "needs_review",
        "roof_outline": {"polygon": _square(0, 0, 20, 20), "holes": []},
        "faces": [{
            "id": "face-1",
            "source_plane_id": "plane-1",
            "polygon": _square(1, 1, 10, 10),
            "holes": [],
            "pitch_degrees": 20,
            "azimuth_degrees": 180,
            "area_m2": 100,
            "fit_rmse_m": 0.02,
            "plane_model": {"a": 0.0, "b": 0.0, "c": 5.0},
        }],
        "obstruction_candidates": [],
        "quality": {"pixel_size_m": 0.1},
    }
    refined = refine(raw, {}, {})
    assert refined["status"] == "experimental"
    result = rank_candidates(refined, raw, {})
    assert len(result) == 1
    assert result[0]["face_id"] == "group-1"
    assert result[0]["shading_status"] == "unknown"
