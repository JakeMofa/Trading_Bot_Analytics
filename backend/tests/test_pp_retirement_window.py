from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from postgres.archive_codec import ArchiveLimit, ArchiveLimits, CycleBudget
from postgres.pp_retirement_verify import TwoMarketReadbackLimits, bound_seal_window


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
