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


def _fixture(hole=False, obstruction=False, bad_height=False, separate=False, block=False):
    transform = Affine(.1, 0, 500000-10, 0, -.1, 4400000+10)
    lon, lat = Transformer.from_crs('EPSG:32613', 'EPSG:4326', always_xy=True).transform(500000, 4400000)
    rows, cols = np.indices((200, 200))
    x = -.0 + (cols+.5)*.1-10
    data = (10-.3*np.abs(x)).astype('float32')
    if bad_height:
        data += 4
    if block:
        # A 2 x 2.5 m section 1 m above the right plane that the raw face polygon still claims.
        y = 10-(rows+.5)*.1
        data[(x >= 3) & (x <= 5) & (y >= 2) & (y <= 4.5)] += 1.
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


def _plane_grid(n=100, a=.3, c=10.):
    from rasterio import Affine as A
    transform = A(.1, 0, 0, 0, -.1, n*.1)
    rows, cols = np.indices((n, n))
    xx, yy = (cols+.5)*.1, n*.1-(rows+.5)*.1
    return transform, xx, yy, (a*xx + c).astype('float64'), np.ones((n, n), dtype=bool)


def _carve(data_edit, shape=None, valid_edit=None):
    from backend.roof_fitting import _carve_unmodeled
    transform, xx, yy, data, valid = _plane_grid()
    data_edit(data, xx, yy)
    if valid_edit:
        valid_edit(valid, xx, yy)
    return _carve_unmodeled(shape or box(0, 0, 10, 10), (.3, 0., 10.), (data, valid, transform), xx, yy)


def test_carve_removes_a_raised_section_the_plane_does_not_explain():
    shape, regions = _carve(lambda d, x, y: d.__setitem__((x > 4) & (x < 6) & (y > 4) & (y < 6.5), d[(x > 4) & (x < 6) & (y > 4) & (y < 6.5)] + 1.))
    assert shape.area == pytest.approx(100-5, abs=.3)
    assert len(regions) == 1
    assert regions[0]['kind'] == 'raised'
    assert regions[0]['area_m2'] == pytest.approx(5, abs=.3)
    assert regions[0]['mean_residual_m'] == pytest.approx(1, abs=.01)


def test_carve_labels_a_recess_and_ignores_small_noisy_and_nodata_areas():
    def edit(d, x, y, delta, x0, x1, y0, y1):
        m = (x > x0) & (x < x1) & (y > y0) & (y < y1)
        d[m] = d[m] + delta
    shape, regions = _carve(lambda d, x, y: edit(d, x, y, -1., 4, 6, 4, 6.5))
    assert [r['kind'] for r in regions] == ['recessed']
    for small in (lambda d, x, y: edit(d, x, y, 1., 4, 4.5, 4, 4.5),           # 0.25 m2 bump
                  lambda d, x, y: edit(d, x, y, .2, 1, 9, 1, 9),               # large area, within limit
                  lambda d, x, y: edit(d, x, y, 1., 1, 9, 5, 5.12)):           # one-pixel seam
        shape, regions = _carve(small)
        assert regions == [] and shape.area == pytest.approx(100)
    def raised(d, x, y): edit(d, x, y, 1., 4, 6, 4, 6.5)
    shape, regions = _carve(raised, valid_edit=lambda v, x, y: v.__setitem__((x > 4) & (x < 6) & (y > 4) & (y < 6.5), False))
    assert regions == []                                                          # no height data there, nothing to judge


def test_carve_declines_when_most_of_the_face_is_unexplained():
    shape, regions = _carve(lambda d, x, y: d.__setitem__(slice(None), d + 1.))
    assert regions == [] and shape.area == pytest.approx(100)


def test_fit_does_not_claim_pixels_its_plane_does_not_explain():
    clean_raw, clean_inputs = _fixture()
    clean = fit(clean_raw, clean_inputs, {})
    assert clean['unmodeled_regions'] == [] and clean['quality']['unmodeled_area_m2'] == 0
    raw, inputs = _fixture(block=True)
    result = fit(raw, inputs, {})
    roof = unary_union(_shapes(result))
    assert roof.intersection(box(3.1, 2.1, 4.9, 4.4)).area < .05
    assert roof.area == pytest.approx(unary_union(_shapes(clean)).area-5, abs=.5)
    assert len(result['unmodeled_regions']) == 1
    region = result['unmodeled_regions'][0]
    assert region['kind'] == 'raised' and region['area_m2'] == pytest.approx(5, abs=.4)
    assert result['quality']['unmodeled_area_m2'] == pytest.approx(5, abs=.4)
    assert result['quality']['height_rmse_m'] < .05
    assert any('unmodeled' in w.lower() for w in result['warnings'])


