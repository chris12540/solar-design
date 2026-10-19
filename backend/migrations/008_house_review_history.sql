CREATE TABLE IF NOT EXISTS house_review_events (
  id uuid PRIMARY KEY,
  created_by text NOT NULL,
  dataset_id text NOT NULL,
  parcel_id text NOT NULL,
  source_version text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('solar_lookup', 'eligibility_report')),
  label text NOT NULL,
  report_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(created_by, dataset_id, parcel_id, kind, report_id),
  FOREIGN KEY(dataset_id, parcel_id) REFERENCES parcels(dataset_id, parcel_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS house_review_events_owner_house_created
  ON house_review_events(created_by, dataset_id, parcel_id, created_at DESC);

-- Rebuild lightweight per-house review history from existing reports and the
-- saved-area snapshots. No report facts are copied into the event table.
INSERT INTO house_review_events
  (id, created_by, dataset_id, parcel_id, source_version, kind, label, report_id, created_at)
SELECT md5(er.id::text || ':' || a.dataset_id || ':' || (parcel->>'id'))::uuid,
       er.created_by, a.dataset_id, parcel->>'id', a.dataset_id,
       'eligibility_report', 'Eligibility review saved', er.id, er.created_at
FROM eligibility_reports er
JOIN runs r ON r.id = er.run_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(r.selection->'area_ids', '[]'::jsonb)) area_id
JOIN area_snapshots a ON a.id::text = area_id AND a.created_by = er.created_by
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(er.report->'homes', '[]'::jsonb)) report_home
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(a.payload->'parcels', '[]'::jsonb)) parcel
WHERE parcel->>'id' IS NOT NULL AND parcel->>'id' = report_home->>'parcel_id'
ON CONFLICT DO NOTHING;

-- Older saved reports retained the lookup timestamp only inside report data.
-- Preserve the timestamp as event metadata before normal expiry cleanup removes
-- those reports without copying Solar response fields.
INSERT INTO house_review_events
  (id, created_by, dataset_id, parcel_id, source_version, kind, label, report_id, created_at)
SELECT md5('solar:' || er.id::text || ':' || a.dataset_id || ':' || (parcel->>'id'))::uuid,
       er.created_by, a.dataset_id, parcel->>'id', a.dataset_id,
       'solar_lookup', 'Solar lookup completed', er.id,
       (report_home->'facts'->>'solar_fetched_at')::timestamptz
FROM eligibility_reports er
JOIN runs r ON r.id = er.run_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(r.selection->'area_ids', '[]'::jsonb)) area_id
JOIN area_snapshots a ON a.id::text = area_id AND a.created_by = er.created_by
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(er.report->'homes', '[]'::jsonb)) report_home
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(a.payload->'parcels', '[]'::jsonb)) parcel
WHERE parcel->>'id' IS NOT NULL AND parcel->>'id' = report_home->>'parcel_id'
  AND report_home->'facts'->>'solar_fetched_at' IS NOT NULL
ON CONFLICT DO NOTHING;
