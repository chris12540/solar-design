# Map selection verification

Verified locally October 12, 2026. No cloud deployment or design jobs.

## Outcome

Revised Step 1 is implemented locally. Three Luna agents handled backend/GIS, UI, and classification; a Sol agent independently reviewed correctness and authorization. Main agent integrated source, imported data, checked real GIS, and walked the browser flow. A recoverable pre-map source copy remains at `/private/tmp/solar-step1-before-map`.

## Automated checks

- Backend: **14 passed**, including legacy import/auth/persistence, classification fidelity, county geometry and holes, disconnected polygons, boundary membership, GIS paging, missing geometry, overlap deduplication, exclusions, single/sample/all intent, saved coverage, idempotency, creator scope, and edit provenance. One existing Starlette TestClient/httpx deprecation warning remains.
- Integrated frontend TypeScript and Vite production build passed.
- Input validation rejects nonfinite or 3D coordinates with 422; polygon area limits preserve gaps between disconnected pieces.

## Real county checks

Local importer v3 promoted 1,759,895 records, with 2 malformed rows quarantined. Residential source count: 1,475,249. Source date remains unknown. All original files and earlier dataset versions remain available.

| Sample | Boundary | Mapped residential records | Unresolved records | Warm seconds |
|---|---|---:|---:|---:|
| CASA ENCANTADORA | County | 5 | 0 | 0.031 |
| PALO VIENTO 1 | County | 105 | 1 | 0.869 |
| PASEO VILLAGE 2ND REPLAT | County | 70 | 0 | 0.824 |
| GILA BEND ESTATES | Estimated parcel union | 88 | 0 | 0.390 |
| FIESTA CASITAS CONDOMINIUMS | County | 46 | 0 | 0.760 |

These are sample join/geometry results, not countywide completeness or speed guarantees. See warm report (private local verification output; excluded from public repository). Initial cold measurements exposed an unindexed upper(APN) join; a matching functional index was added. Earlier timings are retained in cold report (private local verification output; excluded from public repository), but are not current performance baselines.

Standalone APN 17707116 resolved exactly one home and its geometry. Public GIS requests used only required property/geometry fields, without owner or mailing data. Cached source timestamps persist; source refresh remains deliberate rather than automatic.

## Browser walkthrough

- Searched real recorded subdivisions and displayed county outline and home polygons.
- Combined CASA ENCANTADORA and PALO VIENTO 1: 110 homes; excluded one; chose two sample homes. Saved selection retained 109 included homes separately from the two samples and one unresolved source record.
- Reload and a full API/UI restart restored areas, exclusions, sample, counts, and warning. Recent selections showed the saved draft.
- Address search offered area lookup or Home only. Home only returned one residential property and selected single-home intent.
- Redrew a replacement outline around a home; county parcel query returned two included residential homes, with original area provenance retained by the backend.
- Legacy run reopened with an explicit reference-only warning, without inventing neighborhood membership.
- Mobile viewport test: no horizontal overflow (clientWidth and scrollWidth both 375 pixels); viewport reset afterward.

[Saved sample](http://127.0.0.1:5173/runs/b53ba9a2-102e-4b39-93a3-bfec5c9ebf2f). Screenshots are saved in the current Codex visualization directory as `map-selection-desktop.png` and `map-selection-mobile.png`.

## Remaining limits

Residential records are parcels, not guaranteed distinct physical homes. Different APNs at the same situs remain distinct. Recorded subdivisions may be single-lot replats; informal names are not inferred. Coverage is explicit when local data and county geometry disagree. Initial limit is 20 areas / 2,000 residential parcels. Local staff authentication uses one admin account; production access and hosting are outside this slice. Usage estimation, roof designs, and paid services remain Later.
