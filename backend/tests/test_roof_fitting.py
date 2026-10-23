from __future__ import annotations

import copy
from io import BytesIO

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio import Affine
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from backend.roof_fitting import _shift_photo, fit


def _fixture(hole=False, obstruction=False, bad_height=False, separate=False):
    transform = Affine(.1, 0, 500000-10, 0, -.1, 4400000+10)
    lon, lat = Transformer.from_crs('EPSG:32613', 'EPSG:4326', always_xy=True).transform(500000, 4400000)
    rows, cols = np.indices((200, 200))
    x = -.0 + (cols+.5)*.1-10
    data = (10-.3*np.abs(x)).astype('float32')
    if bad_height:
        data += 4
    def tif(array):
        stream = BytesIO()
        with rasterio.open(stream, 'w', driver='GTiff', width=200, height=200, count=1,
                           dtype=array.dtype, crs='EPSG:32613', transform=transform) as ds:
            ds.write(array, 1)
        return stream.getvalue()
    # A noisy observed ridge; both regions share the same original topology.
    edge = [(.14*np.sin(i*2), float(i)) for i in np.linspace(-8, 8, 65)]
    left = Polygon([(-8, -8), *edge, (-8, 8)])
    right = Polygon([*reversed(edge), (8, -8), (8, 8)])
    if hole:
        left = left.difference(box(-5,-2,-4,-1))
    if separate:
        left = box(-8,-8,-2,8)
        right = box(2,-8,8,8)
    def record(p):
        return {'polygon': list(p.exterior.coords), 'holes': [list(r.coords) for r in p.interiors]}
    faces = []
    for i, (shape, slope) in enumerate([(left,.3),(right,-.3)]):
        faces.append(dict(record(shape), id=f'face-{i}', source_plane_id=f'plane-{i}',
                          plane_model=dict(a=slope,b=0,c=10), pitch_degrees=16.7,
                          azimuth_degrees=90 if i else 270, fit_rmse_m=.02))
    raw = dict(status='needs_review', origin=dict(latitude=lat, longitude=lon,crs='EPSG:32613'),
               roof_outline=record(box(-8,-8,8,8)), faces=faces,
               quality={'pixel_size_m':.1}, obstruction_candidates=[])
    if obstruction:
        raw['obstruction_candidates'] = [record(box(3,2,4,3))]
    return raw, dict(dsm=tif(data), mask=tif(np.ones(data.shape,dtype='uint8')))


def _shapes(result):
    return [unary_union([Polygon(p['polygon'],p['holes']) for p in f['parts']])
            for f in result['face_groups']]


def test_arrangement_replaces_noisy_shared_ridge_with_single_straight_edge():
    raw, inputs = _fixture()
    source = copy.deepcopy(raw)
    result = fit(raw, inputs, {})
    shapes = _shapes(result)
    assert result['status'] == 'experimental'
    assert raw == source
    assert len(shapes) == 2
    shared = shapes[0].boundary.intersection(shapes[1].boundary)
    assert shared.length == pytest.approx(16)
    assert shared.hausdorff_distance(LineString([(0,-8),(0,8)])) < 1e-6
    assert result['quality']['fitted_vertex_count'] <= 10
    assert result['quality']['height_rmse_m'] < .01
    assert result['quality']['overlap_area_m2'] < 1e-8
    assert result['quality']['coverage_fraction'] > .999
    assert result['quality']['checks']['height'] is True
    assert result['quality']['checks_passed'] is True
    assert result['design_ready'] is False
    assert all(f['design_ready'] is False for f in result['face_groups'])


def test_holes_obstructions_and_separate_buildings_remain_empty():
    raw, inputs = _fixture(hole=True, obstruction=True)
    result = fit(raw, inputs, {})
    roof = unary_union(_shapes(result))
    assert roof.intersection(box(-5,-2,-4,-1)).area < 1e-8
    assert roof.intersection(box(3,2,4,3)).area < 1e-8
    raw, inputs = _fixture(separate=True)
    result = fit(raw, inputs, {})
    roof = unary_union(_shapes(result))
    assert roof.intersection(box(-1,-7,1,7)).area < 1e-8


