# Step 1 plan: Find and save homes on a map

Status: implemented locally October 12, 2026 after product walkthrough. Revised map selection replaces the earlier address-confirmation-only experience. See [map verification](map-verification.md) for evidence and limits. Cloud deployment and designs have not started.

## Decision

Keep useful foundations. Rebuild the selection experience around a map: search an address or neighborhood, see the matching area and residential parcels, adjust the selection, and save a named draft. Support a single home, a chosen sample, or a whole group as selection intent. Step 1 performs no designs and incurs no design-provider charges.

Initial coverage is Maricopa County, Arizona. Phoenix was an example of search-and-outline behavior, not a requirement for citywide campaign selection. Other counties and city-boundary search are outside this slice.

## Agreed behavior

1. Search by address or neighborhood name, or draw a custom area. Ambiguous results require choosing a match before highlighting its area. Address search locates the home and outlines its recorded subdivision when available.
2. Use county subdivision boundaries first. When unavailable, construct an editable estimated outline from known matching parcel polygons. Label county, estimated, and user-drawn boundaries distinctly.
3. Display residential parcels and their count. Begin with all residential properties in the selected area; do not apply occupancy, age, usage, or roof eligibility filters.
4. Add adjacent neighborhoods to the selection. Remove a neighborhood or individual home. Deduplicate parcels shared by multiple areas.
5. Allow selecting one home, several sample homes, or the whole area for future designs. Keep full area membership separate from the chosen sample.
6. Save a named draft and reopen it through its URL or a recent-runs list. Preserve areas, geometry provenance, exclusions, selected sample, parcel membership, and dataset versions.
7. Searches, edits, and saving never start designs. Test output and a Run designs action belong to later work.

## Selection rules

- Selected parcel IDs determine which properties belong to a run. Displayed outline is a visual aid, not permission to fill gaps between combined neighborhoods.
- County boundary selects residential parcels by a documented representative-point containment rule, including points on the boundary. Same-MCR membership supplies the estimated-boundary fallback when county geometry is missing. Show discrepancies between these sources rather than silently broadening an area.
- Drawing or editing an area recomputes membership and count. Individual removals remain explicit exclusions. Removing an area removes its contribution; parcels contributed by another selected area remain.
- Estimated outlines use unions of available matching parcel polygons. Preserve gaps, holes, and disconnected pieces; do not use a convex hull that includes unrelated land. Support Polygon and MultiPolygon.
- Never invent coordinates. Show unresolved/missing geometry counts separately from confirmed mapped homes. Incomplete GIS coverage must be visible and saved with the run; do not present a partial count as complete.
- A recorded subdivision can be a replat of one lot. Keep exact county names and keys, show candidates, and let users combine areas. Do not guess an informal neighborhood boundary from its name.
- Residential classification is the only initial property-type restriction. Preserve `PropertyType` and `PUC`, document their mapping, and report unknown classifications separately. Keep residential units distinct even if parcel polygons overlap.

## Verified data path

Local source: `Data/Secured_Master_BK100.txt` through `Secured_Master_BK500.txt`. Existing import contains 1,759,895 records; two malformed input rows were quarantined. Source snapshot date is unknown. Files have addresses, `FolioKey`, `MCR_Key`, `MCR_Name`, `PropertyType`, and `PUC`, but no coordinates or polygons.

Read-only county GIS checks on October 12, 2026:

| Check | Result |
|---|---|
| Parcel identity | Four local `FolioKey` values matched county `APN`, including a letter suffix |
| Coordinates and polygons | APNs `17707116`, `17704342L`, `23306121`, and `40361130` each returned latitude, longitude, and polygon geometry in WGS84 |
| Subdivision key | Local `177705` matched GIS `mcrnum_secured=177705`; point containment returned the same subdivision |
| Second subdivision key | Local `108336` matched GIS `mcrnum_secured=108336` |
| Missing boundary | Local `8150` returned no exact subdivision match; this is a real fallback case, not proof that no other county boundary exists |
| Service paging | Both layers advertise pagination and a 1,000-record response limit |

County endpoints:

- [Parcel layer](https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0): `APN`, `LATITUDE`, `LONGITUDE`, parcel geometry.
- [Subdivision layer](https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Subdivisions/MapServer/0): `mcrnum_secured`, `mcrnum`, `subname`, subdivision geometry.

Browser/web retrieval returned HTTP 403; direct Python HTTPS requests succeeded. This verifies a programmatic path, not service availability guarantees or countywide match rates. Request only required public fields; do not fetch owner or mailing fields.

