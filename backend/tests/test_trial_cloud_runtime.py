"""Exact trial application wiring with generated dependencies; no host/cloud I/O."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from postgres.cloud_origin_binding import LEGACY_ORIGIN,TRIAL_ORIGIN,TRIAL_WRITER,TRIAL_READER
from postgres.cloud_runtime_profile import cloud_files,selected_cloud_origin,require_trial_files,storage_paths
from postgres.rehearsal_profile import CYCLE_POLICY
from postgres.config import Settings
from postgres.lifecycle import LifecycleHold
from postgres.archive_codec import ArchiveIntegrityError,ArchiveUnavailable
import postgres.pp_structured_service as structured
import postgres.pp_sealed_archive as archive
import postgres.pp_retirement_verify as retirement
from postgres.runtime_history import configured_history

A='00000000-0000-4000-8000-000000000001'
B='00000000-0000-4000-8000-000000000002'


def environment(*,reader=False):
    return dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',TRADEBOT_ORIGIN_ID=TRIAL_ORIGIN,
        TRADEBOT_PP_WINDOW_POLICY=CYCLE_POLICY,TRADEBOT_PP_CYCLE_INITIAL_A=A,
        **cloud_files(TRIAL_ORIGIN,reader=reader))


class TrialCloudRuntimeTests(unittest.TestCase):
    def test_exact_trial_profile_and_separate_mount_targets(self):
        writer,reader=cloud_files(TRIAL_ORIGIN),cloud_files(TRIAL_ORIGIN,reader=True)
        self.assertEqual(selected_cloud_origin(environment()),TRIAL_ORIGIN)
        self.assertEqual(selected_cloud_origin({}),LEGACY_ORIGIN)
        self.assertNotEqual(writer['TRADEBOT_PP_HISTORY_DSN_FILE'],reader['TRADEBOT_PP_HISTORY_DSN_FILE'])
        self.assertTrue(set(storage_paths(writer)).isdisjoint(storage_paths(reader)))
        for key,value in [('TRADEBOT_ORIGIN_ID',TRIAL_ORIGIN+'-other'),('TRADEBOT_PP_WINDOW_POLICY','two-official-markets'),
                          ('TRADEBOT_PP_CYCLE_INITIAL_A','not-uuid'),('TRADEBOT_ENVIRONMENT','production')]:
            with self.assertRaises(ValueError): selected_cloud_origin(environment()|{key:value})
        with self.assertRaises(ValueError): require_trial_files(environment(reader=True),TRIAL_ORIGIN,structured=True)
        with self.assertRaises(ValueError): require_trial_files(environment(),TRIAL_ORIGIN,reader=True,storage=True)

    def test_structured_service_selects_trial_writer_outbox_and_exact_factory(self):
        env=environment()|{'TRADEBOT_PP_STRUCTURED_RECURRING':'true','TRADEBOT_PP_RETAIN_REVISIONS':'true'}
        with (patch.dict(structured.os.environ,env,clear=True),patch.object(structured.signal,'signal'),
            patch.object(structured,'private_dsn'),patch.object(structured,'connect') as local,
            patch.object(structured,'validate_schema'),patch.object(structured,'LifecycleRepository'),
            patch.object(structured,'PPHistoryConnectionFactory') as remote,
            patch.object(structured,'HistoryV2PostgresTransport') as transport,
            patch.object(structured,'drain_bounded') as drain,patch.object(structured,'supervise') as supervise):
            local.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'login':'tradebot_lifecycle'}
            drain.side_effect=lambda repo,factory,**kw: factory(A,timeout_seconds=20)
            supervise.side_effect=lambda page,*_: (page(),0)[1]
            self.assertEqual(structured.main(),0)
            files=cloud_files(TRIAL_ORIGIN)
            remote.assert_called_once_with(files['TRADEBOT_PP_HISTORY_DSN_FILE'],files['TRADEBOT_PP_HISTORY_CA_FILE'],origin_id=TRIAL_ORIGIN)
            self.assertEqual(drain.call_args.kwargs['origin_id'],TRIAL_ORIGIN)
            self.assertEqual(transport.call_args.kwargs['origin_id'],TRIAL_ORIGIN)
            self.assertEqual(transport.call_args.kwargs['expected_role'],TRIAL_WRITER)
            self.assertTrue(transport.call_args.kwargs['retain_revisions'])

    def test_trial_drain_reuses_actual_fresh_readback_and_preserves_missing_ack(self):
        import test_pp_structured_drain as fixture
        from postgres.pp_structured_drain import drain_bounded
        with patch.object(fixture,'ORIGIN',TRIAL_ORIGIN):
            repository=fixture.Repository()
            result=drain_bounded(repository,lambda *a,**kw:fixture.Transport(),execute=True,
                                 origin_id=TRIAL_ORIGIN,sleep=lambda _:None)
            self.assertEqual(result['acknowledged'],2)
            repository=fixture.Repository(); bad=fixture.Transport(); bad.failure='corrupt'
            with self.assertRaises(ArchiveIntegrityError):
                drain_bounded(repository,lambda *a,**kw:bad,execute=True,origin_id=TRIAL_ORIGIN)
            self.assertEqual(repository.acknowledged,[])

    def test_raw_worker_selects_trial_auth_only_and_passes_exact_scope(self):
        env=environment()|{'TRADEBOT_PP_SEALED_ARCHIVE':'true'}
        with (patch.dict(archive.os.environ,env,clear=True),patch.object(archive.signal,'signal'),
            patch.object(archive,'private_dsn'),patch('postgres.connection.connect') as local,
            patch('postgres.migrate.validate_schema'),patch.object(archive,'LifecycleRepository'),
            patch('postgres.supabase_storage.SupabaseStorageTransport.from_machine_files') as raw,
            patch.object(archive,'serve',return_value=0) as serve):
            local.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'role':'tradebot_lifecycle'}
            self.assertEqual(archive.main(['--execute']),0)
            raw.assert_called_once_with(*storage_paths(cloud_files(TRIAL_ORIGIN)),origin_id=TRIAL_ORIGIN)
            self.assertEqual(serve.call_args.kwargs['origin'],TRIAL_ORIGIN)
        with (patch.dict(archive.os.environ,environment(reader=True)|{'TRADEBOT_PP_SEALED_ARCHIVE':'true'},clear=True),
              patch.object(archive,'private_dsn') as dsn):
            self.assertEqual(archive.main(['--execute']),1); dsn.assert_not_called()

    def test_trial_raw_cycle_preserves_source_rows_and_holds_on_readback_failure(self):
        from test_pp_sealed_archive import SealedFixture
        from postgres_lifecycle_fixtures import ImmutableMemoryTransport
        from postgres.cloud_origin_binding import cloud_binding
        with patch.object(archive,'ORIGIN',TRIAL_ORIGIN):
            repo=SealedFixture(3); raw=ImmutableMemoryTransport(); raw.fail_get=True
            with self.assertRaises(ArchiveUnavailable): archive.cycle(repo,raw,origin=TRIAL_ORIGIN)
            self.assertEqual(repo.record['state'],'sealed'); self.assertEqual(repo.retire_calls,0)
            raw.fail_get=False
            result=archive.cycle(repo,raw,origin=TRIAL_ORIGIN)
            self.assertEqual(result['status'],'archived')
            self.assertTrue(all(key.startswith(cloud_binding(TRIAL_ORIGIN).raw_prefix) for key in raw.objects))
            self.assertEqual(repo.retire_calls,0)

    def test_misbound_trial_credentials_fail_before_secret_or_cloud_access(self):
        env=environment(reader=True)|{'TRADEBOT_PP_STRUCTURED_RECURRING':'true'}
        with (patch.dict(structured.os.environ,env,clear=True),patch.object(structured.signal,'signal'),
              patch.object(structured,'private_dsn') as secret,patch.object(structured,'PPHistoryConnectionFactory') as remote):
            self.assertEqual(structured.main(),1); secret.assert_not_called(); remote.assert_not_called()
        env=environment()|{'TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT':'true','TRADEBOT_PP_RETIREMENT_READBACK':'true',
                          'TRADEBOT_PP_TWO_MARKET_READBACK':'true'}
        argv=['verify','--sealed',A,'--collecting',B,'--seal-hash','a'*64,'--count','1','--two-market-window']
        with (patch.dict(retirement.os.environ,env,clear=True),patch.object(sys,'argv',argv),
              patch.object(retirement,'private_dsn') as secret,patch.object(retirement,'retirement_history_factory') as remote):
            self.assertEqual(retirement.main(),1); secret.assert_not_called(); remote.assert_not_called()

    def test_trial_verifier_uses_readonly_sql_auth_and_window_scope(self):
        env=environment(reader=True)|{'TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT':'true',
            'TRADEBOT_PP_RETIREMENT_READBACK':'true','TRADEBOT_PP_TWO_MARKET_READBACK':'true'}
        argv=['verify','--origin',TRIAL_ORIGIN,'--sealed',A,'--collecting',B,'--seal-hash','a'*64,'--count','1','--two-market-window']
        with (patch.dict(retirement.os.environ,env,clear=True),patch.object(sys,'argv',argv),
              patch.object(retirement,'private_dsn'),patch('postgres.connection.connect') as local,
              patch('postgres.migrate.validate_schema'),patch.object(retirement,'LifecycleRepository'),
              patch('postgres.pp_history_connection.PPHistoryConnectionFactory') as remote,
              patch('postgres.history_v2_transport.HistoryV2PostgresTransport') as transport,
              patch('postgres.supabase_storage.SupabaseStorageTransport.from_machine_files') as raw,
              patch.object(retirement,'RetirementTransport'),patch.object(retirement,'verify') as verify):
            local.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'role':'tradebot_lifecycle'}
            verify.return_value={'status':'fresh_readback_verified','operation_deadline_met':True}
            self.assertEqual(retirement.main(),0)
            files=cloud_files(TRIAL_ORIGIN,reader=True)
            remote.assert_called_once_with(files['TRADEBOT_PP_HISTORY_DSN_FILE'],files['TRADEBOT_PP_HISTORY_CA_FILE'],origin_id=TRIAL_ORIGIN,reader=True)
            raw.assert_called_once_with(*storage_paths(files),reader=True,origin_id=TRIAL_ORIGIN)
            self.assertEqual(transport.call_args.kwargs['expected_role'],TRIAL_READER)
            self.assertEqual(verify.call_args.kwargs['origin'],TRIAL_ORIGIN)
            self.assertIsNone(verify.call_args.kwargs['permit'])

    def test_trial_api_history_is_lazy_and_reader_only_without_writer_mounts(self):
        settings=Settings(data_mode='pp_live',origin_id=TRIAL_ORIGIN)
        with patch('postgres.supabase_storage.SupabaseStorageTransport.from_machine_files') as raw:
            reader=configured_history(settings,Mock(),{'TRADEBOT_PP_ARCHIVE_HISTORY':'true'})
            self.assertEqual(reader.origin_id,TRIAL_ORIGIN); raw.assert_not_called()
            reader.raw_factory()
            raw.assert_called_once_with(*storage_paths(cloud_files(TRIAL_ORIGIN,reader=True)),reader=True,origin_id=TRIAL_ORIGIN)
        with self.assertRaises(ValueError):
            configured_history(Settings(data_mode='pp_live',origin_id='pp-live-other'),Mock(),{'TRADEBOT_PP_ARCHIVE_HISTORY':'true'})


if __name__=='__main__':unittest.main()
