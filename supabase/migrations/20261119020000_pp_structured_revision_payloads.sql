-- Private, additive PP history. The existing projections, receipts and login
-- are unchanged. Operators separately review application and runtime opt-in.
CREATE TABLE history_v2.structured_revision_payloads (
    origin_id text NOT NULL,
    generation_id history_v2.generation_uuid NOT NULL,
    outbox_id bigint NOT NULL CHECK (outbox_id > 0),
    envelope bytea NOT NULL CHECK (octet_length(envelope) BETWEEN 1 AND 4194304),
    PRIMARY KEY (origin_id,generation_id,outbox_id),
    FOREIGN KEY (origin_id,generation_id,outbox_id)
        REFERENCES history_v2.structured_receipts(origin_id,generation_id,outbox_id)
);
ALTER TABLE history_v2.structured_revision_payloads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON history_v2.structured_revision_payloads FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON history_v2.structured_revision_payloads TO tradebot_pp_history;
CREATE POLICY pp_revision_read ON history_v2.structured_revision_payloads
    FOR SELECT TO tradebot_pp_history USING (origin_id='pp-live-pp');
CREATE POLICY pp_revision_append ON history_v2.structured_revision_payloads
    FOR INSERT TO tradebot_pp_history WITH CHECK (origin_id='pp-live-pp');

CREATE FUNCTION history_v2.check_revision_envelope() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
    IF NOT EXISTS (SELECT FROM history_v2.structured_receipts r
        WHERE (r.origin_id,r.generation_id,r.outbox_id) =
              (NEW.origin_id,NEW.generation_id,NEW.outbox_id)
          AND r.envelope_hash=encode(sha256(NEW.envelope),'hex')) THEN
        RAISE EXCEPTION 'envelope does not match exact revision receipt';
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION history_v2.check_revision_envelope() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER pp_revision_check BEFORE INSERT ON history_v2.structured_revision_payloads
FOR EACH ROW EXECUTE FUNCTION history_v2.check_revision_envelope();
