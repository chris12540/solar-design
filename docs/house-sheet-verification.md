# House records and map behavior — 2026-10-15

Implemented shared parcel records, authenticated house inspect/summary APIs, compact desktop inspector and mobile bottom sheet, and explicit map interaction modes.

House records use dataset + parcel identity. Saved review and Solar lookup history is user-scoped metadata. Current Solar content retains existing 30-day expiration; expired content is omitted and prior lookups show refresh needed. Existing saved reviews are backfilled into per-house history. Design remains `not_run` because design generation is not implemented.

Review this house opens the existing review tools with only that parcel included. Saving a scoped review validates its areas and parcels against the saved run, records review scope, and never changes neighborhood membership. Design sample intent does not restrict whole-neighborhood review scope.

Map behavior: initial saved set has no focus; first house click focuses its neighborhood; subsequent click opens that house. Neighborhood background opens its overview. Empty map clears focus without removing membership. Add neighborhoods explicitly enables point lookup; preview uses no auto-pan; click-away cancels preview while staying in Add mode. Search results may fit. Address inspection does not add membership. Sample and draw changes commit only on Done; Cancel restores sample intent/IDs and saved run identity. Native double-click zoom remains unchanged.

Validation:
- Backend: 138 tests passed in isolated PostgreSQL test database. One existing Starlette/httpx deprecation warning.
- Frontend: 22 tests passed; TypeScript and production Vite build passed.
- Live browser: existing saved set reopened unfocused; 110 total house records, 109 reviewed, 109 included homes preserved. Verified group overview, house detail/history, one-house review preview, empty-map dismissal, two-stage map house clicks, sample Cancel preserving saved run URL, and explicit Add-mode preview/click-away without panning.
- Responsive: desktop 1440×900 inspector leaves confirmation bar reachable; mobile 390×844 bottom sheet has no horizontal overflow. Temporary viewport reset.
- API and UI dev servers restarted. No paid Solar checks or design runs invoked during verification. No new production review report saved during browser checks.

Files: `backend/app.py`, migration `008_house_review_history.sql`, backend house API tests, frontend `HouseSheet.tsx`, `houseSheet.css`, `App.tsx`, `FiltersSheet.tsx`, `mapInteraction.ts` and tests, `styles.css`.
