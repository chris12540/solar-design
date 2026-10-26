from __future__ import annotations

import math

import pytest
from shapely.geometry import box

from backend.roof_plausibility import assess, edge_class

S = 5 / 12                              # a 5:12 roof


def _group(name, shape, a, b, c, area=None):
    parts = [{'polygon': [list(p) for p in shape.exterior.coords], 'holes': []}]
    return {'id': name, 'plane_model': {'a': a, 'b': b, 'c': c}, 'parts': parts, 'area_m2': shape.area if area is None else area}


def _gable(split=10.):
    """A 20 x 6 m gable whose planes meet at x = 10; the faces are cut at `split`, so a split other than 10 misplaces the edge."""
    return [_group('west', box(0, 0, split, 6), S, 0, 0), _group('east', box(split, 0, 20, 6), -S, 0, 20*S)]


def _kinds(result):
    return sorted(f['kind'] for f in result['flags'])


def test_a_gable_that_meets_at_its_ridge_is_consistent_and_standard():
    result = assess(_gable())
    assert result['status'] == 'ok' and result['flags'] == []
    assert result['edges']['consistent'] == pytest.approx(1.) and result['edges']['length_m'] == pytest.approx(6., abs=.1)
    framing = result['framing_pitch']
    assert framing['ratio'] == 5 and framing['degrees'] == pytest.approx(22.62, abs=.01) and framing['spread_degrees'] == pytest.approx(0.)
    assert result['axis']['bearing_degrees'] == pytest.approx(0., abs=.01) or result['axis']['bearing_degrees'] == pytest.approx(90., abs=.01)


def test_an_edge_near_the_plane_intersection_is_correctable_and_a_far_one_is_not():
    near = assess(_gable(9.5))
    assert near['edges']['correctable'] == pytest.approx(1.) and near['edges']['consistent'] == 0.
    assert 'edge_inconsistent' not in _kinds(near)
    far = assess(_gable(8.))                                   # the planes meet 2 m east of the edge
    assert far['edges']['inconsistent'] == pytest.approx(1.)
    assert 'edge_inconsistent' in _kinds(far)


def test_parallel_planes_a_constant_height_apart_are_a_step():
    groups = [_group('low', box(0, 0, 10, 6), S, 0, 0), _group('high', box(10, 0, 20, 6), S, 0, .6)]
    assert assess(groups)['edges']['step'] == pytest.approx(1.)
    assert edge_class((S, 0, 0), (S, 0, .6), __import__('numpy').array([[10., 1.], [10., 5.]])) == 'step'


def test_a_flat_patio_cover_is_noted_and_does_not_count_as_a_pitched_face():
    groups = _gable() + [_group('patio', box(20, 0, 26, 6), math.tan(math.radians(4)), 0, -2.)]
    result = assess(groups)
    assert [f['face_ids'] for f in result['flags'] if f['kind'] == 'low_slope'] == [['patio']]
    assert result['framing_pitch']['faces'] == 2 and result['framing_pitch']['ratio'] == 5
    assert [item['id'] for item in result['low_slope_faces']] == ['patio']


def test_a_pitched_face_off_the_framing_pitch_is_flagged_for_review():
    groups = _gable() + [_group('odd', box(0, 6, 3, 8), math.tan(math.radians(32)), 0, 0)]          # 6 m2 at 32 degrees, 9 off
    result = assess(groups)
    assert [(f['face_ids'], f['severity']) for f in result['flags'] if f['kind'] == 'pitch_off_framing'] == [(['odd'], 'review')]
    assert result['status'] == 'review'
    near = assess(_gable() + [_group('near', box(0, 6, 3, 8), math.tan(math.radians(26.4)), 0, 0)])       # 3.8 degrees off: a note, not a review
    assert [(f['face_ids'], f['severity']) for f in near['flags'] if f['kind'] == 'pitch_off_framing'] == [(['near'], 'note')]
    assert near['status'] == 'ok'


def test_a_framing_pitch_between_standard_ratios_is_noted():
    t = math.tan(math.radians(20.5))                            # 4:12 is 18.4 degrees, 5:12 is 22.6
    groups = [_group('west', box(0, 0, 10, 6), t, 0, 0), _group('east', box(10, 0, 20, 6), -t, 0, 20*t)]
    result = assess(groups)
    assert 'framing_pitch_off_standard' in _kinds(result) and result['status'] == 'ok'


def test_a_face_turned_off_the_roofs_axes_is_noted_unless_it_is_nearly_flat():
    turned = [_group('turned', box(0, 6, 3, 9), S*math.sin(math.radians(25)), S*math.cos(math.radians(25)), 0)]   # 5:12 facing 25 degrees off
    result = assess(_gable() + turned)
    assert [f['face_ids'] for f in result['flags'] if f['kind'] == 'azimuth_off_axis'] == [['turned']]
    flat = [_group('flat', box(0, 6, 3, 9), .01 * math.sin(math.radians(25)), .01 * math.cos(math.radians(25)), 0)]
    assert 'azimuth_off_axis' not in _kinds(assess(_gable() + flat))


def test_a_sliver_is_noted():
    result = assess(_gable() + [_group('sliver', box(30, 0, 31, 1.5), S, 0, 0)])
    assert [f['face_ids'] for f in result['flags'] if f['kind'] == 'small_face'] == [['sliver']]


def test_a_roof_the_raw_stage_lost_half_of_is_flagged_for_review():
    result = assess(_gable(), outline_area=240., raw_polygon_coverage=.51)
    assert result['status'] == 'review'
    assert {'raw_coverage_low', 'outline_coverage_low'} <= set(_kinds(result))
    assert assess(_gable(), outline_area=125., raw_polygon_coverage=.95)['status'] == 'ok'


def test_a_wobbly_edge_that_is_on_the_planes_on_average_is_consistent():
    """A raster edge has a few points off the line; the planes still meet there, so the edge is consistent."""
    from shapely.geometry import Polygon
    ys = [i * .5 for i in range(13)]
    shared = [(10 + (.3 if y == 3 else 0), y) for y in ys]                                  # one point 0.3 m off: a gap of 0.25 m there
    west = Polygon([(0, 0), *shared, (0, 6)])
    east = Polygon([*reversed(shared), (20, 0), (20, 6)])
    groups = [_group('west', west, S, 0, 0), _group('east', east, -S, 0, 20*S)]
    assert assess(groups)['edges']['consistent'] == pytest.approx(1.)
