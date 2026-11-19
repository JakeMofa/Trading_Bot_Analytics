from dataclasses import replace
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from types import SimpleNamespace
import uuid
import unittest
from unittest.mock import Mock, patch

from postgres.archive_codec import ArchiveLimit, ArchiveLimits, CycleBudget
from postgres.pp_retirement_verify import TwoMarketReadbackLimits, bound_seal_window, Target, verify
from postgres.lifecycle import LifecycleHold


class ScopedWindowTests(unittest.TestCase):
    def test_rehearsal_limits_leave_other_cycles_unchanged(self):
        limits = TwoMarketReadbackLimits()
        self.assertEqual((limits.max_requests, limits.max_seconds, limits.max_cycle_bytes),
                         (192, 240, 128 * 1024**2))
        self.assertEqual(limits.request_timeout_seconds, 4)
        self.assertEqual(replace(limits, max_rows=7).max_rows, 7)
        for change in ({'max_requests':193}, {'max_seconds':241}, {'max_rows':501}):
            with self.assertRaises(ValueError):
                replace(limits, **change)
        ordinary = ArchiveLimits()
        self.assertEqual((ordinary.max_requests, ordinary.max_seconds, ordinary.max_cycle_bytes),
                         (24, 20, 16 * 1024**2))

    def test_verification_deadline_charges_time_since_database_seal(self):
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        db = Mock()
        db.execute.return_value.fetchone.return_value = {'checked_at':now}
        clock = Mock(return_value=10.25)
        budget = CycleBudget(TwoMarketReadbackLimits(), clock=clock)
        sealed = {'sealed_at':now - timedelta(seconds=1795)}
        wall_end, monotonic_end = bound_seal_window(db,sealed,budget,10)
        self.assertEqual((wall_end, monotonic_end, budget.deadline),
                         (now+timedelta(seconds=5),15,15))
        clock.return_value = 15
        with self.assertRaises(ArchiveLimit):
            budget.request()


class OppositeSlotReadbackTests(unittest.TestCase):
    def exercise(self, sealed_slot, active_slot, *, offset=0, active_id=None):
        now = datetime.now(timezone.utc)
        sealed, collecting = str(uuid.uuid4()), str(uuid.uuid4())
        target = Target(sealed, collecting, 'a' * 64, 1)
        generation = {'generation_id': sealed, 'origin_id': 'generated-symmetric-readback',
                      'slot': sealed_slot, 'sealed_at': now - timedelta(seconds=5),
                      'seal_count': 1, 'seal_hash': target.seal_hash}
        db = Mock()
        def query(sql, *args):
            if 'clock_timestamp() AS checked_at' in sql:
                return Mock(fetchone=lambda: {'checked_at': now})
            if 'SELECT started_at' in sql:
                return Mock(fetchone=lambda: {'started_at': generation['sealed_at'] +
                                             timedelta(seconds=offset)})
            return Mock()
        db.execute.side_effect = query
        @contextmanager
        def retirement(_sealed):
            self.assertEqual(_sealed, sealed)
            yield db, generation, []
        repository = SimpleNamespace(environment='preprod', retirement=retirement)
        transport = SimpleNamespace(origin_id=generation['origin_id'], generation_id=sealed)
        samples = [dict(generation_id=active_id or collecting, slot=active_slot, committed_rows=n)
                   for n in (1, 2)]
        with patch('postgres.pp_retirement_verify.bound_catalog', return_value=True), \
             patch('postgres.pp_retirement_verify.active_sample', side_effect=samples), \
             patch('postgres.pp_retirement_verify.inventory', return_value={'fit': 'fits'}), \
             patch('postgres.pp_retirement_verify.ArchiveWorker') as worker:
            worker.return_value.fresh_retirement_readback.return_value = {}
            result = verify(repository, transport, target, limits=TwoMarketReadbackLimits(),
                            origin=generation['origin_id'])
            worker.return_value.fresh_retirement_readback.assert_called_once()
        return result

    def test_exact_handoffs_are_symmetric(self):
        for sealed, active in (('A', 'B'), ('B', 'A')):
            with self.subTest(sealed=sealed):
                result = self.exercise(sealed, active)
                self.assertEqual(result['status'], 'fresh_readback_verified')
                self.assertEqual(result['opposite_slot_new_rows'], 1)
                self.assertTrue(result['seal_deadline_met'])
                self.assertFalse(result['retirement_authorized'])

    def test_later_same_slot_or_unrelated_generation_is_not_handoff(self):
        for sealed, active, offset, active_id in (
                ('A', 'B', 1, None), ('B', 'A', -1, None), ('B', 'B', 0, None),
                ('B', 'A', 0, str(uuid.uuid4()))):
            with self.subTest(sealed=sealed, active=active, offset=offset), \
                    self.assertRaises(LifecycleHold):
                self.exercise(sealed, active, offset=offset, active_id=active_id)
