-- CP6 receipt extension for the already reviewed PP private-history role.
-- Requires the separately reviewed structured_receipts migration. No login,
-- password, public schema, Storage, or retirement privilege is installed here.
DO $preflight$
DECLARE role_oid oid;
DECLARE receipt_oid oid := to_regclass('history_v2.structured_receipts');
BEGIN
  SELECT oid INTO role_oid FROM pg_roles WHERE rolname = 'tradebot_pp_history'
    AND NOT rolcanlogin AND NOT rolinherit AND NOT rolbypassrls
    AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
    AND NOT rolreplication AND rolconnlimit = 2;
  IF role_oid IS NULL OR receipt_oid IS NULL THEN
    RAISE EXCEPTION 'reviewed PP role and receipt table required';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members
             WHERE roleid = role_oid OR member = role_oid) THEN
    RAISE EXCEPTION 'unexpected PP role membership';
  END IF;
  IF NOT EXISTS (
      SELECT 1 FROM pg_class WHERE oid = receipt_oid
        AND relkind = 'r' AND relrowsecurity
        AND (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute
             WHERE attrelid = receipt_oid AND attnum > 0 AND NOT attisdropped)
          = ARRAY['origin_id','generation_id','outbox_id','entity_type',
                  'entity_id','content_hash','payload_hash','envelope_hash',
                  'applied_at']::name[])
     OR EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'history_v2'
                 AND tablename = 'structured_receipts')
     OR has_table_privilege('tradebot_pp_history', receipt_oid,
                            'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
    RAISE EXCEPTION 'unreviewed receipt table or existing privilege';
  END IF;
  IF EXISTS (
      SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
         AND has_table_privilege('tradebot_pp_history', c.oid,
                                 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')) THEN
    RAISE EXCEPTION 'PP role can access an existing public relation';
  END IF;
END $preflight$;

GRANT SELECT, INSERT ON history_v2.structured_receipts TO tradebot_pp_history;
CREATE POLICY pp_history_select ON history_v2.structured_receipts
  FOR SELECT TO tradebot_pp_history USING (origin_id = 'pp-live-pp');
CREATE POLICY pp_history_insert ON history_v2.structured_receipts
  FOR INSERT TO tradebot_pp_history WITH CHECK (origin_id = 'pp-live-pp');
