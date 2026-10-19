import unittest
import numpy as np
from affine import Affine

from phase2_features import extract_features


def synthetic_scene():
    rows, cols = 80, 100
    transform = Affine(0.1, 0.0, -5.0, 0.0, -0.1, 4.0)
    rr, cc = np.indices((rows, cols))
    x, y = transform * (cc + 0.5, rr + 0.5)
    mask = np.zeros((rows, cols), dtype=bool)
    mask[10:70, 10:90] = True
    dsm = np.zeros((rows, cols), dtype=float)
    left = x < 0
    dsm[mask & left] = 10.0 + 0.45 * x[mask & left]
    dsm[mask & ~left] = 10.0 - 0.45 * x[mask & ~left]
    priors = np.zeros((8, rows, cols), dtype=bool)
    priors[1] = mask & left       # source group 2
    priors[6] = mask & ~left      # source group 7

    # A raised, two-facet roof feature. The common source prior is evidence;
    # both plane fits must still be recovered from DSM residuals.
    dormer = np.zeros_like(mask)
    dormer[27:43, 30:48] = True
    hinge_x = -1.05
    dsm[dormer & (x <= hinge_x)] += 0.65 + 0.25 * (hinge_x - x[dormer & (x <= hinge_x)])
    dsm[dormer & (x > hinge_x)] += 0.65 + 0.25 * (x[dormer & (x > hinge_x)] - hinge_x)
    priors[0] = dormer

    # A compact, curved canopy/tree-like return: positive but non-planar.
    tr, tc = np.indices((rows, cols))
    tree = (tr - 55) ** 2 + (tc - 68) ** 2 <= 9 ** 2
    dome = 1.1 * np.maximum(0.0, 1.0 - ((tr - 55) ** 2 + (tc - 68) ** 2) / 81.0)
    dsm[tree] += dome[tree]
    priors[3] = tree

    # Raised planar patch touching the roof edge, which should fail the edge guard.
    edge = np.zeros_like(mask)
    edge[20:38, 86:90] = True
    dsm[edge] += 0.7
    priors[2] = edge

    # Low DSM returns at the outer roof edge must never become raised features.
    dsm[mask & ((rr < 12) | (rr >= 68) | (cc < 12) | (cc >= 88))] = 1.0
    return dsm, mask, priors, transform


class Phase2FeatureTests(unittest.TestCase):
    def test_raised_two_plane_dormer_is_one_candidate_and_ground_is_estimated(self):
        dsm, mask, priors, transform = synthetic_scene()
        result = extract_features(dsm, mask, priors, transform, pixel_size_m=0.1,
                                  source_expires_at='2026-11-14T00:00:00Z')
        assert set(result['primary_group_ids']) == {'group-2', 'group-7'}
        assert result['ground']['estimated_z_m'] == 0.0
        assert 'not a surveyed elevation' in result['ground']['interpretation']
        candidates = [f for f in result['features'] if 'group-1' in f['source_group_ids']]
        assert len(candidates) == 1  # no duplicate feature for the two roof facets
        dormer = candidates[0]
        assert dormer['type'] == 'dormer_candidate'
        assert dormer['hypothesis_status'] == 'candidate_unconfirmed'
        assert len(dormer['roof_planes']) >= 2
        assert dormer['parent_group_id'] in {'group-2', 'group-7'}
        assert all(p['support_rmse_m'] < 0.075 for p in dormer['roof_planes'])
        assert all(p['height_above_parent_m'] > 0.25 for p in dormer['roof_planes'])
        assert dormer['footprint'][0] == dormer['footprint'][-1]
        assert result['provenance']['source_expires_at'] == '2026-11-14T00:00:00Z'

    def test_curved_tree_edge_patch_and_ground_drop_are_not_dormer_candidates(self):
        dsm, mask, priors, transform = synthetic_scene()
        result = extract_features(dsm, mask, priors, transform, pixel_size_m=0.1)
        source_groups = {g for feature in result['features'] for g in feature['source_group_ids']}
        assert 'group-1' in source_groups
        assert 'group-3' not in source_groups
        assert 'group-4' not in source_groups
        # The edge patch and tree remain unknown/ambiguous evidence rather than being cut out.
        assert result['obstruction_candidates'] == []
        assert all(f['type'] == 'dormer_candidate' for f in result['features'])


if __name__ == "__main__":
    unittest.main()
