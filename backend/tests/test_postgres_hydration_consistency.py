"""Exact saved snapshot/forecast pairing under a real concurrent publication."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.calculation import calculate, forecast
from postgres.config import Settings
from postgres.connection import connect
from postgres.ingestion import generated_events
from postgres.lifecycle import LifecycleRepository
from postgres.live_state import LiveState
from postgres.store import Store


ENABLED = all(os.getenv(name) for name in
              ('TRADEBOT_TEST_APP_DSN', 'TRADEBOT_TEST_LIFECYCLE_DSN'))
NOW = datetime(2026, 11, 19, 12, 5, tzinfo=timezone.utc)


@unittest.skipUnless(ENABLED, 'requires disposable PostgreSQL app/lifecycle roles')
class HydrationConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(origin_id='generated-hydration-' + uuid.uuid4().hex,
                                 dsn=os.environ['TRADEBOT_TEST_APP_DSN'])
        self.writer = Store(self.settings)
        self.reader = Store(self.settings)
        LifecycleRepository(lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'])).bootstrap(
            self.settings.origin_id, NOW)
        for event in generated_events(NOW):
            self.writer.ingest(event)
        self.market = self.writer.active_market(NOW)

    def publish(self, at, *, missing_candles=False):
        price, candles = self.writer.inputs(self.market['id'], at)
        values, quality, evidence = calculate(self.market, price, [] if missing_candles else candles, at)
        snapshot = dict(market_id=self.market['id'], as_of=at.isoformat(),
                        values=values, quality=quality, evidence=evidence)
        prediction = forecast(self.market, snapshot, at)
        return self.writer.save_calculation(self.market, snapshot, prediction, at)

    def test_interleaved_committed_publication_keeps_exact_snapshot_link(self):
        first = self.publish(NOW)
        later = NOW + timedelta(seconds=1)
        published = []
        connection = self.reader.connection

        @contextmanager
        def interleave(readonly=False):
            with connection(readonly) as db:
                class Reader:
                    def execute(inner, query, params=None):
                        cursor = db.execute(query, params)
                        # Execute against one statement snapshot, then commit a
                        # newer real calculation on an independent connection.
                        # Old code next selected its unrelated newer forecast.
                        if 'FROM core.feature_snapshots' in str(query) and not published:
                            published.append(self.publish(later))
                        return cursor
                yield Reader()

        with patch.object(self.reader, 'connection', interleave):
            price, quote, feature, prediction = self.reader.hydrate(self.market['id'], later)
        self.assertEqual(len(published), 1)
        self.assertNotEqual(first, published[0])
        self.assertEqual(feature['snapshot_id'], first)
        self.assertEqual(prediction['snapshot_id'], first)
        self.assertEqual(feature['as_of'], prediction['as_of'])
        state = LiveState(self.settings, clock=lambda: later)
        state.discover(self.market)
        state.publish(self.market['id'], price, quote, feature, prediction)
        view = state.snapshot()
        self.assertEqual(view['feature_snapshot']['snapshot_id'], view['forecast']['snapshot_id'])
        current = self.reader.hydrate(self.market['id'], later)
        self.assertEqual(current[2]['snapshot_id'], published[0])
        self.assertEqual(current[3]['snapshot_id'], published[0])
        self.assertEqual(current[0]['price_usd'], '100025.1234567890123456789')

    def test_latest_feature_without_prediction_does_not_borrow_an_older_forecast(self):
        self.publish(NOW)
        later = NOW + timedelta(seconds=1)
        with self.writer.connection() as db:
            db.execute('''INSERT INTO core.feature_snapshots
                (origin_id,snapshot_id,market_id,as_of,version,values_json,quality_json,evidence_json,content_hash)
                SELECT origin_id,%s,market_id,%s,version,values_json,quality_json,evidence_json,content_hash
                FROM core.feature_snapshots WHERE origin_id=%s''',
                ('new-feature-without-prediction', later, self.settings.origin_id))
        _, _, feature, prediction = self.reader.hydrate(self.market['id'], later)
        self.assertEqual(feature['snapshot_id'], 'new-feature-without-prediction')
        self.assertIsNone(prediction)

    def test_empty_and_abstaining_forecasts_preserve_missing_state(self):
        self.assertEqual(self.reader.hydrate(self.market['id'], NOW)[2:], (None, None))
        identity = self.publish(NOW, missing_candles=True)
        _, _, feature, prediction = self.reader.hydrate(self.market['id'], NOW)
        self.assertEqual(feature['snapshot_id'], identity)
        self.assertEqual(prediction['snapshot_id'], identity)
        self.assertIsNone(prediction['probability_up'])
        self.assertIsNone(prediction['probability_down'])
        self.assertEqual(prediction['abstain_reason'], 'completed_candles_missing_or_stale')


if __name__ == '__main__':
    unittest.main()
