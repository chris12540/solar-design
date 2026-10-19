# Step 3 verification

Verified October 13, 2026. Scope: local filtering and immutable reports; missing-source checks remain explicit.

## Outcome

- Backend integration suite: **41 passed** in isolated test database. One upstream Starlette/httpx deprecation warning remains.
- Frontend: production TypeScript/Vite build and seven severity-policy tests pass.
- Independent reviews covered map request lifecycles, report save/retry and ownership, filtering/counts, importer provenance, and immutable reports. Material findings fixed before handoff.
- Optional fact import published **1,759,895** exact retained parcel rows across five hash-matched source files. Original two quarantined rows skipped. Separate tables; existing parcel dataset and saved neighborhood records retained. Repeat import returns unchanged=true.
- No owner/mailing fields imported; no paid enrichment, designs, usage, quotes, mail, D1 changes, or deployment.

## Real data/API checks

Original Scottsdale draft b53ba9a2-102e-4b39-93a3-bfec5c9ebf2f: 110 source members, one manual exclusion, 109 filter inputs, two selected samples.

Defaults: **33 excluded, 76 need review, 0 pass all selected checks**. Owner-occupancy heuristic matched 32; recent sale matched two with one additional exclusion. Distinct per-step removals sum to 33. Missing condo/multifamily, existing-solar, and do-not-mail evidence stays unknown; remaining homes are not labeled eligible.

Optional construction year >=2000 plus minimum assessor FCV $1,000,000 raises exclusions to 98, with 11 held. Numeric threshold exclusion messages verified with real facts after fixing a format-specifier failure; parameterized regressions cover below/equal/missing values for all numeric thresholds.

Report retries return same ID; report GET matches saved JSON; original run remains unchanged. Internal evaluation date uses America/Phoenix. Source snapshot date remains unknown and warning persists in reports.

- API report: a1ea2a6f-3d17-4e9c-b4f4-5e0f1a7f143d.
- Browser-saved optional-filter report: 547f6bf6-d916-4a0a-99f5-5e32596c5949.
- Evidence: step-3-fact-import.json, step-3-live-checks.json.

## Browser checks

- Live default counts match API; year/value changes update counts and save gating.
- Save filter review opens readonly saved result. Close/reopen retrieves report picker and stored report; explicit Edit filters recalculates.
- Counts remain visible while editing; dropped sample and manual-exclusion context available; per-home reasons and missing checks visible. Home list expands in 40-row batches.
- 390x844 viewport: no horizontal overflow, readable controls, scrollable sheet, visible counts/footer. Temporary viewport reset.
- Cross-step regression: preview/unclick/click-away/Escape, explicit Add, removal, map sample toggling, drawing through existing selected parcels/cancel, and confirmed Edit as draft all verified. See click-first-verification.md.

## Remaining inputs

No verified condo/multifamily PUC mapping, existing-solar feed, or do-not-mail list. Roof area, lot area, and system kW controls remain unavailable. Assessor FCV is not market value; occupancy is a heuristic. Recent-sale default 180 days awaits user review. No per-home rule override (Next story). See questions-for-morning.md and step-3-data-sources.md.


## October 14 completion pass — eligibility-2

Implemented user answers: recent-sale/owner-occupancy/do-not-mail defaults removed; rentals flagged rather than excluded; documented detached-home classification; explicit Google detected-arrays adapter; pending versus unavailable status; optional year/FCV/lot/roof/potential thresholds; warning hierarchy revised.

Validation:

- 136 backend tests pass against the isolated test database. Covers source parsing, auth, per-home outcomes, concurrent lookup deduplication, 10-request batches, failed lookup retry, expiry, and saved-report JSON serialization with native assessor dates/decimals.
- Eight map presentation tests pass. Production build passes.
- Full fact import version 2: 1,759,895 records; 244,867 Y rental flags and 1,515,028 N flags; two known rejected input rows stay excluded. Source manifest a710330be1b0d50a3da21c6216112ce4e4395cd4cc9d9ee655f6eaf8fa7bee94.
- Real 109-home selection: 0 exclusions, 0 needs review, 109 solar checks pending. Year >=2000 plus FCV >=1,000,000 excludes 97. Frozen report save/reload/idempotent retry passes; original run unchanged. Latest report ID in step-3-live-checks.json.
- Browser: toggling solar exclusion off yields 109 passes of selected local checks; restoring it yields 109 not checked. Browser saves eligibility-2 report successfully. Map shows ten raw-rental outlines in this saved example; rentals remain selected.
- Responsive 390×844 check: document and sheet widths 390; no horizontal overflow. Viewport reset after checking.

Live dependency: user has no Google Cloud project yet. Adapter verified using synthetic responses only; no paid requests made. App visibly disables Solar lookup until configured. Follow google-solar-setup.md to connect, then perform first live test.

Classification limitation: assessor single-family codes are a detached-home proxy, not independent shared-wall verification. Additional-dwelling/ambiguous codes stay in review. Assessor source snapshot date remains unknown. These limitations are visible rather than silently clearing missing data.

Google-derived data stays in the filter sheet, not the non-Google map. Its cache and reports expire within 30 days. Historical local-only reports remain unchanged.


## October 14: Google connection verified live

User added server key locally. One real Google Solar lookup succeeded for a home in the saved test neighborhood. Building matched intended parcel; array detection, capture date, roof area, and potential capacity parsed successfully. Existing-solar exclusion applied. Repeated lookup reused cache with zero additional Google requests. Original saved selection remained unchanged. Development servers restarted to load the new key. No designs or neighborhood-wide paid batch started.

Earlier notes that live Google setup is missing are historical; connection is now verified. Broad coverage and imagery freshness remain per-home source limitations.