def test_trim_ridge_keeps_the_supported_span_and_reaches_the_next_line():
    from shapely.geometry import MultiLineString
    from backend.roof_fitting import _trim_ridge
    line = LineString([(-10, 0), (30, 0)])                       # a plane intersection across the whole roof
    supported = LineString([(5, 0), (9, 0)])
    walls = MultiLineString([[(4.5, -5), (4.5, 5)], [(9.8, -5), (9.8, 5)]])
    trimmed = _trim_ridge(line, supported, walls, reach=1.)
    assert sorted(x for x, _ in trimmed.coords) == pytest.approx([4.5, 9.8])
    assert _trim_ridge(line, supported, MultiLineString([[(12, -5), (12, 5)]]), reach=1.).length == pytest.approx(4)
    assert _trim_ridge(line, LineString(), walls, reach=1.) is None


def test_split_mixed_cells_gives_each_source_its_own_piece():
    from backend.roof_fitting import _split_mixed
    cell = box(0, 0, 10, 10)
    pieces = _split_mixed([cell], [box(0, 0, 6, 10), box(6, 0, 10, 10)], minimum=.5, share=.15, floor=.1)
    assert sorted(round(p.area) for p in pieces) == [40, 60]
    pieces = _split_mixed([cell], [box(0, 0, 4, 10), box(6, 0, 10, 10)], minimum=.5, share=.15, floor=.1)
    assert sorted(round(p.area) for p in pieces) == [20, 40, 40]                # two sources and the unclaimed middle
    assert _split_mixed([box(0, 0, 5, 5)], [box(-1, -1, 9, 9), box(20, 20, 30, 30)], .5, .15, .1)[0].area == pytest.approx(25)
    assert len(_split_mixed([cell], [box(0, 0, 10, 9.97), box(0, 9.97, 10, 10.7)], .5, .15, .1)) == 1   # second source only 0.3 m2 in the cell
    assert len(_split_mixed([cell], [box(0, 0, 10, 9), box(0, 9, 10, 200)], .5, .15, .1)) == 1          # 10 m2, but under 1% of a huge face


def test_split_also_keeps_unclaimed_area_out_of_a_single_source_cell():
    from backend.roof_fitting import _split_mixed
    cell = box(0, 0, 10, 10)
    pieces = _split_mixed([cell], [box(0, 0, 6, 10)], minimum=.5, share=.15, floor=.1)
    assert sorted(round(p.area) for p in pieces) == [40, 60]                    # the source's part and the unclaimed part
    assert len(_split_mixed([cell], [box(0, 0, 10, 9.97)], .5, .15, .1)) == 1    # 0.3 m2 unclaimed is edge noise
    assert len(_split_mixed([cell], [], .5, .15, .1)) == 1                       # no source: left for the support rule


