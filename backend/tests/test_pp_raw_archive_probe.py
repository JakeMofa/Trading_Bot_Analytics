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
from postgres_lifecycle_fixtures import ImmutableMemoryTransport, MemoryRepository


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

    def test_impossible_seal_or_exhausted_manifest_budget_stops_before_cloud(self):
        transport = Mock()
        with self.assertRaises(LifecycleHold):
            probe.archive_once(FakeRepository(), transport, generation_id=GENERATION,
                               expected_seal_count=3201, expected_manifest_count=0)
        self.assertFalse(transport.mock_calls)
        repository = Mock()
        pinned = probe.PinnedRepository(repository, GENERATION, 3200, 128)
        repository.archive_page.return_value = ([{'row': 1}], False)
        with self.assertRaises(LifecycleHold):
            pinned.archive_page(GENERATION, None, probe.LIMITS)
        # Recovery may still finalize the last durable manifest after restart.
        repository.archive_page.return_value = ([], False)
        self.assertEqual(pinned.archive_page(GENERATION, None, probe.LIMITS), ([], False))

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

    def test_progress_race_after_initial_review_stops_before_raw_upload(self):
        class RacingRepository(MemoryRepository):
            @contextmanager
            def structured_sync_lock(self, origin):
                self.lock_origin = origin
                yield

            def outbox(self, generation_id, limit, max_bytes=None):
                # A separate, older direct archive caller changed progress
                # after the one-shot's first review but before raw upload.
                self.catalog.append({'manifest_id': 'unexpected'})
                return []

        repository = RacingRepository()
        raw = ImmutableMemoryTransport()
        with patch.object(probe, 'ORIGIN', repository.record['origin_id']):
            with self.assertRaises(LifecycleHold):
                probe.archive_once(repository, raw,
                    generation_id=repository.generation_id,
                    expected_seal_count=len(repository.rows),
                    expected_manifest_count=0)
        self.assertEqual(repository.lock_origin, repository.record['origin_id'])
        self.assertEqual(raw.calls, [])
        self.assertEqual(len(repository.rows), 5)
        self.assertEqual(repository.record['state'], 'sealed')

    def test_no_execute_never_opens_secrets_or_cloud(self):
        with patch.object(probe, 'private_dsn') as local, redirect_stdout(io.StringIO()) as output:
            status = probe.main(['--generation-id', GENERATION,
                '--expected-seal-count', '10', '--expected-manifest-count', '0'])
        self.assertEqual(status, 1)
        self.assertIn('explicit_execute_required', output.getvalue())
        local.assert_not_called()


if __name__ == '__main__':
    unittest.main()
