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
           CASE WHEN :'window_profile' IN ('two_markets','elapsed-30m-cycle') THEN
               least(f.issued+interval '295 seconds', a.sealed_at+interval '30 minutes')
           ELSE f.issued+interval '2 minutes' END)
FROM archive.generations a JOIN ops.writer_state w ON w.origin_id=a.origin_id
JOIN archive.generations b ON b.origin_id=w.origin_id AND b.generation_id=w.generation_id
CROSS JOIN attestation f
WHERE :'freeze_started_at' ~ 'T[0-9:.]+(Z|[+-][0-9]{2}:[0-9]{2})$'
  AND :'freeze_ends_at' ~ 'T[0-9:.]+(Z|[+-][0-9]{2}:[0-9]{2})$'
  AND f.starts<=f.issued AND f.issued<f.ends AND f.ends-f.starts<=interval '295 seconds'
  AND :'window_profile' IN ('standard','two_markets','elapsed-30m-cycle')
  AND (:'window_profile'='standard' OR (a.sealed_at+interval '30 minutes'>f.issued
       AND b.started_at=a.sealed_at))
  AND current_database()='tradebot_pp' AND session_user='tradebot_migrator'
  AND EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1)
  AND ((a.origin_id='pp-live-pp' AND :'window_profile'<>'elapsed-30m-cycle') OR
       (a.origin_id IN ('pp-live-pp-trial-20261119-01','pp-live-pp-trial-20261119-02','pp-live-pp-trial-20261119-03','pp-live-pp-trial-20261119-04','pp-live-pp-trial-20261119-05','pp-live-pp-trial-20261119-06')
        AND :'window_profile'='two_markets') OR
       (a.origin_id='pp-live-pp-trial-20261119-07'
        AND :'window_profile'='elapsed-30m-cycle' AND EXISTS(
         SELECT FROM archive.checkpoints c JOIN archive.generations initial USING(origin_id,generation_id)
         WHERE c.origin_id=a.origin_id AND c.consumer='rehearsal:two-leg-session'
           AND initial.slot='A' AND (initial.generation_id=a.generation_id OR
                                    (a.slot='B' AND initial.state='retired'))
           AND c.cursor->>'initial_a'=initial.generation_id
           AND c.cursor->>'session_id'=w.collector_session_id::text
           AND c.cursor->>'profile'='elapsed-30m-cycle'
           AND c.cursor->'window_seconds'='1800'::jsonb
           AND a.sealed_at >= (CASE WHEN a.slot='A' THEN
             (c.cursor->>'admitted_at')::timestamptz ELSE a.started_at END) + interval '30 minutes')))
  AND a.generation_id=:'sealed' AND a.seal_hash=:'seal_hash'
  AND a.seal_count=:'row_count'::bigint AND a.state='verified' AND a.hold_reason IS NULL
  AND a.verified_at IS NOT NULL AND b.generation_id=:'collecting' AND b.state='collecting'
  AND a.slot<>b.slot AND w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp()
RETURNING ticket AS issued_ticket
\gset
COMMIT;
\echo :issued_ticket
