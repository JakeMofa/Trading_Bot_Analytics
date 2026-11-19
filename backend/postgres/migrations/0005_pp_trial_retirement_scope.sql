-- Apply the same insert fences to one separately qualified PP trial origin.
CREATE TRIGGER pp_trial_outbox_generation_fence BEFORE INSERT ON ops.outbox
FOR EACH ROW WHEN (NEW.origin_id='pp-live-pp-trial-20261119-01' AND NEW.generation_id IS NOT NULL)
EXECUTE FUNCTION archive.pp_capture_retirement_fence();

CREATE TRIGGER pp_trial_protected_generation_fence BEFORE INSERT ON core.protected_evidence
FOR EACH ROW WHEN (NEW.origin_id='pp-live-pp-trial-20261119-01' AND NEW.generation_id IS NOT NULL)
EXECUTE FUNCTION archive.pp_capture_retirement_fence();

CREATE OR REPLACE FUNCTION archive.retire_pp_generation(p_ticket uuid,p_sealed text,p_collecting text,p_release text,p_policy text,p_history text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE permit archive.pp_retirement_permits; g archive.generations; evidence jsonb; child text;
BEGIN
  IF current_database()<>'tradebot_pp' OR
     NOT EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1) THEN
    RAISE EXCEPTION 'PP database identity required';
  END IF;
  SELECT * INTO STRICT permit FROM archive.pp_retirement_permits WHERE ticket=p_ticket FOR UPDATE;
  SELECT * INTO STRICT g FROM archive.generations
    WHERE origin_id IN ('pp-live-pp','pp-live-pp-trial-20261119-01')
      AND generation_id=p_sealed FOR UPDATE;
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
  -- Unlike maintenance of retained legacy data, a fresh trial always uses
  -- the two-market window and the exact successor of the sealed generation.
  IF g.origin_id='pp-live-pp-trial-20261119-01' AND (
       g.sealed_at IS NULL OR clock_timestamp()>=g.sealed_at+interval '30 minutes'
       OR permit.expires_at>g.sealed_at+interval '30 minutes'
       OR NOT EXISTS(SELECT FROM archive.generations a
         WHERE a.origin_id=g.origin_id AND a.generation_id=p_collecting
           AND a.started_at=g.sealed_at AND a.slot<>g.slot)) THEN
    RAISE EXCEPTION 'PP trial requires the exact unexpired two-market handoff';
  END IF;
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
