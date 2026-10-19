# Roof reconstruction validation

Decision: implement one-house automated geometry reconstruction before panel placement. This is an experimental validation path, not an approved solar design engine.

## Required slice

- Explicit one-house action in the house sheet. Reads, opening a sheet, and changing houses never start Google requests.
- Fetch Building Insights plane measurements plus HIGH-quality Data Layers DSM and roof mask. No Google suggested panel layouts are reused.
- Validate building center against selected parcel. Bound radius, raster size, plane count, output size, downloads, and duplicate concurrent requests.
- Align raster grids, select the near-center building component within parcel, assign height pixels to candidate planes, fit conservatively, and emit local-meter polygons with preserved holes.
- Propose raised residual regions as obstruction candidates. Missing heights, unmatched pixels, imagery-date differences, and unvalidated geometry stay explicit.
- All output has design_ready=false. No AHJ setbacks, no panel placement, no claim of complete obstruction detection or measured dimensional accuracy.
- Store source inputs and derived working geometry under the same user/dataset/parcel identity and original expiry, at most 30 days. Reuse fresh sources when algorithm changes without extending expiry. Expired rows are inaccessible and removed on application startup/hourly cleanup. Production lifecycle enforcement must also cover periods when application is stopped.
- Use a standalone local roof diagram, never overlay Google roof results on the existing OpenStreetMap basemap.

## Validation

Synthetic roofs test orientation, adjacent planes, bounding-box assignment guards, holes, missing heights, obstruction proposals, malformed inputs, and resource bounds. Isolated database tests cover creator/membership authorization, explicit-only acquisition, cached reuse, no expiry extension, stale-data purge, and concurrent duplicate-call rejection. Browser checks cover a real-house result, cached reopening, and changing houses without stale results.

Real-data evaluation must distinguish plane-fit residual from true geometric accuracy. Assigned-pixel percentage is not a confidence score. A comparison set with independent roof measurements/designs is needed before automatic design approval.

## Later

RGB-based edge refinement and obstruction detection; connected edge topology with ridge/hip/valley classification; verified AHJ rule application and access paths; panel packing and production; automated acceptance thresholds validated against independent references; neighborhood design queues; production object storage/lifecycle configuration.
