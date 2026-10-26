# Roof face accuracy: results against Aurora designs

How well the fitted roof faces (`backend/roof_fitting.py`, versions `fit-1` to `fit-5`) match roof designs made in Aurora Solar, on three houses. Scores come from the benchmark in [`experiments/roof-vision/aurora-benchmark`](../experiments/roof-vision/aurora-benchmark/README.md). Everything here is experimental and no result is design-ready.

![Accuracy by algorithm version](images/roof-accuracy/fig1-accuracy-by-version.svg)

## Summary

- On houses A and B, which are on one street, large-face IoU against the Aurora designs rose on all three cases, from 0.73-0.77 to 0.81-0.85, and area swallowed from faces we do not reproduce fell by 72-86%.
- On house C, a simpler roof in a different neighbourhood that none of the fixes were tuned on, large-face IoU fell from 0.820 to 0.792 and the swallowed area did not change (9.3 m2). The gains are not shown to carry over to other roofs.
- Ridge trimming (`fit-4`) is a trade-off. Turning it off scores higher on houses A and C and lower on house B.
- The outer outline was already close on all three houses (IoU 0.956-0.975) and did not change.
- On houses A and B the fitted stage used to be clearly worse than the raw stage it starts from (house B: 0.771 against 0.807). It is now level with it, with straight edges. On house C it is also level with the raw stage now (0.792 against 0.790), but `fit-1` and `fit-2` were about 0.03 above it, so there the fits lost an advantage they had.
- Not solved: small hips and facets as faces, obstructions (vents are not visible in a 10 cm height model), and the cost of reporting more of the roof as unmodeled (coverage down 0.02-0.03).

## What was measured

A saved reconstruction for a house is scored against the Aurora design for the same house (exported as DXF). The DXF has no georeference, so its outline is registered to ours by rotation and shift; that fit absorbs any constant offset, so overlap scores are slightly optimistic. Only the largest connected structure in the DXF is scored (designs include neighbouring roofs for shading).

| Metric | Meaning |
|---|---|
| Large-face IoU | Area-weighted best intersection-over-union of our faces against the reference faces of 3 m2 or more |
| All-face IoU | The same over every reference face |
| Face recall | Share of reference roof area reproduced by a face at IoU of 0.5 or more |
| Absorbed area | Area of reference faces we did not reproduce that our faces nevertheless cover, i.e. claimed by a neighbour |
| Coverage | Share of the roof outline covered by fitted faces |

