> Historical prototype plan. Superseded by [revised Step 1 plan](step-1-plan.md). Implementation claims below refer only to the former scope.

# Step 1 plan: Start from an address

Status: Step 1 implemented and verified locally on October 12, 2026. Cloud deployment has not started. See verification.md for evidence and limits.

## Decision

Build a small, local-first vertical slice: enter an address, confirm its parcel or choose a geographic fallback, then save a named draft run. Use React/TypeScript, FastAPI and PostgreSQL/PostGIS. This keeps the spatial data model compatible with Step 2.

Initial coverage assumption: Maricopa County, Arizona. Other counties require another data adapter. The screen must make coverage clear.

Repository location: `/Users/chris/code/solar-designer`. Git initialized on `codex/step-1`. Application code, local launch scripts and documentation are present. Raw `Data/`, secrets, local database files and dependency/build outputs are ignored.

Verified source: `/Users/chris/code/solar-designer/Data/Secured_Master_BK100.txt` through `Secured_Master_BK500.txt`. Five pipe-delimited files total approximately 485 MB. All five have the same 39-column header; the first five records in each file have 39 fields. Full import validated 1,759,897 input records: 1,759,895 imported, two quarantined for wrong field count. Source snapshot date remains unknown. File modification time is not an authoritative snapshot date.

| Required value | Available source field | Remaining check |
|---|---|---|
| Parcel identity | `FolioKey` | Verified four literal FolioKey values against official county GIS APN/address records, including one letter suffix |
| Property address | `SitusAddress`, `SitusUnitNumber`, `SitusCity`, `SitusPostalCode` | Normalize address and unit without merging distinct units |
| Occupancy evidence | `RentalInd`, `MailingAddress1`, `MailingAddress2`, `MailingCity`, `MailingState`, `MailingPostalCode`, `MailingCountry` | Decode rental values and compare normalized addresses; retain unknown state |
| Year built | `ConstrYear` | Check missing values and invalid/sentinel years |
| Subdivision | `MCR_Key`, `MCR_Name` | Preserve key strings and identify missing/sentinel values |
| Coordinates and parcel geometry | No matching fields in headers | Supplement with county GIS or use manual map selection for fallback |

Other useful available fields include `PropertyType`, `NumUnits`, `LivingArea`, `SaleDate` and `PoolSize`. Preserve source values; eligibility filtering remains outside Step 1.

## Required scope

| Story | Deliverable | Pass condition |
|---|---|---|
| 1.1 | Address entry and parcel confirmation showing address, APN, owner-occupancy indicator, year built and MCR subdivision | A known address resolves correctly; ambiguous matches require a selection; missing fields are shown explicitly |
| 1.2 | Radius or drawn-boundary fallback when the address is absent or MCR is missing | User can choose a center and radius or draw a valid polygon, and save that selection |
| 1.3 | Named, persistent draft run | Run survives an API restart and opens through its saved URL |

Step 1 saves the intended selection. Fetching all neighborhood parcels, counts, AHJ matching and neighborhood editing belong to Step 2. Eligibility exclusions belong to Step 3.

## Checkpoints

### 1. Verify the source and settle the contract

- Inspect the local Secured Master filenames, headers, companion layout documentation and snapshot date. Identify the authoritative address, APN, MCR, year-built, rental and mailing-address fields. Do not assume all required fields exist in this dataset.
- Stream the pipe-delimited files into a staging table, validate them, then publish an indexed parcel lookup table. Preserve the original files. Search the local database at request time; do not scan the text files on each search.
- Track source file, snapshot date, import time, input/imported/rejected row counts and rejection reasons. Make repeat imports idempotent and keep the last good dataset available if a new import fails.
- Use county API or supplementary county downloads only for required fields or geometry missing from Secured Master. Keep source-specific mapping behind one county adapter. Determine whether address coordinates are present before choosing fallback map positioning.
- Test several representative addresses: exact match, alternate formatting, multiple matches, missing MCR and no match. Distinguish an unavailable source from an address that is absent.
- Preserve APN/MCR strings and leading zeros. Namespace parcel identity with county identifier. MCR is a recorded subdivision reference, not a guaranteed complete neighborhood boundary.
- Return owner occupancy as `likely_owner_occupied`, `likely_not_owner_occupied` or `unknown`, with evidence and source date. Address equality is evidence, not proof; missing mailing data must not become a negative result.

Done when: the local import works, representative records match assessor data, and a documented API contract covers all match and failure states. County documentation retrieval returned HTTP 403; supplementary programmatic access remains unverified and is not required if the local dataset supplies the necessary fields.

