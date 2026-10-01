from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect, timestamp
from history_batch import chunks, run


class HistoryBatchTests(unittest.TestCase):
    def test_chunk_boundaries_and_resume(self):
        end = timestamp('2026-10-01T02:00:00Z')
        windows = list(chunks(end, 1))
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[0][1], end)
        self.assertEqual(windows[-1][0], end - timedelta(days=1))
        db = connect(':memory:')
        calls = []
        def backfill(_db, start, finish):
            calls.append(start)
            return {'new_display_price_points': 4,
                    'missing_intervals': [], 'price_history_failures': [],
                    'resolved_markets_found': 32, 'expected_complete_intervals': 32}
        try:
            first = run(db, end, 1, backfill, lambda *args, **kwargs: None)
            second = run(db, end, 1, backfill, lambda *args, **kwargs: None)
            self.assertEqual(first['completed_chunks'], 3)
            self.assertEqual(first['new_price_points'], 12)
            self.assertEqual(second['skipped_chunks'], 3)
            self.assertEqual(len(calls), 3)
        finally:
            db.close()

    def test_missing_chunk_retries(self):
        end = timestamp('2026-10-01T02:00:00Z')
        db = connect(':memory:')
        calls = []
        def backfill(_db, start, finish):
            calls.append(start)
            return {'new_display_price_points': 0,
                    'missing_intervals': ['missing'] if start == end-timedelta(hours=8) and len(calls) == 1 else [],
                    'price_history_failures': [],
                    'resolved_markets_found': 31, 'expected_complete_intervals': 32}
        try:
            run(db, end, 1, backfill, lambda *args, **kwargs: None)
            second = run(db, end, 1, backfill, lambda *args, **kwargs: None)
            self.assertEqual(second['completed_chunks'], 1)
            self.assertEqual(second['skipped_chunks'], 2)
        finally:
            db.close()


if __name__ == '__main__': unittest.main()
