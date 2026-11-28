-- REVIEW ONLY: additive exact-origin authority; no login, Storage, data or activation.
-- Apply only after fresh schema/grant/policy inventory and separate operator review.
BEGIN;
DO $preflight$
DECLARE t text;
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname IN
    ('tradebot_pp_benchmark_watch_writer','tradebot_pp_benchmark_watch_reader')) THEN
    RAISE EXCEPTION 'trial roles already exist; inspect rather than broadening';
  END IF;
  FOREACH t IN ARRAY ARRAY['markets','candles','current_prices','protected_evidence',
    'feature_snapshots','snapshot_evidence','predictions','outcomes','generation_checkpoints',
    'structured_receipts','structured_revision_payloads'] LOOP
    IF NOT EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='history_v2' AND c.relname=t AND c.relkind='r' AND c.relrowsecurity) THEN
      RAISE EXCEPTION 'reviewed RLS table missing';
    END IF;
  END LOOP;
END $preflight$;
CREATE ROLE tradebot_pp_benchmark_watch_writer NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
CREATE ROLE tradebot_pp_benchmark_watch_reader NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
GRANT USAGE ON SCHEMA history_v2 TO tradebot_pp_benchmark_watch_writer,tradebot_pp_benchmark_watch_reader;
GRANT USAGE ON TYPE history_v2.exact_numeric,history_v2.generation_uuid,history_v2.sha256
  TO tradebot_pp_benchmark_watch_writer,tradebot_pp_benchmark_watch_reader;
GRANT EXECUTE ON FUNCTION history_v2.source_epoch(text)
  TO tradebot_pp_benchmark_watch_writer;
DO $policy$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['markets','candles','current_prices','protected_evidence',
    'feature_snapshots','snapshot_evidence','predictions','outcomes','generation_checkpoints',
    'structured_receipts','structured_revision_payloads'] LOOP
    EXECUTE format('GRANT SELECT ON history_v2.%I TO tradebot_pp_benchmark_watch_writer,tradebot_pp_benchmark_watch_reader',t);
    EXECUTE format('GRANT INSERT ON history_v2.%I TO tradebot_pp_benchmark_watch_writer',t);
    EXECUTE format('CREATE POLICY pp_benchmark_watch_select ON history_v2.%I FOR SELECT
      TO tradebot_pp_benchmark_watch_writer,tradebot_pp_benchmark_watch_reader
      USING (origin_id=%L)',t,'pp-live-pp-benchmark-watch');
    EXECUTE format('CREATE POLICY pp_benchmark_watch_insert ON history_v2.%I FOR INSERT
      TO tradebot_pp_benchmark_watch_writer WITH CHECK (origin_id=%L)',t,'pp-live-pp-benchmark-watch');
    -- An unrelated permissive policy must never widen these new principals.
    EXECUTE format('CREATE POLICY pp_benchmark_watch_origin_fence ON history_v2.%I
      AS RESTRICTIVE FOR ALL TO tradebot_pp_benchmark_watch_writer,tradebot_pp_benchmark_watch_reader
      USING (origin_id=%L) WITH CHECK (origin_id=%L)',t,'pp-live-pp-benchmark-watch','pp-live-pp-benchmark-watch');
  END LOOP;
  FOREACH t IN ARRAY ARRAY['markets','current_prices','generation_checkpoints'] LOOP
    EXECUTE format('GRANT UPDATE ON history_v2.%I TO tradebot_pp_benchmark_watch_writer',t);
    EXECUTE format('CREATE POLICY pp_benchmark_watch_update ON history_v2.%I FOR UPDATE
      TO tradebot_pp_benchmark_watch_writer USING (origin_id=%L) WITH CHECK (origin_id=%L)',
      t,'pp-live-pp-benchmark-watch','pp-live-pp-benchmark-watch');
  END LOOP;
END $policy$;
-- No coverage/public grants, owner/role membership, DELETE/TRUNCATE or future-table defaults.
COMMIT;
