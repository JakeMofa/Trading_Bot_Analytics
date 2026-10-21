import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from fastapi.testclient import TestClient

from api import create_app
from live_state import LiveState


class FastAPITests(unittest.TestCase):
    def populated_state(self):
        state = LiveState()
        state.set_market({
            'id': 'm',
            'slug': 'btc-market',
            'start': '2026-10-21T04:00:00Z',
            'end': '2999-10-21T04:15:00Z',
            'target_usd': '100',
            'status': 'MARKET_STATUS_OPEN',
        })
        state.update_coinbase_ticker({
            'type': 'ticker',
            'product_id': 'BTC-USD',
            'trade_id': 1,
            'price': '101',
            'last_size': '0.1',
            'side': 'buy',
            'time': '2026-10-21T04:10:00Z',
        }, '2026-10-21T04:10:00.100000Z')
        state.update_polymarket({
            'marketData': {
                'marketSlug': 'btc-market',
                'longQuote': {'value': '0.55'},
                'shortQuote': {'value': '0.45'},
            }
        }, '2026-10-21T04:10:00.200000Z')
        state.set_feature_snapshot(
            'm', '2026-10-21T04:10:00Z',
            {'realized_volatility_15m': '0.002', 'target_usd': '100'},
            {'price': {'status': 'fresh'}, 'candle_status': 'fresh'})
        state.set_forecast(
            'gaussian_distance_v1', 0.7, as_of='2026-10-21T04:10:00Z')
        state.update_feed_health(
            'coinbase_stream', 'live',
            updated_at='2026-10-21T04:10:01Z',
            last_data_at='2026-10-21T04:10:00Z')
        return state

    def test_state_forecast_models_and_health_are_served_from_shared_ram(self):
        state = self.populated_state()
        app = create_app(state, start_collectors=False)
        with TestClient(app) as client:
            response = client.get('/state/current')
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['market']['id'], 'm')
            self.assertEqual(body['coinbase']['price_usd'], 101.0)
            self.assertIn('X-Process-Time-Ms', response.headers)
            self.assertLess(float(response.headers['X-Process-Time-Ms']), 1000)

            forecast = client.get('/forecast/current').json()
            self.assertEqual(
                forecast['forecast']['model_version'], 'gaussian_distance_v1')
            models = client.get('/models/current').json()
            self.assertIn('gaussian_distance_v1', models['models'])

            health = client.get('/health').json()
            self.assertFalse(health['collector']['enabled'])
            self.assertEqual(
                health['feeds']['coinbase_stream']['status'], 'live')

    def test_prediction_history_is_bounded_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.db'
            db = sqlite3.connect(path)
            db.execute('''CREATE TABLE predictions(
              id INTEGER PRIMARY KEY,
              market_id TEXT,
              model_version TEXT,
              as_of TEXT,
              created_at TEXT,
              seconds_remaining REAL,
              probability_up TEXT,
              probability_down TEXT,
              abstain_reason TEXT)''')
            for i in range(3):
                db.execute('''INSERT INTO predictions(
                  market_id,model_version,as_of,created_at,seconds_remaining,
                  probability_up,probability_down,abstain_reason)
                  VALUES(?,?,?,?,?,?,?,?)''',
                  (f'm{i}','gaussian_distance_v1',
                   f'2026-10-21T04:0{i}:00Z',f'2026-10-21T04:0{i}:01Z',
                   300-i,'0.6','0.4',None))
            db.commit()
            db.close()

            app = create_app(LiveState(), db_path=str(path), start_collectors=False)
            with TestClient(app) as client:
                response = client.get('/history/predictions?limit=2')
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(len(body['items']), 2)
                self.assertEqual(body['items'][0]['market_id'], 'm2')
                self.assertEqual(body['limit'], 2)
                self.assertEqual(
                    client.get('/history/predictions?limit=501').status_code, 422)

            check = sqlite3.connect(path)
            self.assertEqual(
                check.execute('SELECT COUNT(*) FROM predictions').fetchone()[0], 3)
            check.close()

    def test_sse_route_is_registered(self):
        app = create_app(LiveState(), start_collectors=False)
        paths = {route.path for route in app.routes}
        self.assertIn('/events', paths)


if __name__ == '__main__':
    unittest.main()