### 2. Build address confirmation and fallback

- Add address input with explicit search, loading, result selection and retry states.
- Show matched parcel facts and let the user confirm or change the result. Preserve original input alongside normalized address.
- Offer radius and polygon selection when parcel/MCR lookup cannot define a subdivision. A valid parcel without MCR supplies a possible center. If no parcel exists, permit manual center selection; use an optional geocoder only after its provider and cost are settled.
- Validate polygon geometry, positive bounded radius and supported geographic coverage. Configure a permitted basemap for the map picker.
- Keep county/provider credentials server-side. Restrict owner and mailing data to authorized staff; avoid exposing mailing addresses where they are not needed.

Done when: each source outcome leads to a usable confirmation or fallback screen without silently selecting the wrong home.

### 3. Save and reopen a named run

- Require a nonempty run name and confirmed selection.
- Save creator, timestamps, draft status, input address, selected parcel facts, source provenance and selection mode.
- Support three selection modes: `mcr`, `radius` and `polygon`. Store MCR reference, radius center/distance or GeoJSON boundary as appropriate. Radius uses a single canonical distance unit; polygon uses WGS84 coordinates.
- Use a county-qualified parcel ID when present; fallback runs may have no parcel ID or MCR.
- Make run creation idempotent so double-clicks and request retries create one run. Authorize read/write access to each run.
- Return a run URL and reopen the saved input/selection through it. Do not automatically fetch or design the neighborhood.

Done when: reload and restart preserve the run; duplicate submissions and unauthorized access are handled correctly.

### 4. Integrate and verify

- Test address normalization, ambiguous selection, missing values and provider outages using representative fixtures.
- Test radius/polygon validation, persistence, duplicate submissions and staff access enforcement.
- Perform a browser walkthrough for all three stories, including a small-screen view.
- Compare real parcel matches against assessor records and record the source timestamp. Fixtures alone do not prove county integration works.
- Deliver setup instructions, a sample run and a short list of remaining limitations. Keep paid enrichment and mailing outside this slice.

Done when: stories 1.1–1.3 pass with a verified source path. Any blocked external integration is reported explicitly, rather than presented as completed.

## Subagent assignments

Implementation used GPT-6 Luna with medium reasoning for data profiling, backend and frontend work. GPT-6.1 Sol handled independent review; the main agent handled contracts, integration and end-to-end verification.

| Role | Ownership | Sequence |
|---|---|---|
| Data/backend agent | County adapter, field mapping, lookup endpoints, migrations and run persistence | Source discovery first; build after shared contract is fixed |
| UI agent | Address screen, match selection, fallback map and saved-run screen | Build against agreed fixtures/API contract, alongside backend work |
| Review agent | Independent checks of matching, persistence, authorization and story coverage | Review integrated changes; report concrete defects |
| Main agent | Shared contracts, project setup, integration, verification and progress updates | Coordinates work and resolves cross-cutting decisions |

Limit concurrent child agents to three. Give agents separate file ownership. No geometry-design agent is needed for Step 1.

## Material tradeoffs and decisions

- Local Secured Master is the primary lookup source: predictable search and no live county-service dependency for fields present in the files. Snapshot age, field completeness and refresh/import work remain material constraints.
- PostgreSQL/PostGIS adds local setup but supports the spatial selection required here and the neighborhood queries coming next.
- Fallback map selection requires a basemap choice. Automatic geocoding is not assumed to be free or required for saving a manually selected area.
- Start locally. Cloud deployment and paid provider setup need a separate concrete deployment plan; they are not acceptance criteria for this slice.

## Later

- Story 1.4: recent-runs list and dashboard.
- Step 2 neighborhood expansion, parcel counts, multi-MCR merging and AHJ assignment.
- Step 3 eligibility rules and exclusion summaries.
- Roof design, obstruction detection, usage estimates, quotes, postcards and homeowner signup.
- Multi-county coverage and production hosting.

## Reference

[Current Light design stories](https://claude.ai/artifact/VbehsqLsRA6ExpPyLQ9J1c#4f0272d7-e721)

## Implementation notes

Local development uses project-isolated PostgreSQL 17. Geometry is saved as GeoJSON in JSONB and validated with Shapely. PostGIS is included in the optional Docker configuration; Step 1 needs no spatial database queries. The local staff workspace has one admin identity, not individual Cognito accounts. Team authentication and cloud deployment remain outside this local slice.
