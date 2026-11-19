-- Disposable CI fixture. Application cloud migrations are separately reviewed.
BEGIN;
DO $test$
BEGIN
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='history_v2.structured_revision_payloads'::regclass)
       OR EXISTS (SELECT FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')
                  AND has_table_privilege(rolname,'history_v2.structured_revision_payloads','SELECT'))
       OR has_table_privilege('tradebot_pp_history','history_v2.structured_revision_payloads','TRUNCATE') THEN
        RAISE EXCEPTION 'revision grants or RLS expanded';
    END IF;
END $test$;
INSERT INTO history_v2.structured_receipts
 (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,payload_hash,envelope_hash)
 SELECT o,'00000000-0000-4000-8000-000000000004',42,'fixture','1',
        repeat('a',64),repeat('b',64),encode(sha256(convert_to('exact','UTF8')),'hex')
 FROM unnest(ARRAY['production','pp-live-pp']) o;
INSERT INTO history_v2.structured_revision_payloads VALUES
 ('production','00000000-0000-4000-8000-000000000004',42,convert_to('exact','UTF8'));
SET LOCAL ROLE tradebot_pp_history;
DO $test$
DECLARE id text := '00000000-0000-4000-8000-000000000004';
BEGIN
    BEGIN
        INSERT INTO history_v2.structured_revision_payloads VALUES ('pp-live-pp',id,42,convert_to('wrong','UTF8'));
        RAISE EXCEPTION 'wrong envelope accepted' USING ERRCODE='XX000';
    EXCEPTION WHEN raise_exception THEN NULL;
    END;
    INSERT INTO history_v2.structured_revision_payloads VALUES ('pp-live-pp',id,42,convert_to('exact','UTF8'));
    IF (SELECT count(*) FROM history_v2.structured_revision_payloads)<>1 THEN
        RAISE EXCEPTION 'cross-origin private revision visible or PP revision unavailable';
    END IF;
    BEGIN
        INSERT INTO history_v2.structured_revision_payloads VALUES ('production',id,42,convert_to('exact','UTF8'));
        RAISE EXCEPTION 'cross-origin insert allowed';
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN
        IF SQLERRM='cross-origin insert allowed' THEN RAISE; END IF;
    END;
    BEGIN
        UPDATE history_v2.structured_revision_payloads SET envelope=convert_to('wrong','UTF8');
        RAISE EXCEPTION 'historical envelope update allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM history_v2.structured_revision_payloads;
        RAISE EXCEPTION 'historical envelope delete allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $test$;
ROLLBACK;
