# Solar Designer — Neighborhood selection, confirmation and filtering

Local staff workspace to find residential homes on a map, adjust the selection, choose a future design sample, save a named draft, confirm a neighborhood and jurisdiction snapshot, and review local filters before designing. No design jobs, usage estimates, paid enrichment, or mailing run in these steps.

## What works

- Click-first full-window map: anchored preview/Add popups, compact selection/draw tools, on-demand search and selected-set drawer.
- Click or search a recorded subdivision to preview its outline, then explicitly add it. Click again, away, X or Escape to dismiss. Select houses through an added-neighborhood menu.
- Neighborhood outline and parcel colors show highest severity, with permanent geographic text labels. All notices available inside neighborhood details; no issue-count icons.
- Review included homes, construction years, coverage, and parcel-level AHJ matches; override individual assignments when needed.
- Confirm and reopen an immutable snapshot with source hashes; edit a copy as a new draft. Confirmation is not design approval.

- Search local addresses/APNs and recorded subdivision names; choose an exact result.
- Locate a home and its subdivision, or select the home alone.
- County subdivision outlines, with clearly labeled parcel-union estimates when a boundary is unavailable.
- Combine areas, draw a custom boundary, redraw an existing outline, exclude/restore homes, and choose one home, several sample homes, or the full group.
- Residential classification only; no occupancy/age/roof eligibility filters.
- Persistent immutable selections, retry-safe saving, recent runs, and source/coverage warnings.
- Versioned county geometry cache, PostGIS spatial membership, and bounded ArcGIS queries. No per-address geocoder.

Step 3 adds local occupancy/sale filters, optional construction-year and assessor-FCV limits, live deduplicated removal counts, per-home reasons, and separately saved immutable filter reports. Missing enabled checks remain **needs review**, not cleared. Condo/multifamily mapping, existing solar, and do-not-mail sources remain unconnected. Roof/lot area and kW controls are unavailable until sourced measurements exist.

Optional source facts were imported separately for all 1,759,895 retained rows, using original file hashes and source-row identity. No owner or mailing fields added; the original two malformed rows remain quarantined. Repeat imports are no-ops.

Local Secured Master import contains 1,759,895 records, including 1,475,249 residential records. Two malformed rows were quarantined. Raw county files remain unchanged and ignored by Git. Owner names and mailing addresses are neither stored in the application parcel table nor returned to the browser.

## Start

```sh
cd solar-design
python3 scripts/local_db.py start
.venv/bin/python scripts/dev.py
```

Open http://127.0.0.1:5173. Sign in with `STAFF_TOKEN` from your private `.env`. Ctrl-C stops the API and UI. Database uses its own cluster on `127.0.0.1:55432`; stop it with `python3 scripts/local_db.py stop`.

## Fresh setup

Requires Python 3.11+, Node.js 22.12+, PostgreSQL 17 and PostGIS. Native macOS setup:

```sh
brew install postgresql@17 postgis
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm --prefix frontend ci
python3 scripts/local_db.py start
.venv/bin/python scripts/import_data.py
.venv/bin/python scripts/dev.py
```

Put `Secured_Master_BK*.txt` in `Data/` before import. Add `--snapshot-date YYYY-MM-DD` only when the authoritative source date is known. Importer v3 preserves property classification and source PUC codes. Repeat imports are no-ops; failed imports leave the last good active dataset intact. Earlier dataset versions and saved runs are retained.

`compose.yaml` provides PostgreSQL/PostGIS as a Docker alternative. Configure its password and matching `DATABASE_URL`; use either Docker or the native database on port 55432. API startup applies additive migrations. A database administrator must permit creation of the PostGIS extension on fresh installations. Never publish `.env` or raw `Data/`.

## Verify

```sh
.venv/bin/python scripts/check_backend.py
npm --prefix frontend run build
node --test frontend/src/mapPresentation.test.mjs
```

