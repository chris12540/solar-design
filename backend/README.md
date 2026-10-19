# Backend

Python 3.11+ FastAPI API and streaming PostgreSQL importer. Install `requirements.txt`, set `DATABASE_URL`, `STAFF_TOKEN`, and `SESSION_SECRET`, then run from the project root:

```sh
uvicorn backend.app:app --host 127.0.0.1 --port 8000
python -m backend.import_data --data-dir /path/to/Data
python scripts/import_step3_facts.py --data-dir /path/to/Data --dataset-id DATASET_ID
```

The importer autodetects strict UTF-8 or Windows-1252 per file. Use `--encoding utf-8` or `--encoding cp1252` to force one encoding. Set `--snapshot-date YYYY-MM-DD` only when the source snapshot date is known; it remains null otherwise. Files, strict encodings, snapshot date, and importer transform version define the dataset identity. Identical inputs are a no-op even if a newer dataset is currently active; bump the importer transform version when parsing rules change. A temporary PostgreSQL staging table is loaded with COPY, validation/reject accounting and active dataset promotion occur in one transaction, and re-importing an identical file set is a no-op. Progress is printed every 100,000 input rows. Rejected rows store only filename, line, and reason.

The optional Step 3 fact importer reads the original files again and requires exact filename and SHA-256 matches with the selected dataset. It stores only sale date, assessor FCV, unit count, PUC, property type, construction year, and exact source row identity in separate tables; it does not change the parcel dataset or its identity. Invalid or negative numeric facts and malformed dates remain null. The initial recent-sale window is 180 days and can be disabled with zero. PUC, existing-solar, and do-not-mail checks remain in review until verified sources are configured.

Set `ALLOWED_ORIGINS` to a comma-separated list of UI/API origins in development. Set `COOKIE_SECURE=1` behind HTTPS. The default staff token and session secret are for local development only; configure both before use. Parcel geometry is deferred. JSON geometry in saved selections is validated with Shapely; county bounds are coarse validation and do not prove county membership.
