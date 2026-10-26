# Automatic photo-and-height roof fitting

Scope: one-house experimental proof before neighborhood-scale use. No AHJ setbacks, panel placement, or production approval.

## Processing

- Acquire matching RGB, DSM and mask bytes from one Solar Data Layers response. Fresh acquisitions also use Building Insights; the one-house upgrade reuses existing Insights.
- Keep downloads server-side and user/dataset/parcel scoped. RGB shares existing cache expiry. Algorithm reruns never trigger acquisition when fresh source bytes exist.
- Crop RGB using its CRS and geotransform into the raw model's local projected meter frame. Display a north-up PNG at matching bounds, with attribution. Georeferencing is not independent registration validation.
- Generate a shared line arrangement from dominant building directions, simplified source boundaries and neighboring plane intersections. Assign arrangement cells using raw plane support and DSM residuals. Preserve holes and separate structures.
- Image contrast can adjust proposed lines only within a bounded search and only while plane-height consistency remains acceptable. Contrast is not semantic roof-edge detection: shadows and tile patterns remain limitations.
- Report coverage, outline intersection-over-union, height residual, overlap, outline displacement and photo contrast support. Numeric checks are development diagnostics, not validated acceptance criteria. Every result remains design_ready=false.

## Ridge extent and mixed cells (fit-4)

A ridge, hip or valley is evidence only where its two faces actually meet. Each accepted plane-intersection line is therefore kept only over the span where the two faces touch, and its ends run on at most 1.5 m, to the first existing line. Before fit-4 these lines ran across the whole roof (10-22 m past the real contact), cutting uniform slopes in two and leaving diagonals where no roof edge exists.

Lines that no longer span the roof do not close every cell, so a cell can hold parts of two faces. A cell now goes whole to one plane only if it holds essentially one source. A cell holding at least 0.5 m2 and 15% of two sources is split into one piece per source, and a cell holding a source plus at least 0.5 m2 that no source claims is split so the face does not absorb that area. The 15% share keeps raster edge noise around a correctly straight ridge from undoing the ridge.

## Unmodeled regions (fit-3)

A face never claims pixels its own plane does not explain. After cells are assigned, each face is checked against the DSM: connected areas of at least 0.5 m2 that sit more than 0.35 m off the face's plane (after ignoring seam-width noise) are cut out and reported in `unmodeled_regions`, each with its area, mean and maximum residual, and a kind: `raised` (at least 0.5 m above the plane), `recessed` (at least 0.5 m below), `uneven`, or `tilt` (see below). They count against `coverage_fraction`, and `height_rmse_m` is measured over the faces as emitted. If more than 40% of a face would be cut, nothing is cut and the height error stays visible instead.

This is not classification. A raised region can be a roof section, a chimney or a tree; a recessed one can be a hip or valley the plane does not cover. Vents and similar objects under about 0.5 m are not visible in a 10 cm DSM and are not detected.

## Tilt regions (fit-5)

A hip or small facet beside larger faces fits their planes to within about 10 cm, so the height test above never sees it; the faces swallow it. Its slope is different, though. The local slope (a least-squares plane over a 5 x 5 pixel window) is compared with the slope of the face that owns each pixel. A region needs a seed: a patch of at least 0.5 m2 and 0.6 m wide where the slope differs from the owner's by more than 0.5, with a coherent direction (median spread at most 0.4) and a plausible pitch (8 to 45 degrees). The width rule keeps smoothed creases, which are long thin bands, out. A seed grows over nearby pixels that differ by more than 0.3, and the result is cut out of the faces and reported as an unmodeled region of kind `tilt`. If more than 15% of the roof would be cut this way the height model is treated as unreliable and nothing is cut.

These are reported as unmodeled, not as faces. In Google's height model a 2 m hip never forms a clean plane (a plane fitted to a seed explains almost nothing beyond it), so a face would need an invented plane. Likewise, a ring around a flat roof that an Aurora design draws as a separate face is coplanar with the roof in the heights and is not separated.

## Ridge junctions (fit-6)

Hips and the ridge they climb to meet at one point, but a ridge's supported span stops where its two faces stop touching, often about a metre short of that point: the height model blurs a 2 m hip and the raw faces end early. In fit-4 and fit-5 the other ridges were not among the lines an end could run on to, so a hip met the ridge only if some boundary line happened to lie ahead. A ridge end now also runs on, within the same 1.5 m reach, to the point where its line crosses another accepted ridge's line, provided both ridges have evidence within 1.5 m of that point. Plane intersections cross everywhere, so a crossing away from the evidence of either ridge is ignored.

On a synthetic hip roof whose raw faces stop 1 m short of the apex, this restores the 9, 9, 21 and 21 m2 faces that fit-5 cut to about 6, 6, 21 and 21 m2 (coverage 0.906 before, 1.0 after).

## Straight edges (fit-7)

The fit traces faces from a 10 cm raster, so a 10 m edge can carry 25 vertices in a stair. After the fit, `backend/roof_cleanup.py` builds a second set of face groups, `fitting.straightened`, whose edges are straight like a drawn roof. The fit's own `face_groups` are unchanged and remain what the benchmark scores as `fitted`; `straightened` is scored as its own stage. The app shows it by default, behind a "Straight edges" checkbox.

Everything is done in the roof's own frame (the outline's dominant direction along x), on the edges the faces share, so neighbours keep tiling:

