# Development status

Application: React/TypeScript map UI, FastAPI backend, PostgreSQL/PostGIS storage. Neighborhood selection, house records, saved review reports, Google Solar lookups, and experimental roof inspection are implemented locally. Read the feature-specific docs for limits; historical plans and questions are not all current requirements.

Current roof research is isolated in `experiments/roof-vision/`. RGB-only RoofMapNet linework plus Google plane/DSM fusion is the active experimental direction. Missing boundaries, dormers, height joins, image registration, and obstruction completeness remain unresolved. Clean polygons and numerical consistency are not physical accuracy validation. No design-ready model or AHJ-compliant panel layout has been established. Customer-facing 3D remains deferred.

A five-house comparison is prepared but has no acquired imagery yet: the configured Google API key rejected acquisition with a source-IP restriction. Correct authorized network access before resuming paid calls. Private request ledgers, original imagery, annotations, and outputs stay in their original local workspace; do not reset ledgers to bypass retry limits. No model training or commercial model permission has been established.

Initial repository verification: frontend production build passes; 227 backend tests pass against the isolated test database, 22 frontend behavior tests pass, and five fusion plus five Google-cleanup tests pass. These software checks do not establish roof reconstruction accuracy. No real Solar API calls were made for publication checks.

When sharing or deploying, provision separate credentials and private source data. The public repository includes source code and public AHJ seed data, not a database dump or complete property cache.
