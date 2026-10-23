"""Registration must recover a known rotation and shift from shape alone."""
import unittest
from shapely import affinity
from shapely.geometry import Polygon, box
from metrics import iou
from registration import Transform, register

L_SHAPE = Polygon([(0, 0), (20, 0), (20, 6), (8, 6), (8, 12), (0, 12)])


def moved(shape, rotation, dx, dy):
    """Inverse of Transform(rotation, dx, dy).apply, so register() should recover that transform."""
    return affinity.rotate(affinity.translate(shape, -dx, -dy), -rotation, origin=(0, 0))


class RegistrationTests(unittest.TestCase):
    def test_transform_apply_matches_inverse_helper(self):
        t = Transform(2.5, 4., -3.)
        back = t.apply(moved(L_SHAPE, 2.5, 4., -3.))
        self.assertGreater(iou(back, L_SHAPE), .999999)

    def test_recovers_small_rotation_and_shift(self):
        t, score = register(moved(L_SHAPE, 2.5, 4., -3.), L_SHAPE)
        self.assertGreater(score, .999)
        self.assertAlmostEqual(t.rotation_deg, 2.5, delta=.25)
        self.assertAlmostEqual(t.dx, 4., delta=.05)
        self.assertAlmostEqual(t.dy, -3., delta=.05)

    def test_negative_rotation_and_far_shift(self):
        t, score = register(moved(L_SHAPE, -4.2, -35., 60.), L_SHAPE)
        self.assertGreater(score, .999)
        self.assertAlmostEqual(t.rotation_deg, -4.2, delta=.25)

    def test_identity_stays_identity(self):
        t, score = register(L_SHAPE, L_SHAPE)
        self.assertAlmostEqual(score, 1., places=6)
        self.assertAlmostEqual(t.rotation_deg, 0., delta=.15)
        self.assertAlmostEqual(abs(t.dx) + abs(t.dy), 0., delta=.02)

    def test_quarter_turn_needs_any_orientation(self):
        target = moved(L_SHAPE, 91.5, 3., 2.)
        _, plain = register(target, L_SHAPE)
        self.assertLess(plain, .9)
        t, score = register(target, L_SHAPE, any_orientation=True)
        self.assertGreater(score, .999)
        self.assertAlmostEqual(t.rotation_deg, 91.5, delta=.25)

    def test_tolerates_a_missing_corner(self):
        chopped = L_SHAPE.difference(box(18, 0, 20, 2))  # about 2.4% of the area
        t, score = register(moved(chopped, 1.5, 6., -4.), L_SHAPE)
        self.assertGreater(score, .95)
        self.assertAlmostEqual(t.rotation_deg, 1.5, delta=.5)
        self.assertAlmostEqual(t.dx, 6., delta=.15)
        self.assertAlmostEqual(t.dy, -4., delta=.15)


if __name__ == '__main__':
    unittest.main()
