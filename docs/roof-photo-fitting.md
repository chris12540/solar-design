# Automatic photo-and-height roof fitting

Scope: one-house experimental proof before neighborhood-scale use. No AHJ setbacks, panel placement, or production approval.

## Processing

- Acquire matching RGB, DSM and mask bytes from one Solar Data Layers response. Fresh acquisitions also use Building Insights; the one-house upgrade reuses existing Insights.
- Keep downloads server-side and user/dataset/parcel scoped. RGB shares existing cache expiry. Algorithm reruns never trigger acquisition when fresh source bytes exist.
- Crop RGB using its CRS and geotransform into the raw model's local projected meter frame. Display a north-up PNG at matching bounds, with attribution. Georeferencing is not independent registration validation.
- Generate a shared line arrangement from dominant building directions, simplified source boundaries and neighboring plane intersections. Assign arrangement cells using raw plane support and DSM residuals. Preserve holes and separate structures.
- Image contrast can adjust proposed lines only within a bounded search and only while plane-height consistency remains acceptable. Contrast is not semantic roof-edge detection: shadows and tile patterns remain limitations.
- Report coverage, outline intersection-over-union, height residual, overlap, outline displacement and photo contrast support. Numeric checks are development diagnostics, not validated acceptance criteria. Every result remains design_ready=false.

## Unmodeled regions (fit-3)

A face never claims pixels its own plane does not explain. After cells are assigned, each face is checked against the DSM: connected areas of at least 0.5 m2 that sit more than 0.35 m off the face's plane (after ignoring seam-width noise) are cut out and reported in `unmodeled_regions`, each with its area, mean and maximum residual, and a kind: `raised` (at least 0.5 m above the plane), `recessed` (at least 0.5 m below) or `uneven`. They count against `coverage_fraction`, and `height_rmse_m` is measured over the faces as emitted. If more than 40% of a face would be cut, nothing is cut and the height error stays visible instead.

This is not classification. A raised region can be a roof section, a chimney or a tree; a recessed one can be a hip or valley the plane does not cover. Vents and similar objects under about 0.5 m are not visible in a 10 cm DSM and are not detected.

## Cost and failure handling

One authorized Data Layers request was used for the sample upgrade; no new Building Insights requests. No retry loop. Optional RGB failure retains acquired DSM/mask inputs. All later fitting checks run on saved bytes. Original sample expiry remains unchanged.

Image dates can differ between Insights and raster layers. That discrepancy remains visible. A clean-looking polygon is not evidence of accurate roof geometry. Failed height checks must remain visible.

## UI

House record → Roof reconstruction → Fitted roof. Show photo toggles imagery; Raw overlay compares original raster geometry. Raw and prior refined geometry remain available for comparison. Validation details are collapsed by default.

## Verification — 2026-10-15

Backend full suite: 226 passed. Added unresolved-plane regression afterwards: six fitter tests passed. Frontend interaction/queue suite: 22 passed. TypeScript/production build passed. Browser verified fitted-tab default, actual photo alignment, raw overlay, geometry-only view, and visible numeric failure details.

Cached sample: 7 fitted groups, 846 source exterior vertices to 178 fitted exterior vertices; 97.417% source-outline coverage, 0.95467 outline IoU, zero face overlaps, 0.4416 m outer-outline Hausdorff displacement. Height all-point RMSE 0.51684 m fails 0.35 m development threshold; median absolute residual 0.01262 m and p90 0.63677 m. One source plane (plane-7) remains unrepresented and is explicitly flagged. Automated checks fail; every result remains not design-ready.

Photo evidence was evaluated, but no bounded photo-driven line shift met current acceptance criteria in final sample. Contrast at proposed edges is 62.1%, a gradient statistic rather than an accuracy score. Outer geometry fitting remains driven primarily by mask, planes, and height data. Photo-guided semantic edge detection and accurate complex junction recovery have not been demonstrated.

One acquisition: one Data Layers request, zero Building Insights requests; later recomputations explicitly blocked network acquisition. Existing source timestamp and expiry preserved. Local raw/refine/fit/photo/cache update took about 0.31 seconds, excluding network and UI; this is not a mass-processing benchmark or a total-cost estimate.