def _hip_roof():
    """A 10 x 6 m hip roof with a 4 m ridge at y=0: four planes, hips at 45 degrees."""
    from backend.roof_fitting import fit as _fit
    transform = Affine(.1, 0, 500000-10, 0, -.1, 4400000+10)
    lon, lat = Transformer.from_crs('EPSG:32613', 'EPSG:4326', always_xy=True).transform(500000, 4400000)
    rows, cols = np.indices((200, 200))
    x, y = (cols+.5)*.1-10, 10-(rows+.5)*.1
    north = 10-.5*y
    south = 10+.5*y
    east = 10-.5*(x-2)
    west = 10+.5*(x+2)
    data = np.where(y >= 0, north, south)
    data = np.where((x > 2) & (np.abs(y) < x-2), east, data)
    data = np.where((x < -2) & (np.abs(y) < -x-2), west, data)
    data = np.where(np.abs(x) > 5, 0, data)
    def tif(array):
        stream = BytesIO()
        with rasterio.open(stream, 'w', driver='GTiff', width=200, height=200, count=1, dtype=array.dtype,
                           crs='EPSG:32613', transform=transform) as ds:
            ds.write(array.astype(array.dtype), 1)
        return stream.getvalue()
    def record(points):
        p = Polygon(points)
        return {'polygon': list(p.exterior.coords), 'holes': []}
    shapes_ = {'north': [(-5, 3), (5, 3), (2, 0), (-2, 0)], 'south': [(-5, -3), (5, -3), (2, 0), (-2, 0)],
               'east': [(5, -3), (5, 3), (2, 0)], 'west': [(-5, -3), (-5, 3), (-2, 0)]}
    models = {'north': (0, -.5, 10), 'south': (0, .5, 10), 'east': (-.5, 0, 11), 'west': (.5, 0, 11)}
    az = {'north': 0, 'south': 180, 'east': 90, 'west': 270}
    faces = [dict(record(pts), id=f'face-{k}', source_plane_id=f'plane-{k}', plane_model=dict(zip('abc', models[k])),
                  pitch_degrees=26.6, azimuth_degrees=az[k], fit_rmse_m=.02) for k, pts in shapes_.items()]
    raw = dict(status='needs_review', origin=dict(latitude=lat, longitude=lon, crs='EPSG:32613'),
               roof_outline=record([(-5, -3), (5, -3), (5, 3), (-5, 3)]), faces=faces,
               quality={'pixel_size_m': .1}, obstruction_candidates=[])
    return raw, dict(dsm=tif((data*1).astype('float32')), mask=tif(np.where(np.abs(x) <= 5, np.where(np.abs(y) <= 3, 1, 0), 0).astype('uint8')))


def test_hip_roof_keeps_four_faces_with_straight_hips():
    raw, inputs = _hip_roof()
    result = fit(raw, inputs, {})
    assert result['status'] == 'experimental'
    areas = sorted(round(a, 1) for a in (s.area for s in _shapes(result)))
    assert areas == pytest.approx([9., 9., 21., 21.], abs=.5)                  # two triangles (6 x 3 / 2) and two trapezoids ((10 + 4) / 2 x 3)
    assert result['quality']['height_rmse_m'] < .05
    assert result['quality']['coverage_fraction'] > .95
    assert result['unmodeled_regions'] == []


def _blur(array, radius=2):
    """Box blur, to give synthetic heights the smoothness of a real 10 cm DSM."""
    k = 2*radius+1
    padded = np.pad(array, radius, mode='edge')
    total = np.zeros(array.shape, dtype=float)
    for dy in range(k):
        for dx in range(k):
            total += padded[dy:dy+array.shape[0], dx:dx+array.shape[1]]
    return total/(k*k)


def test_local_slope_recovers_a_plane_in_either_raster_orientation():
    from backend.roof_fitting import _local_slope
    n = 60
    rows, cols = np.indices((n, n))
    for transform in (Affine(.1, 0, 0, 0, -.1, 6), Affine(.1, 0, 0, 0, .1, 0)):    # north-up, and rows running north
        x = transform.a*(cols+.5)+transform.b*(rows+.5)+transform.c
        y = transform.d*(cols+.5)+transform.e*(rows+.5)+transform.f
        east, north = _local_slope((10+.3*x-.2*y), np.ones((n, n), bool), transform, 2)
        assert np.nanmedian(east) == pytest.approx(.3, abs=1e-6)
        assert np.nanmedian(north) == pytest.approx(-.2, abs=1e-6)
    valid = np.ones((n, n), bool)
    valid[:, :30] = False
    east, _ = _local_slope(10+.3*x, valid, transform, 2)
    assert np.isnan(east[:, :20]).all() and not np.isnan(east[:, 40:55]).any()      # no data, no slope


def _tilt_case(patch=(4, 4, 7.5, 5.2), slope=.55, noise=0., owner_size=10):
    """A flat 10 x 10 m face with one patch whose tilt is clearly different but whose heights stay within 0.3 m."""
    from backend.roof_fitting import _carve_tilt
    transform, xx, yy, data, valid = _plane_grid(a=0.)
    x0, y0, x1, y1 = patch
    inside = (xx > x0) & (xx < x1) & (yy > y0) & (yy < y1)
    data = data.copy()
    data[inside] += slope*(yy[inside]-(y0+y1)/2)
    if noise:
        data += np.random.default_rng(0).normal(0, noise, data.shape)
    shape, regions = _carve_tilt([box(0, 0, owner_size, owner_size)], [(0., 0., 10.)], (data, valid, transform), xx, yy)
    return shape[0], regions


