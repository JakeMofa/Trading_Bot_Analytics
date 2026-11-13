-- CP2 additive private contract ONLY. Not an executable local migration.
-- Applying to cloud, privileges and authenticated mutation/readback require CP6.
-- Existing public objects are never modified. Fails if history_v2 already exists.
CREATE SCHEMA history_v2;
REVOKE ALL ON SCHEMA history_v2 FROM PUBLIC,anon,authenticated;

CREATE DOMAIN history_v2.exact_numeric AS numeric
  CHECK (VALUE NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));
CREATE DOMAIN history_v2.sha256 AS text CHECK (VALUE ~ '^[0-9a-f]{64}$');
CREATE DOMAIN history_v2.generation_uuid AS text
  CHECK (VALUE ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');

CREATE FUNCTION history_v2.source_epoch(value text) RETURNS numeric
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
REVOKE ALL ON FUNCTION history_v2.source_epoch(text) FROM PUBLIC;



CREATE TABLE history_v2.markets (
  origin_id text NOT NULL CHECK (length(origin_id)>0), market_id text NOT NULL,
  source text NOT NULL, slug text NOT NULL, duration integer NOT NULL CHECK (duration IN (900,3600)),
  start_time text NOT NULL, end_time text NOT NULL,
  start_epoch history_v2.exact_numeric NOT NULL, end_epoch history_v2.exact_numeric NOT NULL,
  target history_v2.exact_numeric, final history_v2.exact_numeric, result text CHECK (result IN ('UP','DOWN')),
  status text NOT NULL, index_symbol text, rules text,
  first_seen timestamptz NOT NULL, last_seen timestamptz NOT NULL,
  payload jsonb NOT NULL, content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY (origin_id,market_id), CHECK (end_epoch>start_epoch),
  CHECK (start_epoch=history_v2.source_epoch(start_time) AND end_epoch=history_v2.source_epoch(end_time)),
  CHECK (last_seen>=first_seen), UNIQUE (origin_id,source,slug)
);

CREATE TABLE history_v2.candles (
  origin_id text NOT NULL, source text NOT NULL, symbol text NOT NULL,
  granularity integer NOT NULL CHECK (granularity>0), time bigint NOT NULL,
  low history_v2.exact_numeric, high history_v2.exact_numeric, open history_v2.exact_numeric,
  close history_v2.exact_numeric, volume history_v2.exact_numeric CHECK (volume>=0),
  first_seen timestamptz NOT NULL, payload jsonb NOT NULL, content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY (origin_id,source,symbol,granularity,time), CHECK (low<=high)
);

CREATE TABLE history_v2.protected_evidence (
  origin_id text NOT NULL, evidence_id text NOT NULL, generation_id history_v2.generation_uuid,
  source text NOT NULL, event_id text NOT NULL, kind text NOT NULL, market_id text,
  source_time text, source_epoch history_v2.exact_numeric,
  received_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  payload jsonb NOT NULL, raw_payload text, content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY (origin_id,evidence_id), UNIQUE(origin_id,evidence_id,market_id),
  FOREIGN KEY (origin_id,market_id) REFERENCES history_v2.markets(origin_id,market_id),
  CHECK ((source_time IS NULL)=(source_epoch IS NULL)),
  CHECK (source_epoch=history_v2.source_epoch(source_time)), CHECK (available_at>=received_at)
);

CREATE TABLE history_v2.feature_snapshots (
  origin_id text NOT NULL, snapshot_id text NOT NULL, market_id text NOT NULL,
  as_of timestamptz NOT NULL, version integer NOT NULL CHECK (version>0),
  values_json jsonb NOT NULL, quality_json jsonb NOT NULL, evidence_json jsonb NOT NULL,
  content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY (origin_id,snapshot_id), UNIQUE(origin_id,market_id,as_of,version),
  UNIQUE(origin_id,snapshot_id,market_id), UNIQUE(origin_id,snapshot_id,market_id,as_of),
  FOREIGN KEY (origin_id,market_id) REFERENCES history_v2.markets(origin_id,market_id)
);

CREATE TABLE history_v2.snapshot_evidence (
  origin_id text NOT NULL, snapshot_id text NOT NULL, evidence_id text NOT NULL,
  PRIMARY KEY(origin_id,snapshot_id,evidence_id),
  FOREIGN KEY(origin_id,snapshot_id) REFERENCES history_v2.feature_snapshots(origin_id,snapshot_id),
  FOREIGN KEY(origin_id,evidence_id) REFERENCES history_v2.protected_evidence(origin_id,evidence_id)
);

CREATE TABLE history_v2.predictions (
  origin_id text NOT NULL, prediction_id text NOT NULL, snapshot_id text NOT NULL,
  market_id text NOT NULL, model_version text NOT NULL,
  as_of timestamptz NOT NULL, created_at timestamptz NOT NULL,
  seconds_remaining history_v2.exact_numeric NOT NULL,
  probability_up history_v2.exact_numeric CHECK(probability_up BETWEEN 0 AND 1),
  probability_down history_v2.exact_numeric CHECK(probability_down BETWEEN 0 AND 1),
  abstain_reason text, assumptions_json jsonb NOT NULL, payload jsonb NOT NULL,
  content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY(origin_id,prediction_id), UNIQUE(origin_id,snapshot_id,model_version),
  FOREIGN KEY(origin_id,snapshot_id,market_id,as_of) REFERENCES history_v2.feature_snapshots(origin_id,snapshot_id,market_id,as_of),
  CHECK(created_at>=as_of), CHECK((probability_up IS NULL)=(probability_down IS NULL)),
  CHECK(probability_up IS NOT NULL OR abstain_reason IS NOT NULL)
);

CREATE TABLE history_v2.outcomes (
  origin_id text NOT NULL, outcome_id text NOT NULL, market_id text NOT NULL, evidence_id text NOT NULL,
  result text NOT NULL CHECK(result IN ('UP','DOWN')), final history_v2.exact_numeric,
  source_time text, source_epoch history_v2.exact_numeric, confirmed_at timestamptz NOT NULL,
  available_at timestamptz NOT NULL, payload jsonb NOT NULL, content_hash history_v2.sha256 NOT NULL,
  PRIMARY KEY(origin_id,outcome_id),
  FOREIGN KEY(origin_id,market_id) REFERENCES history_v2.markets(origin_id,market_id),
  FOREIGN KEY(origin_id,evidence_id,market_id) REFERENCES history_v2.protected_evidence(origin_id,evidence_id,market_id),
  CHECK((source_time IS NULL)=(source_epoch IS NULL)),
  CHECK(source_epoch=history_v2.source_epoch(source_time))
);

CREATE TABLE history_v2.generation_checkpoints (
  origin_id text NOT NULL, generation_id history_v2.generation_uuid NOT NULL,
  dataset text NOT NULL, cursor jsonb NOT NULL, row_count bigint NOT NULL CHECK(row_count>=0),
  content_hash history_v2.sha256 NOT NULL, acknowledged_at timestamptz NOT NULL,
  PRIMARY KEY(origin_id,generation_id,dataset)
);
CREATE TABLE history_v2.coverage (
  origin_id text NOT NULL,generation_id history_v2.generation_uuid NOT NULL,
  manifest_id text NOT NULL,object_key text NOT NULL,sha256 history_v2.sha256 NOT NULL,
  row_count bigint NOT NULL CHECK(row_count>=0),byte_count bigint NOT NULL CHECK(byte_count>=0),
  format_version integer NOT NULL CHECK(format_version>0),coverage jsonb NOT NULL,
  verified_at timestamptz NOT NULL,verification jsonb NOT NULL,
  PRIMARY KEY(origin_id,generation_id,manifest_id)
);

ALTER TABLE history_v2.markets ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.candles ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.protected_evidence ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.feature_snapshots ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.snapshot_evidence ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.predictions ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.outcomes ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.generation_checkpoints ENABLE ROW LEVEL SECURITY;

ALTER TABLE history_v2.coverage ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA history_v2 FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA history_v2 FROM PUBLIC,anon,authenticated;
-- No public policies and no service-role grant are provisioned here.
-- CP6 must qualify a separate narrow authenticated importer/retriever identity,
-- exact immutable-content conflict handling, checkpoint acknowledgement and
-- irreversible object protection. This contract alone grants no mutation authority.
