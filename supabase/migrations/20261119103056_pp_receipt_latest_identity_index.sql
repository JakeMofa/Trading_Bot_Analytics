-- Additive candidate ONLY; no hosted DDL authorization or grants.
-- Run this ONE statement standalone with autocommit, outside any explicit or
-- tool-managed transaction/pipeline. CREATE INDEX CONCURRENTLY is prohibited
-- inside a transaction. Do not assume `supabase db push` on CLI 2.65.5 is safe.
-- Review the standalone operator binding/version before applying. A failed
-- concurrent build may leave an INVALID index: inspect, do not IF NOT EXISTS.
-- Application opt-in stays OFF until the exact valid/ready/live ABI is verified.
CREATE INDEX CONCURRENTLY structured_receipts_latest_identity_v1_idx
ON history_v2.structured_receipts
USING btree (origin_id,entity_type,(pg_catalog.md5(entity_id)),outbox_id DESC);
