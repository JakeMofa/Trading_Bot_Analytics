import asyncio
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.reference_prices import published_buckets, BUCKET
from postgres.live_contract import polymarket_bbo


class ReferenceTests(unittest.TestCase):
    def test_bucket_units_identity_availability_and_empty_seconds(self):
        candle = {'timestamp': 100, 'tickCount': 2, 'open': '123.450', 'high': '124.01',
                  'low': '122.99', 'close': '123.999'}
        series = {'asset': {'assetClass': 'ASSET_CLASS_CRYPTO', 'symbol': 'btc'},
                  'currency': 'USD', 'bucket': BUCKET,
                  'candles': [candle, {**candle, 'timestamp': 101, 'tickCount': 0}]}
        doc = {'series': [series]}
        a, = published_buckets(doc, 100, 101, '1970-01-01T00:01:51Z')
        b, = published_buckets(doc, 100, 101, '1970-01-01T00:01:55Z')
        self.assertEqual(a['source_time'], '1970-01-01T00:01:40+00:00')
        self.assertEqual(a['event_id'], b['event_id'])
        self.assertNotEqual(a['received_at'], b['received_at'])
        self.assertEqual((a['payload']['open'], a['price']), ('123.450', '123.999'))
        changed = deepcopy(doc)
        changed['series'][0]['candles'][0]['close'] = '124'
        rev, = published_buckets(changed,100,101,b['received_at'])
        self.assertNotEqual(a['event_id'], rev['event_id'])

    def test_size_follows_best_price_and_absent_side(self):
        market = {'market_id':'test','payload':{'slug':'slug'}}
        book = {'marketData': {'marketSlug':'slug', 'bids': [
            {'px':'0.2','qty':'180'}, {'px':'0.61', 'qty':'1.23400'}], 'offers':[]}}
        event = polymarket_bbo(book,market,'2026-11-27T12:00:00Z',route='book')
        self.assertEqual(event['payload']['best_bid_qty'],'1.23400')
        self.assertIsNone(event['payload']['best_ask_qty'])

class ReferenceWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_newest_is_visible_before_slow_writes_and_stop_preserves_all_buckets(self):
        from postgres.reference_prices import collect_reference
        stop = asyncio.Event()
        first_write = Event()
        release = Event()
        saved = []
        shown = []
        events = [{'event_id': str(i), 'source_time': f'1970-01-01T00:00:0{i}+00:00'}
                  for i in (2, 3, 1, 2)]
        def persist(event):
            first_write.set()
            if not release.wait(3):
                raise RuntimeError('fixture writer timed out')
            saved.append(event)
        def publish(latest):
            shown.append(latest)
        with patch('postgres.reference_prices._fetch', return_value=events):
            task = asyncio.create_task(collect_reference(SimpleNamespace(ingest=persist),
                                       None, stop, None, publish))
            try:
                self.assertTrue(await asyncio.to_thread(first_write.wait, 2))
                self.assertEqual(shown, [events[1]])
                self.assertEqual(saved, [])
                stop.set()
            finally:
                release.set()
                await asyncio.wait_for(task, 2)
        self.assertEqual(saved, events[:3])
