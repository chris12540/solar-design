ALTER TABLE parcels ADD COLUMN IF NOT EXISTS property_type text;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS puc text;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS residential boolean;

CREATE INDEX IF NOT EXISTS parcels_dataset_mcr ON parcels(dataset_id, mcr_key);
CREATE INDEX IF NOT EXISTS parcels_dataset_residential_mcr ON parcels(dataset_id, residential, mcr_key);
CREATE INDEX IF NOT EXISTS parcels_dataset_mcr_name ON parcels(dataset_id, lower(mcr_name) text_pattern_ops);
