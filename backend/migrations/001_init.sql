CREATE TABLE IF NOT EXISTS datasets (
 id text PRIMARY KEY, imported_at timestamptz NOT NULL DEFAULT now(), snapshot_date date,
 input_rows bigint NOT NULL, imported_rows bigint NOT NULL, rejected_rows bigint NOT NULL,
 files jsonb NOT NULL, active boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS datasets_one_active ON datasets(active) WHERE active;
CREATE TABLE IF NOT EXISTS parcels (
 dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
 parcel_id text NOT NULL, apn text NOT NULL, address text NOT NULL, unit text,
 city text NOT NULL, postal_code text NOT NULL, year_built integer,
 mcr_key text, mcr_name text, occupancy text NOT NULL, occupancy_reason text NOT NULL,
 source_file text NOT NULL, source_row bigint NOT NULL,
 search_norm text NOT NULL,
 PRIMARY KEY(dataset_id, parcel_id)
);
CREATE INDEX IF NOT EXISTS parcels_search_prefix ON parcels(dataset_id, search_norm text_pattern_ops);
CREATE INDEX IF NOT EXISTS parcels_apn_prefix ON parcels(dataset_id, apn text_pattern_ops);
CREATE INDEX IF NOT EXISTS parcels_address_prefix ON parcels(dataset_id, address text_pattern_ops);
CREATE INDEX IF NOT EXISTS parcels_city_prefix ON parcels(dataset_id, city text_pattern_ops);
CREATE TABLE IF NOT EXISTS rejected_rows (
 dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
 source_file text NOT NULL, source_row bigint NOT NULL, reason text NOT NULL,
 PRIMARY KEY(dataset_id, source_file, source_row)
);
CREATE TABLE IF NOT EXISTS runs (
 id uuid PRIMARY KEY, idempotency_key uuid NOT NULL, request_hash text NOT NULL,
 created_by text NOT NULL, name text NOT NULL, original_address text NOT NULL,
 parcel_id text, parcel_snapshot jsonb, selection jsonb NOT NULL,
 status text NOT NULL DEFAULT 'draft', county_fips text NOT NULL DEFAULT '04013',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(created_by, idempotency_key)
);
