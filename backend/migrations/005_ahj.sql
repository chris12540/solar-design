CREATE TABLE IF NOT EXISTS ahj_registry (
  id text PRIMARY KEY,
  name text NOT NULL,
  ahj_type text NOT NULL CHECK (ahj_type IN ('city','town','county_unincorporated','other')),
  county text NOT NULL,
  state text NOT NULL CHECK (state = 'AZ'),
  boundary_ref text,
  status text NOT NULL CHECK (status IN ('draft','verified'))
);

CREATE TABLE IF NOT EXISTS ahj_assignments (
  dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  parcel_id text NOT NULL,
  ahj_id text REFERENCES ahj_registry(id),
  method text NOT NULL CHECK (method IN ('boundary','manual','unresolved','ambiguous')),
  status text NOT NULL CHECK (status IN ('provisional','verified','unresolved')),
  source jsonb NOT NULL,
  candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (dataset_id, parcel_id)
);

CREATE INDEX IF NOT EXISTS ahj_assignments_ahj ON ahj_assignments(ahj_id);
