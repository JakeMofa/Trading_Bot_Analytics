"""Exact, finite envelope repair without cloud access or local mutation."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit
from postgres.pp_revision_backfill import LocalPages, backfill, inventory
from postgres.pp_structured_probe import retain_revisions
from postgres.lifecycle import LifecycleHold


def pages_for(rows):
    return lambda after: deepcopy([row for row in rows if row['id'] > after][:50])


class BackfillTests(unittest.TestCase):
    def test_local_pages_reject_unacknowledged_or_other_origin_before_cloud(self):
        generation = '00000000-0000-4000-8000-000000000001'
        factory = MagicMock()
        db = factory.return_value.__enter__.return_value
        db.execute.return_value.fetchone.return_value = {'origin_id': 'pp-live-pp', 'state': 'collecting'}
        reader = LocalPages(factory, generation, 7)
        for row in (dict(id=7, origin_id='pp-live-pp', acknowledged_at=None),
                    dict(id=7, origin_id='production', acknowledged_at='2026-11-19')):
            with patch('postgres.pp_revision_backfill.LifecycleRepository._pending', return_value=[row]):
                with self.assertRaises(LifecycleHold):
                    reader(0)
        db.execute.assert_any_call('SET TRANSACTION READ ONLY')
        db.execute.return_value.fetchone.return_value = {'origin_id': 'production', 'state': 'collecting'}
        with self.assertRaises(LifecycleHold):
            reader(0)

    def execute(self, rows, transport=None, **kwargs):
        pages = pages_for(rows)
        scope, _ = inventory(pages, rows[-1]['id'])
        remote = transport or Mock()
        if transport is None:
            remote.read_revisions.side_effect = lambda ids, **kw: [row for row in rows if row['id'] in ids]
        result = backfill(pages, remote, rows[-1]['id'],
            expected_count=scope['rows'], expected_sha256=scope['sha256'], **kwargs)
        return result, remote

    def test_exact_5268_rows_cross_pages_fresh_readback_no_local_ack(self):
        rows = [dict(id=i, payload={'price': '100.2300', 'source_time': str(i)})
                for i in range(1, 5269)]
        result, remote = self.execute(rows)
        self.assertEqual((result['verified_rows'], result['pages'], result['cloud_operations']),
                         (5268, 106, 212))
        self.assertEqual(remote.backfill_verified_revisions.call_count, 106)
        self.assertEqual(remote.read_revisions.call_count, 106)
        self.assertEqual(remote.backfill_verified_revisions.call_args.kwargs, {'timeout_seconds': 4})
        self.assertEqual(result['local_ack_changes'], 0)
        self.assertEqual(result['projection_changes'], 0)
        self.assertFalse(result['retirement_authorized'])

    def test_wrong_reviewed_digest_has_no_cloud_calls(self):
        remote = Mock()
        with self.assertRaises(ArchiveIntegrityError):
            backfill(pages_for([dict(id=7)]), remote, 7,
                     expected_count=1, expected_sha256='0' * 64)
        self.assertEqual(remote.mock_calls, [])

    def test_changed_local_page_has_no_cloud_calls(self):
        pages = Mock(side_effect=[[dict(id=7, payload='original')],
                                  [dict(id=7, payload='changed')]])
        scope, _ = inventory(pages_for([dict(id=7, payload='original')]), 7)
        remote = Mock()
        with self.assertRaises(ArchiveIntegrityError):
            backfill(pages, remote, 7, expected_count=1, expected_sha256=scope['sha256'])
        self.assertEqual(remote.mock_calls, [])

    def test_corrupt_or_missing_readback_stops_before_next_page(self):
        rows = [dict(id=i, price='1.0000') for i in range(1, 52)]
        for returned in ([], [dict(id=1, price='1')]):
            remote = Mock()
            remote.read_revisions.return_value = returned
            with self.assertRaises(ArchiveIntegrityError):
                self.execute(rows, remote)
            self.assertEqual(remote.backfill_verified_revisions.call_count, 1)

    def test_partial_cloud_commit_retry_preserves_original_scope(self):
        rows = [dict(id=i, price='1.0000') for i in range(1, 52)]
        remote = Mock()
        remote.read_revisions.side_effect = [rows[:50], ArchiveLimit('injected deadline')]
        with self.assertRaises(ArchiveLimit):
            self.execute(rows, remote)
        first = list(remote.backfill_verified_revisions.call_args_list)
        remote.reset_mock(side_effect=True)
        remote.read_revisions.side_effect = lambda ids, **kw: [row for row in rows if row['id'] in ids]
        result, _ = self.execute(rows, remote)
        self.assertEqual(result['verified_rows'], 51)
        self.assertEqual(remote.backfill_verified_revisions.call_args_list, first)

    def test_inventory_rejects_missing_upper_id_disorder_and_oversize(self):
        for pages, through, error in (
            (lambda after: [], 3, ArchiveIntegrityError),
            (lambda after: [dict(id=2), dict(id=1)], 2, ArchiveIntegrityError),
            (lambda after: [dict(id=3)], 2, ArchiveIntegrityError),
            (lambda after: [dict(id=1, payload='p' * (256 * 1024))], 1, ArchiveLimit),
        ):
            with self.subTest(through=through, error=error):
                with self.assertRaises(error):
                    inventory(pages, through)

    def test_total_deadline_prevents_remote_operation(self):
        rows = [dict(id=7)]
        scope, _ = inventory(pages_for(rows), 7)
        remote = Mock()
        ticks = iter([0, 0, 0, 1800])
        with self.assertRaises(ArchiveLimit):
            backfill(pages_for(rows), remote, 7, expected_count=1,
                     expected_sha256=scope['sha256'], clock=lambda: next(ticks))
        self.assertEqual(remote.mock_calls, [])

    def test_capture_is_default_off_and_requires_exact_opt_in(self):
        self.assertFalse(retain_revisions({}))
        self.assertFalse(retain_revisions({'TRADEBOT_PP_RETAIN_REVISIONS': 'false'}))
        self.assertTrue(retain_revisions({'TRADEBOT_PP_RETAIN_REVISIONS': 'true'}))
        for value in ('TRUE', '1', '', True):
            with self.assertRaises(LifecycleHold):
                retain_revisions({'TRADEBOT_PP_RETAIN_REVISIONS': value})


if __name__ == '__main__':
    unittest.main()
