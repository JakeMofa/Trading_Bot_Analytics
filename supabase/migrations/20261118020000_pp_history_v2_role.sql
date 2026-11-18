-- PP-only structured history authority. This migration creates no login secret,
-- Storage policy, public API grant, cloud worker, or retirement authorization.
-- The later structured_receipts migration/grant is reviewed separately.
CREATE ROLE tradebot_pp_history NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;

GRANT USAGE ON SCHEMA history_v2 TO tradebot_pp_history;
GRANT USAGE ON TYPE history_v2.exact_numeric, history_v2.generation_uuid,
  history_v2.sha256 TO tradebot_pp_history;
GRANT EXECUTE ON FUNCTION history_v2.source_epoch(text) TO tradebot_pp_history;

-- Immutable structured rows are insert/read only. Mutability is limited to the
-- two current projections and the generation-scoped outbox checkpoint.
GRANT SELECT, INSERT ON history_v2.markets, history_v2.candles,
  history_v2.current_prices, history_v2.protected_evidence,
  history_v2.feature_snapshots, history_v2.snapshot_evidence,
  history_v2.predictions, history_v2.outcomes,
  history_v2.generation_checkpoints TO tradebot_pp_history;
GRANT UPDATE ON history_v2.markets, history_v2.current_prices,
  history_v2.generation_checkpoints TO tradebot_pp_history;

-- The deployed PP origin is exactly pp-live-pp. A prefix check would permit
-- unrelated PP or production identities to enter this private history.
DO $policy$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'markets','candles','current_prices','protected_evidence',
    'feature_snapshots','snapshot_evidence','predictions','outcomes',
    'generation_checkpoints'] LOOP
    EXECUTE format('CREATE POLICY pp_history_select ON history_v2.%I
      FOR SELECT TO tradebot_pp_history USING (origin_id = %L)',
      table_name, 'pp-live-pp');
    EXECUTE format('CREATE POLICY pp_history_insert ON history_v2.%I
      FOR INSERT TO tradebot_pp_history WITH CHECK (origin_id = %L)',
      table_name, 'pp-live-pp');
  END LOOP;
END $policy$;

CREATE POLICY pp_history_update ON history_v2.markets FOR UPDATE
  TO tradebot_pp_history USING (origin_id = 'pp-live-pp')
  WITH CHECK (origin_id = 'pp-live-pp');
CREATE POLICY pp_history_update ON history_v2.current_prices FOR UPDATE
  TO tradebot_pp_history USING (origin_id = 'pp-live-pp')
  WITH CHECK (origin_id = 'pp-live-pp');
CREATE POLICY pp_history_update ON history_v2.generation_checkpoints FOR UPDATE
  TO tradebot_pp_history USING (origin_id = 'pp-live-pp')
  WITH CHECK (origin_id = 'pp-live-pp');

-- history_v2.coverage and future structured_receipts stay inaccessible here.
-- Grant the receipt table only after PR #92's schema and importer qualify.