def test_unavailable_inputs_and_crs_mismatch_do_not_create_faces():
    raw, inputs = _fixture()
    for variant in ({}, {'dsm':b'not a raster'}):
        result = fit(raw, variant, {})
        assert result['status'] == 'unavailable'
        assert result['face_groups'] == []
    raw['origin']['crs'] = 'EPSG:32612'
    assert fit(raw, inputs, {})['status'] == 'unavailable'


def test_bad_dsm_height_reports_failed_check_and_actual_error():
    raw, inputs = _fixture(bad_height=True)
    result = fit(raw, inputs, {})
    assert result['status'] == 'experimental'
    assert result['quality']['height_rmse_m'] > 3.9
    assert result['quality']['checks']['height'] is False
    assert result['design_ready'] is False


def test_photo_gradient_search_is_bounded_and_ignores_uniform_image():
    gradient = np.zeros((100,100))
    gradient[:,52] = .3
    evidence = dict(gradient=gradient, valid=np.ones(gradient.shape,dtype=bool),
                    transform=Affine(.1,0,-5,0,.1,-5))
    line = LineString([(0,-4),(0,4)])
    shifted, used = _shift_photo(line,evidence,.3)
    assert used
    assert shifted.hausdorff_distance(line) <= .3+1e-8
    assert shifted.coords[0][0] == pytest.approx(.225)
    evidence['gradient'][:] = 0
    assert _shift_photo(line,evidence,.3)[1] is False


def test_unrepresented_source_plane_is_reported_and_prevents_check_pass():
    raw,inputs=_fixture()
    # Conflicting tiny plane cannot win ownership of a shared arrangement cell.
    extra=copy.deepcopy(raw['faces'][0])
    extra.update(id='unresolved',source_plane_id='plane-unresolved',
                 polygon=[[1,1],[1.2,1],[1.2,1.2],[1,1.2],[1,1]],holes=[],
                 plane_model={'a':0,'b':0,'c':1000})
    raw['faces'].append(extra)
    result=fit(raw,inputs,{})
    assert 'plane-unresolved' in result['quality']['unrepresented_source_planes']
    assert result['quality']['checks']['source_planes_retained'] is False
    assert result['quality']['checks_passed'] is False
    assert any('unresolved' in warning for warning in result['warnings'])


def test_contact_lines_keep_the_label_boundary_of_a_rejected_pair():
    from backend.roof_fitting import _contact_lines
    lines = _contact_lines([box(0, 0, 4, 10), box(4, 0, 8, 10)], set(), reach=.05, tolerance=.35, minimum=.5)
    assert len(lines) == 1
    assert lines[0].length == pytest.approx(10, abs=.1)
    assert lines[0].hausdorff_distance(LineString([(4, 0), (4, 10)])) < .06


def test_contact_lines_skip_accepted_distant_and_brief_contacts():
    from backend.roof_fitting import _contact_lines
    left, right = box(0, 0, 4, 10), box(4, 0, 8, 10)
    assert _contact_lines([left, right], {(0, 1)}, .05, .35, .5) == []             # ridge was accepted
    assert _contact_lines([left, box(6, 0, 8, 10)], set(), .05, .35, .5) == []     # 2 m apart
    assert _contact_lines([left, box(4, 9.8, 8, 20)], set(), .05, .35, .5) == []   # 0.2 m of contact
    assert len(_contact_lines([left, right, box(0, 10, 4, 14)], {(0, 1)}, .05, .35, .5)) == 1


def test_retention_flags_groups_that_kept_under_half_their_source_region():
    from backend.roof_fitting import _retention
    assert _retention([12.5, 80., 0.], [1.1, 95., 0.]) == pytest.approx([1.1 / 12.5, 95 / 80., 1.])
