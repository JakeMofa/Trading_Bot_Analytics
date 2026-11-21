"""Exact trial cloud binding controls. No Supabase connection or secret inputs."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'deploy/preprod'))
import httpx
from postgres.archive_codec import ArchiveIntegrityError
from postgres.cloud_origin_binding import cloud_binding,LEGACY_ORIGIN,TRIAL_ORIGIN,TRIAL_WRITER,TRIAL_READER
from postgres.pp_history_connection import PPHistoryConnectionFactory
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.supabase_storage import _MachineSession,PROJECT_URL,SupabaseStorageTransport
from bind_trial_cloud_policy import render

UID='00000000-0000-4000-8000-0000000000cc'
OTHER='00000000-0000-4000-8000-0000000000dd'


class TrialCloudBindingTests(unittest.TestCase):
    def test_exact_allowlist_and_separate_role_bindings(self):
        self.assertEqual(cloud_binding(LEGACY_ORIGIN).role(),'tradebot_pp_history')
        binding=cloud_binding(TRIAL_ORIGIN)
        self.assertEqual(binding.role(),TRIAL_WRITER); self.assertEqual(binding.role(reader=True),TRIAL_READER)
        next_binding=cloud_binding('pp-live-pp-trial-20261119-02')
        self.assertEqual(next_binding.role(),'tradebot_pp_trial_20261119_02_writer')
        self.assertEqual(next_binding.role(reader=True),'tradebot_pp_trial_20261119_02_reader')
        self.assertNotEqual(next_binding.raw_prefix,binding.raw_prefix)
        for value in ('production','generated-test',TRIAL_ORIGIN+'-other','pp-live-pp-trial-20261119-05'):
            with self.assertRaises(ValueError): cloud_binding(value)
        with self.assertRaises(ValueError): binding.role(reader='true')
        self.assertEqual(PPHistoryConnectionFactory(origin_id=TRIAL_ORIGIN).expected_role,TRIAL_WRITER)
        self.assertEqual(PPHistoryConnectionFactory(origin_id=TRIAL_ORIGIN,reader=True).expected_role,TRIAL_READER)

    def test_trial_dsn_files_cannot_reuse_legacy_or_opposite_role(self):
        from test_pp_history_connection import PPHistoryConnectionTests
        fixture=PPHistoryConnectionTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        for reader in (False,True):
            role=cloud_binding(TRIAL_ORIGIN).role(reader=reader)
            fixture.dsn_file.write_text(fixture.dsn.replace('tradebot_pp_history',role))
            factory=PPHistoryConnectionFactory(fixture.dsn_file,fixture.ca_file,origin_id=TRIAL_ORIGIN,reader=reader)
            factory._validated_dsn(4)
            for wrong in ('tradebot_pp_history',cloud_binding(TRIAL_ORIGIN).role(reader=not reader)):
                fixture.dsn_file.write_text(fixture.dsn.replace('tradebot_pp_history',wrong))
                with patch('psycopg.connect') as connect,self.assertRaises(ArchiveIntegrityError): factory(timeout_seconds=4)
                connect.assert_not_called()

    def test_trial_structured_role_scope_and_readonly_reject_before_connection(self):
        factory=Mock()
        for role in ('postgres','tradebot_pp_history','service_role'):
            with self.assertRaises(ValueError):
                HistoryV2PostgresTransport(factory,origin_id=TRIAL_ORIGIN,generation_id=UID,
                    expected_database='postgres',expected_role=role)
        reader=HistoryV2PostgresTransport(factory,origin_id=TRIAL_ORIGIN,generation_id=UID,
            expected_database='postgres',expected_role=TRIAL_READER)
        with self.assertRaises(ArchiveIntegrityError): reader.put_structured([],timeout_seconds=4)
        factory.assert_not_called()

    def test_trial_auth_requires_admin_controlled_origin_and_operation_role(self):
        with httpx.Client(transport=httpx.MockTransport(lambda _:self.fail('unexpected network'))) as client:
            for reader in (False,True):
                session=_MachineSession('sb_publishable_fixture','fixture@example.invalid','p'*40,UID,
                                        client,reader=reader,origin_id=TRIAL_ORIGIN)
                claims=dict(sub=UID,role='authenticated',iss=PROJECT_URL+'/auth/v1',exp=int(time.time())+3600,
                    app_metadata=dict(tradebot_origin=TRIAL_ORIGIN,
                        tradebot_role='pp_storage_history_reader' if reader else 'pp_storage_archive'))
                def jwt(value): return 'x.'+base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')+'.x'
                self.assertGreater(session._validate_access(jwt(claims)),0)
                claims['app_metadata']['tradebot_origin']=LEGACY_ORIGIN
                with self.assertRaises(ValueError): session._validate_access(jwt(claims))
                claims['user_metadata']={'tradebot_origin':TRIAL_ORIGIN}
                with self.assertRaises(ValueError): session._validate_access(jwt(claims))

    def test_machine_keys_are_exact_origin_and_reader_cannot_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            paths=[]
            for index,value in enumerate(('sb_publishable_fixture_key','fixture@example.invalid','p'*40,UID)):
                path=Path(folder)/str(index); path.write_text(value); path.chmod(0o600); paths.append(path)
            with httpx.Client(transport=httpx.MockTransport(lambda _:self.fail('unexpected network'))) as client:
                transport=SupabaseStorageTransport.from_machine_files(*paths,client=client,reader=True,origin_id=TRIAL_ORIGIN)
                suffix=UID+'/'+'a'*64+'.jsonl.gz'
                transport._url(cloud_binding(TRIAL_ORIGIN).raw_prefix+suffix,authenticated=True)
                with self.assertRaises(ArchiveIntegrityError): transport._url(cloud_binding(LEGACY_ORIGIN).raw_prefix+suffix,authenticated=True)
                with self.assertRaises(ArchiveIntegrityError): transport.put_if_absent(cloud_binding(TRIAL_ORIGIN).raw_prefix+suffix,b'x',timeout_seconds=4)

    def test_review_renderer_rejects_unbound_or_injected_identities(self):
        values=dict(writer_uid=UID,reader_uid=OTHER,writer_email='writer@example.invalid',
                    reader_email='reader@example.invalid',policy_sha256='a'*64)
        self.assertNotIn('__TRIAL_',render(**values))
        for changes in (dict(reader_uid=UID),dict(writer_email="writer'@example.invalid"),dict(policy_sha256='abc')):
            with self.assertRaises(ValueError): render(**(values|changes))


if __name__=='__main__': unittest.main()
