import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy' / 'preprod'))

import profile_retained_b_page as profile


class RetainedPageProfileTests(unittest.TestCase):
    def setUp(self):
        self.records = [dict(id=i, origin_id=profile.ORIGIN, generation_id=profile.GENERATION,
                             payload={'x': str(i)}) for i in range(1001, 1501)]
        self.pin, self.body = profile.page_pin(self.records)

    def test_pin_matches_both_order_and_payload(self):
        changed = [dict(row) for row in self.records]
        changed[2]['payload'] = {'x': '2.0'}
        pin, _ = profile.page_pin(changed)
        self.assertEqual(pin['ordered_ids_sha256'], self.pin['ordered_ids_sha256'])
        self.assertNotEqual(pin['canonical_sha256'], self.pin['canonical_sha256'])
        self.assertEqual(self.pin['canonical_bytes'], len(self.body))
        with self.assertRaises(profile.ArchiveIntegrityError):
            profile.page_pin(list(reversed(self.records)))
        changed[1]['generation_id'] = 'different'
        with self.assertRaises(profile.ArchiveIntegrityError):
            profile.page_pin(changed)

    def test_explain_only_captures_deployed_history_selects_and_baseline_pin(self):
        from postgres.history_v2_latest_receipts import INDEXED_SQL
        self.assertEqual(profile.explain_family(INDEXED_SQL, None), 'indexed_latest_receipts')
        self.assertIsNone(profile.explain_family('SET TRANSACTION READ ONLY', None))
        with self.assertRaises(profile.ArchiveIntegrityError):
            profile.explain_family('SELECT 1 FROM history_v2.unknown', None)
        with self.assertRaises(profile.ArchiveIntegrityError):
            profile.explain_history(None, None, self.pin)

    def test_snapshots_fail_closed_on_reset_or_eviction(self):
        old = (('reset',0),{1: dict(calls=5,rows=2,total_exec_time=2.0)})
        new = (('reset',0),{1: dict(calls=9,rows=502,total_exec_time=11.0)})
        self.assertEqual(profile.stats_delta(old,new),
                         dict(calls=4,rows=500,server_execution_seconds=0.009))
        self.assertIsNone(profile.stats_delta(old,(('reset',1),new[1])))
        self.assertIsNone(profile.stats_delta(new,old))
        self.assertIsNone(profile.stats_delta(old,None))

    def test_cold_and_warm_share_exact_one_session_and_compare_returned_bytes(self):
        raw = object()
        @contextmanager
        def remote(**kwargs):
            yield raw
        class Reader:
            def __init__(self, checkout, times):
                self.checkout = checkout
            def read_retirement_revisions(self, records, **kwargs):
                with self.checkout(timeout_seconds=4):
                    return records, 0
        with patch.object(profile, 'ProfiledHistory', Reader), patch.object(
                profile, 'local_page', return_value=self.records):
            runs = profile.profile(None, remote, self.pin)
        self.assertEqual([r['mode'] for r in runs],
                         ['cold_session','warm_session_1','warm_session_2','warm_session_3'])
        self.assertTrue(all(r['history_sql_counters'] is None for r in runs))
        with patch.object(profile, 'local_page', return_value=self.records):
            with self.assertRaises(profile.ArchiveIntegrityError):
                profile.profile(None, remote, dict(self.pin,first_id=0))


if __name__ == '__main__':
    unittest.main()
