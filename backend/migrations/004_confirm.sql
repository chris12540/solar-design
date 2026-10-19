ALTER TABLE runs ADD COLUMN IF NOT EXISTS review jsonb;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;
ALTER TABLE county_subdivisions ADD COLUMN IF NOT EXISTS county_mcr_key text;
CREATE INDEX IF NOT EXISTS parcels_dataset_maricopa_mcr_numeric
  ON parcels(dataset_id, (COALESCE(NULLIF(ltrim(mcr_key, '0'), ''), '0')))
  WHERE mcr_key ~ '^[0-9]+$' AND split_part(parcel_id, ':', 1) = '04013';
CREATE INDEX IF NOT EXISTS runs_confirmed_owner_created
  ON runs(created_by, created_at DESC) WHERE status = 'confirmed';
