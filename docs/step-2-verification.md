# Step 2 verification

Verified October 13, 2026, against the local imported dataset and public boundary sources.

## Result

- Backend integration suite: 27 passed in the isolated test database. One upstream Starlette/httpx deprecation warning remains.
- Production frontend: TypeScript and Vite build passed.
- Registry: all 28 supplied AHJs retained as draft; all 27 supported public boundary features load. Twelve invalid source polygons repaired in memory; originals and hashes preserved.
- Real review: CASA ENCANTADORA + PALO VIENTO 1, one exclusion, 109 included parcels, two samples. All 109 Scottsdale matches provisional; no unresolved AHJs in this fixture. PALO VIENTO coverage and broad construction-year notices retained.
- Point lookup: Scottsdale parcel maps to county subdivision 177705. Gila Bend parcel maps local MCR 8150 to county key 08150. Gila Bend county outline resolves 88 residential parcels.
- Confirmation: repeated idempotency key returns one saved record; reload preserves exact review and source hashes. Browser-confirmed record: c8462462-5c64-491b-a97a-54091bbdbda2.

## Browser checks

- Full-window map, compact floating search panel, bottom review bar. Panel reduced from 440px to 360px after user feedback; supporting text 14px and search input 16px. Notices collapsed by neighborhood.
- Native map click previews PALO VIENTO 1; included count stays 109 and duplicate Add is disabled.
- Searching GILA BEND ESTATES previews before Add. Add raises total to 197; removal restores 109 and preserves the original exclusion.
- Warning badge popup lists all affected neighborhood notices.
- Native home click changes sample count once; second click restores the sample.
- Hide/show panel works. Fixed missing desktop stacking order that blocked its reopen button.
- AHJ adjustment expands, manual selection remains provisional, and clearing override returns to geographic match. Fixed a deferred React event-target read that crashed the disclosure.
- Browser confirmation saves and reopens a frozen selection; review fields disabled, Edit as draft offered.
- 390 × 844 viewport: no horizontal page overflow; compact panel scrolls, hidden panel reveals map, confirmation sheet and bottom controls remain usable. Temporary viewport override reset.

## Material limits

Registry is a supplied D1 snapshot, not a live connection. Geographic matching does not verify permit authority. County-unincorporated, missing, and ambiguous boundary matches stay unresolved unless manually assigned; manual matches stay provisional. Construction-year spread is a heuristic, not a roof or development-phase assessment. Source record and GIS coverage gaps remain explicit. Confirmation creates no design jobs and approves no design rules.

Evidence: live checks (private local verification output; excluded from public repository), [AHJ provenance](ahj-sources.md).
