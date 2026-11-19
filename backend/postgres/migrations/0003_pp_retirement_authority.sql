-- Only the migration owner can issue an expiring ticket. The ordinary PP
-- collector, API, and lifecycle services cannot discover, create, or renew one.
CREATE TABLE archive.pp_retirement_permits (
    ticket uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sealed_id core.generation_uuid NOT NULL,
    collecting_id core.generation_uuid NOT NULL CHECK (collecting_id <> sealed_id),
    seal_hash core.sha256 NOT NULL,
    seal_count bigint NOT NULL CHECK (seal_count > 0),
    release_sha text NOT NULL CHECK (release_sha ~ '^[0-9a-f]{40}$'),
    policy_epoch_hash core.sha256 NOT NULL,
    history_reader_proof core.sha256 NOT NULL,
    authority_scope text NOT NULL CHECK (authority_scope='pp-admin-change-freeze-v1'),
    issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL CHECK (expires_at>issued_at AND expires_at<=issued_at+interval '5 minutes'),
    used_at timestamptz,
    used_txid bigint
);
REVOKE ALL ON archive.pp_retirement_permits FROM PUBLIC,tradebot_app,tradebot_reader,tradebot_lifecycle;

-- Missing FK on ops.outbox is intentional for older non-generation records.
-- A new privileged retirement cannot race an app insertion for its sealed PP
-- generation. Other origins keep their existing semantics.
CREATE FUNCTION archive.pp_capture_retirement_fence() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
  IF NOT EXISTS (SELECT FROM archive.generations g
      WHERE g.origin_id=NEW.origin_id AND g.generation_id=NEW.generation_id
          AND g.state IN ('collecting','sealed','verified') FOR SHARE) THEN
    RAISE EXCEPTION 'PP structured capture targets a retired or absent generation';
  END IF;
  RETURN NEW;
END $fn$;
CREATE TRIGGER pp_outbox_generation_fence BEFORE INSERT ON ops.outbox
FOR EACH ROW WHEN (NEW.origin_id='pp-live-pp' AND NEW.generation_id IS NOT NULL)
EXECUTE FUNCTION archive.pp_capture_retirement_fence();

CREATE TRIGGER pp_protected_generation_fence BEFORE INSERT ON core.protected_evidence
FOR EACH ROW WHEN (NEW.origin_id='pp-live-pp' AND NEW.generation_id IS NOT NULL)
EXECUTE FUNCTION archive.pp_capture_retirement_fence();

CREATE FUNCTION archive.retire_pp_generation(p_ticket uuid,p_sealed text,p_collecting text,p_release text,p_policy text,p_history text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE permit archive.pp_retirement_permits; g archive.generations; evidence jsonb; child text;
BEGIN
  IF current_database()<>'tradebot_pp' OR
     NOT EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1) THEN
    RAISE EXCEPTION 'PP database identity required';
  END IF;
  SELECT * INTO STRICT permit FROM archive.pp_retirement_permits WHERE ticket=p_ticket FOR UPDATE;
  SELECT * INTO STRICT g FROM archive.generations
    WHERE origin_id='pp-live-pp' AND generation_id=p_sealed FOR UPDATE;
  SELECT cursor INTO STRICT evidence FROM archive.checkpoints
    WHERE origin_id=g.origin_id AND generation_id=p_sealed AND consumer='retirement:pp-fresh-readback';
  child := 'events_g_'||replace(g.generation_id,'-','');
  IF permit.sealed_id<>g.generation_id OR permit.collecting_id<>p_collecting
     OR permit.release_sha IS DISTINCT FROM p_release OR permit.policy_epoch_hash IS DISTINCT FROM p_policy
     OR permit.history_reader_proof IS DISTINCT FROM p_history OR permit.used_at IS NOT NULL
     OR clock_timestamp() NOT BETWEEN permit.issued_at AND permit.expires_at
     OR permit.seal_hash IS DISTINCT FROM g.seal_hash OR permit.seal_count IS DISTINCT FROM g.seal_count
     OR g.state<>'verified' OR g.hold_reason IS NOT NULL OR g.partition_name<>child
     OR evidence->>'txid' IS DISTINCT FROM txid_current()::text
     OR evidence->>'enabled' IS DISTINCT FROM 'true'
     OR evidence->>'policy' IS DISTINCT FROM 'pp-exact-retirement-v1'
     OR evidence->>'policy_epoch' IS DISTINCT FROM p_policy
     OR evidence->>'history_reader_proof' IS DISTINCT FROM p_history
     OR evidence->>'source' IS DISTINCT FROM p_release
     OR evidence->>'seal_hash' IS DISTINCT FROM g.seal_hash::text
     OR evidence->>'count' IS DISTINCT FROM g.seal_count::text
     OR evidence->>'active' IS DISTINCT FROM p_collecting
     OR COALESCE((evidence->>'active_new_rows')::bigint,0)<1 THEN
    RAISE EXCEPTION 'PP ticket or fresh verified evidence does not match';
  END IF;
  PERFORM 1 FROM ops.writer_state w JOIN archive.generations b USING(origin_id,generation_id)
    WHERE w.origin_id=g.origin_id AND w.generation_id=p_collecting AND b.state='collecting'
      AND b.slot<>g.slot AND w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp()
    FOR SHARE OF w,b;
  IF NOT FOUND OR EXISTS(SELECT FROM archive.reader_leases WHERE origin_id=g.origin_id
          AND generation_id=p_sealed AND expires_at>clock_timestamp())
    OR NOT EXISTS(SELECT FROM archive.manifests WHERE origin_id=g.origin_id AND generation_id=p_sealed)
    OR EXISTS(SELECT FROM archive.manifests WHERE origin_id=g.origin_id AND generation_id=p_sealed
          AND verified_at IS NULL)
    OR EXISTS(SELECT FROM ops.outbox WHERE origin_id=g.origin_id AND generation_id=p_sealed AND acknowledged_at IS NULL)
    OR EXISTS(SELECT FROM core.protected_evidence e WHERE e.origin_id=g.origin_id AND e.generation_id=p_sealed
          AND NOT EXISTS(SELECT FROM ops.outbox o WHERE o.origin_id=e.origin_id AND o.generation_id=e.generation_id
            AND o.entity_type='core.protected_evidence' AND o.payload->>'evidence_id'=e.evidence_id
            AND o.payload->>'origin_id'=e.origin_id AND o.content_hash=e.content_hash AND o.acknowledged_at IS NOT NULL
            AND jsonb_populate_record(NULL::core.protected_evidence,o.payload) IS NOT DISTINCT FROM e))
    OR NOT EXISTS(SELECT FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
            AND n.nspname='raw' AND c.relname=child AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%L)',p_sealed))
  THEN RAISE EXCEPTION 'PP partition, active collector, reference, reader or archive gate failed'; END IF;
  EXECUTE format('DROP TABLE raw.%I',child);
  UPDATE archive.generations SET state='retired',retired_at=clock_timestamp()
    WHERE origin_id=g.origin_id AND generation_id=p_sealed;
  UPDATE archive.pp_retirement_permits SET used_at=clock_timestamp(),used_txid=txid_current()
    WHERE ticket=p_ticket AND expires_at>clock_timestamp();
  IF NOT FOUND THEN RAISE EXCEPTION 'PP ticket expired during removal'; END IF;
  RETURN child;
END $fn$;
REVOKE ALL ON FUNCTION archive.retire_pp_generation(uuid,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION archive.retire_pp_generation(uuid,text,text,text,text,text) TO tradebot_lifecycle;
