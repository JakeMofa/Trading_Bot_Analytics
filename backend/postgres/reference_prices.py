"""Polymarket US BTC index candles. Each observation carries its availability time."""
import asyncio
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging

import httpx

from .contract import canonical_json, content_hash, exact_decimal
from .feed_writer import feed_writer
from .live_contract import PROVENANCE
from .live_sources import POLYMARKET_REST

BUCKET = 'ASSET_PRICE_BUCKET_1S'


def published_buckets(document, start, end, received):
    events = []
    for series in document['series']:
        if series['asset'] != {'assetClass': 'ASSET_CLASS_CRYPTO', 'symbol': 'btc'}:
            continue
        if series['currency'] != 'USD' or series['bucket'] != BUCKET:
            raise ValueError('BTC reference series units or bucket changed')
        candles = series['candles']
        if len(candles) > end - start + 1:
            raise ValueError('unexpected BTC reference response length')
        for candle in candles:
            second, ticks = candle['timestamp'], candle['tickCount']
            if type(second) is not int or not start <= second <= end or type(ticks) is not int or ticks < 0:
                raise ValueError('invalid BTC reference timestamp or count')
            if ticks == 0:
                continue  # Venue carried the preceding close into an empty second.
            prices = {k: exact_decimal(candle[k]) for k in ('open', 'high', 'low', 'close')}
            if not (0 < prices['low'] <= min(prices['open'], prices['close'])
                    <= max(prices['open'], prices['close']) <= prices['high']):
                raise ValueError('invalid BTC reference OHLC')
            payload = {**{k: str(v) for k, v in prices.items()}, 'tick_count': ticks,
                       'bucket_seconds': 1, 'currency': 'USD'}
            events.append({'source': 'polymarket_us', 'kind': 'price', 'symbol': 'BTC-USD',
                'event_id': 'btc-index-' + content_hash([second, payload]),
                'source_time': datetime.fromtimestamp(second, timezone.utc).isoformat(),
                'received_at': received, 'payload': payload, 'price': payload['close'],
                'raw_payload': canonical_json(candle),
                'provenance': {**PROVENANCE, 'feed': 'polymarket_us_asset_prices',
                               'price_role': 'venue_reference_index', 'source_time_role': 'bucket_start'}})
    return events


async def _fetch(client, clock):
    end = int(clock().timestamp()) - 1
    start = end - 11
    params = {'assets': 'crypto:btc', 'bucket': BUCKET, 'from': start, 'to': end}
    async with client.stream('GET', POLYMARKET_REST + '/v1/asset-prices/history',
                             params=params, timeout=4, follow_redirects=False) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 32768:
                raise ValueError('BTC reference response exceeds bound')
    return published_buckets(json.loads(body, parse_float=Decimal), start, end, clock().isoformat())


async def collect_reference(store, client, stop, clock, publish):
    queue = asyncio.Queue(maxsize=24)  # At most two full HTTP windows awaiting the writer.
    recent = deque(maxlen=64)

    async def write():
        async with feed_writer(store):
            while True:
                event = await queue.get()
                if event is None:
                    return
                await asyncio.to_thread(store.ingest, event)

    loop = asyncio.get_running_loop()
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(write())
        while not stop.is_set():
            started = loop.time()
            try:
                events = await _fetch(client, clock)
            except (httpx.HTTPError, ValueError, ArithmeticError, TypeError, KeyError):
                logging.getLogger(__name__).warning('pp_btc_reference_unavailable')
            else:
                new = [event for event in events if event['event_id'] not in recent]
                if new:
                    # All timestamps are UTC bucket starts emitted in the same
                    # fixed format. Revisions for the newest second prefer the
                    # last venue entry; validated historical buckets are all saved.
                    latest = max(reversed(new), key=lambda event: event['source_time'])
                    publish(latest)
                    for event in new:
                        if event['event_id'] not in recent:
                            await queue.put(event)
                            recent.append(event['event_id'])
            remaining = 5 - (loop.time() - started)
            if remaining > 0:
                try:
                    await asyncio.wait_for(stop.wait(), remaining)
                except TimeoutError:
                    pass
        await queue.put(None)  # The writer drains accepted observations before returning.
