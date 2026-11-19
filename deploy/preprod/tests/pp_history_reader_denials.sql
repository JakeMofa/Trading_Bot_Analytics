-- Joined only to the open transaction of the generated CI fixture.
CREATE POLICY hypothetical_extra_grants ON storage.objects FOR ALL TO authenticated
  USING (true) WITH CHECK (true);
SET LOCAL ROLE authenticated;
SET LOCAL request.jwt.claim.sub='00000000-0000-4000-8000-0000000000bb';
SET LOCAL storage.operation='object.get_authenticated_info';
SELECT test_fixture.assert_visible(test_fixture.object_key(),1);
SELECT test_fixture.assert_visible(test_fixture.object_key(repeat('a',64),repeat('f',64)),0);
SET LOCAL storage.operation='storage.object.list';
SELECT test_fixture.assert_visible(test_fixture.object_key(),0);
SET LOCAL storage.operation='storage.object.upload';
SELECT test_fixture.expect_insert_denied('market-raw',test_fixture.object_key(repeat('d',64)));
SET LOCAL storage.operation='object.get_authenticated_info';
SELECT test_fixture.assert_update_denied(test_fixture.object_key());
SELECT test_fixture.assert_delete_denied(test_fixture.object_key());
ROLLBACK;
