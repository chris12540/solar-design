from __future__ import annotations

import math

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend import roof_cleanup
from backend.roof_cleanup import straighten, straighten_fit


def _jag(a, b, amplitude=.1, spacing=.4):
    """A polyline from a to b with a raster-like stair of +-amplitude across the line; the ends are exact."""
    length = math.dist(a, b)
    count = max(2, round(length / spacing))
    ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
    out = [a]
    for i in range(1, count):
        along = length * i / count
        side = amplitude * (1 if i % 2 else -1)
        out.append((a[0] + ux*along - uy*side, a[1] + uy*along + ux*side))
    return out + [b]


def _ring(*corners):
    """Closed ring through the corners with every side jagged. A side given as a list is used as is (to share it exactly)."""
    points = []
    for here, there in zip(corners, corners[1:] + corners[:1]):
        side = here if isinstance(here, list) else _jag(here, there)
        points += side[:-1]
    return points


def _directions(shape):
    return [math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 180. for a, b in zip(shape.exterior.coords, shape.exterior.coords[1:])]


def _two_rooms():
    """Two 10 x 6 m faces side by side that share one jagged edge."""
    shared = _jag((10, 0), (10, 6))
    a = Polygon(_jag((0, 0), (10, 0)) + shared[1:-1] + _jag((10, 6), (0, 6)) + _jag((0, 6), (0, 0))[:-1])
    b = Polygon(_jag((10, 0), (20, 0)) + _jag((20, 0), (20, 6))[1:-1] + _jag((20, 6), (10, 6)) + list(reversed(shared))[1:-1])
    return {'a': a, 'b': b}


def test_jagged_rooms_become_two_rectangles_sharing_one_straight_edge():
    faces = _two_rooms()
    assert all(not f.is_empty and f.is_valid for f in faces.values())
    straight = straighten(faces, 0.)
    for name in 'ab':
        assert len(straight[name].exterior.coords) - 1 == 4
        assert straight[name].area == pytest.approx(60, abs=1)
        for direction in _directions(straight[name]):
            assert min(direction, 180-direction) < .01 or abs(direction-90) < .01
    assert straight['a'].intersection(straight['b']).area < 1e-6
    assert straight['a'].boundary.intersection(straight['b'].boundary).length == pytest.approx(6, abs=.3)
    assert unary_union(list(straight.values())).area == pytest.approx(120, abs=1.5)


def test_a_turned_roof_is_straightened_along_its_own_axes():
    faces = {name: rotate(shape, 30, origin=(0, 0)) for name, shape in _two_rooms().items()}
    straight = straighten(faces, math.radians(30))
    for shape in straight.values():
        assert len(shape.exterior.coords) - 1 == 4
        for direction in _directions(shape):
            assert min(abs(direction-30), abs(direction-120), abs(direction-210)) < .01 or abs(direction-30) < .01 or abs(direction-120) < .01


def test_a_jagged_diagonal_becomes_an_exact_45_degree_hip():
    diagonal = _jag((0, 0), (10, 10), spacing=.5)
    lower = Polygon([(0, 0), (10, 0), (10, 10)] + list(reversed(diagonal))[1:-1])
    upper = Polygon([(0, 0)] + diagonal[1:-1] + [(10, 10), (0, 10)])
    straight = straighten({'lower': lower, 'upper': upper}, 0.)
    for shape in straight.values():
        assert len(shape.exterior.coords) - 1 == 3
        assert sorted(round(d, 3) for d in _directions(shape)) == [0., 45., 90.]
        assert shape.area == pytest.approx(50, abs=1.5)


def test_a_chamfered_corner_is_squared():
    outline = [(0, 0), (10, 0), (10, 5.5), (9.5, 6), (0, 6)]
    shape = Polygon(_ring(*outline))
    straight = straighten({'roof': shape}, 0.)['roof']
    assert len(straight.exterior.coords) - 1 == 4
    assert straight.area == pytest.approx(60, abs=.7)


def test_an_opening_inside_a_face_stays_open_and_straight():
    hole = [(4, 2), (6, 2), (6, 4), (4, 4)]
    shape = Polygon(_ring((0, 0), (10, 0), (10, 6), (0, 6)), [_ring(*reversed(hole))])
    assert shape.is_valid
    straight = straighten({'roof': shape}, 0.)['roof']
    assert len(straight.interiors) == 1
    opening = Polygon(straight.interiors[0])
    assert opening.area == pytest.approx(4, abs=.5)
    assert len(straight.interiors[0].coords) - 1 == 4


