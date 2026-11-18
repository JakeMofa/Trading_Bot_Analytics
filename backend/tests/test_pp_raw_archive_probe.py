"""Generated fail-closed checks for the unmounted PP raw archive entrypoint."""
from contextlib import contextmanager, redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.lifecycle import LifecycleHold
from postgres import pp_raw_archive_probe as probe


GENERATION = '00000000-0000-4000-8000-000000000001'


def environment():
    return dict(probe.FILES, TRADEBOT_ENVIRONMENT='preprod',
                TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID='pp-live-pp',
                TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT='true')


class FakeRepository:
    def __init__(self, *, origin=probe.ORIGIN, state='sealed', seal_count=10,
                 manifests=0):
        self.row = {'origin_id': origin, 'state': state,
                    'seal_count': seal_count}
        self.catalog = [object()] * manifests
        self.calls = []

    @contextmanager
    def structured_sync_lock(self, origin):
        self.calls.append(('lock', origin))
        yield

    def generation(self, generation_id):
        self.calls.append(('generation', generation_id))
        return self.row

    def manifests(self, generation_id):
        self.calls.append(('manifests', generation_id))
        return self.catalog


class ProbeTests(unittest.TestCase):
    def test_environment_requires_exact_pp_identity_and_distinct_secret_files(self):
        probe.check_environment(environment())
        for change in ({'TRADEBOT_ORIGIN_ID': 'generated-pp'},
                       {'TRADEBOT_ENVIRONMENT': 'production'},
                       {'TRADEBOT_COLLECTOR_ENABLED': 'true'},
                       {'TRADEBOT_CLOUD_ENABLED': 'true'},
                       {'TRADEBOT_RETIREMENT_ENABLED': 'true'},
                       {'TRADEBOT_PP_STORAGE_API_KEY_FILE': '/tmp/key'},
                       {'TRADEBOT_PP_HISTORY_DSN_FILE': '/run/secrets/lifecycle_dsn'},
                       {'TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT': 'false'}):
            with self.subTest(change=change):
                with self.assertRaises(LifecycleHold):
                    probe.check_environment(environment() | change)
        with self.assertRaises(LifecycleHold):
            probe.check_environment(environment() | {'TRADEBOT_DATABASE_DSN': 'inline'})

    def test_invalid_target_and_changed_seal_or_progress_stop_before_worker(self):
        with patch.object(probe, 'ArchiveWorker') as worker:
            for generation, seal, manifests in (('bad', 10, 0),
                                                 (GENERATION, -1, 0),
                                                 (GENERATION, 10, 129)):
                with self.subTest(generation=generation, seal=seal):
                    with self.assertRaises(ValueError):
                        probe.archive_once(FakeRepository(), Mock(),
                            generation_id=generation, expected_seal_count=seal,
                            expected_manifest_count=manifests)
            for repo in (FakeRepository(origin='generated-pp'),
                         FakeRepository(state='collecting'),
                         FakeRepository(seal_count=11),
                         FakeRepository(manifests=1)):
                with self.subTest(row=repo.row, manifests=len(repo.catalog)):
                    with self.assertRaises(LifecycleHold):
                        probe.archive_once(repo, Mock(), generation_id=GENERATION,
                            expected_seal_count=10, expected_manifest_count=0)
            worker.assert_not_called()

    def test_bounded_cycle_never_calls_retirement(self):
        repo = FakeRepository()
        fake = Mock()
        fake.archive_cycle.return_value = dict(status='partial', outbox_rows=2,
                                              raw_rows=25)
        with patch.object(probe, 'ArchiveWorker', return_value=fake) as constructor:
            result = probe.archive_once(repo, Mock(), generation_id=GENERATION,
                expected_seal_count=10, expected_manifest_count=0)
        self.assertEqual(result['status'], 'cycle_complete')
        self.assertEqual(result['raw_coverage'], 'partial')
        self.assertEqual(result['retirement'], 'off')
        self.assertEqual(result['bounds']['rows'], 25)
        self.assertEqual(result['bounds']['seconds'], 20)
        self.assertEqual(result['bounds']['cloud_operations'], 8)
        constructor.assert_called_once()
        fake.archive_cycle.assert_called_once_with(GENERATION)
        fake.retire_generated.assert_not_called()
        self.assertIn(('lock', probe.ORIGIN), repo.calls)

    def test_no_execute_never_opens_secrets_or_cloud(self):
        with patch.object(probe, 'private_dsn') as local, redirect_stdout(io.StringIO()) as output:
            status = probe.main(['--generation-id', GENERATION,
                '--expected-seal-count', '10', '--expected-manifest-count', '0'])
        self.assertEqual(status, 1)
        self.assertIn('explicit_execute_required', output.getvalue())
        local.assert_not_called()


if __name__ == '__main__':
    unittest.main()
