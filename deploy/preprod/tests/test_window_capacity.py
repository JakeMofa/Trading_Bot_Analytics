import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from window_capacity import estimate


class MarketWindowCapacityTests(unittest.TestCase):
    sample = dict(elapsed=282, initial_a=2711552, final_a=9109504, rows_added=3456,
                  db_growth=15859712, retained_a=9109504, retained_rows=4845)

    def test_retained_a_alignment_poll_and_full_lease(self):
        result = estimate(**self.sample)
        self.assertEqual(result['status'], 'PROJECTION_ONLY')
        self.assertGreater(result['a_relation_bytes'], 67 * 1024**2)
        self.assertGreater(result['b_growth_bytes'], 40 * 1024**2)
        self.assertGreater(result['minimum_archive_chunks'], 75)
        self.assertGreater(result['db_growth_bytes_over_max_lease'], 244 * 1024**2)

    def test_faster_feed_can_exhaust_catalog_and_rejects_invalid_samples(self):
        result = estimate(**{**self.sample, 'elapsed': 140})
        self.assertGreater(result['minimum_archive_chunks'],128)
        for change in ({'elapsed': 0}, {'db_growth': 0}, {'initial_a': 99999999}, {'rows_added': -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                estimate(**{**self.sample, **change})
