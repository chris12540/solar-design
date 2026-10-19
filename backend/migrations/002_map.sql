CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE runs ALTER COLUMN original_address DROP NOT NULL;

ALTER TABLE parcels
  ADD COLUMN IF NOT EXISTS county_geometry geometry(Geometry,4326),
  ADD COLUMN IF NOT EXISTS county_latitude double precision,
  ADD COLUMN IF NOT EXISTS county_longitude double precision,
  ADD COLUMN IF NOT EXISTS county_fetched_at timestamptz,
  ADD COLUMN IF NOT EXISTS county_gis_version text;
CREATE INDEX IF NOT EXISTS parcels_county_geometry_gist ON parcels USING gist(county_geometry);
CREATE INDEX IF NOT EXISTS parcels_dataset_upper_apn ON parcels(dataset_id, upper(apn));

CREATE TABLE IF NOT EXISTS county_subdivisions (
  mcr_key text PRIMARY KEY,
  mcr_num text,
  mcr_name text NOT NULL,
  geometry geometry(Geometry,4326),
  fetched_at timestamptz NOT NULL DEFAULT now(),
  gis_version text NOT NULL
);
CREATE INDEX IF NOT EXISTS county_subdivisions_geometry_gist ON county_subdivisions USING gist(geometry);
CREATE INDEX IF NOT EXISTS county_subdivisions_name_prefix ON county_subdivisions(lower(mcr_name) text_pattern_ops);

CREATE TABLE IF NOT EXISTS area_snapshots (
  id uuid PRIMARY KEY,
  created_by text NOT NULL,
  dataset_id text NOT NULL REFERENCES datasets(id),
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS area_snapshots_owner_created ON area_snapshots(created_by, created_at DESC);

CREATE TABLE IF NOT EXISTS county_area_queries (
  dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  query_key text NOT NULL,
  apns jsonb NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  gis_version text NOT NULL,
  complete boolean NOT NULL DEFAULT true,
  PRIMARY KEY(dataset_id, query_key)
);
