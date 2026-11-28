"""Bounded, read-only PP feed clients. No collector activation or database writes.

The caller must hold the sole-collector fence before consuming either source.
These clients deliberately have no account, order or trading routes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import time
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect as websocket_connect

from .boundary_trace import boundary_trace
from .coinbase_timing import ACTIVE_TIMING, observed_connection
from .contract import source_timestamp
from .live_contract import QuoteContractError, coinbase_ticker, coinbase_closed_candle, polymarket_bbo, polymarket_market
from .live_diagnostics import SourceHTTPFailure, SourceTransportFailure


COINBASE_WS = 'wss://ws-feed.exchange.coinbase.com'
POLYMARKET_REST = 'https://gateway.polymarket.us'
MAX_RESPONSE_BYTES = 1024 * 1024


async def fetch_coinbase_closed_candles(client: httpx.AsyncClient, now: datetime):
    """One bounded historical read for 17 completed minutes; no gap filling.

    Coinbase documents that historical candles may omit no-trade intervals and
    should not be polled frequently. Scheduling belongs to the owning collector.
    """
    if now.tzinfo is None:
        raise ValueError('candle request requires timezone-aware time')
    now = now.astimezone(timezone.utc)
    end = int(now.timestamp()) // 60 * 60
    start = end - 17 * 60
    try:
        async with client.stream('GET', 'https://api.exchange.coinbase.com/products/BTC-USD/candles',
                                 params={'start': datetime.fromtimestamp(start, timezone.utc).isoformat(),
                                         'end': datetime.fromtimestamp(end, timezone.utc).isoformat(),
                                         'granularity': 60},
                                 headers={'Accept': 'application/json'},
                                 timeout=4, follow_redirects=False) as response:
            if response.status_code != 200:
                raise SourceHTTPFailure(response.status_code, 'Coinbase candles unavailable')
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError('Coinbase candle response exceeds bound')
    except httpx.HTTPError as error:
        raise SourceTransportFailure(timeout=isinstance(error, httpx.TimeoutException),
                                     message='Coinbase candles unavailable') from None
    rows = json.loads(body, parse_float=Decimal)
    if not isinstance(rows, list) or len(rows) > 25:
        raise ValueError('invalid Coinbase candle response')
    received = datetime.now(timezone.utc).isoformat()
    events, seen = [], set()
    for row in rows:
        event = coinbase_closed_candle(row, received)
        second = event['payload']['time']
        if second in seen:
            raise ValueError('duplicate Coinbase candle bucket')
        seen.add(second)
        # Coinbase may return buckets before the requested start. An open
        # current minute is never admitted as a stable immutable candle.
        if start <= second < end:
            events.append(event)
    return sorted(events, key=lambda item: item['payload']['time'])


async def coinbase_once(stop: asyncio.Event, *, connector=websocket_connect):
    """Yield normalized ticker events from one bounded public subscription.

    Connection failure is reported to the owning collector, which owns retry
    and health state. This function never silently fills a missing interval.
    """
    timing = ACTIVE_TIMING.get()
    options = dict(ping_interval=20, ping_timeout=20, open_timeout=10,
                   max_size=MAX_RESPONSE_BYTES, max_queue=128)
    if timing is not None:
        timing.connection_attempt()
        options['create_connection'] = observed_connection(timing)
    async with connector(COINBASE_WS, **options) as websocket:
        await websocket.send(json.dumps({'type': 'subscribe', 'product_ids': ['BTC-USD'],
                                         'channels': ['ticker', 'heartbeat']}))
        while not stop.is_set():
            if timing is not None:
                timing.read_started()
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            if timing is not None:
                timing.read_completed()
            if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_RESPONSE_BYTES:
                raise ValueError('Coinbase frame exceeds bound')
            message = json.loads(raw, parse_float=Decimal)
            if not isinstance(message, dict) or message.get('type') == 'error':
                raise ValueError('invalid Coinbase feed response')
            received = datetime.now(timezone.utc).isoformat()
            event = coinbase_ticker(message, received, raw_wire=raw)
            if timing is not None:
                timing.parsed(event)
            if event is not None:
                yield event


async def discover_polymarket_15m(client: httpx.AsyncClient, now: datetime,
                                  *, max_pages: int = 20, include_next=False):
    """Find one current official-US BTC 15-minute market; fail on ambiguity.

    A full last page is incomplete discovery and must not look like no market.
    """
    if now.tzinfo is None or not 1 <= max_pages <= 20:
        raise ValueError('invalid bounded market discovery request')
    current = upcoming = None
    now = now.astimezone(timezone.utc)
    instant = source_timestamp(now.isoformat())[1]
    deadline = time.monotonic() + 10
    for page in range(max_pages):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Polymarket discovery deadline reached')
        try:
            params = {'limit': 100, 'offset': page * 100, 'closed': 'false', 'categories': 'crypto'}
            if not include_next:
                params['active'] = 'true'
            async with client.stream('GET', POLYMARKET_REST + '/v1/markets',
                                     params=params,
                                     headers={'Accept': 'application/json'},
                                     timeout=min(4, remaining), follow_redirects=False) as response:
                if response.status_code != 200:
                    raise SourceHTTPFailure(response.status_code,
                                            'Polymarket discovery HTTP failure')
                body = bytearray()
                try:
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError('Polymarket discovery response exceeds bound')
                except httpx.StreamConsumed:
                    # MockTransport can supply an already-buffered response.
                    body = bytearray(response.content)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError('Polymarket discovery response exceeds bound')
        except httpx.HTTPError as error:
            raise SourceTransportFailure(timeout=isinstance(error, httpx.TimeoutException),
                                         message='Polymarket discovery unavailable') from None
        payload = json.loads(body, parse_float=Decimal)
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
            elif include_next and instant < start <= instant + 900:
                if upcoming and upcoming['market_id'] != event['market_id']:
                    raise ValueError('ambiguous upcoming Polymarket market')
                upcoming = event
        if len(markets) < 100:
            return (current, upcoming) if include_next else current
    raise ValueError('Polymarket discovery pagination limit reached')


async def fetch_polymarket_bbo(client: httpx.AsyncClient, market_event: dict):
    """Read one bounded BBO, with the legacy book fallback on an exact 404."""
    slug = market_event.get('payload', {}).get('slug')
    if not isinstance(slug, str) or not slug or len(slug) > 256:
        raise ValueError('invalid BBO market slug')
    for route in ('bbo', 'book'):
        boundary_trace('bbo_request', market_event, route=route)
        try:
            async with client.stream('GET', POLYMARKET_REST + '/v1/markets/' +
                                     quote(slug, safe='') + '/' + route,
                                     headers={'Accept': 'application/json'},
                                     timeout=4, follow_redirects=False) as response:
                boundary_trace('bbo_response', market_event, route=route, status=response.status_code)
                if response.status_code == 404 and route == 'bbo':
                    continue
                if response.status_code != 200:
                    raise SourceHTTPFailure(response.status_code, 'Polymarket BBO unavailable')
                body = bytearray()
                try:
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise QuoteContractError('response_limit', 'Polymarket BBO exceeds byte bound')
                except httpx.StreamConsumed:
                    body = bytearray(response.content)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise QuoteContractError('response_limit', 'Polymarket BBO exceeds byte bound')
        except httpx.HTTPError as error:
            raise SourceTransportFailure(timeout=isinstance(error, httpx.TimeoutException),
                                         message='Polymarket BBO unavailable') from None
        try:
            raw = json.loads(body, parse_float=Decimal)
        except (ValueError, UnicodeError):
            raise QuoteContractError('invalid_json', 'invalid quote document') from None
        return polymarket_bbo(raw, market_event, datetime.now(timezone.utc).isoformat(), route=route)
    raise ValueError('Polymarket BBO unavailable')