1. The face boundaries are noded so each shared edge appears once, then split into chains that run from junction to junction.
2. Each chain is simplified (Douglas-Peucker, 0.25 m) to a few segments. A segment of 1 m or more within 10 degrees of 0, 45, 90 or 135 degrees is made exactly that direction, through the median of the points it replaces; other segments keep their fitted direction.
3. A short jog between two parallel segments less than 0.5 m apart becomes one line. A run of short segments (1.6 m or less in all) cutting a corner between two long edges is replaced by the two lines' intersection, so rounded corners square off. Collinear edges meeting at a junction share one line.
4. Each junction is placed at the least-squares point of the edges that end there, if that is within 0.7 m of where it was. Corners are the intersections of consecutive lines, with the same limit.
5. Faces are rebuilt from the new lines and given back to the fitted face they overlap most. An opening the rebuilt faces now cover is cut out again.

A straightened result is only used if every face survives, each still overlaps its fitted face by at least 0.6, the faces together change area by at most 3% and do not overlap. Otherwise `straightened.status` is `skipped` with the reason, and the app shows the fit. A failure in this step never affects the fit.

On the five houses scored so far it keeps 8-25% of the fit's vertices, puts 79-92% of the edge length in straight runs of a metre or more (9-61% before), changes total roof area by under 2 m2 and leaves large-face IoU against the Aurora designs level or higher (0.000 to +0.007). Corners that are cut at an angle and are not short, and faces the fit itself gets wrong (teeth beside a chimney, irregular patio covers), stay as they are.

## Plausibility report (fit-8)

`backend/roof_plausibility.py` checks the fitted faces, and the straightened copy, against how pitched roofs are built, and stores the result as `fitting.plausibility.fitted` and `.straightened`. It reports; it never changes a face. The app shows it under the fit checks.

- **Shared edges.** Each edge two faces share is classed by how their two planes behave along it: `consistent` (they meet there, within 0.15 m on average, because a raster edge wobbles), `correctable` (the line where the planes meet passes within 0.8 m, so the edge is misplaced), `step` (near-parallel planes a constant height apart: a real step between roof levels, or a bad plane) or `inconsistent`.
- **Framing pitch.** The area-weighted pitch of the main pitched faces (10 m2 or more, 2:12 or steeper), the nearest standard n:12 ratio, and the spread.
- **Low-slope faces.** Faces under 2:12 (9.5 degrees), below the usual shingle and tile minimum: patio covers, porches or flat roofs.
- **Axes.** The roof's axes from the main faces' azimuths, and how far each pitched face of 5 m2 or more faces from them.
- **Flags**, each a note or a review. A review means part of the roof was probably lost (the raw stage covers under 80% of the roof mask, or the faces cover under 90% of the outline) or a face of 5 m2 or more is more than 5 degrees off the framing pitch. Notes cover a face 3 to 5 degrees off, a framing pitch more than 1.5 degrees from any standard ratio, low-slope faces, faces off the axes, slivers under 2 m2 and edges that are steps.

On the five houses scored so far the main faces average within 0.6 degrees of a standard pitch (4:12 or 5:12), face within 0 to 4 degrees of the roof's axes, and 55-94% of the straightened faces' shared-edge length is consistent. Every house has at least one low-slope face. The large gaps are between near-parallel faces at different heights, which are steps, not misplaced edges.

The straightening can move a ridge or hip a few tenths of a metre off the line where its planes meet (the fit's edges are 95% consistent on one house and the straightened ones 55%); this is open work. Moving edges onto the line where their planes meet (a plane-intersection snap in the straightening) was tried and removed: it changed large-face IoU against the Aurora designs by -0.008 to +0.005 and the average gap along shared edges by only 0.01-0.02 m, because the ridges and hips that matter already sit on plane intersections.



One authorized Data Layers request was used for the sample upgrade; no new Building Insights requests. No retry loop. Optional RGB failure retains acquired DSM/mask inputs. All later fitting checks run on saved bytes. Original sample expiry remains unchanged.

Image dates can differ between Insights and raster layers. That discrepancy remains visible. A clean-looking polygon is not evidence of accurate roof geometry. Failed height checks must remain visible.

## UI

House record → Roof reconstruction → Fitted roof. Show photo toggles imagery; Raw overlay compares original raster geometry. Raw and prior refined geometry remain available for comparison. Validation details are collapsed by default.

## Verification — 2026-10-15

Backend full suite: 226 passed. Added unresolved-plane regression afterwards: six fitter tests passed. Frontend interaction/queue suite: 22 passed. TypeScript/production build passed. Browser verified fitted-tab default, actual photo alignment, raw overlay, geometry-only view, and visible numeric failure details.

Cached sample: 7 fitted groups, 846 source exterior vertices to 178 fitted exterior vertices; 97.417% source-outline coverage, 0.95467 outline IoU, zero face overlaps, 0.4416 m outer-outline Hausdorff displacement. Height all-point RMSE 0.51684 m fails 0.35 m development threshold; median absolute residual 0.01262 m and p90 0.63677 m. One source plane (plane-7) remains unrepresented and is explicitly flagged. Automated checks fail; every result remains not design-ready.

Photo evidence was evaluated, but no bounded photo-driven line shift met current acceptance criteria in final sample. Contrast at proposed edges is 62.1%, a gradient statistic rather than an accuracy score. Outer geometry fitting remains driven primarily by mask, planes, and height data. Photo-guided semantic edge detection and accurate complex junction recovery have not been demonstrated.

One acquisition: one Data Layers request, zero Building Insights requests; later recomputations explicitly blocked network acquisition. Existing source timestamp and expiry preserved. Local raw/refine/fit/photo/cache update took about 0.31 seconds, excluding network and UI; this is not a mass-processing benchmark or a total-cost estimate.
