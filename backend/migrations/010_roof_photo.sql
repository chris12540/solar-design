-- Photo and matching metadata expire with original roof acquisition.
ALTER TABLE roof_reconstructions ADD COLUMN IF NOT EXISTS rgb bytea;
ALTER TABLE roof_reconstructions ADD COLUMN IF NOT EXISTS source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
