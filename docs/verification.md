# Step 1 verification — October 12, 2026

## Outcome

Stories 1.1–1.3 run locally against the supplied Secured Master files. No AWS resources or paid enrichment calls were created.

## Data

- Five source files, 39 columns, approximately 485 MB; originals unchanged.
- 1,759,897 input records; 1,759,895 imported; two malformed-width records quarantined from BK500.
- Addressless records remain in the source table; imported count is not a count of searchable street addresses or eligible homes.
- File SHA-256 hashes, strict encoding choice, transform version 2 and source row are recorded. Snapshot date is unknown; file modification/import dates are not substituted.
- Re-importing the same manifest exits without publishing another dataset.
- Direct official county GIS queries matched APNs and situs addresses for 17707116, 17704342L, 23306121 and 40361130. FolioKey is preserved exactly, including suffix letters.
- Official source: https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0/query (read-only APN queries, no owner/mail fields retrieved).

## Checks

- Three PostgreSQL integration tests pass. Each covers multiple related assertions: encoding/import rollback and idempotence; authentication/origin/privacy and address/unit aliases; geometry validation, first-request concurrent retry safety, immutable snapshots and creator isolation.
- Production TypeScript/Vite build passes. Dependency audit reports zero vulnerabilities.
- Browser walkthrough: explicit parcel selection, normalized full address, missing MCR, radius center selection, polygon drawing, save URLs and reload persistence.
- Radius restoration initially crashed because Leaflet circle bounds were queried before attaching a layer. Fixed using LatLng bounds; radius and polygon reload checks then passed.
- Edited address clears old candidates. An unchanged loaded run cannot be submitted as a duplicate. Default Phoenix map center cannot be saved until explicitly chosen.
- Saved subdivision run survived a full API/frontend restart.
- 390-pixel responsive view has 390-pixel content width, with no horizontal overflow.
- Five representative local API lookups measured 5–6 ms; this small warm local sample is not a production performance guarantee.
- Git exclusions verified for raw Data, .env, local database, Python environment and node_modules.

## Runtime

- App: http://127.0.0.1:5173
- API: http://127.0.0.1:8000
- Project PostgreSQL: 127.0.0.1:55432
- Local credentials are generated in .env with restricted file permissions; browser testing's temporary login token is no longer accepted by the final server.
- Source and implementation are uncommitted on codex/step-1. No remote push or deployment.

## Limits

Coordinates/parcel polygons are absent from the source. Fallback map selection is manual. Exact county-boundary membership, neighborhood expansion, eligibility filters and roof design belong to subsequent steps. Local staff login has one admin identity; individual team accounts and production hardening are not implemented. Step 1 validates GeoJSON with Shapely and persists it in PostgreSQL JSONB; PostGIS spatial queries are not needed yet.
