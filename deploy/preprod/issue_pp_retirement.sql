-- The single result is a capability. Only run psql with -X -qAt, with
-- stdout redirected to the one-shot private file, never to logs or evidence.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE tradebot_owner;
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='250ms';
INSERT INTO archive.pp_retirement_permits
    (sealed_id,collecting_id,seal_hash,seal_count,release_sha,policy_epoch_hash,
     history_reader_proof,authority_scope,expires_at)
SELECT a.generation_id,b.generation_id,a.seal_hash,a.seal_count,:'release_sha',
       :'policy_epoch_hash',:'history_reader_proof','pp-admin-change-freeze-v1',
       clock_timestamp()+interval '2 minutes'
FROM archive.generations a JOIN ops.writer_state w ON w.origin_id=a.origin_id
JOIN archive.generations b ON b.origin_id=w.origin_id AND b.generation_id=w.generation_id
WHERE current_database()='tradebot_pp' AND session_user='tradebot_migrator'
  AND EXISTS(SELECT FROM ops.environment_identity WHERE environment='preprod' AND foundation_version=1)
  AND a.origin_id='pp-live-pp' AND a.generation_id=:'sealed' AND a.seal_hash=:'seal_hash'
  AND a.seal_count=:'row_count'::bigint AND a.state='verified' AND a.hold_reason IS NULL
  AND a.verified_at IS NOT NULL AND b.generation_id=:'collecting' AND b.state='collecting'
  AND a.slot<>b.slot AND w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp()
RETURNING ticket AS issued_ticket
\gset
COMMIT;
\echo :issued_ticket
