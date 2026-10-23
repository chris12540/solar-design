"""Reader for Aurora Solar DXF exports (ASCII R12; LINE and CIRCLE entities).

The file is untrusted input: it is read as plain group-code pairs and nothing in
it is evaluated. Output geometry is in metres, in the DXF's own local frame.
"""
from dataclasses import dataclass, field
from pathlib import Path
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

MAX_BYTES = 50 * 1024 * 1024
INSUNITS_TO_M = {1: .0254, 2: .3048, 4: .001, 5: .01, 6: 1.}
BUILDINGS, MODULES, OBSTRUCTIONS = 'Buildings', 'Modules', 'Obstructions'
MIN_FACE_M2 = .05
SNAP_M = .001
MODULE_FALLBACK_M2 = (.2, 5.)


class DxfError(ValueError):
    pass


@dataclass
class AuroraDesign:
    units_to_m: float
    faces: list              # roof face polygons, largest first
    roof_outline: object
    modules: list            # module polygons
    vents: list              # (x, y, radius) circles on the obstruction layer
    obstruction_polygons: list
    counts: dict             # entity count per layer
    warnings: list = field(default_factory=list)

    @property
    def face_ids(self):
        return [f'A{i}' for i in range(len(self.faces))]

    @property
    def faces_by_id(self):
        return dict(zip(self.face_ids, self.faces))


def _pairs(text):
    lines = text.splitlines()
    pairs = []
    for i in range(0, len(lines) - 1, 2):
        try:
            pairs.append((int(lines[i].strip()), lines[i + 1].strip()))
        except ValueError:
            raise DxfError(f'line {i + 1}: group code is not an integer') from None
    return pairs


def _num(value, what):
    try:
        return float(value)
    except ValueError:
        raise DxfError(f'{what}: {value!r} is not a number') from None


def _read(pairs):
    """Return ($INSUNITS or None, entities as {'type','layer','codes'})."""
    units, entities = None, []
    section, current, i = None, None, 0
    while i < len(pairs):
        code, value = pairs[i]
        if code == 0 and value == 'SECTION' and i + 1 < len(pairs):
            section, current = pairs[i + 1][1], None
            i += 2
            continue
        if code == 0 and value == 'ENDSEC':
            section, current = None, None
        elif section == 'HEADER' and code == 9 and value == '$INSUNITS' and i + 1 < len(pairs):
            units = int(_num(pairs[i + 1][1], '$INSUNITS'))
        elif section == 'ENTITIES':
            if code == 0:
                current = {'type': value, 'layer': '', 'codes': {}}
                entities.append(current)
            elif current is not None:
                if code == 8:
                    current['layer'] = value
                else:
                    current['codes'].setdefault(code, []).append(value)
        i += 1
    return units, entities


def _first(entity, code):
    values = entity['codes'].get(code)
    if not values:
        raise DxfError(f"{entity['type']} on layer {entity['layer']!r} lacks group code {code}")
    return _num(values[0], f"{entity['type']} code {code}")


def _snap(v, scale):
    return round(v * scale / SNAP_M) * SNAP_M


def _line(entity, scale):
    p = (_snap(_first(entity, 10), scale), _snap(_first(entity, 20), scale))
    q = (_snap(_first(entity, 11), scale), _snap(_first(entity, 21), scale))
    return LineString([p, q]) if p != q else None


def _faces(lines, warnings):
    if not lines:
        return []
    polys = list(polygonize(unary_union(lines)))
    kept = [p for p in polys if p.area >= MIN_FACE_M2]
    if len(kept) < len(polys):
        warnings.append(f'{len(polys) - len(kept)} sliver face(s) under {MIN_FACE_M2} m2 dropped')
    return sorted(kept, key=lambda p: -p.area)


def _modules(lines, warnings):
    """Aurora writes each module as four consecutive LINEs."""
    mods, bad = [], len(lines) % 4 != 0
    for i in range(0, len(lines) - len(lines) % 4, 4):
        polys = list(polygonize(unary_union(lines[i:i + 4])))
        if len(polys) == 1 and polys[0].area > .05:
            mods.append(polys[0])
        else:
            bad = True
    if bad and lines:
        warnings.append('module lines are not four-line groups; falling back to loop detection')
        lo, hi = MODULE_FALLBACK_M2
        mods = [p for p in polygonize(unary_union(lines)) if lo <= p.area <= hi]
    return mods


def _primary_building(faces, warnings, join=.15):
    """Keep the faces of the largest connected structure; designs often include neighbouring roofs for shading."""
    if len(faces) < 2:
        return faces
    joined = unary_union([f.buffer(join) for f in faces])
    parts = list(joined.geoms) if hasattr(joined, 'geoms') else [joined]
    if len(parts) < 2:
        return faces
    owner = [next(i for i, p in enumerate(parts) if p.contains(f.representative_point())) for f in faces]
    area = [sum(f.area for f, o in zip(faces, owner) if o == i) for i in range(len(parts))]
    keep = max(range(len(parts)), key=area.__getitem__)
    warnings.append(f'{len(parts)-1} other structure(s) totalling {sum(area)-area[keep]:.1f} m2 ignored; the largest building was kept')
    return [f for f, o in zip(faces, owner) if o == keep]


def parse(text, units=None, primary_only=True):
    """Parse DXF text. `units` (metres per drawing unit) overrides $INSUNITS.

    With `primary_only` (default) only the largest connected structure is kept as the roof.
    """
    header_units, entities = _read(_pairs(text))
    if units is None:
        if header_units not in INSUNITS_TO_M:
            raise DxfError(f'unsupported or missing $INSUNITS {header_units!r}; pass units=metres per unit')
        units = INSUNITS_TO_M[header_units]
    warnings, counts = [], {}
    by_layer = {BUILDINGS: [], MODULES: [], OBSTRUCTIONS: []}
    vents = []
    for e in entities:
        counts[e['layer']] = counts.get(e['layer'], 0) + 1
        if e['type'] == 'LINE' and e['layer'] in by_layer:
            line = _line(e, units)
            if line is not None:
                by_layer[e['layer']].append(line)
        elif e['type'] == 'CIRCLE' and e['layer'] == OBSTRUCTIONS:
            vents.append((_first(e, 10) * units, _first(e, 20) * units, _first(e, 40) * units))
    faces = _faces(by_layer[BUILDINGS], warnings)
    if primary_only:
        faces = _primary_building(faces, warnings)
    if not faces:
        warnings.append('no roof faces found on the Buildings layer')
    outline = unary_union([f.buffer(.02) for f in faces]).buffer(-.02) if faces else None
    obstruction_polys = list(polygonize(unary_union(by_layer[OBSTRUCTIONS]))) if by_layer[OBSTRUCTIONS] else []
    return AuroraDesign(units, faces, outline, _modules(by_layer[MODULES], warnings),
                        vents, obstruction_polys, counts, warnings)


def load(path, units=None, primary_only=True):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise DxfError(f'{path.name} is larger than {MAX_BYTES} bytes')
    return parse(path.read_text(encoding='utf-8', errors='replace'), units, primary_only)