## Required work, in order

### 1. Prepare map data and selection contract

- Extend the importer to preserve property classification; existing parcel table drops `PropertyType` and `PUC`.
- Add versioned county geometry storage and indexes. Retain local PostgreSQL/FastAPI/React stack. Use PostGIS for spatial membership and geometry operations; current native database does not yet use it.
- Cache subdivision names/keys and boundaries for search. Fetch parcel geometry for selected areas in bounded, paginated batches, joining through county-qualified APN. Cache results; do not geocode every address or request geometry one home at a time during searches.
- Measure joins across representative residential subdivisions, replats, missing-boundary groups, and overlapping unit parcels. Report match coverage, duplicates, invalid geometry, and changed county records.
- Settle membership, exclusions, sampling, and snapshot contracts before parallel implementation. Existing API contract describes the prototype only.

Pass condition: address-to-parcel and MCR-to-boundary joins work on documented samples; missing geometry and missing boundaries remain explicit; classification mapping is documented.

### 2. Build map discovery and area editing

- One search accepts addresses or subdivision names. Show named candidates when ambiguous.
- Fit map to chosen area; render subdivision outline and parcel shapes with home selection states.
- Add/remove areas, draw/edit custom geometry, and remove individual homes. Show total selected residential parcels and unresolved records.
- Keep county boundary and editable working boundary separate so edits retain provenance.
- Handle no match, no MCR, missing geometry, empty residential selection, provider outage, and truncated results. Never silently use a Phoenix-centered fallback as a matched location.

Pass condition: user can search, see and adjust the actual selection, combine neighboring areas, and understand coverage limits without triggering designs.

### 3. Support individual, sample, and whole-group intent

- A standalone address can save a one-home selection without requiring subdivision membership.
- Clicking homes can select a sample from the group. Clearly distinguish included homes from homes chosen for testing.
- Preserve full group when sample changes. No design engine, fake output, or disabled design workflow is required for this slice.

Pass condition: the same draft can represent a single home, a sample, or all homes, with unambiguous counts and membership.

### 4. Save and reopen selections

- Extend run persistence beyond one parcel/MCR reference. Store explicit parcel IDs, area sources and geometries, exclusions, sample IDs, source versions, and coverage status.
- Add recent-runs list scoped to the authenticated staff identity. Reopen exact saved selection after reload or restart; editing must not alter another saved snapshot silently.
- Retain existing authentication, retry-safe creation, authorization, and importer rollback protections. Do not require an address for neighborhood-only or drawn-area drafts.

Pass condition: named selection reopens with matching membership, map, sample, and counts; retries create one run.

### 5. Verify and deliver

- Focused backend checks: classification, geometry joins, pagination, overlaps, point-on-edge membership, deduplication, exclusions, sampling, persistence, and unavailable sources.
- Browser walkthrough: address, named subdivision, drawn area, adjacent combination, individual removal, sample selection, and recent-run reopen; include small-screen view.
- Use real county samples alongside fixtures. Report measured coverage and search timings, not assumed performance.

Pass condition: agreed flow works locally and limitations are visible. Update API contract, README, and verification notes to match implementation.

## Keep versus change

See [prototype comparison](step-1-gap-review.md) for code evidence. Keep imported local data, indexed address search, authentication, run persistence patterns, map library, and launch scripts. Replace address-first confirmation layout and single-reference selection model. No wholesale restart is needed.

## Material risks and tradeoffs

- Informal neighborhoods and recorded subdivisions differ; explicit choices and area combination are required.
- Local source and live GIS may describe different dates. Save each source version and report unmatched parcels. Source snapshot date remains unknown.
- Geometry union may produce disconnected pieces or holes; UI and persistence must support them.
- GIS outages and paging affect completeness. Cached results and visible coverage state prevent silent undercounts.
- Geometry storage and PostGIS add setup work, but avoid paid per-address geocoding and support reliable selection queries.

## Later

- Eligibility filters beyond residential classification and explicit manual selection.
- Estimated usage, 100% default annual usage offset, Aurora comparison, roof layout, production, and design warnings.
- Single-home/sample design execution, batch execution, and reuse of successful sample designs.
- Homeowner bill corrections, QR signup, quotes, postcards, AHJ rules, and production hosting.

## Reference

[Light design stories](https://claude.ai/artifact/VbehsqLsRA6ExpPyLQ9J1c#4f0272d7-e721). This revised scope includes map membership and recent runs that the earlier prototype deferred. It does not claim that the Claude artifact has been edited.