Four cases: house A against its AI-made Aurora design, house B against its AI-made design, house B against a human-made design (the better reference: its lines sit on the visible roof edges in a 2 cm image, while the AI design's hips were about 0.5 m off), and house C against its AI-made design. Houses A and B were used to develop and tune the fixes. House C was scored afterwards with no change to the code, and has no human-made design.

## Results by version

Fitted stage, large-face IoU (higher is better):

| Case | fit-1 | fit-2 | fit-3 | fit-4 | fit-5 | raw stage |
|---|---|---|---|---|---|---|
| House A vs AI design | 0.767 | 0.819 | 0.841 | 0.849 | **0.853** | 0.850 |
| House B vs AI design | 0.728 | 0.759 | 0.771 | 0.810 | **0.814** | 0.807 |
| House B vs human design | 0.731 | 0.763 | 0.787 | 0.837 | **0.849** | 0.839 |
| House C vs AI design | 0.820 | 0.820 | 0.811 | 0.792 | 0.792 | 0.790 |

Area absorbed from faces we do not reproduce, m2 (lower is better):

| Case | fit-1 | fit-2 | fit-3 | fit-4 | fit-5 |
|---|---|---|---|---|---|
| House A vs AI design | 23.1 | 11.9 | 7.0 | 7.3 | **3.3** |
| House B vs AI design | 18.7 | 7.2 | 6.1 | 6.7 | **3.6** |
| House B vs human design | 24.6 | 13.8 | 11.6 | 11.2 | **6.8** |
| House C vs AI design | 9.3 | 9.3 | 9.3 | 9.3 | 9.3 |

Final state (`fit-5`):

| | House A vs AI | House B vs AI | House B vs human | House C vs AI |
|---|---|---|---|---|
| Reference faces (3 m2 or more) / ours | 16 (11) / 9 | 11 (8) / 7 | 14 (9) / 7 | 8 (8) / 7 |
| All-face IoU | 0.830 | 0.810 | 0.830 | 0.792 |
| Face recall | 0.943 | 0.972 | 0.934 | 0.969 |
| Outline IoU / edge gap p90 / max | 0.972 / 0.24 / 0.55 m | 0.962 / 0.30 / 0.61 m | 0.956 / 0.36 / 0.85 m | 0.975 / 0.29 / 0.64 m |
| Coverage / reported unmodeled | 0.918 / 6.2 m2 | 0.928 / 6.1 m2 | 0.928 / 6.1 m2 | 0.949 / 0.0 m2 |
| Obstructions found, false positives | 0 of 7, 1 | 1 of 11, 0 | 3 of 12, 0 (see note) | 2 of 17, 1 |

Note: the human design draws one chimney as three shapes and our single candidate matches all three, so "3 of 12" is about one of ten physical objects. Fourteen of house C's 17 reference obstructions are vents. The full per-version table is in [`results.json`](images/roof-accuracy/results.json). Height RMSE is in that file but is measured over different areas before and after `fit-3`, so it is not comparable across that change.

## House C: where the fixes did not help

House C has a simple roof: the Aurora design has 8 faces, all of 3 m2 or more, and we produce 7, with two reference faces merged into one of ours. The outline matches closely (IoU 0.975). Large-face IoU fell by 0.028 from `fit-2` to `fit-5`: 0.009 at `fit-3` and 0.019 at `fit-4`. The swallowed area was 9.3 m2 in every version, so nothing here reduced it.

Ridge trimming on and off, everything else as in `fit-5`, large-face IoU:

| Case | Trimming on (`fit-5`) | Trimming off |
|---|---|---|
| House A vs AI design | 0.853 | 0.863 |
| House B vs AI design | 0.814 | 0.804 |
| House B vs human design | 0.849 | 0.819 |
| House C vs AI design | 0.792 | 0.807 |

Trimming gains 0.010 and 0.030 on house B and loses 0.010 on house A and 0.015 on house C. House B is the roof it was developed on, and we have not established why it helps there and costs elsewhere. Even with trimming off, house C stays below its 0.820 at `fit-2`, so trimming is not the whole story.

Two explanations for the house C drop were tested and ruled out by the data: thin eave strips, and clipping each ridge to the pair of faces it separates. The cause of the drop is otherwise not known.

## What each version changed

- **fit-2: a plane lost to its neighbour.** A 12 m2 face facing west was given to the large east-facing plane, a 180 degree azimuth error. After a ridge candidate was rejected, neighbouring ridges erased half of the shared boundary, leaving a cell that mixed both planes, and a cell goes whole to one plane. Fix: keep the label boundary of rejected pairs, and report any plane that keeps under half its source area.
- **fit-3: faces no longer claim what their plane cannot explain.** Connected areas of at least 0.5 m2 more than 0.35 m off a face's plane are cut out and reported as unmodeled regions instead of being absorbed.
- **fit-4: ridges stop where their faces stop.** Nearly every accepted plane-intersection line ran 10-22 m past the 3-8 m where its two faces meet. Lines are trimmed to their supported span, and cells that straddle faces are split by owner (trimming alone collapsed a roof to four faces, so the two changes go together). It helps house B and costs on houses A and C; see above.
- **fit-5: coherent-tilt regions.** A hip beside larger faces fits their planes to about 10 cm, so no height test sees it, but its slope differs. Compact patches whose local slope disagrees coherently with their owner are cut out and reported as unmodeled regions of kind `tilt`. It did not change any scored metric on house C.

![Ridge extent](images/roof-accuracy/fig2-ridge-extent.svg)

![Mixed cells](images/roof-accuracy/fig3-mixed-cells.svg)

![Tilt region on a synthetic roof](images/roof-accuracy/fig4-tilt-region-synthetic.svg)

The last figure is the real output of `fit-4` and `fit-5` on the synthetic roof used by `test_fit_leaves_a_hip_sized_tilt_change_unmodeled`. The other two are illustrations, not measured data.

## Findings that did not become code

- **A5/A7 (a ring Aurora draws around a flat roof) is not a height defect.** The ring is coplanar with the roof in the heights (median offset -0.02 m, 3 degrees). Only the photo separates them.
- **Small hips cannot be recovered as faces from this height model.** A plane fitted to a hip's core explains almost nothing beyond it: the 10 cm DSM is too smooth for a 2 m hip to form a clean plane. They are reported as unmodeled instead of being given an invented plane.
- **Vents are not visible in the heights** (rise of 0.03-0.17 m for a 7 inch vent), and are at best faint in a 10 cm photo. On house C we found 2 of 17 reference obstructions, 14 of which are vents.
- **Raising the image resolution through the current tool changes nothing.** The photo path shrinks images to 0.1 m and nudges lines by about 6 cm. A 2 cm image showed that outer edges are already within about 6 cm and that interior lines need a different detector.

## Limits

- Three houses and four references, all AI-made except one. Houses A and B are on one street, and thresholds (reach, share, tilt gap, width) were swept on those two only. The one house outside that set got worse, so read the gains as shown on those roofs, not as a general improvement. One more roof does not establish a rate in either direction.
- Aurora designs are references, not surveyed truth. Registration is a fit.
- Sources are Google Solar data with a 10 cm height model. Higher-resolution imagery or lidar might change which of these limits hold.

## Data handling

The Aurora designs, saved reconstructions, imagery and per-house reports used for these numbers are private. They live in the git-ignored `experiments/roof-vision/aurora-benchmark/private/` folder, and Google-derived files carry the original acquisition expiry. Nothing here is a property-specific output: houses are anonymised, the figures use only aggregate numbers, illustrations and synthetic test data, and no imagery is included. To reproduce on your own data, see the benchmark README.
