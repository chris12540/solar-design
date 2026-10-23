"""Synthetic Aurora-style DXF and saved-result builders for tests. No real house data."""
FT = .3048


def dxf_text(buildings=(), modules=(), obstruction_lines=(), vents=(), units=2, extra=''):
    """Build DXF text. Lines are ((x1, y1), (x2, y2)); vents are (x, y, r); all in drawing units."""
    out = ['999', 'synthetic', '0', 'SECTION', '2', 'HEADER']
    if units is not None:
        out += ['9', '$INSUNITS', '70', str(units)]
    out += ['0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES']

    def line(layer, p, q):
        return ['0', 'LINE', '8', layer, '10', repr(float(p[0])), '20', repr(float(p[1])), '30', '0',
                '11', repr(float(q[0])), '21', repr(float(q[1])), '31', '0']
    for layer, lines in (('Buildings', buildings), ('Obstructions', obstruction_lines)):
        for p, q in lines:
            out += line(layer, p, q)
    for rect in modules:
        out += [t for i in range(4) for t in line('Modules', rect[i], rect[(i + 1) % 4])]
    for x, y, r in vents:
        out += ['0', 'CIRCLE', '8', 'Obstructions', '10', repr(float(x)), '20', repr(float(y)), '30', '0', '40', repr(float(r))]
    out += [extra, '0', 'ENDSEC', '0', 'EOF'] if extra else ['0', 'ENDSEC', '0', 'EOF']
    return '\n'.join(out) + '\n'


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def ring_lines(points):
    return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


# Gable: 40 x 30 ft footprint, ridge along y=15. Two faces of 600 ft2.
GABLE = ring_lines(rect(0, 0, 40, 30)) + [((0, 15), (40, 15))]
# Hip: 40 x 20 ft, ridge (10,10)-(30,10); two trapezoids (300 ft2) and two triangles (100 ft2).
HIP = (ring_lines(rect(0, 0, 40, 20)) + [((10, 10), (30, 10))]
       + [((0, 0), (10, 10)), ((0, 20), (10, 10)), ((40, 0), (30, 10)), ((40, 20), (30, 10))])


def result_dict(outline, fitted, refined=None, raw=None, obstructions=(), holes=None):
    """A saved-result dict. `fitted`/`refined` are {id: (polygon_coords, azimuth, pitch)}; `raw` the same per plane."""
    def groups(spec):
        return [{'id': k, 'parts': [{'polygon': [list(p) for p in poly], 'holes': []}],
                 'azimuth_degrees': az, 'pitch_degrees': pitch} for k, (poly, az, pitch) in spec.items()]
    return {'roof_outline': {'polygon': [list(p) for p in outline], 'holes': holes or []},
            'faces': [{'id': f'{k}-face', 'source_plane_id': k, 'polygon': [list(p) for p in poly], 'holes': [],
                       'azimuth_degrees': az, 'pitch_degrees': pitch} for k, (poly, az, pitch) in (raw or fitted).items()],
            'refinement': {'face_groups': groups(refined or fitted)},
            'fitting': {'face_groups': groups(fitted), 'quality': {'height_rmse_m': .3, 'photo_edge_support': .5}},
            'obstruction_candidates': [{'polygon': [list(p) for p in o], 'holes': []} for o in obstructions],
            'algorithm_version': 'test', 'pipeline_version': 'test', 'design_ready': False}


def feet_to_m(points):
    return [(x * FT, y * FT) for x, y in points]
