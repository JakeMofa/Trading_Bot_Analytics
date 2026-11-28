"""Guard healthy Polymarket US subscriptions across repeated rollover."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.config import Settings
from postgres.live_contract import polymarket_bbo, polymarket_market
from postgres.live_state import LiveState
from postgres.quote_recovery import RecoveredQuote
from postgres.quote_session import QuotePipeline, run, stream_books


class QuietSession(unittest.IsolatedAsyncioTestCase):
    async def test_quiet_connected_session_uses_the_existing_writer(self):
        start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        now = start + timedelta(seconds=31)
        market = polymarket_market({
            'id': 'quiet-market', 'slug': 'quiet-market', 'status': 'open',
            'assetPriceTerms': {
                'asset': {'symbol': 'btc'},
                'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                'horizon': '15m',
                'windowStart': start.isoformat(),
                'windowEnd': (start + timedelta(minutes=15)).isoformat(),
                'priceToBeat': '60000.0123',
            },
        }, now.isoformat())
        quote = polymarket_bbo({'marketData': {
            'marketSlug': 'quiet-market', 'bestBid': {'value': '0.4501'},
        }}, market, now.isoformat())
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()

        def ingest(event):
            if event['kind'] == 'quote':
                loop.call_soon_threadsafe(stop.set)
            return {'duplicate': False}

        async def quiet_socket(*args, **kwargs):
            await stop.wait()

        async def idle_reference(*args, **kwargs):
            await stop.wait()

        store = Mock(ingest=Mock(side_effect=ingest))
        sender = Mock()
        with patch('postgres.quote_session.DisplaySender', return_value=sender), \
             patch('postgres.quote_session.signing_key'), \
             patch('postgres.quote_session.stream_books', quiet_socket), \
             patch('postgres.quote_session.collect_reference', idle_reference), \
             patch('postgres.quote_session.discover_polymarket_15m', AsyncMock(return_value=(market, None))), \
             patch('postgres.quote_session.fetch_polymarket_bbo', AsyncMock(return_value=quote)) as fetch:
            await asyncio.wait_for(run(store, Mock(), stop, 1, lambda: now), timeout=2)

        fetch.assert_awaited_once()
        self.assertEqual([call.args[0] for call in store.ingest.call_args_list], [market, quote])
        preview = sender.send.call_args.args[0]['quote']
        self.assertEqual(preview['best_bid'], '0.4501')
        self.assertEqual(preview['provenance']['feed'], 'polymarket_us_bbo')

    async def test_stale_websocket_replay_preserves_recovered_book(self):
        start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        now = start + timedelta(seconds=31)
        market = {'event_id': 'market-event', 'market_id': 'quiet-market',
                  'payload': {'slug': 'quiet-market', 'start': start.isoformat(),
                              'end': (start + timedelta(minutes=15)).isoformat(),
                              'target_usd': '60000.0123', 'status': 'open'}}
        pipe = QuotePipeline(Mock(), Mock())
        await pipe.market(market)
        wire = {'marketData': {'marketSlug': 'quiet-market', 'transactTime': start.isoformat(),
                               'bids': [{'px': {'value': '0.44'}}]}}
        await pipe.book(wire, received_at=start.isoformat())
        recovered = polymarket_bbo({'marketData': {
            'marketSlug': 'quiet-market', 'bestBid': {'value': '0.4501'},
        }}, market, now.isoformat())
        pipe.publish_recovery(RecoveredQuote('quiet-market', now, recovered))
        await pipe.book(wire, received_at=now.isoformat())
        self.assertEqual(pipe.quote['event_id'], recovered['event_id'])
        self.assertEqual(pipe.last_usable_ws_at, start)
        self.assertEqual(pipe.queue.qsize(), 3)


class EmptyRecoveryDisplay(unittest.TestCase):
    def test_empty_book_hides_only_older_hydrated_quote(self):
        start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        now = start + timedelta(seconds=35)
        settings = Settings(data_mode='pp_live', origin_id='pp-live-display-test')
        state = LiveState(settings, clock=lambda: now)
        market = {'id': 'btc-15m', 'start': start.isoformat(),
                  'end': (start + timedelta(minutes=15)).isoformat(),
                  'target_usd': '60000.0123'}
        state.discover(market)
        old = (start + timedelta(seconds=20)).isoformat()
        quote = {'market_id': market['id'], 'source_time': old, 'received_at': old,
                 'best_bid': '0.45', 'best_ask': '0.55', 'event_id': 'old-book'}
        state.publish(market['id'], None, quote, None, None)
        self.assertEqual(state.snapshot()['polymarket']['event_id'], 'old-book')

        state.display({'market': market, 'quote': None, 'reference': None,
                       'received': 1, 'saved': 1, 'duplicates': 0,
                       'started_at': start.isoformat(), 'last_commit': None,
                       'empty_book_at': (now - timedelta(seconds=1)).isoformat()})
        state.publish(market['id'], None, quote, None, None)
        self.assertIsNone(state.snapshot()['polymarket'])
        self.assertEqual(state.snapshot()['polymarket_empty_book_at'],
                         (now - timedelta(seconds=1)).isoformat())
        self.assertIn('polymarket_quote', state.snapshot()['missing_data'])

        state.publish(market['id'], None, {**quote, 'event_id': 'new-book',
                                         'received_at': now.isoformat()}, None, None)
        self.assertEqual(state.snapshot()['polymarket']['event_id'], 'new-book')
        self.assertIsNone(state.snapshot()['polymarket_empty_book_at'])


class RolloverSubscriptions(unittest.IsolatedAsyncioTestCase):
    async def test_retired_markets_are_unsubscribed_on_the_same_socket(self):
        start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        markets = []
        for index in range(5):
            opening = start + timedelta(minutes=15 * index)
            slug = f'btc-15m-{index}'
            markets.append(polymarket_market({
                'id': slug, 'slug': slug, 'status': 'open',
                'assetPriceTerms': {
                    'asset': {'symbol': 'btc'},
                    'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                    'horizon': '15m',
                    'windowStart': opening.isoformat(),
                    'windowEnd': (opening + timedelta(minutes=15)).isoformat(),
                    'priceToBeat': '60000.0123',
                },
            }, start.isoformat()))

        stop = asyncio.Event()
        pipe = QuotePipeline(Mock(), Mock())
        await pipe.market(markets[0])
        pipe.upcoming = markets[1]
        now = start
        observed = []

        class Socket:
            def __init__(self):
                self.subscriptions = {}
                self.market_index = 0
                self.just_rolled = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def send(self, body):
                message = json.loads(body)
                if 'subscribe' in message:
                    subscribe = message['subscribe']
                    self.subscriptions[subscribe['requestId']] = set(subscribe['marketSlugs'])
                else:
                    self.subscriptions.pop(message['unsubscribe']['requestId'])

            async def recv(self):
                nonlocal now
                active = set().union(*self.subscriptions.values())
                observed.append((self.market_index, self.just_rolled, active))
                if self.just_rolled:
                    self.just_rolled = False
                    if self.market_index == len(markets) - 1:
                        stop.set()
                    else:
                        pipe.upcoming = markets[self.market_index + 1]
                    return '{}'

                self.market_index += 1
                self.just_rolled = True
                now = start + timedelta(minutes=15 * self.market_index)
                return json.dumps({'marketData': {
                    'marketSlug': markets[self.market_index]['payload']['slug'],
                    'transactTime': now.isoformat(),
                    'bids': [{'px': {'value': '0.45'}}],
                }})

        with patch('postgres.quote_session.connect', return_value=Socket()) as connect, \
             patch('postgres.quote_session.headers', return_value={}), \
             patch('postgres.quote_session.utc', side_effect=lambda: now.isoformat()):
            await asyncio.wait_for(stream_books(pipe, stop, None), timeout=2)

        self.assertEqual(connect.call_count, 1)
        self.assertEqual(pipe.current['market_id'], markets[-1]['market_id'])
        expected = []
        for index, just_rolled, _ in observed:
            wanted = {markets[index]['payload']['slug']}
            if not just_rolled:
                wanted.add(markets[index + 1]['payload']['slug'])
            expected.append((index, just_rolled, wanted))
        self.assertEqual(observed, expected)