Integration checks use separate `solar_designer_test` database and reset only test data. Real county checks can be run with `.venv/bin/python scripts/check_live_map.py`; these populate private area snapshots and county caches without creating design jobs. See [Step 1 verification](docs/map-verification.md) and [Step 2 verification](docs/step-2-verification.md). The Step 2 live check is `.venv/bin/python scripts/check_step2_live.py`; it creates a named private confirmation fixture.

## Step 3 fact refresh

After the original dataset is imported and migrations applied, import optional sale/value facts for that existing dataset ID (available from the authenticated status endpoint). The wrapper reads private local configuration:

```sh
.venv/bin/python scripts/import_step3_facts.py --data-dir Data --dataset-id DATASET_ID
```

Changed raw files must be imported as a new original dataset first; source hash mismatches are rejected. Do not substitute today's date for an unknown snapshot date. Real Step 3 API checks: `.venv/bin/python -m scripts.check_step3_live` (creates one private saved-report fixture).

## Limits

- AHJ registry is the supplied 28-row D1 snapshot, not a live D1 connection. All entries remain draft/provisional.
- Public boundaries support 24 municipalities and three tribal areas. County-unincorporated territory is not inferred by elimination; unmatched or ambiguous assignments remain unresolved. Manual assignments also remain provisional. See [AHJ sources](docs/ahj-sources.md).
- Construction-year spread is a labeled heuristic; it does not assess roofs or establish development phases.

- Maricopa County and recorded subdivisions only. Informal neighborhood names and citywide boundaries are not inferred.
- Initial limits: 20 areas and 2,000 residential parcels per draft; user-drawn geometry at most 100 km² and 10,000 vertices. Oversized requests fail explicitly.
- County GIS and local records can disagree or omit geometry. Coverage warnings persist with the selection; incomplete counts are not presented as complete.
- Source snapshot date is unknown. GIS fetch time and local import time are separate timestamps.
- Cached geometry is reused; automatic scheduled refresh is not implemented. Data refresh and GIS cache management must be deliberate before production use.
- Boundary editing redraws a replacement outline; original geometry/provenance remains saved. Vertex drag editing is not implemented.
- Overlapping parcel IDs count once. Separate APNs sharing an address remain separate records; source data does not prove separate physical homes.
- Legacy runs remain accessible as references; they lack resolved neighborhood membership.
- Live basemap tiles require internet. OSM tiles are for interactive viewing; no bulk/offline download.
- Local login uses one admin identity. Individual accounts and production hosting are Later.

[Plan](docs/step-1-plan.md) · [Map API contract](docs/map-api-contract.md) · [Classification](docs/classification.md)

[Step 2 plan](docs/step-2-plan.md) · [Step 2 API contract](docs/step-2-contract.md)

[Click-first verification](docs/click-first-verification.md) · [Step 3 plan](docs/step-3-plan.md) · [Step 3 verification](docs/step-3-verification.md) · [Morning questions](docs/questions-for-morning.md)


### Step 3 source setup (October 14)

Filters now keep rentals and recent sales, use detached-home classifications, and separate unchecked Google data from exclusions. Rental flags use local assessor data. Optional checks support year, FCV, county parcel area, Google roof area and potential capacity.

Google Solar requires your own enabled project and server-only key: [setup instructions](docs/google-solar-setup.md). Preview and saved-report reads never trigger paid requests. Google-backed reports expire within 30 days; local-only reports remain frozen.

## Roof research and public repository scope

[Roof experiments](experiments/roof-vision/README.md) contain isolated image/height reconstruction trials and tests. Current fusion work is experimental and is not integrated into the app's production roof pipeline. The five-roof trial has no acquired comparison data yet.

The public repository excludes credentials, private assessor inputs, local databases, property-specific outputs, cached Solar imagery/responses, and model binaries. Public AHJ jurisdiction seed data is included under `backend/data/`. Existing private data must be supplied locally before imports and real-house research runs.