def test_carve_tilt_cuts_out_a_compact_coherent_tilt_change():
    shape, regions = _tilt_case()
    assert len(regions) == 1 and regions[0]['kind'] == 'tilt'
    assert 2. < regions[0]['area_m2'] < 7.
    assert shape.area == pytest.approx(100-regions[0]['area_m2'], abs=.3)
    assert shape.intersection(box(4.6, 4.2, 6.9, 5.0)).area < .5                  # the patch's core is no longer claimed


def test_carve_tilt_refuses_what_is_not_a_hip():
    for case, kwargs in (('thin band like a smoothed crease', dict(patch=(2, 4.5, 9, 4.9))),
                         ('too steep to be a roof facet', dict(patch=(4, 4, 7.5, 5.2), slope=1.6)),
                         ('too small', dict(patch=(4, 4, 4.8, 4.8))),
                         ('same tilt as its face (nothing to find)', dict(slope=0.)),
                         ('height noise only', dict(slope=0., noise=.02))):
        shape, regions = _tilt_case(**kwargs)
        assert regions == [] and shape.area == pytest.approx(100), case


def _flat_roof_with_tilted_patch():
    """One flat 12 x 8 m face; a 3.5 x 1.2 m patch inside it tilts 0.55 but never leaves the plane by more than 0.33 m."""
    transform = Affine(.1, 0, 500000-10, 0, -.1, 4400000+10)
    lon, lat = Transformer.from_crs('EPSG:32613', 'EPSG:4326', always_xy=True).transform(500000, 4400000)
    rows, cols = np.indices((200, 200))
    x, y = (cols+.5)*.1-10, 10-(rows+.5)*.1
    data = np.full((200, 200), 10.)
    patch = (x > -1.5) & (x < 2) & (y > -3.6) & (y < -2.4)
    data[patch] += .55*(y[patch]+3.)
    data = _blur(data, 1)
    def tif(array):
        stream = BytesIO()
        with rasterio.open(stream, 'w', driver='GTiff', width=200, height=200, count=1, dtype=array.dtype,
                           crs='EPSG:32613', transform=transform) as ds:
            ds.write(array, 1)
        return stream.getvalue()
    def record(p):
        return {'polygon': list(p.exterior.coords), 'holes': []}
    outline = box(-6, -4, 6, 4)
    face = dict(record(outline), id='face', source_plane_id='plane-1', plane_model=dict(a=0, b=0, c=10),
                pitch_degrees=0., azimuth_degrees=0., fit_rmse_m=.02)
    raw = dict(status='needs_review', origin=dict(latitude=lat, longitude=lon, crs='EPSG:32613'),
               roof_outline=record(outline), faces=[face], quality={'pixel_size_m': .1}, obstruction_candidates=[])
    return raw, dict(dsm=tif(data.astype('float32')), mask=tif(np.where((np.abs(x) <= 6) & (np.abs(y) <= 4), 1, 0).astype('uint8')))


def test_fit_leaves_a_hip_sized_tilt_change_unmodeled():
    raw, inputs = _flat_roof_with_tilted_patch()
    result = fit(raw, inputs, {})
    assert result['status'] == 'experimental'
    roof = unary_union(_shapes(result))
    assert roof.intersection(box(-1., -3.4, 1.5, -2.6)).area < 1.0                 # the patch core is not claimed by the flat face
    kinds = [r['kind'] for r in result['unmodeled_regions']]
    assert 'tilt' in kinds
    assert result['quality']['unmodeled_area_m2'] > 1.5


def test_smoothed_hip_roof_creases_are_not_taken_for_facets():
    raw, inputs = _hip_roof()
    with rasterio.open(BytesIO(inputs['dsm'])) as src:
        data, transform = src.read(1).astype('float64'), src.transform
    smooth = _blur(data, 2)
    stream = BytesIO()
    with rasterio.open(stream, 'w', driver='GTiff', width=200, height=200, count=1, dtype='float32',
                       crs='EPSG:32613', transform=transform) as ds:
        ds.write(smooth.astype('float32'), 1)
    inputs = dict(inputs, dsm=stream.getvalue())
    result = fit(raw, inputs, {})
    assert [r for r in result['unmodeled_regions'] if r['kind'] == 'tilt'] == []
    assert len(result['face_groups']) == 4
