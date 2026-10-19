"""Evaluate frozen photo annotations without feeding them into roof fitting."""
from pathlib import Path
import hashlib
import json
import pickle
import numpy as np

ROOT = Path(__file__).resolve().parent


def line_check(item, archive, groups, transform):
    ends = np.asarray(item['xy'], dtype=float)
    delta = ends[1] - ends[0]
    tangent = delta / np.linalg.norm(delta)
    normal = np.array([-tangent[1], tangent[0]])
    samples = ends[0] + np.linspace(.15, .85, 40)[:, None] * delta
    counts = []
    for sign in (-1, 1):
        side = samples + sign * 3. * normal
        xy = np.rint(side).astype(int)
        valid = ((xy[:, 0] >= 0) & (xy[:, 0] < archive['face_priors'].shape[2]) &
                 (xy[:, 1] >= 0) & (xy[:, 1] < archive['face_priors'].shape[1]))
        xy = xy[valid]
        hits = archive['face_priors'][:, xy[:, 1], xy[:, 0]]
        count = {identifier: int(hits[i].sum()) for i, identifier in enumerate(archive['face_ids'])}
        count['unassigned_samples'] = int((~hits.any(axis=0)).sum())
        counts.append(count)
    sides = [max(groups, key=lambda identifier: side.get(identifier, 0)) for side in counts]
    report = {'reference_id': item['id'], 'label': item['label'],
              'sampling_offset_pixels': 3, 'samples_per_side': 40,
              'prior_side_sample_counts': counts, 'dominant_source_groups': sides,
              'relationship': 'photo_annotation_checked_against_source_planes_not_used_to_fit_them'}
    if sides[0] == sides[1] or any(max(s.get(i, 0) for i in groups) < 12 for s in counts):
        report['intersection_status'] = 'source_ownership_ambiguous_or_same_on_both_sides'
        return report
    a, b = [groups[identifier]['plane_model'] for identifier in sides]
    coefficients = np.array([a[k]-b[k] for k in ('a', 'b', 'c')])
    local = np.array([transform * tuple(point + .5) for point in samples])
    dz = local @ coefficients[:2] + coefficients[2]
    length = np.linalg.norm(coefficients[:2])
    report['plane_height_disagreement_on_visible_seam_m'] = {
        'median_absolute': float(np.median(np.abs(dz))),
        'max_absolute': float(np.max(np.abs(dz))),
        'signed_range': [float(dz.min()), float(dz.max())]}
    if length < 1e-6:
        report['intersection_status'] = 'parallel_planes_no_stable_intersection'
    else:
        distances = np.abs(dz) / length
        report['intersection_status'] = 'diagnostic_intersection_computed'
        report['distance_from_visible_seam_to_analytic_intersection_m'] = {
            'median': float(np.median(distances)), 'max': float(distances.max())}
        report['interpretation'] = ('Agreement supports a continuous-join hypothesis; disagreement may be '
                                    'a height step, wrong source ownership, plane error or annotation/registration error. '
                                    'No edge semantics are certified by this comparison.')
    return report


def main():
    data = pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    reference_bytes = (ROOT/'phase1-reference.json').read_bytes()
    reference = json.loads(reference_bytes)
    archive = np.load(ROOT/'outputs/sam-masks.npz')
    groups = {g['id']:g for g in data['raw']['refinement']['face_groups']}
    checks = [line_check(item, archive, groups, data['aligned']['transform'])
              for item in reference['lines'] if item['id'] in ('R1', 'H1', 'H2', 'J1')]
    report = {
        'phase': 1, 'reference_version': reference['version'],
        'reference_sha256': hashlib.sha256(reference_bytes).hexdigest(),
        'reference_status': reference['status'],
        'source_input_sha256': hashlib.sha256((ROOT/'data/inputs.pkl').read_bytes()).hexdigest(),
        'seam_checks': checks,
        'production_accuracy_established': False,
        'source_expires_at': data['expires_at'],
        'evaluation_contract': {
            'annotation_uncertainty_pixels': reference['endpoint_uncertainty_pixels'],
            'not_a_production_tolerance': True,
            'required_reports': [
                'Perimeter and seam distances separately; show distribution and disagreement regions.',
                'Photo-visible junction incidence and endpoints; do not infer correctness from polygon validity.',
                'Full and interior DSM residuals separately, plus spatial hold-out checks.',
                'Roof area unsupported by source planes; report every coverage denominator.',
                'Uncertain connections, source registration and objects remain explicitly unresolved.',
                'No routine manual reference fitting: reference coordinates cannot enter reconstruction inputs.'
            ],
            'hard_geometry_checks': ['Valid non-self-intersecting faces', 'No unintentional overlaps',
                                     'Declared edges exactly match resulting faces',
                                     'No automatic bridging of ambiguous gaps or erasure of obstruction candidates'],
            'phase2_gate': 'Can test main-roof plane-intersection hypotheses. Small connections remain competing hypotheses; no whole-roof or design-readiness claim.',
            'commercial_accuracy_gate': 'Unset: requires independent measured/reference roofs and broader held-out validation.'
        },
        'limitations': ['Annotations are photo interpretation, not survey truth or a blinded benchmark.',
                        'Nearby source ownership may be incorrect; dominant-side selection is diagnostic only.',
                        'Inputs share source data; small residuals are not independent physical accuracy.',
                        'No reconstruction, image correction or new acquisition is performed.']
    }
    (ROOT/'outputs/phase1-evidence.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'reference_sha256': report['reference_sha256'], 'seam_checks': checks}, indent=2))


if __name__ == '__main__':
    main()
