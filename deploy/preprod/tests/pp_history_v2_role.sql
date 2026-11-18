-- Runs only in the disposable CI PostgreSQL database after both migrations.
-- A failure aborts psql with ON_ERROR_STOP; no cloud request or row is involved.
BEGIN;
INSERT INTO history_v2.generation_checkpoints
  (origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at)
VALUES ('production','00000000-0000-4000-8000-000000000001','test',
        '{}'::jsonb,0,repeat('a',64),now());

SET LOCAL ROLE tradebot_pp_history;
DO $test$
DECLARE blocked boolean; n bigint;
BEGIN
  IF current_user <> 'tradebot_pp_history' THEN
    RAISE EXCEPTION 'wrong role';
  END IF;
  INSERT INTO history_v2.markets
    (origin_id,market_id,source,slug,duration,start_time,end_time,
     start_epoch,end_epoch,status,first_seen,last_seen,payload,content_hash)
  VALUES ('pp-live-pp','test-market','polymarket-us','test-market',900,
          '2026-11-17T00:00:00Z','2026-11-17T00:15:00Z',
          history_v2.source_epoch('2026-11-17T00:00:00Z'),
          history_v2.source_epoch('2026-11-17T00:15:00Z'),'open',
          '2026-11-17T00:00:01Z','2026-11-17T00:00:01Z',
          '{}'::jsonb,repeat('d',64));
  INSERT INTO history_v2.generation_checkpoints
    (origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at)
  VALUES ('pp-live-pp','00000000-0000-4000-8000-000000000002','test',
          '{}'::jsonb,0,repeat('b',64),now());
  UPDATE history_v2.generation_checkpoints SET row_count=1
    WHERE origin_id='pp-live-pp' AND dataset='test';
  SELECT count(*) INTO n FROM history_v2.generation_checkpoints
    WHERE origin_id='pp-live-pp' AND row_count=1;
  IF n<>1 THEN RAISE EXCEPTION 'PP write/read denied'; END IF;
  SELECT count(*) INTO n FROM history_v2.generation_checkpoints
    WHERE origin_id='production';
  IF n<>0 THEN RAISE EXCEPTION 'production rows visible'; END IF;

  blocked:=false;
  BEGIN
    INSERT INTO history_v2.generation_checkpoints
      (origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at)
    VALUES ('production','00000000-0000-4000-8000-000000000003','test',
            '{}'::jsonb,0,repeat('c',64),now());
  EXCEPTION WHEN insufficient_privilege THEN blocked:=true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'production insert allowed'; END IF;

  UPDATE history_v2.generation_checkpoints SET row_count=2
    WHERE origin_id='production';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'production update allowed'; END IF;

  blocked:=false;
  BEGIN
    DELETE FROM history_v2.generation_checkpoints WHERE origin_id='pp-live-pp';
  EXCEPTION WHEN insufficient_privilege THEN blocked:=true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'delete allowed'; END IF;

  blocked:=false;
  BEGIN
    UPDATE history_v2.predictions SET content_hash=repeat('f',64)
      WHERE origin_id='pp-live-pp';
  EXCEPTION WHEN insufficient_privilege THEN blocked:=true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'immutable update allowed'; END IF;

  blocked:=false;
  BEGIN
    PERFORM 1 FROM history_v2.coverage LIMIT 1;
  EXCEPTION WHEN insufficient_privilege THEN blocked:=true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'unqualified coverage access allowed'; END IF;
END $test$;
ROLLBACK;
