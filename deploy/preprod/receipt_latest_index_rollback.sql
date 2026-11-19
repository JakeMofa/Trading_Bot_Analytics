-- Separately authorized rollback ONLY. Disable the application opt-in first,
-- stop audit/readback borrowers, then run this ONE statement standalone with
-- autocommit, outside a transaction/pipeline. No receipt/envelope is removed.
DROP INDEX CONCURRENTLY history_v2.structured_receipts_latest_identity_v1_idx;
