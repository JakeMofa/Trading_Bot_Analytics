-- The single result is a capability. Only run psql with -X -qAt, with
-- stdout redirected to the one-shot private file, never to logs or evidence.
\set ON_ERROR_STOP on
\if :{?window_profile}
\else
\set window_profile standard
\endif
BEGIN;
SET LOCAL ROLE tradebot_owner;
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='250ms';
WITH attestation AS MATERIALIZED (
    SELECT clock_timestamp() AS issued,
           :'freeze_started_at'::timestamptz AS starts,
           :'freeze_ends_at'::timestamptz AS ends
)
INSERT INTO archive.pp_retirement_permits
    (sealed_id,collecting_id,seal_hash,seal_count,release_sha,policy_epoch_hash,
     history_reader_proof,authority_scope,issued_at,expires_at)
SELECT a.generation_id,b.generation_id,a.seal_hash,a.seal_count,:'release_sha',
       :'policy_epoch_hash',:'history_reader_proof','pp-admin-change-freeze-v1',
       f.issued, least(f.ends,
           CASE WHEN :'window_profile'='two_markets' THEN
               least(f.issued+interval '295 seconds', a.sealed_at+interval '30 minutes')
           ELSE f.issued+interval '2 minutes' END)
FROM archive.generations a JOIN ops.writer_state w ON w.origin_id=a.origin_id
JOIN archive.generations b ON b.origin_id=w.origin_id AND b.generation_id=w.generation_id
CROSS JOIN attestation f
WHERE :'freeze_started_at' ~ 'T[0-9:.]+(Z|[+-][0-9]{2}:[0-9]{2})$'
  AND :'freeze_ends_at' ~ 'T[0-9:.]+(Z|[+-][0-9]{2}:[0-9]{2})$'
  AND f.starts<=f.issued AND f.issued<f.ends AND f.ends-f.starts<=interval '295 seconds'
  AND :'window_profile' IN ('standard','two_markets')
  AND (:'window_profile'='standard' OR (a.sealed_at+interval '30 minutes'>f.issued
       AND b.started_at=a.sealed_at))
  AND current_database()='tradebot_pp' AND session_user='tradebot_migrator'
  AND EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1)
  AND a.origin_id='pp-live-pp' AND a.generation_id=:'sealed' AND a.seal_hash=:'seal_hash'
  AND a.seal_count=:'row_count'::bigint AND a.state='verified' AND a.hold_reason IS NULL
  AND a.verified_at IS NOT NULL AND b.generation_id=:'collecting' AND b.state='collecting'
  AND a.slot<>b.slot AND w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp()
RETURNING ticket AS issued_ticket
\gset
COMMIT;
\echo :issued_ticket
