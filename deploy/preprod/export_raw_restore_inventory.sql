-- Owner-reviewed local PP inventory only; no raw payloads, cloud access or writes.
-- Invoke psql -X -w -qAt as the existing tradebot_reader on tradebot_pp.
-- Required -v: expected_origin, generation_id, expected_seal_count,
-- expected_seal_hash. Optional -v max_manifests=1..128 (default 128).
-- stdout is one JSON line after successful read-only COMMIT, or no payload.
-- Keep stdout in a private temporary file; promote it only when psql exits 0.
-- The offline restore verifier independently recomputes manifest_set_hash and
-- validates chunk checksums/coverage. This export grants no retirement authority.
\set ON_ERROR_STOP on
\set QUIET on
\set ECHO none
\set VERBOSITY terse
\if :{?max_manifests}
\else
\set max_manifests 128
\endif
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path=pg_catalog;
SET LOCAL transaction_timeout='4s';
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='250ms';

-- psql SQL-literal quoting is intentional: never use raw :variable SQL syntax.
-- Invalid input/identity terminates with nonzero status before any payload.
SELECT 1 / CASE WHEN
    :'expected_origin'='pp-live-pp'
    AND :'generation_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    AND :'expected_seal_count' ~ '^(0|[1-9][0-9]{0,18})$'
    AND :'expected_seal_hash' ~ '^[0-9a-f]{64}$'
    AND :'max_manifests' ~ '^[0-9]{1,3}$'
    AND :'max_manifests'::integer BETWEEN 1 AND 128
    AND current_database()='tradebot_pp'
    AND current_user='tradebot_reader' AND session_user=current_user
    AND current_setting('transaction_read_only')='on'
    AND current_setting('transaction_isolation')='repeatable read'
    AND EXISTS (SELECT FROM pg_roles WHERE rolname=current_user
        AND NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication))
    AND NOT has_schema_privilege(current_user,'archive','CREATE')
    AND NOT EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='archive' AND c.relkind IN ('r','p','v','m','f')
          AND (has_table_privilege(current_user,c.oid,
              'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
            OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE,REFERENCES')))
    THEN 1 ELSE 0 END AS inventory_identity_checked
\gset

WITH generation AS MATERIALIZED (
    SELECT origin_id,generation_id,seal_count,seal_hash
    FROM archive.generations
    WHERE origin_id=:'expected_origin' AND generation_id=:'generation_id'
      AND state IN ('verified','retired') AND hold_reason IS NULL
      AND sealed_at IS NOT NULL AND verified_at IS NOT NULL
      AND (state<>'retired' OR retired_at IS NOT NULL)
      AND seal_count=:'expected_seal_count'::bigint
      AND seal_hash=:'expected_seal_hash'
), candidates AS MATERIALIZED (
    SELECT m.*,row_number() OVER (ORDER BY manifest_id COLLATE "C")-1 AS ordinal,
        lag(coverage->'last',1,'null'::jsonb) OVER
            (ORDER BY manifest_id COLLATE "C") AS prior_last
    FROM archive.manifests m JOIN generation g USING(origin_id,generation_id)
    ORDER BY manifest_id COLLATE "C" LIMIT 129
), admissible AS MATERIALIZED (
    SELECT count(*) BETWEEN 1 AND :'max_manifests'::integer
      AND sum(row_count)=(SELECT seal_count FROM generation)
      -- Bound metadata before constructing its aggregate JSON (1 MiB input).
      AND sum(octet_length(manifest_id)+octet_length(object_key)+octet_length(sha256)
              +octet_length(coverage::text))<=1048576
      AND bool_and(coalesce(verified_at IS NOT NULL
          AND verification='{"method":"fresh_authenticated_readback"}'::jsonb
          AND format_version=1 AND row_count>=0 AND byte_count>0
          AND sha256 ~ '^[0-9a-f]{64}$'
          AND manifest_id='raw.events:'||lpad(ordinal::text,12,'0')
          AND object_key='raw-v1/'||encode(sha256(convert_to(origin_id,'UTF8')),'hex')
                           ||'/'||generation_id||'/'||sha256||'.jsonl.gz'
          AND jsonb_typeof(coverage)='object'
          AND coverage->>'origin_id'=origin_id
          AND coverage->>'generation_id'=generation_id
          AND coverage->>'dataset'='raw.events'
          AND coverage ? 'after' AND coverage ? 'last'
          AND coverage->'after'=prior_last
          AND (row_count>0 OR (ordinal=0 AND
              (SELECT count(*) FROM candidates)=1)),false)) AS allowed
    FROM candidates
), eligible AS MATERIALIZED (
    SELECT c.* FROM candidates c CROSS JOIN admissible a WHERE a.allowed IS TRUE
), payload AS (
    SELECT jsonb_build_object('generation',jsonb_build_object(
        'origin_id',g.origin_id,'generation_id',g.generation_id,
        'seal_count',g.seal_count,'seal_hash',g.seal_hash),
        'manifests',(SELECT jsonb_agg(jsonb_build_object(
            'manifest_id',manifest_id,'format_version',format_version,
            'object_key',object_key,'sha256',sha256,'row_count',row_count,
            'byte_count',byte_count,'coverage',coverage) ORDER BY manifest_id COLLATE "C")
            FROM eligible))::text AS inventory
    FROM generation g CROSS JOIN admissible a WHERE a.allowed IS TRUE
)
SELECT inventory AS raw_restore_inventory FROM payload
-- Reserve one byte for psql's terminating newline within the 2 MiB file cap.
WHERE octet_length(inventory)<2097152
\gset
-- Zero-row gset is an error under ON_ERROR_STOP; nothing has been printed.
COMMIT;
\echo :raw_restore_inventory
