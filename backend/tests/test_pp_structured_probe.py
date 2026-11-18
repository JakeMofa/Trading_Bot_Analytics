"""Default-OFF one-shot PP structured diagnostic safety regressions."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveUnavailable
from postgres.lifecycle import LifecycleHold
from postgres.pp_structured_probe import (ORIGIN, check_environment, main,
                                          private_dsn, probe_once)


GENERATION = '00000000-0000-4000-8000-000000000001'


def price(outbox_id=10):
    payload = dict(origin_id=ORIGIN, source='coinbase', symbol='BTC-USD',
                   event_id=f'tick-{outbox_id}', generation_id=GENERATION,
                   source_time='2026-11-18T00:00:01Z', source_epoch='1794960001',
                   received_at='2026-11-18T00:00:01Z',
                   available_at='2026-11-18T00:00:01Z', price='100.2300',
                   size=None, payload={'source': 'fixture'},
                   content_hash=f'{outbox_id:064x}')
    return dict(id=outbox_id, origin_id=ORIGIN, generation_id=GENERATION,
                entity_type='core.current_prices',
                entity_id='["pp-live-pp","coinbase","BTC-USD"]',
                content_hash=payload['content_hash'], payload=payload)


class CountConnection:
    def __init__(self, total):
        self.total = total

    def execute(self, query, params):
        assert 'ops.outbox' in query and params == (ORIGIN, 10_001)
        return self

    def fetchone(self):
        return {'total': self.total}


class Repository:
    def __init__(self, rows=None, *, state='collecting', origin=ORIGIN,
                 total=1):
        self.rows = rows if rows is not None else [price()]
        self.state, self.origin, self.total = state, origin, total
        self.acknowledged = []
        self.lock_held = False

    @contextmanager
    def transaction(self):
        assert self.lock_held
        yield CountConnection(self.total)

    @contextmanager
    def structured_sync_lock(self, origin):
        assert origin == ORIGIN and not self.lock_held
        self.lock_held = True
        try:
            yield
        finally:
            self.lock_held = False

    def generation(self, generation_id):
        assert generation_id == GENERATION and self.lock_held
        return {'origin_id': self.origin, 'state': self.state}

    def has_other_pending(self, origin, generation_id):
        return False

    def outbox(self, generation_id, limit, max_bytes):
        assert generation_id == GENERATION and self.lock_held
        assert limit == 25 and max_bytes == 256 * 1024
        return deepcopy(self.rows[:limit])

    def acknowledge(self, generation_id, records):
        assert self.lock_held
        self.acknowledged.extend(row['id'] for row in records)
        del self.rows[:len(records)]


class Transport:
    def __init__(self, *, fail_put=False, fail_read=False, corrupt=False):
        self.fail_put, self.fail_read, self.corrupt = fail_put, fail_read, corrupt
        self.calls = []
        self.remote = None

    def put_structured(self, records, *, timeout_seconds):
        self.calls.append('put')
        assert 0 < timeout_seconds <= 4
        self.remote = deepcopy(records)
        if self.fail_put:
            raise ArchiveUnavailable('ambiguous cloud commit')

    def read_structured_authenticated(self, records, *, max_bytes,
                                      timeout_seconds):
        self.calls.append('read')
        assert max_bytes == 256 * 1024 and 0 < timeout_seconds <= 4
        if self.fail_read:
            raise ArchiveUnavailable('cloud readback failed')
        result = deepcopy(self.remote)
        if self.corrupt:
            result[0]['payload']['price'] = '999.0000'
        return result


def run(repository, transport, first_id=10, state='collecting'):
    return probe_once(repository, transport, generation_id=GENERATION,
                      expected_state=state, expected_first_id=first_id)


class ProbeTests(unittest.TestCase):
    def test_success_is_one_bounded_cycle_after_fresh_readback(self):
        repo, transport = Repository(), Transport()
        result = run(repo, transport)
        self.assertEqual(result['acknowledged'], 1)
        self.assertEqual(result['bounds'], dict(rows=25, decoded_bytes=256 * 1024,
                                                cloud_operations=2, seconds=20))
        self.assertEqual(result['retirement'], 'off')
        self.assertEqual(transport.calls, ['put', 'read'])
        self.assertEqual(repo.acknowledged, [10])
        self.assertFalse(repo.lock_held)

    def test_sealed_generation_uses_same_bounded_recheck(self):
        repo, transport = Repository(state='sealed'), Transport()
        self.assertEqual(run(repo, transport, state='sealed')['acknowledged'], 1)
        self.assertEqual(transport.calls, ['put', 'read'])

    def test_changed_identity_state_first_id_and_backlog_hold_before_cloud(self):
        cases = ((dict(origin='generated-pp'), 10, 'collecting'),
                 (dict(state='sealed'), 10, 'collecting'),
                 (dict(), 11, 'collecting'),
                 (dict(total=10_001), 10, 'collecting'))
        for kwargs, first_id, expected_state in cases:
            with self.subTest(kwargs=kwargs, first_id=first_id):
                repo, transport = Repository(**kwargs), Transport()
                with self.assertRaises(LifecycleHold):
                    run(repo, transport, first_id, expected_state)
                self.assertEqual(transport.calls, [])
                self.assertEqual(repo.acknowledged, [])
                self.assertFalse(repo.lock_held)

    def test_failed_or_corrupt_cloud_readback_never_acks_and_retry_can_reconcile(self):
        for fault, expected in (('fail_put', ArchiveUnavailable),
                                ('fail_read', ArchiveUnavailable),
                                ('corrupt', ArchiveIntegrityError)):
            with self.subTest(fault=fault):
                repo, transport = Repository(), Transport(**{fault: True})
                with self.assertRaises(expected):
                    run(repo, transport)
                self.assertEqual(repo.acknowledged, [])
                self.assertEqual(len(repo.rows), 1)
                self.assertFalse(repo.lock_held)
                transport.fail_put = transport.fail_read = transport.corrupt = False
                self.assertEqual(run(repo, transport)['acknowledged'], 1)

    def test_wrong_generation_and_invalid_targets_do_not_import(self):
        repo, transport = Repository(), Transport()
        for generation, first_id, state in (('bad', 10, 'collecting'),
                                            ('AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', 10, 'collecting'),
                                            (GENERATION, 0, 'collecting'),
                                            (GENERATION, True, 'collecting'),
                                            (GENERATION, 10, 'retired')):
            with self.subTest(generation=generation, first_id=first_id, state=state):
                with self.assertRaises(ValueError):
                    probe_once(repo, transport, generation_id=generation,
                               expected_state=state, expected_first_id=first_id)
        self.assertEqual(transport.calls, [])

    def test_environment_requires_exact_pp_identity_and_all_off_flags(self):
        good = dict(TRADEBOT_ENVIRONMENT='preprod', TRADEBOT_DATA_MODE='pp_live',
                    TRADEBOT_ORIGIN_ID=ORIGIN,
                    TRADEBOT_PP_STRUCTURED_ONE_SHOT='true',
                    TRADEBOT_DATABASE_DSN_FILE='/run/secrets/lifecycle_dsn')
        check_environment(good)
        for key, value in (('TRADEBOT_ORIGIN_ID', 'pp-live-other'),
                           ('TRADEBOT_DATA_MODE', 'generated'),
                           ('TRADEBOT_PP_STRUCTURED_ONE_SHOT', 'false'),
                           ('TRADEBOT_DATABASE_DSN_FILE', '/tmp/other'),
                           ('ENABLE_SUPABASE_SYNC', 'true'),
                           ('TRADEBOT_RETIREMENT_ENABLED', 'true'),
                           ('ENABLE_OPENAI_ANALYST', 'true')):
            with self.subTest(key=key):
                changed = dict(good, **{key: value})
                with self.assertRaises(LifecycleHold):
                    check_environment(changed)

    def test_no_execute_stops_without_reading_secrets(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(['--generation-id', GENERATION,
                           '--expected-state', 'collecting',
                           '--expected-first-outbox-id', '10'], environ={})
        self.assertEqual(result, 1)
        self.assertIn('explicit_execute_required', output.getvalue())

    def test_private_dsn_rejects_symlink_and_public_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dsn'
            path.write_text('generated-test-value')
            path.chmod(0o600)
            self.assertEqual(private_dsn(path), 'generated-test-value')
            path.chmod(0o644)
            with self.assertRaises(LifecycleHold):
                private_dsn(path)
            path.chmod(0o600)
            link = Path(folder) / 'link'
            link.symlink_to(path)
            with self.assertRaises(LifecycleHold):
                private_dsn(link)


if __name__ == '__main__':
    unittest.main()
