# Step 2: Confirm the neighborhood

Status: implemented and verified October 13, 2026. Required behavior agreed with user. No roof designs, usage estimation, quotes, cloud deployment, or D1 writes.

## Decision

Keep the existing local data, geometry cache, and saved selections. Replace the boxed page layout with a full-window map, a compact floating left panel, and a bottom confirmation bar. Clicking a neighborhood previews its boundary; only Add neighborhood changes the selected group.

## Required work

1. **Map workspace.** Map fills the viewport. Search, selected neighborhoods, and focused tools float above it. Typography remains 16–18px. Home lists, recent runs, and detailed review use drawers/sheets; they do not shrink the map into another card. Mobile controls collapse and preserve space for the map.
2. **Neighborhood discovery.** A county point query finds recorded subdivisions under a clicked map location. One result outlines automatically; overlapping results offer a chooser. Search/address results use the same preview-before-add flow. Neighborhood browsing, home sampling, and boundary drawing have separate interaction modes.
3. **Area warnings.** Badges attach to the affected area's interior map point and its selected-area row. Clicking a badge shows the reason and available affected records. Missing geometry has a row warning instead of fabricated map coordinates. Coverage discrepancies, estimated outlines, construction-year spread, recorded replats, and AHJ uncertainty stay distinct. Age/name signals are review heuristics, not proof of roof conditions or phases.
4. **AHJ assignment.** Seed a local snapshot of the user's 28 D1 AHJ records. All are draft with no boundary reference. Link defensible public jurisdiction boundaries to the same IDs; assign per parcel. Geographic matches remain provisional while registry records are draft. Unmapped or overlapping sources stay unresolved, with manual selection from the registry. Never infer county jurisdiction merely by exclusion from city polygons.
5. **Confirm and persist.** Review included count, samples, construction-year range, warnings, and AHJ summary. Name and confirm an immutable snapshot containing server-computed membership, assignments, overrides, warning provenance, and data versions. Confirmation does not approve design rules or start designs. Unresolved assignments remain explicit after save; empty groups cannot be confirmed.
6. **Verify.** Check point discovery, ambiguity, holes/boundary edges, assignment gaps/overlaps, manual provenance, creator scope, retries, and immutable confirmed snapshots. Browser check full-map layout, preview/add separation, anchored warnings, review/confirm/reopen, and mobile controls.

## Agent ownership

- Backend/GIS agent: point lookup, review/warnings, confirmation endpoints and tests.
- UI agent: full-map layout, previews, warnings, review sheet, and confirmation flow.
- AHJ agent: user registry snapshot, authoritative boundary discovery, per-parcel assignment, provenance and tests.
- Main agent: shared API contract, integration, real-source checks, browser verification, and delivery.
- Independent reviewer: grounded correctness/access/data-loss findings; no optional features.

## Material limits

Recorded subdivisions can be single-lot replats and differ from informal neighborhood names. Boundary coverage and parcel/AHJ data can be incomplete. All supplied AHJs are draft; geographic matching must not be presented as permit-authority or code-rule approval. D1 is not connected yet; its shared records are a labeled snapshot. Source data date remains unknown. Existing 20-area/2,000-parcel draft limits remain.

## Later

Live D1 synchronization after access is available. Roof designs, usage, design rules, AHJ approval workflow, quote/mail/QR signup, and production hosting.

See [shared contract](step-2-contract.md).

Verification: [Step 2 checks](step-2-verification.md).
