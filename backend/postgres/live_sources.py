"""Bounded, read-only PP feed clients. No collector activation or database writes.

The caller must hold the sole-collector fence before consuming either source.
These clients deliberately have no account, order or trading routes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

import httpx
from websockets.asyncio.client import connect as websocket_connect

from .contract import source_timestamp
from .live_contract import coinbase_ticker, polymarket_market


COINBASE_WS = 'wss://ws-feed.exchange.coinbase.com'
POLYMARKET_REST = 'https://gateway.polymarket.us'
MAX_RESPONSE_BYTES = 1024 * 1024


async def coinbase_once(stop: asyncio.Event, *, connector=websocket_connect):
    """Yield normalized ticker events from one bounded public subscription.

    Connection failure is reported to the owning collector, which owns retry
    and health state. This function never silently fills a missing interval.
    """
    async with connector(COINBASE_WS, ping_interval=20, ping_timeout=20,
                         open_timeout=10, max_size=MAX_RESPONSE_BYTES,
                         max_queue=128) as websocket:
        await websocket.send(json.dumps({'type': 'subscribe', 'product_ids': ['BTC-USD'],
                                         'channels': ['ticker', 'heartbeat']}))
        while not stop.is_set():
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_RESPONSE_BYTES:
                raise ValueError('Coinbase frame exceeds bound')
            message = json.loads(raw)
            if not isinstance(message, dict) or message.get('type') == 'error':
                raise ValueError('invalid Coinbase feed response')
            received = datetime.now(timezone.utc).isoformat()
            event = coinbase_ticker(message, received)
            if event is not None:
                yield event


async def discover_polymarket_15m(client: httpx.AsyncClient, now: datetime,
                                  *, max_pages: int = 20):
    """Find one current official-US BTC 15-minute market; fail on ambiguity.

    A full last page is incomplete discovery and must not look like no market.
    """
    if now.tzinfo is None or not 1 <= max_pages <= 20:
        raise ValueError('invalid bounded market discovery request')
    current = None
    now = now.astimezone(timezone.utc)
    instant = source_timestamp(now.isoformat())[1]
    for page in range(max_pages):
        try:
            async with client.stream('GET', POLYMARKET_REST + '/v1/markets',
                                     params={'limit': 100, 'offset': page * 100,
                                             'active': 'true', 'closed': 'false',
                                             'categories': 'crypto'},
                                     headers={'Accept': 'application/json'},
                                     timeout=4, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError('Polymarket discovery HTTP failure')
                body = bytearray()
                try:
                    async for chunk in response.aiter_raw():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError('Polymarket discovery response exceeds bound')
                except httpx.StreamConsumed:
                    # MockTransport can supply an already-buffered response.
                    body = bytearray(response.content)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError('Polymarket discovery response exceeds bound')
        except httpx.HTTPError:
            raise ValueError('Polymarket discovery unavailable') from None
        payload = json.loads(body)
        markets = payload.get('markets') if isinstance(payload, dict) else None
        if not isinstance(markets, list) or len(markets) > 100:
            raise ValueError('invalid Polymarket discovery response')
        received = datetime.now(timezone.utc).isoformat()
        for raw in markets:
            event = polymarket_market(raw, received)
            if event is None:
                continue
            terms = event['payload']
            start = source_timestamp(terms['start'])[1]
            end = source_timestamp(terms['end'])[1]
            if start <= instant < end:
                if current is not None and current['market_id'] != event['market_id']:
                    raise ValueError('ambiguous active Polymarket market')
                current = event
        if len(markets) < 100:
            return current
    raise ValueError('Polymarket discovery pagination limit reached')
