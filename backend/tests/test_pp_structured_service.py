"""Qualification of recurring PP drain scheduling independent of cloud access."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveUnavailable
from postgres.lifecycle import LifecycleHold
from postgres.pp_structured_probe import check_environment
from postgres.pp_structured_service import supervise
import postgres.pp_structured_service as service


class StructuredServiceTests(unittest.TestCase):
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
                    expected_role='tradebot_pp_history', retain_revisions=enabled == 'true')

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
