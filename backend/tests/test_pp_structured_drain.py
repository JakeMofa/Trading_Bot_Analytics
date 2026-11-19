"""Network-free bounded PP structured drainage; no service is enabled."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded
from postgres.lifecycle import LifecycleHold
from postgres.pp_structured_drain import DrainLimits, drain_bounded

ORIGIN = 'pp-live-pp'
A = '00000000-0000-4000-8000-000000000001'
B = '00000000-0000-4000-8000-000000000002'


def price(outbox_id, generation_id):
    row = dict(origin_id=ORIGIN, source='coinbase', symbol='BTC-USD',
               event_id=f'tick-{outbox_id}', generation_id=generation_id,
               source_time=f'2026-11-18T00:00:{outbox_id:02d}Z',
               source_epoch=str(1794960000 + outbox_id),
               received_at=f'2026-11-18T00:00:{outbox_id:02d}Z',
               available_at=f'2026-11-18T00:00:{outbox_id:02d}Z',
               price='100.2300', size=None, payload={'source': 'fixture'},
               content_hash=f'{outbox_id:064x}')
    return {'id': outbox_id, 'origin_id': ORIGIN, 'generation_id': generation_id,
            'entity_type': 'core.current_prices',
            'entity_id': encoded([ORIGIN, 'coinbase', 'BTC-USD']).decode(),
            'content_hash': row['content_hash'], 'payload': row}


class Repository:
    pending_outbox_limit = 10_000

    def __init__(self):
        self.rows = {A: [price(1, A)], B: [price(2, B)]}
        self.acknowledged = []
        self.lock = threading.Lock()

    def structured_pending_generations(self, origin_id):
        assert origin_id == ORIGIN
        return [{'generation_id': generation, 'state': state,
                 'first_id': rows[0]['id']}
                for generation, state in ((A, 'sealed'), (B, 'collecting'))
                if (rows := self.rows[generation])]

    @contextmanager
    def structured_sync_lock(self, origin_id):
        assert origin_id == ORIGIN
        if not self.lock.acquire(blocking=False):
            raise LifecycleHold('another structured worker is active')
        try:
            yield
        finally:
            self.lock.release()

    def generation(self, generation_id):
        return {'origin_id': ORIGIN,
                'state': 'sealed' if generation_id == A else 'collecting'}

    def has_other_pending(self, origin_id, generation_id):
        return any(rows for key, rows in self.rows.items() if key != generation_id)

    def outbox(self, generation_id, limit, max_bytes):
        return deepcopy(self.rows[generation_id][:limit])

    def acknowledge(self, generation_id, records):
        self.acknowledged.extend(record['id'] for record in records)
        del self.rows[generation_id][:len(records)]


class Transport:
    def __init__(self):
        self.calls = []
        self.remote = None
        self.failure = None

    def put_structured(self, records, *, timeout_seconds):
        self.calls.append('put')
        if self.failure == 'put':
            raise ArchiveUnavailable('generated cloud outage')
        self.remote = deepcopy(records)

    def read_structured_authenticated(self, records, *, max_bytes,
                                      timeout_seconds):
        self.calls.append('read')
        if self.failure == 'read':
            raise ArchiveUnavailable('generated readback failure')
        value = deepcopy(self.remote)
        if self.failure == 'corrupt':
            value[0]['payload']['price'] = 'wrong'
        return value


class BoundedDrainTests(unittest.TestCase):
    def test_default_off_and_changed_cap_make_no_cloud_call(self):
        repository, calls = Repository(), []
        factory = lambda generation, *, timeout_seconds: calls.append(generation) or Transport()
        with self.assertRaises(LifecycleHold):
            drain_bounded(repository, factory)
        repository.pending_outbox_limit = 10_001
        with self.assertRaises(LifecycleHold):
            drain_bounded(repository, factory, execute=True)
        self.assertEqual(calls, [])
        self.assertEqual(repository.acknowledged, [])

    def test_sealed_a_then_active_b_with_fresh_readback(self):
        repository, transports, handoffs = Repository(), [], []
        def factory(generation, *, timeout_seconds):
            self.assertGreaterEqual(timeout_seconds, 5)
            self.assertLessEqual(timeout_seconds, 20)
            transport = Transport()
            transports.append((generation, transport))
            return transport
        result = drain_bounded(repository, factory, execute=True,
                               sleep=lambda seconds: handoffs.append(seconds))
        self.assertEqual(result['status'], 'drained')
        self.assertEqual(result['acknowledged'], 2)
        self.assertEqual(result['cloud_operations'], 4)
        self.assertEqual([generation for generation, _ in transports], [A, B])
        self.assertEqual([transport.calls for _, transport in transports],
                         [['put', 'read'], ['put', 'read']])
        self.assertEqual(repository.acknowledged, [1, 2])
        self.assertEqual(handoffs, [0.1, 0.1])

    def test_outage_and_corrupt_readback_preserve_pending(self):
        for failure in ('put', 'read', 'corrupt'):
            with self.subTest(failure=failure):
                repository, transport = Repository(), Transport()
                transport.failure = failure
                with self.assertRaises((ArchiveUnavailable, ArchiveIntegrityError)):
                    drain_bounded(repository, lambda _, **kwargs: transport, execute=True)
                self.assertEqual(repository.acknowledged, [])
                self.assertEqual(len(repository.rows[A]), 1)

    def test_cycle_limit_stops_without_extra_cloud_call(self):
        repository, transports = Repository(), []
        def factory(_, *, timeout_seconds):
            transport = Transport()
            transports.append(transport)
            return transport
        result = drain_bounded(repository, factory, execute=True,
                               limits=DrainLimits(max_cycles=1,
                                                  max_cloud_operations=2),
                               sleep=lambda _: None)
        self.assertEqual(result['status'], 'bounded_stop')
        self.assertEqual(result['acknowledged'], 1)
        self.assertEqual(len(transports), 1)
        self.assertEqual(repository.acknowledged, [1])
        self.assertEqual(len(repository.rows[B]), 1)

    def test_row_limit_stops_without_touching_new_generation(self):
        repository, calls = Repository(), []
        def factory(generation, *, timeout_seconds):
            calls.append(generation)
            return Transport()
        result = drain_bounded(repository, factory, execute=True,
                               limits=DrainLimits(max_rows=1), sleep=lambda _: None)
        self.assertEqual(result['status'], 'bounded_stop')
        self.assertEqual(result['acknowledged'], 1)
        self.assertEqual(calls, [A])
        self.assertEqual(repository.acknowledged, [1])

    def test_other_worker_ack_between_selection_and_origin_lock_reselects(self):
        class ConcurrentAck(Repository):
            raced = False

            def outbox(self, generation_id, limit, max_bytes):
                if generation_id == A and not self.raced:
                    self.raced = True
                    # Simulate a different worker's durable ACK after our
                    # selector ran but before this worker read the page.
                    self.rows[A].clear()
                    return []
                return super().outbox(generation_id, limit, max_bytes)

        repository, transports = ConcurrentAck(), []
        def factory(generation, *, timeout_seconds):
            transport = Transport()
            transports.append((generation, transport))
            return transport
        result = drain_bounded(repository, factory, execute=True,
                               sleep=lambda _: None)
        self.assertEqual(result['status'], 'drained')
        self.assertEqual(result['acknowledged'], 1)
        self.assertEqual(result['cloud_operations'], 2)
        self.assertEqual([generation for generation, _ in transports], [A, B])
        self.assertEqual(transports[0][1].calls, [])
        self.assertEqual(transports[1][1].calls, ['put', 'read'])
        self.assertEqual(repository.acknowledged, [2])

    def test_repeated_idle_selection_has_finite_stop_and_zero_false_ack(self):
        class AlwaysRaced(Repository):
            def outbox(self, generation_id, limit, max_bytes):
                return []

        repository, calls = AlwaysRaced(), []
        result = drain_bounded(repository,
            lambda generation, **kwargs: calls.append(generation) or Transport(),
            execute=True, limits=DrainLimits(max_cycles=3), sleep=lambda _: None)
        self.assertEqual(result['status'], 'bounded_stop')
        self.assertEqual(result['acknowledged'], 0)
        self.assertEqual(result['cloud_operations'], 0)
        self.assertEqual(result['cycles'], 3)
        self.assertEqual(calls, [A, A, A])
        self.assertEqual(repository.acknowledged, [])

    def test_wrong_selector_order_holds_before_cloud_call(self):
        repository, calls = Repository(), []
        original = repository.structured_pending_generations
        repository.structured_pending_generations = lambda origin: list(reversed(original(origin)))
        with self.assertRaisesRegex(LifecycleHold, 'sealed structured backlog'):
            drain_bounded(repository, lambda generation, **kwargs: calls.append(generation),
                          execute=True)
        self.assertEqual(calls, [])
        self.assertEqual(repository.acknowledged, [])

    def test_late_cycle_return_reports_ambiguous_ack(self):
        repository, ticks = Repository(), [0.0]
        def clock(): return ticks[0]
        class SlowTransport(Transport):
            def read_structured_authenticated(self, records, *, max_bytes,
                                              timeout_seconds):
                value = super().read_structured_authenticated(
                    records, max_bytes=max_bytes, timeout_seconds=timeout_seconds)
                # The mock advances only the outer session clock; the worker's
                # own real monotonic deadline still permits its durable ACK.
                ticks[0] = 181.0
                return value
        with self.assertRaisesRegex(ArchiveLimit, 'reconcile ACK'):
            drain_bounded(repository, lambda _, **kwargs: SlowTransport(),
                          execute=True, clock=clock)
        self.assertEqual(repository.acknowledged, [1])
        self.assertEqual(len(repository.rows[B]), 1)

    def test_expired_session_stops_before_transport_creation(self):
        repository, calls = Repository(), []
        ticks = iter([0.0, 171.0, 171.0])
        result = drain_bounded(repository, lambda _, **kwargs: calls.append(1),
                               execute=True, clock=lambda: next(ticks))
        self.assertEqual(result['status'], 'bounded_stop')
        self.assertEqual(calls, [])

    def test_unreviewed_limits_rejected(self):
        for kwargs in ({'max_cycles': 13}, {'max_rows': 301},
                       {'max_cloud_operations': 25}, {'max_seconds': 181},
                       {'max_cycle_rows': 51}, {'handoff_seconds': 1},
                       {'max_cycles': True}, {'max_seconds': float('nan')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DrainLimits(**kwargs)
