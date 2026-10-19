ALTER TABLE parcel_source_facts ADD COLUMN IF NOT EXISTS rental_ind text;

CREATE TABLE IF NOT EXISTS parcel_solar_facts (
  dataset_id text NOT NULL,
  parcel_id text NOT NULL,
  outcome text NOT NULL,
  facts jsonb NOT NULL DEFAULT '{}',
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(dataset_id, parcel_id),
  FOREIGN KEY(dataset_id, parcel_id) REFERENCES parcels(dataset_id, parcel_id) ON DELETE CASCADE
);
