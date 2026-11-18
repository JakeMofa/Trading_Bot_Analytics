-- Disposable PostgreSQL only. All data and grants from this file roll back.
BEGIN;
CREATE TABLE public.pp_receipt_denied_probe (id integer);
INSERT INTO public.pp_receipt_denied_probe VALUES (1);
INSERT INTO history_v2.structured_receipts
  (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,
   payload_hash,envelope_hash)
VALUES ('production','00000000-0000-4000-8000-000000000001',1,
        'core.markets','p',repeat('a',64),repeat('b',64),repeat('c',64));

SET LOCAL ROLE tradebot_pp_history;
DO $test$
DECLARE n bigint; blocked boolean;
BEGIN
  IF current_user <> 'tradebot_pp_history' THEN
    RAISE EXCEPTION 'wrong receipt test role';
  END IF;
  INSERT INTO history_v2.structured_receipts
    (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,
     payload_hash,envelope_hash)
  VALUES ('pp-live-pp','00000000-0000-4000-8000-000000000002',2,
          'core.markets','pp',repeat('d',64),repeat('e',64),repeat('f',64));
  SELECT count(*) INTO n FROM history_v2.structured_receipts;
  IF n <> 1 THEN RAISE EXCEPTION 'PP receipt read or origin fence failed'; END IF;

  blocked := false;
  BEGIN
    INSERT INTO history_v2.structured_receipts
      (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,
       payload_hash,envelope_hash)
    VALUES ('pp-live-pp-other','00000000-0000-4000-8000-000000000003',3,
            'core.markets','wrong',repeat('a',64),repeat('b',64),repeat('c',64));
  EXCEPTION WHEN insufficient_privilege THEN blocked := true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'other-origin receipt insert allowed'; END IF;

  blocked := false;
  BEGIN
    UPDATE history_v2.structured_receipts SET entity_id = 'modified'
      WHERE origin_id = 'pp-live-pp';
  EXCEPTION WHEN insufficient_privilege THEN blocked := true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'receipt update allowed'; END IF;

  blocked := false;
  BEGIN
    PERFORM 1 FROM history_v2.structured_receipts
      WHERE origin_id = 'pp-live-pp' FOR UPDATE;
  EXCEPTION WHEN insufficient_privilege THEN blocked := true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'receipt FOR UPDATE allowed'; END IF;

  blocked := false;
  BEGIN
    DELETE FROM history_v2.structured_receipts WHERE origin_id = 'pp-live-pp';
  EXCEPTION WHEN insufficient_privilege THEN blocked := true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'receipt delete allowed'; END IF;

  blocked := false;
  BEGIN
    PERFORM 1 FROM public.pp_receipt_denied_probe;
  EXCEPTION WHEN insufficient_privilege THEN blocked := true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'public table read allowed'; END IF;
END $test$;
ROLLBACK;
