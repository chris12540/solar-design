"""Load a saved roof reconstruction (the `result` JSON) into comparable geometry."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from shapely.geometry import Polygon
from shapely.ops import unary_union

STAGES = ('raw', 'refined', 'fitted', 'straightened')


class ResultFormatError(ValueError):
    pass


@dataclass
class OurFace:
    polygon: object
    azimuth_deg: float
    pitch_deg: float


@dataclass
class OurRoof:
    outline: object
    stages: dict                    # stage -> {face id: OurFace}
    obstructions: list              # candidate polygons
    meta: dict = field(default_factory=dict)

    def polygons(self, stage):
        return {k: f.polygon for k, f in self.stages.get(stage, {}).items()}

    def orientation(self, stage):
        return {k: (f.azimuth_deg, f.pitch_deg) for k, f in self.stages[stage].items()}


def _poly(entry, where):
    try:
        shell = entry['polygon']
        return Polygon(shell, entry.get('holes') or None).buffer(0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultFormatError(f'{where}: bad polygon ({exc})') from None


def _union(parts, where):
    geom = unary_union([_poly(p, where) for p in parts])
    return None if geom.is_empty else geom


def _groups(groups, where):
    out = {}
    for g in groups:
        try:
            geom = _union(g['parts'], where)
            if geom is not None:
                out[g['id']] = OurFace(geom, float(g['azimuth_degrees']), float(g['pitch_degrees']))
        except KeyError as exc:
            raise ResultFormatError(f'{where}: group lacks {exc}') from None
    return out


def _raw(faces):
    by_plane = {}
    for f in faces:
        if f.get('polygon'):
            by_plane.setdefault(f.get('source_plane_id') or f['id'], []).append(f)
    out = {}
    for plane, items in by_plane.items():
        geom = _union(items, 'faces')
        if geom is not None:
            out[plane] = OurFace(geom, float(items[0]['azimuth_degrees']), float(items[0]['pitch_degrees']))
    return out


def from_result(data):
    """Build an OurRoof from the saved result dict (or the API payload that wraps it)."""
    if 'faces' not in data and isinstance(data.get('result'), dict):
        data = data['result']
    try:
        stages = {'raw': _raw(data['faces']),
                  'refined': _groups(data['refinement']['face_groups'], 'refinement'),
                  'fitted': _groups(data['fitting']['face_groups'], 'fitting')}
    except KeyError as exc:
        raise ResultFormatError(f'result lacks {exc}') from None
    straightened = data['fitting'].get('straightened') or {}
    if straightened.get('status') == 'ok':
        stages['straightened'] = _groups(straightened['face_groups'], 'straightened')
    outline = None
    if data.get('roof_outline'):
        outline = _poly(data['roof_outline'], 'roof_outline')
    if outline is None or outline.is_empty:
        faces = [f.polygon for f in stages['fitted'].values()]
        if not faces:
            raise ResultFormatError('result has neither roof_outline nor fitted faces')
        outline = unary_union(faces)
    obstructions = [_poly(o, 'obstruction_candidates') for o in data.get('obstruction_candidates') or []]
    quality = (data.get('fitting') or {}).get('quality') or {}
    meta = {'algorithm_version': data.get('algorithm_version'), 'pipeline_version': data.get('pipeline_version'),
            'design_ready': data.get('design_ready'),
            'height_rmse_m': quality.get('height_rmse_m'),
            'photo_edge_support': quality.get('photo_edge_support'),
            'plausibility': (data.get('fitting') or {}).get('plausibility')}
    return OurRoof(outline, stages, [o for o in obstructions if not o.is_empty], meta)


def load(path):
    data = json.loads(Path(path).read_text())
    roof = from_result(data)
    roof.meta['export'] = data.get('_export')
    return roof
