-- Immutable once applied. Explicit migration only; never application startup.
CREATE DOMAIN core.exact_numeric AS numeric
  CHECK (VALUE NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));
CREATE DOMAIN core.sha256 AS text CHECK (VALUE ~ '^[0-9a-f]{64}$');
CREATE DOMAIN core.generation_uuid AS text
  CHECK (VALUE ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');

CREATE FUNCTION core.source_epoch(value text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
DECLARE parts text[]; seconds numeric;
BEGIN
  parts := regexp_match(value, '^(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2}:\d{2})(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})$');
  IF parts IS NULL OR parts[4]='-00:00' OR substring(parts[2],1,2)::integer>23
      OR substring(parts[2],4,2)::integer>59 OR substring(parts[2],7,2)::integer>59 THEN
    RAISE EXCEPTION 'invalid exact source timestamp';
  END IF;
  seconds := extract(epoch FROM (parts[1]||'T'||parts[2]||parts[4])::timestamptz);
  RETURN seconds + CASE WHEN parts[3] IS NULL THEN 0 ELSE ('0.'||parts[3])::numeric END;
END $fn$;
REVOKE ALL ON FUNCTION core.source_epoch(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.source_epoch(text) TO tradebot_app,tradebot_reader,tradebot_lifecycle;

CREATE TABLE core.markets (
  origin_id text NOT NULL CHECK (length(origin_id)>0), market_id text NOT NULL,
  source text NOT NULL, slug text NOT NULL, duration integer NOT NULL CHECK (duration IN (900,3600)),
  start_time text NOT NULL, end_time text NOT NULL,
  start_epoch core.exact_numeric NOT NULL, end_epoch core.exact_numeric NOT NULL,
  target core.exact_numeric, final core.exact_numeric, result text CHECK (result IN ('UP','DOWN')),
  status text NOT NULL, index_symbol text, rules text,
  first_seen timestamptz NOT NULL, last_seen timestamptz NOT NULL,
  payload jsonb NOT NULL, content_hash core.sha256 NOT NULL,
  PRIMARY KEY (origin_id,market_id), CHECK (end_epoch>start_epoch),
  CHECK (start_epoch=core.source_epoch(start_time) AND end_epoch=core.source_epoch(end_time)),
  CHECK (last_seen>=first_seen), UNIQUE (origin_id,source,slug)
);
CREATE INDEX markets_active ON core.markets (origin_id,duration,end_epoch,start_epoch);
CREATE TABLE core.candles (
  origin_id text NOT NULL, source text NOT NULL, symbol text NOT NULL,
  granularity integer NOT NULL CHECK (granularity>0), time bigint NOT NULL,
  low core.exact_numeric, high core.exact_numeric, open core.exact_numeric,
  close core.exact_numeric, volume core.exact_numeric CHECK (volume>=0),
  first_seen timestamptz NOT NULL, payload jsonb NOT NULL, content_hash core.sha256 NOT NULL,
  PRIMARY KEY (origin_id,source,symbol,granularity,time), CHECK (low<=high)
);
CREATE TABLE archive.generations (
  origin_id text NOT NULL, generation_id core.generation_uuid NOT NULL,
  slot text NOT NULL CHECK (slot IN ('A','B')),
  state text NOT NULL CHECK (state IN ('prepared','collecting','sealed','verified','retired')),
  partition_name text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL, started_at timestamptz, sealed_at timestamptz,
  verified_at timestamptz, retired_at timestamptz,
  seal_count bigint CHECK (seal_count>=0), seal_hash core.sha256, hold_reason text,
  PRIMARY KEY (origin_id,generation_id), UNIQUE (generation_id),
  CHECK (partition_name='events_g_'||replace(generation_id,'-','')),
  CHECK (state NOT IN ('sealed','verified','retired') OR sealed_at IS NOT NULL),
  CHECK (state NOT IN ('verified','retired') OR (verified_at IS NOT NULL AND seal_count IS NOT NULL AND seal_hash IS NOT NULL)),
  CHECK (state<>'retired' OR retired_at IS NOT NULL)
);
CREATE UNIQUE INDEX generations_one_collecting ON archive.generations(origin_id) WHERE state='collecting';
CREATE UNIQUE INDEX generations_live_slot ON archive.generations(origin_id,slot) WHERE state IN ('prepared','collecting','sealed','verified');
CREATE TABLE ops.writer_state (
  origin_id text PRIMARY KEY, generation_id core.generation_uuid NOT NULL,
  epoch bigint NOT NULL CHECK (epoch>=0), collector_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL,
  FOREIGN KEY (origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id)
);
CREATE TABLE raw.events (
  generation_id core.generation_uuid NOT NULL, origin_id text NOT NULL,
  source text NOT NULL, event_id text NOT NULL, kind text NOT NULL,
  market_id text, symbol text, source_time text, source_epoch core.exact_numeric,
  received_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  price core.exact_numeric, size core.exact_numeric,
  payload jsonb NOT NULL, raw_payload text, content_hash core.sha256 NOT NULL,
  PRIMARY KEY (generation_id,origin_id,source,event_id),
  FOREIGN KEY (origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id),
  FOREIGN KEY (origin_id,market_id) REFERENCES core.markets(origin_id,market_id),
  CHECK ((source_time IS NULL)=(source_epoch IS NULL)),
  CHECK (source_epoch=core.source_epoch(source_time)), CHECK (available_at>=received_at)
) PARTITION BY LIST(generation_id);
CREATE INDEX events_market_time ON raw.events(origin_id,market_id,available_at);
CREATE INDEX events_latest_quote ON raw.events(origin_id,market_id,kind,source_epoch DESC);
CREATE INDEX events_source_time ON raw.events(origin_id,source,symbol,source_epoch DESC);
CREATE TABLE core.current_prices (
  origin_id text NOT NULL, source text NOT NULL, symbol text NOT NULL,
  event_id text NOT NULL, generation_id core.generation_uuid NOT NULL,
  source_time text NOT NULL, source_epoch core.exact_numeric NOT NULL,
  received_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  price core.exact_numeric NOT NULL, size core.exact_numeric,
  payload jsonb NOT NULL, content_hash core.sha256 NOT NULL,
  PRIMARY KEY (origin_id,source,symbol), CHECK (available_at>=received_at),
  CHECK(source_epoch=core.source_epoch(source_time))
);
CREATE TABLE core.protected_evidence (
  origin_id text NOT NULL, evidence_id text NOT NULL, generation_id core.generation_uuid,
  source text NOT NULL, event_id text NOT NULL, kind text NOT NULL, market_id text,
  source_time text, source_epoch core.exact_numeric,
  received_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  payload jsonb NOT NULL, raw_payload text, content_hash core.sha256 NOT NULL,
  PRIMARY KEY (origin_id,evidence_id), UNIQUE(origin_id,evidence_id,market_id),
  FOREIGN KEY (origin_id,market_id) REFERENCES core.markets(origin_id,market_id),
  CHECK ((source_time IS NULL)=(source_epoch IS NULL)),
  CHECK (source_epoch=core.source_epoch(source_time)), CHECK (available_at>=received_at)
);
CREATE INDEX protected_evidence_generation ON core.protected_evidence(origin_id,generation_id);
CREATE TABLE core.feature_snapshots (
  origin_id text NOT NULL, snapshot_id text NOT NULL, market_id text NOT NULL,
  as_of timestamptz NOT NULL, version integer NOT NULL CHECK (version>0),
  values_json jsonb NOT NULL, quality_json jsonb NOT NULL, evidence_json jsonb NOT NULL,
  content_hash core.sha256 NOT NULL,
  PRIMARY KEY (origin_id,snapshot_id), UNIQUE(origin_id,market_id,as_of,version),
  UNIQUE(origin_id,snapshot_id,market_id), UNIQUE(origin_id,snapshot_id,market_id,as_of),
  FOREIGN KEY (origin_id,market_id) REFERENCES core.markets(origin_id,market_id)
);
CREATE TABLE core.snapshot_evidence (
  origin_id text NOT NULL, snapshot_id text NOT NULL, evidence_id text NOT NULL,
  PRIMARY KEY(origin_id,snapshot_id,evidence_id),
  FOREIGN KEY(origin_id,snapshot_id) REFERENCES core.feature_snapshots(origin_id,snapshot_id),
  FOREIGN KEY(origin_id,evidence_id) REFERENCES core.protected_evidence(origin_id,evidence_id)
);
CREATE INDEX snapshot_evidence_reverse ON core.snapshot_evidence(origin_id,evidence_id);
CREATE TABLE core.predictions (
  origin_id text NOT NULL, prediction_id text NOT NULL, snapshot_id text NOT NULL,
  market_id text NOT NULL, model_version text NOT NULL,
  as_of timestamptz NOT NULL, created_at timestamptz NOT NULL,
  seconds_remaining core.exact_numeric NOT NULL,
  probability_up core.exact_numeric CHECK(probability_up BETWEEN 0 AND 1),
  probability_down core.exact_numeric CHECK(probability_down BETWEEN 0 AND 1),
  abstain_reason text, assumptions_json jsonb NOT NULL, payload jsonb NOT NULL,
  content_hash core.sha256 NOT NULL,
  PRIMARY KEY(origin_id,prediction_id), UNIQUE(origin_id,snapshot_id,model_version),
  FOREIGN KEY(origin_id,snapshot_id,market_id,as_of) REFERENCES core.feature_snapshots(origin_id,snapshot_id,market_id,as_of),
  CHECK(created_at>=as_of), CHECK((probability_up IS NULL)=(probability_down IS NULL)),
  CHECK(probability_up IS NOT NULL OR abstain_reason IS NOT NULL)
);
CREATE INDEX predictions_history ON core.predictions(origin_id,as_of DESC);
CREATE INDEX predictions_market_time ON core.predictions(origin_id,market_id,as_of);
CREATE TABLE core.outcomes (
  origin_id text NOT NULL, outcome_id text NOT NULL, market_id text NOT NULL, evidence_id text NOT NULL,
  result text NOT NULL CHECK(result IN ('UP','DOWN')), final core.exact_numeric,
  source_time text, source_epoch core.exact_numeric, confirmed_at timestamptz NOT NULL,
  available_at timestamptz NOT NULL, payload jsonb NOT NULL, content_hash core.sha256 NOT NULL,
  PRIMARY KEY(origin_id,outcome_id),
  FOREIGN KEY(origin_id,market_id) REFERENCES core.markets(origin_id,market_id),
  FOREIGN KEY(origin_id,evidence_id,market_id) REFERENCES core.protected_evidence(origin_id,evidence_id,market_id),
  CHECK((source_time IS NULL)=(source_epoch IS NULL)),
  CHECK(source_epoch=core.source_epoch(source_time))
);
CREATE INDEX outcomes_market_time ON core.outcomes(origin_id,market_id,confirmed_at);
CREATE INDEX outcomes_evidence ON core.outcomes(origin_id,evidence_id);
CREATE TABLE ops.feed_health (
  origin_id text NOT NULL, source text NOT NULL, status text NOT NULL,
  updated_at timestamptz NOT NULL, last_data_at timestamptz,
  reconnects bigint NOT NULL DEFAULT 0 CHECK(reconnects>=0), detail jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY(origin_id,source)
);
CREATE TABLE ops.worker_checkpoints (
  origin_id text NOT NULL, worker text NOT NULL, cursor jsonb NOT NULL,
  updated_at timestamptz NOT NULL, PRIMARY KEY(origin_id,worker)
);
CREATE TABLE ops.dedup (
  origin_id text NOT NULL, source text NOT NULL, event_id text NOT NULL,
  generation_id core.generation_uuid NOT NULL, content_hash core.sha256 NOT NULL,
  expires_at timestamptz NOT NULL, PRIMARY KEY(origin_id,source,event_id)
);
CREATE INDEX dedup_expiry ON ops.dedup(expires_at);
CREATE TABLE ops.outbox (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  origin_id text NOT NULL, generation_id core.generation_uuid,
  entity_type text NOT NULL, entity_id text NOT NULL, content_hash core.sha256 NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL, acknowledged_at timestamptz,
  UNIQUE(origin_id,entity_type,entity_id,content_hash)
);
CREATE INDEX outbox_pending ON ops.outbox(origin_id,generation_id,id) WHERE acknowledged_at IS NULL;
CREATE TABLE archive.manifests (
  origin_id text NOT NULL, generation_id core.generation_uuid NOT NULL, manifest_id text NOT NULL,
  format_version integer NOT NULL CHECK(format_version>0), object_key text NOT NULL,
  sha256 core.sha256 NOT NULL, row_count bigint NOT NULL CHECK(row_count>=0),
  byte_count bigint NOT NULL CHECK(byte_count>=0), coverage jsonb NOT NULL,
  created_at timestamptz NOT NULL, verified_at timestamptz, verification jsonb,
  PRIMARY KEY(origin_id,generation_id,manifest_id),
  FOREIGN KEY(origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id),
  CHECK ((verified_at IS NULL)=(verification IS NULL))
);
CREATE TABLE archive.checkpoints (
  origin_id text NOT NULL, generation_id core.generation_uuid NOT NULL, consumer text NOT NULL,
  cursor jsonb NOT NULL, acknowledged_at timestamptz NOT NULL,
  PRIMARY KEY(origin_id,generation_id,consumer),
  FOREIGN KEY(origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id)
);
CREATE TABLE archive.reader_leases (
  lease_id text PRIMARY KEY, origin_id text NOT NULL, generation_id core.generation_uuid NOT NULL,
  holder text NOT NULL, expires_at timestamptz NOT NULL,
  FOREIGN KEY(origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id)
);
CREATE INDEX reader_leases_generation ON archive.reader_leases(origin_id,generation_id,expires_at);

-- DML access is explicit: no schema CREATE, ownership membership, or broad defaults.
GRANT USAGE ON SCHEMA raw,core,ops,archive TO tradebot_app,tradebot_reader,tradebot_lifecycle;
GRANT SELECT ON ALL TABLES IN SCHEMA raw,core,archive TO tradebot_app,tradebot_reader,tradebot_lifecycle;
GRANT SELECT ON ops.writer_state,ops.feed_health,ops.worker_checkpoints,ops.outbox,ops.dedup
  TO tradebot_app,tradebot_reader,tradebot_lifecycle;
GRANT SELECT ON ops.environment_identity TO tradebot_lifecycle;
GRANT INSERT,UPDATE ON core.markets,core.candles,core.current_prices,ops.feed_health,ops.worker_checkpoints TO tradebot_app;
GRANT INSERT ON raw.events,core.protected_evidence,core.feature_snapshots,core.snapshot_evidence,core.predictions,core.outcomes,ops.outbox TO tradebot_app;
GRANT INSERT,UPDATE,DELETE ON ops.dedup TO tradebot_app;
GRANT USAGE ON SEQUENCE ops.outbox_id_seq TO tradebot_app;
-- Row locking FOR SHARE requires UPDATE privilege on at least one column.
GRANT UPDATE(updated_at) ON ops.writer_state TO tradebot_app;
GRANT SELECT,INSERT,UPDATE ON archive.generations,archive.manifests,archive.checkpoints TO tradebot_lifecycle;
GRANT SELECT,INSERT,UPDATE,DELETE ON archive.reader_leases TO tradebot_lifecycle;
GRANT INSERT,UPDATE ON ops.writer_state TO tradebot_lifecycle;
GRANT UPDATE(acknowledged_at) ON ops.outbox TO tradebot_lifecycle;

-- Runtime lifecycle has no owner membership. These are the only DDL capabilities.
CREATE FUNCTION archive.create_generation_partition(p_origin text,p_generation text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE g archive.generations; expected text;
BEGIN
  SELECT * INTO STRICT g FROM archive.generations
    WHERE origin_id=p_origin AND generation_id=p_generation FOR UPDATE;
  expected := 'events_g_'||replace(g.generation_id,'-','');
  IF g.state<>'prepared' OR g.partition_name<>expected THEN
    RAISE EXCEPTION 'partition creation requires prepared canonical generation';
  END IF;
  IF to_regclass(format('raw.%I',expected)) IS NOT NULL THEN
    RAISE EXCEPTION 'partition relation already exists';
  END IF;
  EXECUTE format('CREATE TABLE raw.%I PARTITION OF raw.events FOR VALUES IN (%L)',expected,g.generation_id);
  EXECUTE format('GRANT SELECT ON raw.%I TO tradebot_app,tradebot_reader,tradebot_lifecycle',expected);
  EXECUTE format('GRANT INSERT ON raw.%I TO tradebot_app',expected);
  RETURN expected;
END $fn$;
REVOKE ALL ON FUNCTION archive.create_generation_partition(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION archive.create_generation_partition(text,text) TO tradebot_lifecycle;

CREATE FUNCTION archive.retire_generation_partition(p_origin text,p_generation text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE g archive.generations; gate jsonb; expected text;
BEGIN
  -- CP4 permits generated preprod retirement only. Real authority is CP6+ work.
  IF current_database()<>'tradebot_pp' OR p_origin NOT LIKE 'generated-%'
      OR NOT EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1) THEN
    RAISE EXCEPTION 'retirement is restricted to generated preprod qualification';
  END IF;
  SELECT * INTO STRICT g FROM archive.generations
    WHERE origin_id=p_origin AND generation_id=p_generation FOR UPDATE;
  expected := 'events_g_'||replace(g.generation_id,'-','');
  SELECT cursor INTO gate FROM archive.checkpoints
    WHERE origin_id=p_origin AND generation_id=p_generation AND consumer='retirement:fresh-readback';
  IF g.state<>'verified' OR g.partition_name<>expected OR g.hold_reason IS NOT NULL
      OR g.seal_count IS NULL OR g.seal_hash IS NULL
      OR EXISTS(SELECT FROM ops.writer_state WHERE origin_id=p_origin AND generation_id=p_generation)
      OR EXISTS(SELECT FROM archive.reader_leases WHERE origin_id=p_origin AND generation_id=p_generation AND expires_at>clock_timestamp())
      OR NOT EXISTS(SELECT FROM archive.manifests WHERE origin_id=p_origin AND generation_id=p_generation AND verified_at IS NOT NULL)
      OR EXISTS(SELECT FROM archive.manifests WHERE origin_id=p_origin AND generation_id=p_generation AND verified_at IS NULL)
      OR EXISTS(SELECT FROM ops.outbox WHERE origin_id=p_origin AND generation_id=p_generation AND acknowledged_at IS NULL)
      OR EXISTS(SELECT FROM core.protected_evidence e WHERE e.origin_id=p_origin AND e.generation_id=p_generation AND NOT EXISTS(
        SELECT FROM ops.outbox o WHERE o.origin_id=e.origin_id AND o.entity_type='core.protected_evidence'
        AND o.generation_id=e.generation_id AND o.payload->>'origin_id'=e.origin_id
        AND o.payload->>'evidence_id'=e.evidence_id AND o.content_hash=e.content_hash AND o.acknowledged_at IS NOT NULL))
      OR gate IS NULL OR gate->>'gate_scope' IS DISTINCT FROM 'immutable-generated'
      OR gate->>'authorized_txid' IS DISTINCT FROM txid_current()::text
      OR gate->>'sha256' IS DISTINCT FROM g.seal_hash::text
      OR gate->>'row_count' IS DISTINCT FROM g.seal_count::text
      OR gate->>'retirement_enabled' IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'retirement verification, references, outbox, reader, or enablement gate is not satisfied';
  END IF;
  IF NOT EXISTS(SELECT FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
      AND n.nspname='raw' AND c.relname=expected
      AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%L)',g.generation_id)) THEN
    RAISE EXCEPTION 'registered partition is absent or inconsistent';
  END IF;
  EXECUTE format('DROP TABLE raw.%I',expected);
  UPDATE archive.generations SET state='retired',retired_at=clock_timestamp()
    WHERE origin_id=p_origin AND generation_id=p_generation;
  RETURN expected;
END $fn$;
REVOKE ALL ON FUNCTION archive.retire_generation_partition(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION archive.retire_generation_partition(text,text) TO tradebot_lifecycle;
-- Generation row locks fence protected-input capture against seal/retirement.
GRANT UPDATE(started_at) ON archive.generations TO tradebot_app;
