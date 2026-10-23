"""Register an Aurora outline to ours by rotation + translation, maximising outline IoU.

The DXF has no georeference, so some fit is unavoidable. The fit absorbs any
constant offset between the two sources, so overlap scores are slightly
optimistic; it cannot absorb differences in shape.
"""
from dataclasses import dataclass
from shapely import affinity
from metrics import iou


@dataclass(frozen=True)
class Transform:
    """Rotate about the origin (degrees, counter-clockwise), then translate (metres)."""
    rotation_deg: float = 0.
    dx: float = 0.
    dy: float = 0.

    def apply(self, geom):
        return affinity.translate(affinity.rotate(geom, self.rotation_deg, origin=(0, 0)), self.dx, self.dy)


def _polish(moving, fixed, rotation, dx, dy, step, min_step=.005):
    """Coordinate descent on translation for a fixed rotation."""
    rotated = affinity.rotate(moving, rotation, origin=(0, 0))
    score = iou(affinity.translate(rotated, dx, dy), fixed)
    while step > min_step:
        improved = True
        while improved:
            improved = False
            for ddx, ddy in ((step, 0), (-step, 0), (0, step), (0, -step)):
                s = iou(affinity.translate(rotated, dx + ddx, dy + ddy), fixed)
                if s > score + 1e-9:
                    score, dx, dy, improved = s, dx + ddx, dy + ddy, True
        step /= 2
    return score, dx, dy


def _centroid_start(moving, fixed, rotation):
    c = affinity.rotate(moving, rotation, origin=(0, 0)).centroid
    return fixed.centroid.x - c.x, fixed.centroid.y - c.y


def register(moving, fixed, search_deg=5., coarse_step=1., any_orientation=False):
    """Return (Transform, iou) that maps `moving` onto `fixed`.

    Searches rotations within +/- `search_deg` of 0 (and of 90, 180, 270 when
    `any_orientation`), then hill-climbs the best down to 0.02 degree.
    """
    bases = (0., 90., 180., 270.) if any_orientation else (0.,)
    n = int(round(search_deg / coarse_step))
    best = None
    for base in bases:
        for k in range(-n, n + 1):
            rotation = base + k * coarse_step
            dx, dy = _centroid_start(moving, fixed, rotation)
            score, dx, dy = _polish(moving, fixed, rotation, dx, dy, 1.)
            if best is None or score > best[0]:
                best = (score, rotation, dx, dy)
    score, rotation, dx, dy = best
    for step in (.5, .1, .02):
        improved = True
        while improved:
            improved = False
            for r in (rotation - step, rotation + step):
                s, ddx, ddy = _polish(moving, fixed, r, dx, dy, .1, min_step=.002)
                if s > score + 1e-9:
                    score, rotation, dx, dy, improved = s, r, ddx, ddy, True
    return Transform(rotation % 360. if rotation % 360. <= 180. else rotation % 360. - 360., dx, dy), score
