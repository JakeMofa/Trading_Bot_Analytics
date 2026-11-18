-- Run after applying the exact-catalog-bound legacy-readback amendment.
BEGIN;
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000aa';
SET LOCAL storage.operation='storage.object.get_authenticated';
SELECT test_fixture.assert_visible(test_fixture.object_key(),1);
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
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000bb';
SET LOCAL storage.operation='object.get_authenticated_info';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
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
SET LOCAL storage.operation='storage.object.delete';
SELECT test_fixture.assert_delete_denied(test_fixture.object_key());
COMMIT;

DO $final$
BEGIN
  IF (SELECT count(*) FROM storage.objects)<>3 THEN
    RAISE EXCEPTION 'readback amendment changed generated objects';
  END IF;
END $final$;
