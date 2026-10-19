# Step 2 shared contract

Required scope: full-window Leaflet map; floating compact left panel; floating bottom confirmation bar. Click map in neighborhood mode to preview an outline, then explicit Add neighborhood. Preview does not change current group or saved draft. Separate neighborhood/home/draw modes prevent conflicting clicks. 16–18px body/control text retained.

Existing map API and legacy runs remain supported. All new endpoints authenticated; mutation Origin validation unchanged. No design jobs, paid APIs, D1 writes, or rule approvals. Registry uses 28 AHJs supplied by user, all draft and boundary_ref null. Boundary sources and jurisdiction assignment confidence stay separate from registry status.

## Endpoints

- `GET /api/neighborhoods/at?lat=...&lng=...` -> `{matches:[{mcr_key,mcr_name,geometry:Geometry|null,boundary_source:"county"|"estimated",parcel_count:number|null}],warnings:string[]}`. Bounded point query against county subdivision layer; cached spatial lookup allowed, distinguish outage from no match. Overlapping boundaries return candidates, never silently choose. One match UI previews by resolving subdivision Area; multiple matches chooser. Address/name search also preview first; standalone Home only can resolve parcel.
- `GET /api/ahjs` -> `{ahjs:[{id,name,ahj_type,county,state,boundary_ref,status}],source:"user_provided_d1_snapshot"}`.
- `POST /api/neighborhoods/review` body `{selection:Selection,ahj_overrides?:{[parcel_id]:ahj_id}}` -> Review below. Selection is existing `{mode:"areas",area_ids,excluded_ids,sample_ids,intent}`. Server loads staff-owned immutable snapshots; validates membership/exclusions/samples and override keys.
- `POST /api/runs/confirm` body `{name,original_address?:string,selection:Selection,ahj_overrides?:{[parcel_id]:ahj_id}}`, `Idempotency-Key: UUID` -> Run with `status:"confirmed"`, map fields plus `review:Review`. Recompute review server-side in same create transaction, freeze assignments/warnings/source versions. Snapshot selection confirmation is not design-rule approval. Unresolved AHJ or geometry allowed with clearly preserved warnings; no silent success message implying design readiness. Empty included group rejected. Existing `/api/runs` saves ordinary draft; confirmed edits create new draft/snapshot.
- Existing `GET /api/runs/{id}` returns `review` if present in selection payload; recent endpoint status uses saved status.

## Review shape

`{included_count:number,sample_count:number,areas:[AreaSummary],warnings:[Warning],ahj:AHJAssessment,registry_source:string,registry_snapshot_sha256:string|null}`.

`AreaSummary`: `{area_id,label,selected_count,year_min:number|null,year_max:number|null,year_unknown_count:number,boundary_source,warnings:[Warning],ahjs:[{ahj_id,name,count,status}],unresolved_ahj_count:number}`. Area counts after exclusions; overlaps counted once in total, per-area counts may overlap.

`Warning`: `{id,area_id,code,severity:"warning"|"info",message,parcel_ids:string[],anchor:{lat,lng}|null}`. Stable ID derived area+code. Anchor is interior representative point of area's display polygon, not fabricated home coordinates. No geometry => no on-map anchor; visible badge stays on left area row. Warnings for estimated boundary, coverage/unmatched geometry/classification, wide construction-year range (>20 years, explicitly heuristic), recorded replat/single-lot scope (heuristic), unresolved/provisional/mixed AHJs. Never claim a roof issue or actual construction phase based on age/name alone.

`AHJAssessment`: `{assignments:[{parcel_id,ahj_id:string|null,ahj_name:string|null,method:"boundary"|"manual"|"unresolved"|"ambiguous",status:"provisional"|"verified"|"unresolved",source:object,candidates:string[]}],summary:[{ahj_id,name,count,status}],unresolved_count:number}`. Keep draft registry provisional even with authoritative municipal geography; geographic jurisdiction is not proof of permitting-authority verification. All overrides auditable manual assignments, do not update registry status.

## AHJ module interface

AHJ agent owns `backend/ahj.py`, `backend/jurisdictions.py` (if needed), `backend/migrations/005_ahj.sql`, `backend/data/ahj_registry.json`, any jurisdiction boundary artifact, `backend/tests/test_ahj.py`, and `docs/ahj-sources.md`. Backend agent imports `backend.ahj` and calls:

- `ahj.registry(c)` -> registry response above.
- `ahj.assess(c, parcels:list[MapParcel], overrides:dict)` -> AHJAssessment.

AHJ agent discovers and caches official boundaries where source is defensible. No fallback 'not inside city == county' because tribal/federal areas exist. Missing/overlapping/source mismatch => unresolved. No boundary seed may use municipality name alone to create fake geometry. Registry source is local snapshot until D1 access supplied.

## Ownership

Backend agent: `backend/app.py`, `backend/gis.py`, new `backend/neighborhood_review.py`, `backend/migrations/004_confirm.sql`, `backend/tests/test_neighborhood_review.py`; do not edit AHJ/importer or frontend.
UI agent: `frontend/` only. Builds against this contract; requests changes before divergence. Review inline badges/popovers on affected area; show all warnings for each area, not one hidden global notice. Bottom confirmation opens concise review sheet with counts/AHJ/manual assignment/name, then confirms. No automatic confirm/design trigger.
Main: contracts, docs, integration, GIS boundary verification and browser checks. Reviewer: read-only grounded findings. Compact reports, no optional feature work.
