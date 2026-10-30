# Height-data fitting findings

Captured CAD bundle SHA256 065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb
contains BuildingFitLidar component and fitToLidar action; captured roof and roof-plane
inspectors contain Fit to LiDAR buttons/callbacks. Own frontend-ui.js explicitly sets
isLidarAvailable=false and supplies no-op callbacks. Therefore current lab feature is
not connected; presence of controls alone is not a working adapter.

Bounded static observation: exact isolated BuildingFitLidar class reads
this.deps.dataStore.elevation.getPoints(), rejects empty samples, handles grouped roof
sources and separate roof.plane entries, and references L1IRLS fitting helpers. Helper
bodies, complete display/loading pipeline and runtime behavior are not established by
this excerpt. Do not claim unchanged native fitter accepts DSM directly or guarantees
correct roof results. Separate Show LiDAR pathway not fully traced.

Private exact excerpt/provenance: runtime/lidar-analysis/. REA parent
 ev_87bf5b049fa6d778ad114a1581bc82b138f3cf32c4f4d7712b5d66ee20082cd6
summary ev_037f556d610eed22b7775b977803cd7d909c473a62549805c328ea1669c60596.
One parsed JS file, no parse failures; semantic coverage unknown/partial,219 unknowns.
Static evidence only; no engine mutation, data acquisition or native fitting executed.

Google Solar DataLayers supplies dsmUrl: height raster in meters above EGM96 geoid;
-9999 is invalid, maskUrl identifies rooftop pixels. This can support analogous height
visualization and roof fitting after correct XY registration and local height reference,
mask/outlier filtering and valid sample checks. Raster samples are not a raw LiDAR
point cloud; pixel spacing is not a promise of vertical accuracy. Current acquisition
only downloads RGB; no DSM/mask acquired for current lab house.

Primary reference:
https://developers.google.com/maps/documentation/solar/reference/rest/v1/dataLayers

Potential next implementation, only after user requests it: show height surface first;
then selected-roof fit preview/apply with Undo and measured geometry comparison.
Preserve source expiry, separate permanent manual library, current Phoenix-only lookup
and no production reconstruction rewrite. Do not download height data on heartbeat.


## Implemented adapter update — October 30, 2026

Earlier statements that fitting/loading is disconnected are historical. Own DSM/mask
adapter, point overlay and robust preview/apply fitter now run. Both roof and standalone
face controls invoke this adapter; retained vendor fitting implementation is not used.
Cached live imagery/height display and planar patch fit passed. Expanded synthetic tests
cover concave outlines, base roofs with details and independent faces. See current
README/CONTINUE state for limits; no whole-house accuracy claim.
