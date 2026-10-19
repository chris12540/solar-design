> Historical gap review before implementation. Revised scope is now implemented locally; see [map verification](map-verification.md).

# Step 1 prototype comparison

Reviewed October 12, 2026 against the revised map-first plan. Static code review plus read-only GIS verification; no application changes or new runtime tests in this planning pass.

## Outcome

Keep foundations; replace selection experience. Existing prototype satisfies its former address-confirmation scope, but does not satisfy the revised Step 1. Previous test results remain evidence for that older implementation only.

| Agreed capability | Current evidence | Required change |
|---|---|---|
| Address search | `backend/app.py` indexed address/APN lookup; `frontend/src/App.tsx` candidate selection | Keep; attach real coordinates, polygons, and area result |
| Neighborhood search | Search SQL uses address/APN only | Add named subdivision search and ambiguous candidates |
| Search outlines area | `parcel_dict` returns null coordinates; MCR map is a Phoenix reference map | County GIS joins, real map bounds, parcel and subdivision rendering |
| Estimated boundary | Radius/polygon saved without resolving homes | Union known matching parcel polygons; retain provenance and incomplete coverage |
| All residential homes/count | Database has neither classification nor geometry; no membership query | Preserve classification, implement spatial membership, count unresolved records |
| Combine adjacent areas | Run selection is one `mcr`, `radius`, or `polygon` | Multiple area contributions, deduplication, individual exclusions |
| Edit outline | Drawing supports add/undo/clear vertices only | Edit selected working boundary and recompute membership |
| Single/sample/full selection | Run stores one parcel snapshot; no sample state | Explicit group membership plus independently chosen sample |
| Named save/reopen | Retry-safe POST and creator-scoped GET exist | Extend snapshots for map selection and source versions |
| Recent runs | Only GET by ID; UI requires pasted run ID | List endpoint and recent-runs interface |
| No automatic designs | No design endpoints or engine | Preserve |

## Reusable code

- `backend/import_data.py`: streaming staging/COPY, encoding checks, hashes, quarantine, atomic promotion, repeat-import handling.
- `backend/app.py`: address normalization, authentication, mutation-origin checks, creator authorization, and idempotent save pattern.
- `backend/migrations/001_init.sql`: datasets, parcels, runs as migration starting point; add migration rather than discard data.
- `frontend/src/App.tsx`: Leaflet integration, address candidates, dataset status, save/load handling; reorganize into map discovery flow.
- Local database/dev scripts and existing security/import tests.

## Contract changes required before coding

Existing `docs/api-contract.md` is accurate for parked prototype. Revised contract must include subdivision search, county geometry provenance, multiple areas, residential membership, unresolved counts, manual exclusions, separate sample IDs, saved selection versions, and recent-run listing. Neighborhood and drawn-area saves must not require `original_address`.

Geometry validation currently permits only a single Polygon without holes and checks a coarse bounding extent. That is insufficient for county boundaries and parcel unions. Add Polygon/MultiPolygon support with valid rings/holes, spatial containment rules, and explicit limits for large selections.

## Verified integration limits

Four tested APNs returned coordinates and polygon geometry. Two tested local subdivision keys matched GIS `mcrnum_secured`; key `8150` did not. A spatial lookup for APN `17707116` confirmed matching subdivision `177705`. Countywide coverage, residential classification mapping, full-area membership, and cache refresh behavior remain implementation checks.

## Next implementation checkpoint

Complete plan section 1: classification retention, county geometry adapter/cache, representative coverage report, and shared selection contract. Then build UI and backend against that contract. No usage or roof-design work belongs in this checkpoint.
