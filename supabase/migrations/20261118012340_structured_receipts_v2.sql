-- Additive CP6 preparation only. This creates immutable per-revision receipts
-- for a future, separately granted private importer. It does not enable a
-- runtime identity, cloud sync, or local partition retirement.
CREATE TABLE history_v2.structured_receipts (
  origin_id text NOT NULL CHECK (length(origin_id)>0),
  generation_id history_v2.generation_uuid NOT NULL,
  outbox_id bigint NOT NULL CHECK (outbox_id>0),
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  content_hash history_v2.sha256 NOT NULL,
  payload_hash history_v2.sha256 NOT NULL,
  envelope_hash history_v2.sha256 NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (origin_id,generation_id,outbox_id)
);

ALTER TABLE history_v2.structured_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON history_v2.structured_receipts FROM PUBLIC,anon,authenticated,service_role;
-- No runtime grant or policy. Applying this migration requires separate review.
