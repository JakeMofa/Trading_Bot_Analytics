-- Each transaction models a distinct Storage HTTP request. The real helper is
-- STABLE and request operation state must not be changed mid-transaction.
BEGIN;
INSERT INTO storage.objects(bucket_id,name) VALUES
  ('market-raw',test_fixture.object_key(repeat('a',64),repeat('f',64)));
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.upload';
INSERT INTO storage.objects(bucket_id,name,owner_id)
  VALUES('market-raw',test_fixture.object_key(),auth.uid()::text);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.get_authenticated';
SELECT test_fixture.assert_visible(test_fixture.object_key(),1);
SELECT test_fixture.assert_visible(test_fixture.object_key(repeat('a',64),repeat('f',64)),0);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='object.get_authenticated_info';
SELECT test_fixture.assert_visible(test_fixture.object_key(),1);
SELECT test_fixture.assert_visible(test_fixture.object_key(repeat('a',64),repeat('f',64)),0);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.list';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.get_public';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.copy';
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key(repeat('1',64)));
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.upload_signed';
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key(repeat('2',64)));
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.upload';
SELECT test_fixture.expect_insert_denied('knowledge',test_fixture.object_key(repeat('3',64)));
SELECT test_fixture.expect_insert_denied('market-raw',
  test_fixture.object_key(repeat('4',64),repeat('f',64)));
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key()||'.tmp');
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.move';
SELECT test_fixture.assert_update_denied(test_fixture.object_key());
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.upload_update';
SELECT test_fixture.assert_update_denied(test_fixture.object_key());
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.delete';
SELECT test_fixture.assert_delete_denied(test_fixture.object_key());
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000bb';
SET LOCAL storage.operation='storage.object.get_authenticated';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
COMMIT;

BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000bb';
SET LOCAL storage.operation='storage.object.upload';
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key(repeat('5',64)));
COMMIT;

BEGIN;
SET LOCAL ROLE anon;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.get_authenticated';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
COMMIT;

BEGIN;
SET LOCAL ROLE anon;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.upload';
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key(repeat('6',64)));
COMMIT;

DO $final$
BEGIN
  IF (SELECT count(*) FROM storage.objects WHERE name=test_fixture.object_key())<>1 THEN
    RAISE EXCEPTION 'protected generated object changed';
  END IF;
  IF (SELECT count(*) FROM storage.objects)<>2 THEN
    RAISE EXCEPTION 'unexpected generated object';
  END IF;
END $final$;
