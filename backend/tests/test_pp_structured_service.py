"""Qualification of recurring PP drain scheduling independent of cloud access."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from postgres.lifecycle import LifecycleHold
from postgres.pp_structured_probe import check_environment
from postgres.pp_structured_service import supervise
import postgres.pp_structured_service as service


class StructuredServiceTests(unittest.TestCase):
    def test_opt_in_reuse_selects_single_session_and_closes_on_stop(self):
        with (patch.dict(service.os.environ, {'TRADEBOT_PP_REUSE_HISTORY_SESSION':'true'}),
              patch.object(service.signal, 'signal'),
              patch.object(service, 'check_environment'),
              patch.object(service, 'private_dsn'),
              patch.object(service, 'connect') as connection,
              patch.object(service, 'validate_schema'),
              patch.object(service, 'LifecycleRepository'),
              patch.object(service, 'PPHistoryConnectionFactory') as cold,
              patch.object(service, 'ReusablePPHistoryConnectionFactory') as reused,
              patch.object(service, 'supervise', return_value=0)):
            connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'login':'tradebot_lifecycle'}
            self.assertEqual(service.main(), 0)
            cold.assert_not_called()
            reused.assert_called_once_with()
            reused.return_value.close.assert_called_once_with()

    def test_recurring_runtime_binds_explicit_capture_without_raising_other_flags(self):
        for enabled in ('true', 'false'):
            with (self.subTest(enabled=enabled),
                  patch.dict(service.os.environ, {'TRADEBOT_PP_RETAIN_REVISIONS': enabled}),
                  patch.object(service.signal, 'signal'),
                  patch.object(service, 'check_environment'),
                  patch.object(service, 'private_dsn'),
                  patch.object(service, 'connect') as connection,
                  patch.object(service, 'validate_schema'),
                  patch.object(service, 'LifecycleRepository'),
                  patch.object(service, 'PPHistoryConnectionFactory') as remote,
                  patch.object(service, 'HistoryV2PostgresTransport') as transport,
                  patch.object(service, 'drain_bounded') as drain,
                  patch.object(service, 'supervise') as supervisor):
                connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'login': 'tradebot_lifecycle'}
                drain.side_effect = lambda repo, factory, **kw: factory('generation', timeout_seconds=20)
                supervisor.side_effect = lambda page, *_: (page(), 0)[1]
                self.assertEqual(service.main(), 0)
                transport.assert_called_once_with(remote.return_value, origin_id='pp-live-pp',
                    generation_id='generation', expected_database='postgres',
                    expected_role='tradebot_pp_history', retain_revisions=enabled == 'true',
                    sync_barriers=False)

    def test_sync_selection_is_strict_default_off_and_trial_revision_only(self):
        for env in ({}, {'TRADEBOT_PP_SYNC_BARRIERS':'false'}):
            self.assertFalse(service.synchronized_batches_requested(env, origin='pp-live-pp', retain_revisions=False))
        self.assertTrue(service.synchronized_batches_requested({'TRADEBOT_PP_SYNC_BARRIERS':'true'},
            origin=service.TRIAL_ORIGIN, retain_revisions=True))
        for value, origin, capture in [('True',service.TRIAL_ORIGIN,True), ('1',service.TRIAL_ORIGIN,True),
                ('yes',service.TRIAL_ORIGIN,True), ('true','pp-live-pp',True), ('true',service.TRIAL_ORIGIN,False)]:
            with self.subTest(value=value,origin=origin,capture=capture), self.assertRaises(ArchiveIntegrityError):
                service.synchronized_batches_requested({'TRADEBOT_PP_SYNC_BARRIERS':value},
                    origin=origin, retain_revisions=capture)

    def test_second_exact_trial_uses_same_measured_sync_contract(self):
        from postgres.cloud_origin_binding import NEXT_TRIAL_ORIGIN
        self.assertTrue(service.synchronized_batches_requested({'TRADEBOT_PP_SYNC_BARRIERS':'true'},
            origin=NEXT_TRIAL_ORIGIN, retain_revisions=True))
        for origin in ('pp-live-pp-trial-20261119-03','pp-live-pp-trial-anything'):
            with self.subTest(origin=origin),self.assertRaises(ArchiveIntegrityError):
                service.synchronized_batches_requested({'TRADEBOT_PP_SYNC_BARRIERS':'true'},
                    origin=origin, retain_revisions=True)

    def test_sync_misuse_holds_before_secret_or_connection_access(self):
        for value, origin, capture in [('True',service.TRIAL_ORIGIN,'true'),
                ('true','pp-live-pp','true'), ('true',service.TRIAL_ORIGIN,'false')]:
            with (self.subTest(value=value,origin=origin,capture=capture),
                  patch.dict(service.os.environ, {'TRADEBOT_PP_SYNC_BARRIERS':value,
                      'TRADEBOT_PP_RETAIN_REVISIONS':capture},clear=True),
                  patch.object(service.signal,'signal'),
                  patch.object(service,'selected_cloud_origin',return_value=origin),
                  patch.object(service,'check_environment'), patch.object(service,'require_trial_files'),
                  patch.object(service,'private_dsn') as secret, patch.object(service,'connect') as connect,
                  patch.object(service,'PPHistoryConnectionFactory') as cold,
                  patch.object(service,'ReusablePPHistoryConnectionFactory') as reused):
                self.assertEqual(service.main(),1)
                secret.assert_not_called();connect.assert_not_called()
                cold.assert_not_called();reused.assert_not_called()

    def test_trial_recurring_binds_measured_modes_and_reports_readiness(self):
        env=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
            TRADEBOT_ORIGIN_ID=service.TRIAL_ORIGIN,TRADEBOT_PP_WINDOW_POLICY='two-official-markets-cycle',
            TRADEBOT_PP_CYCLE_INITIAL_A='94107d29-626f-480a-b61a-ce6a10f44301',
            TRADEBOT_DATABASE_DSN_FILE='/run/secrets/lifecycle_dsn',TRADEBOT_PP_STRUCTURED_RECURRING='true',
            TRADEBOT_PP_RETAIN_REVISIONS='true',TRADEBOT_PP_SYNC_BARRIERS='true',
            TRADEBOT_PP_REUSE_HISTORY_SESSION='true',
            TRADEBOT_PP_HISTORY_DSN_FILE='/run/secrets/pp_trial_history_writer_dsn',
            TRADEBOT_PP_HISTORY_CA_FILE='/run/secrets/pp_history_ca')
        with (patch.dict(service.os.environ,env,clear=True), patch.object(service.signal,'signal'),
              patch.object(service,'private_dsn'), patch.object(service,'connect') as connection,
              patch.object(service,'validate_schema'), patch.object(service,'LifecycleRepository'),
              patch.object(service,'PPHistoryConnectionFactory') as cold,
              patch.object(service,'ReusablePPHistoryConnectionFactory') as reused,
              patch.object(service,'HistoryV2PostgresTransport') as transport,
              patch.object(service,'drain_bounded') as drain, patch.object(service,'supervise') as supervisor,
              patch('builtins.print') as output):
            connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'login':'tradebot_lifecycle'}
            drain.side_effect=lambda repo,factory,**kw:factory('generation',timeout_seconds=20)
            supervisor.side_effect=lambda page,*_: (page(),0)[1]
            self.assertEqual(service.main(),0)
            cold.assert_not_called()
            reused.assert_called_once_with(env['TRADEBOT_PP_HISTORY_DSN_FILE'],env['TRADEBOT_PP_HISTORY_CA_FILE'],origin_id=service.TRIAL_ORIGIN)
            transport.assert_called_once_with(reused.return_value,origin_id=service.TRIAL_ORIGIN,
                generation_id='generation',expected_database='postgres',expected_role=service.cloud_binding(service.TRIAL_ORIGIN).writer_role,
                retain_revisions=True,sync_barriers=True)
            reused.return_value.close.assert_called_once_with()
            import json
            self.assertEqual(json.loads(output.call_args_list[-2].args[0]),
                dict(status='structured_worker_modes',sync_barriers=True,session_reuse=True))
            self.assertEqual(json.loads(output.call_args.args[0]),dict(status='structured_worker_ready'))
            # Feed actual producer output through both unchanged controller
            # startup paths, rather than supplying an invented readiness line.
            from contextlib import nullcontext
            from types import SimpleNamespace
            from unittest.mock import MagicMock
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'deploy/preprod'))
            import trial_cloud_control as trial
            import structured_probe_control as legacy
            raw=('\n'.join(call.args[0] for call in output.call_args_list)+'\n').encode()
            ctx=SimpleNamespace(image='sha256:'+'b'*64,
                request=SimpleNamespace(source_sha='a'*40,controller_sha256='c'*64))
            actions=MagicMock();actions.attempt_id='d'*32
            row=dict(Id='e'*64,State=dict(Running=True))
            with (patch.object(legacy,'_require_stopped'),patch.object(legacy,'_write_sync_owner'),
                  patch.object(legacy,'_stage_local_secret',return_value=nullcontext()),
                  patch.object(trial,'preflight',return_value=(ctx,actions,'generation','c'*64,{})),
                  patch.object(trial,'_compose'),patch.object(trial,'_inspect_worker',return_value=row),
                  patch.object(trial.Budget,'run',return_value=raw),patch.object(trial.time,'sleep') as wait):
                self.assertEqual(trial.start(Path('bundle'))['status'],'started')
                wait.assert_not_called()
            with (patch.object(legacy,'_require_stopped'),patch.object(legacy,'_write_sync_owner'),
                  patch.object(legacy,'_stage_local_secret',return_value=nullcontext()),
                  patch.object(legacy,'preflight',return_value=(ctx,actions,'c'*64)),
                  patch.object(legacy,'_compose'),patch.object(legacy,'_sync_container',return_value=row),
                  patch.object(legacy.Budget,'run',return_value=raw),patch('time.sleep') as wait):
                self.assertEqual(legacy.recurring_start(Path('bundle'))['status'],'started')
                wait.assert_not_called()

    def test_recurring_must_be_explicit_and_exclusive(self):
        env = dict(TRADEBOT_ENVIRONMENT='preprod', TRADEBOT_DATA_MODE='pp_live',
                   TRADEBOT_ORIGIN_ID='pp-live-pp',
                   TRADEBOT_DATABASE_DSN_FILE='/run/secrets/lifecycle_dsn')
        with self.assertRaises(LifecycleHold):
            check_environment(env, recurring=True)
        env['TRADEBOT_PP_STRUCTURED_RECURRING'] = 'true'
        check_environment(env, recurring=True)
        with self.assertRaises(LifecycleHold):
            check_environment(env)
        env['TRADEBOT_PP_STRUCTURED_ONE_SHOT'] = 'true'
        with self.assertRaises(LifecycleHold):
            check_environment(env, recurring=True)

    def test_backoff_recovers_and_resets_after_ack(self):
        page = Mock(side_effect=[ArchiveUnavailable(), ArchiveUnavailable(),
                                 dict(status='bounded_stop', acknowledged=25),
                                 ArchiveUnavailable(), dict(status='drained', acknowledged=0)])
        stop, emit = Mock(), Mock()
        stop.is_set.side_effect = [False] * 5 + [True]
        self.assertEqual(supervise(page, stop, emit), 0)
        self.assertEqual([v.args[0] for v in stop.wait.call_args_list], [1, 2, 0.1, 1, 5])
        self.assertEqual(emit.call_args_list[2].args[0]['acknowledged'], 25)

    def test_conflict_holds_without_retry_or_error_text(self):
        stop, emit = Mock(), Mock()
        stop.is_set.return_value = False
        page = Mock(side_effect=ArchiveIntegrityError('private details'))
        self.assertEqual(supervise(page, stop, emit), 1)
        page.assert_called_once()
        stop.wait.assert_not_called()
        emit.assert_called_once_with(dict(status='hold', reason='archive_integrity'))

    def test_deadline_logs_only_bounded_phase_and_page_identity(self):
        stop, emit = Mock(), Mock()
        stop.is_set.return_value = False
        error = ArchiveLimit('private details')
        error.structured_phase = 'cloud_readback'
        error.structured_page = (23, 73, 50)
        self.assertEqual(supervise(Mock(side_effect=error), stop, emit), 1)
        stop.wait.assert_not_called()
        emit.assert_called_once_with(dict(status='hold', reason='archive_limit',
            phase='cloud_readback', first_outbox_id=23, last_outbox_id=73,
            page_rows=50))
