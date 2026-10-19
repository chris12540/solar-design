-- Short-lived roof inputs and derived working geometry share one expiry.
CREATE TABLE IF NOT EXISTS roof_reconstructions (
  created_by text NOT NULL,
  dataset_id text NOT NULL,
  parcel_id text NOT NULL,
  source_fetched_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  algorithm_version text NOT NULL,
  insights jsonb NOT NULL,
  source_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  dsm bytea NOT NULL,
  roof_mask bytea NOT NULL,
  result jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(created_by,dataset_id,parcel_id),
  FOREIGN KEY(dataset_id,parcel_id) REFERENCES parcels(dataset_id,parcel_id) ON DELETE CASCADE,
  CHECK(expires_at <= source_fetched_at + interval '30 days')
);
CREATE INDEX IF NOT EXISTS roof_reconstructions_expiry ON roof_reconstructions(expires_at);

ALTER TABLE roof_reconstructions ADD COLUMN IF NOT EXISTS source_warnings jsonb NOT NULL DEFAULT '[]'::jsonb;