def test_straight_input_is_left_alone():
    faces = {'a': box(0, 0, 10, 6), 'b': box(10, 0, 20, 6)}
    straight = straighten(faces, 0.)
    for name, shape in faces.items():
        assert straight[name].symmetric_difference(shape).area < 1e-6


def _groups(faces):
    return [{'id': name, 'plane_model': {'a': 0, 'b': 0, 'c': 0}, 'pitch_degrees': 20., 'azimuth_degrees': 180., 'area_m2': shape.area,
             'parts': [], 'fit_rmse_m': .02, 'design_ready': False} for name, shape in faces.items()]


def test_straightened_fit_keeps_each_group_and_reports_what_it_gained():
    faces = _two_rooms()
    result = straighten_fit(_groups(faces), list(faces.values()), 0.)
    assert result['status'] == 'ok'
    assert [g['id'] for g in result['face_groups']] == ['a', 'b']
    for group in result['face_groups']:
        assert group['pitch_degrees'] == 20. and group['plane_model'] == {'a': 0, 'b': 0, 'c': 0}
        assert group['area_m2'] == pytest.approx(60, abs=1)
        assert len(group['parts']) == 1 and len(group['parts'][0]['polygon']) == 5
    quality = result['quality']
    assert quality['vertex_count'] == 8 and quality['source_vertex_count'] > 40
    assert quality['long_edge_share'] > .95 > quality['source_long_edge_share']
    assert abs(quality['area_change_m2']) < 1.5 and quality['min_face_overlap'] > .9


def test_straightening_is_skipped_when_a_face_would_be_lost(monkeypatch):
    faces = _two_rooms()
    monkeypatch.setattr(roof_cleanup, 'straighten', lambda shapes, angle: {'a': shapes['a'].buffer(0)})
    result = straighten_fit(_groups(faces), list(faces.values()), 0.)
    assert result['status'] == 'skipped' and 'faces were lost: b' in result['reason'] and result['face_groups'] == []


def test_straightening_is_skipped_when_a_face_moves_too_far(monkeypatch):
    faces = _two_rooms()
    monkeypatch.setattr(roof_cleanup, 'straighten', lambda shapes, angle: {'a': shapes['a'], 'b': box(40, 40, 50, 46)})
    result = straighten_fit(_groups(faces), list(faces.values()), 0.)
    assert result['status'] == 'skipped' and 'b changed too much' in result['reason']


def test_straightening_is_skipped_when_the_area_changes_or_faces_overlap(monkeypatch):
    faces = _two_rooms()
    monkeypatch.setattr(roof_cleanup, 'straighten', lambda shapes, angle: {'a': shapes['a'].buffer(.4), 'b': shapes['b'].buffer(.4)})
    result = straighten_fit(_groups(faces), list(faces.values()), 0.)
    assert result['status'] == 'skipped' and ('changed area' in result['reason'] or 'overlap' in result['reason'])


def test_a_failure_in_straightening_never_costs_the_fit(monkeypatch):
    faces = _two_rooms()

    def broken(shapes, angle):
        raise RuntimeError('boom')
    monkeypatch.setattr(roof_cleanup, 'straighten', broken)
    result = straighten_fit(_groups(faces), list(faces.values()), 0.)
    assert result['status'] == 'skipped' and 'RuntimeError' in result['reason']


def test_fit_adds_straightened_faces_beside_the_unchanged_fit():
    from backend.tests.test_roof_fitting import _hip_roof
    from backend.roof_fitting import fit
    raw, inputs = _hip_roof()
    result = fit(raw, inputs, {})
    straight = result['straightened']
    assert straight['status'] == 'ok'
    assert [g['id'] for g in straight['face_groups']] == [g['id'] for g in result['face_groups']]
    fitted = sorted(round(g['area_m2'], 1) for g in result['face_groups'])
    assert sorted(round(g['area_m2'], 1) for g in straight['face_groups']) == pytest.approx(fitted, abs=.5)
    assert straight['quality']['vertex_count'] <= straight['quality']['source_vertex_count']
