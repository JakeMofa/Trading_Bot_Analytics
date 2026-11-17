"""Isolated PostgreSQL 17 read-path evidence for one PP live 15-minute session.

CI supplies disposable app/lifecycle roles. No network feed, PP host, cloud, or
production connection is used. These assertions compare behavior with the
SQLite dashboard's evidence semantics, not its SQL or optional model fields.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.api import create_app, event_stream
from postgres.calculation import calculate, forecast
from postgres.config import Settings
from postgres.connection import connect
from postgres.lifecycle import LifecycleRepository
from postgres.live_contract import (coinbase_closed_candle, coinbase_ticker,
                                    polymarket_bbo, polymarket_market)
from postgres.live_state import LiveState
from postgres.store import Store


ENABLED = bool(os.getenv('TRADEBOT_TEST_APP_DSN') and os.getenv('TRADEBOT_TEST_LIFECYCLE_DSN'))


@unittest.skipUnless(ENABLED, 'requires disposable PostgreSQL app/lifecycle roles')
class LiveQueryParityTests(unittest.TestCase):
    def test_official_us_session_reads_and_time_guards(self):
        from fastapi.testclient import TestClient

        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=5)).replace(microsecond=0)
        end = start + timedelta(minutes=15)
        origin = 'pp-live-query-' + uuid.uuid4().hex
        settings = Settings(data_mode='pp_live', origin_id=origin,
                            dsn=os.environ['TRADEBOT_TEST_APP_DSN'])
        store = Store(settings)
        repository = LifecycleRepository(lambda: connect(
            os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'], environment='preprod'))
        generation = repository.bootstrap(origin, now)
        repository.enable_collector(origin, session_id=str(uuid.uuid4()),
                                    expected_generation_id=str(generation['generation_id']),
                                    max_seconds=180)
        self.addCleanup(repository.disable_collector, origin)

        raw_market = {'id': 'fixture-' + uuid.uuid4().hex, 'slug': 'btc-up-down-query-fixture',
                      'status': 'MARKET_STATUS_OPEN', 'updatedAt': now.isoformat(),
                      'assetPriceTerms': {'asset': {'symbol': 'btc'},
                                          'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                                          'horizon': '15m', 'windowStart': start.isoformat(),
                                          'windowEnd': end.isoformat(),
                                          'priceToBeat': {'value': '100000.1234567890123456789'}}}
        market_event = polymarket_market(raw_market, now.isoformat())
        store.ingest(market_event)
        market_id = market_event['market_id']

        def tick(seconds_ago, trade_id, price):
            source = now - timedelta(seconds=seconds_ago)
            exact_time = source.strftime('%Y-%m-%dT%H:%M:%S') + '.123456789Z'
            return coinbase_ticker({'type': 'ticker', 'product_id': 'BTC-USD',
                                    'trade_id': trade_id, 'time': exact_time,
                                    'price': price, 'last_size': '0.000000001'}, now.isoformat())

        latest = tick(2, 'latest-' + uuid.uuid4().hex, '100025.1234567890123456789')
        older = tick(20, 'older-' + uuid.uuid4().hex, '100020.1234567890123456789')
        store.ingest(latest)
        store.ingest(older)  # Arrival order must not rewind the current price.
        sample_at = (now - timedelta(minutes=3)).isoformat()
        raw_book = {'marketData': {'marketSlug': raw_market['slug'],
                    'lastPriceSample': {'ts': sample_at},
                    'bestBid': {'value': '0.510000000000000001'},
                    'bestAsk': {'value': '0.530000000000000001'}}}
        first_book = polymarket_bbo(raw_book, market_event, now.isoformat())
        second_book = polymarket_bbo(raw_book, market_event,
                                     (now + timedelta(microseconds=1)).isoformat())
        store.ingest(first_book)
        store.ingest(second_book)
        self.assertNotEqual(first_book['event_id'], second_book['event_id'])

        wanted = int(now.timestamp()) // 60 * 60 - 60
        for index in range(17):
            bucket = wanted - (16 - index) * 60
            close = 100000 + index
            store.ingest(coinbase_closed_candle(
                [bucket, str(close - 2), str(close + 2), str(close - 1),
                 str(close), '0.1234567890123456789'], now.isoformat()))

        active = store.active_market(now)
        self.assertEqual((active['id'], active['target_usd']),
                         (market_id, '100000.1234567890123456789'))
        price, candles = store.inputs(market_id, now)
        self.assertEqual(len(candles), 17)
        self.assertEqual(price['event_id'], latest['event_id'])
        self.assertEqual(price['source_time'], latest['source_time'])
        self.assertEqual(price['price_usd'], latest['price'])
        self.assertEqual(price['provenance']['price_role'], 'reference_not_settlement')
        self.assertEqual(candles[-1]['volume'], '0.1234567890123456789')
        quote = store.hydrate(market_id, now + timedelta(seconds=1))[1]
        self.assertEqual(quote['received_at'], second_book['received_at'])
        self.assertEqual(quote['source_time'], sample_at)
        self.assertEqual(quote['best_bid'], '0.510000000000000001')
        self.assertFalse(quote['provenance']['quote_prices_are_probabilities'])

        saved_ids = []
        for offset in (0, 1):
            at = now + timedelta(microseconds=offset)
            values, quality, evidence = calculate(active, price, candles, at)
            snapshot = {'market_id': market_id, 'as_of': at.isoformat(),
                        'values': values, 'quality': quality, 'evidence': evidence}
            prediction = forecast(active, snapshot, at)
            saved_ids.append(store.save_calculation(active, snapshot, prediction))
        self.assertEqual(len(set(saved_ids)), 2)
        history = store.predictions(2)
        self.assertEqual([row['as_of'] for row in history],
                         [(now + timedelta(microseconds=1)).isoformat(), now.isoformat()])
        self.assertEqual([row['market_id'] for row in history], [market_id, market_id])
        chart = store.chart(now + timedelta(seconds=1))
        self.assertEqual(chart['market']['id'], market_id)
        self.assertEqual([point['price_usd'] for point in chart['points']],
                         [older['price'], latest['price']])
        self.assertEqual(chart['bounded_input_limit'], 5000)
        self.assertFalse(chart['truncated'])

        # Poll the real API hydration tasks against the disposable database.
        with TestClient(create_app(settings, store, refresh=True)) as client:
            deadline = time.monotonic() + 4
            while True:
                started = time.monotonic()
                response = client.get('/state/current')
                self.assertLess(time.monotonic() - started, 2)
                state = response.json()
                if (state['market'] and state['market']['id'] == market_id
                        and state['feature_snapshot'] and state['polymarket']
                        and state['collector']['enabled'] is True):
                    break
                if time.monotonic() >= deadline:
                    self.fail('PP live API did not hydrate acknowledged SQL rows')
                time.sleep(.05)
            self.assertEqual(state['coinbase']['price_usd'], latest['price'])
            self.assertEqual(state['feature_snapshot']['quality']['price']['input_id'], latest['event_id'])
            self.assertEqual(state['feeds']['polymarket_rest']['freshness_basis'], 'received_at')
            self.assertEqual(state['feeds']['polymarket_rest']['source_sample_at'], sample_at)
            self.assertEqual(state['feeds']['polymarket_rest']['status'], 'fresh')
            self.assertEqual(client.get('/health').json()['status'], 'ok')
            self.assertEqual(client.get('/history/predictions?limit=2').json()['items'], history)
            started = time.monotonic()
            self.assertEqual(client.get('/history/coinbase-chart').json()['market']['id'], market_id)
            self.assertLess(time.monotonic() - started, 2)
            dashboard = client.get('/dashboard').text
            self.assertIn("new EventSource('/events')", dashboard)
            self.assertIn('Polymarket US REST BBO', dashboard)
            frame = asyncio.run(anext(event_stream(client.app.state.live_state)))
            streamed = json.loads(frame.split('data: ', 1)[1])
            self.assertEqual(streamed['market']['id'], state['market']['id'])
            self.assertEqual(streamed['feature_snapshot']['market_id'], market_id)

        # Source-time expiry and rollover must remain visible as missing data.
        clock = [now + timedelta(seconds=31)]
        view = LiveState(settings, clock=lambda: clock[0])
        view.discover(active)
        view.publish(market_id, *store.hydrate(market_id, clock[0]))
        stale = view.snapshot()
        self.assertEqual(stale['feeds']['coinbase_stream']['status'], 'stale')
        self.assertEqual(stale['feeds']['polymarket_rest']['status'], 'stale')
        self.assertIsNone(stale['feature_snapshot'])
        next_raw = {**raw_market, 'id': 'next-' + uuid.uuid4().hex,
                    'slug': 'btc-up-down-next-fixture',
                    'assetPriceTerms': {**raw_market['assetPriceTerms'],
                                        'windowStart': end.isoformat(),
                                        'windowEnd': (end + timedelta(minutes=15)).isoformat()}}
        next_event = polymarket_market(next_raw, now.isoformat())
        store.ingest(next_event)
        clock[0] = end
        next_market = store.active_market(clock[0])
        self.assertEqual(next_market['id'], next_event['market_id'])
        view.discover(next_market)
        self.assertIsNone(view.snapshot()['polymarket'])
        self.assertIn('polymarket_quote', view.snapshot()['missing_data'])

        # A source timestamp ahead of the query clock cannot appear on chart.
        future = tick(-120, 'future-' + uuid.uuid4().hex, '100030.1234567890123456789')
        store.ingest(future)
        self.assertEqual([point['price_usd'] for point in store.chart(now + timedelta(seconds=2))['points']],
                         [older['price'], latest['price']])
