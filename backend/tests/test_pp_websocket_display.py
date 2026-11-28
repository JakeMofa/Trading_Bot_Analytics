"""Market rollover on the production client loop, using local socket doubles."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.config import Settings
from postgres.live_contract import polymarket_market
from postgres.live_state import LiveState
from postgres.quote_session import QuotePipeline, stream_books


class Rollover(unittest.IsolatedAsyncioTestCase):
    async def test_same_socket_next_market_and_stale_db(self):
        start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        now = [start + timedelta(minutes=14)]
        def market(name, offset, target):
            opening = start + timedelta(minutes=offset)
            row = {'id': name, 'slug': name, 'status': 'open', 'assetPriceTerms': {
                'asset': {'symbol': 'btc'}, 'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                'horizon': '15m', 'windowStart': opening.isoformat(),
                'windowEnd': (opening + timedelta(minutes=15)).isoformat(), 'priceToBeat': target}}
            return polymarket_market(row, now[0].isoformat())
        settings = Settings(data_mode='pp_live', origin_id='pp-live-display-test')
        state = LiveState(settings, clock=lambda: now[0])
        sender = Mock()
        sender.send.side_effect = state.display
        pipe = QuotePipeline(Mock(settings=settings), sender)
        old = market('old', 0, '100000')
        await pipe.market(old)
        stop = asyncio.Event()
        subscriptions = []
        class Socket:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                return False
            async def send(self, body):
                subscriptions.append(json.loads(body)['subscribe']['marketSlugs'])
            async def recv(self):
                if pipe.upcoming is None:
                    pipe.upcoming = market('new', 15, None)
                    return '{}'
                now[0] = start + timedelta(minutes=15)
                stop.set()
                return json.dumps({'marketData': {'marketSlug':'new', 'transactTime':now[0].isoformat(),
                    'bids':[{'px':{'value':'0.45'}}]}})
        with patch('postgres.quote_session.connect', return_value=Socket()) as connect, \
             patch('postgres.quote_session.headers', return_value={}), \
             patch('postgres.quote_session.utc', side_effect=lambda: now[0].isoformat()):
            await stream_books(pipe, stop, None)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(subscriptions, [['old'], ['new']])
        state.discover({**old['payload'], 'id':'old'})
        visible = state.snapshot()
        self.assertEqual(visible['market']['id'], 'new')
        self.assertIsNone(visible['market']['target_usd'])
        self.assertEqual(visible['polymarket']['best_bid'], '0.45')
        self.assertIsNone(visible['polymarket']['best_ask'])
        await pipe.market(market('new', 15, '60000.0123'))
        self.assertEqual(state.snapshot()['market']['target_usd'], '60000.0123')
        self.assertEqual(state.snapshot()['polymarket']['event_id'], visible['polymarket']['event_id'])
