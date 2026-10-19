CREATE TABLE IF NOT EXISTS parcel_source_fact_snapshots (
  dataset_id text PRIMARY KEY REFERENCES datasets(id) ON DELETE CASCADE,
  source_files jsonb NOT NULL,
  source_snapshot_date date,
  transform_version integer NOT NULL,
  imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parcel_source_facts (
  dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  parcel_id text NOT NULL,
  source_file text NOT NULL,
  source_row bigint NOT NULL,
  source_sha256 text NOT NULL,
  sale_date date,
  fcv numeric,
  num_units integer,
  puc text,
  property_type text,
  construction_year integer,
  PRIMARY KEY(dataset_id, parcel_id),
  UNIQUE(dataset_id, source_file, source_row),
  FOREIGN KEY(dataset_id, parcel_id) REFERENCES parcels(dataset_id, parcel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS parcel_source_facts_sale_date ON parcel_source_facts(dataset_id, sale_date);

CREATE TABLE IF NOT EXISTS eligibility_reports (
  id uuid PRIMARY KEY,
  created_by text NOT NULL,
  run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  report jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(created_by, idempotency_key)
);
CREATE INDEX IF NOT EXISTS eligibility_reports_owner_run_created
  ON eligibility_reports(created_by, run_id, created_at DESC);
