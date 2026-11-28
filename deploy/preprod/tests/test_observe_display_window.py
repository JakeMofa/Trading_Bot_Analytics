import unittest

from observe_display_window import clock_sample, sample_market


class MatchedDashboardObservation(unittest.TestCase):
    def test_lagging_db_does_not_label_previous_market_as_target(self):
        windows = {}
        state = {'market': {'active': True, 'slug': 'next', 'start': 900, 'id': '2'},
                 'polymarket': {'market_id': '2', 'event_id': 'next-first'},
                 'database_quote_id': 'previous-market', 'generated_at': 'at-1'}
        sample_market(windows, state)
        self.assertEqual(windows['next']['database_observations'], {})
        sample_market(windows, {**state, 'database_quote_id': 'next-first', 'generated_at': 'at-2'})
        sample_market(windows, {**state, 'database_quote_id': 'next-first', 'generated_at': 'at-3'})
        self.assertEqual(windows['next']['database_observations'], {'next-first': 'at-2'})

    def test_clock_interval(self):
        self.assertEqual(clock_sample(980, 1040, {'generated_at':'1970-01-01T00:00:01+00:00'}),
                         {'min_offset_ms':-40, 'max_offset_ms':20})
