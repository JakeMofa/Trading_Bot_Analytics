"""Bounded same-clock PP quote comparison. Writes only a new local JSONL file."""
from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import time
from urllib.parse import quote
import uuid

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from .contract import source_timestamp
from .live_contract import polymarket_bbo, polymarket_market
from .live_sources import MAX_RESPONSE_BYTES, POLYMARKET_REST

WS_URL = 'wss://api.polymarket.us/v1/ws/markets'
LEAD_SECONDS = 120
TAIL_SECONDS = 300
PAGE_LIMIT = 20


def utc(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, timezone.utc).isoformat()


def stamp():
    return {'ts_utc': utc(), 'mono_ns': time.monotonic_ns()}


def boundary_epoch(value):
    _, epoch = source_timestamp(value)
    if epoch % 900:
        raise ValueError('boundary must be aligned to a UTC quarter hour')
    return int(epoch)


def evidence_file(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', buffering=1)


class Boundary:
    def __init__(self, epoch, stream):
        self.epoch = epoch
        self.stream = stream
        self.market = None
        self.counts = Counter()
        self.latest = {}

    def emit(self, reader, stage, *, observed=None, **fields):
        context = {'window_start': utc(self.epoch)}
        if self.market:
            context.update(market_id=self.market['market_id'], slug=self.market['payload']['slug'])
        row = dict(**(observed or stamp()), reader=reader, stage=stage, **context)
        row.update(fields)
        self.counts[(reader, stage)] += 1
        self.stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')

    def ws_sample(self, stage, fields, observed):
        # Preserve first observations across the boundary for each book shape
        # and exchange-time category. Bound high-rate repeated book samples.
        phase = 'pre' if source_timestamp(observed['ts_utc'])[1] < self.epoch else 'post'
        source = fields.get('source_time')
        source_phase = ('unknown' if not source else
                        'pre' if source_timestamp(source)[1] < self.epoch else 'post')
        key = (phase, stage, fields.get('sides'), source_phase)
        previous = self.latest.get(key)
        if previous is None or observed['mono_ns'] - previous >= 5_000_000_000:
            self.emit('websocket', stage, observed=observed, **fields)
            self.latest[key] = observed['mono_ns']
        else:
            self.counts[('websocket', 'suppressed_' + stage)] += 1


class HttpStatus(Exception):
    def __init__(self, code):
        self.code = code


async def read_json(client, url, trace, reader, route, *, params=None):
    trace.emit(reader, 'request', route=route)
    async with asyncio.timeout(5):
        async with client.stream('GET', url, params=params, headers={'Accept': 'application/json'}) as response:
            if response.status_code != 200:
                trace.emit(reader, 'response', route=route, status=response.status_code)
                raise HttpStatus(response.status_code)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ValueError('response exceeds limit')
            observed = stamp()
            trace.emit(reader, 'response', route=route, status=200, observed=observed)
            return json.loads(data, parse_float=Decimal), observed


async def catalog(client, trace):
    found = {}
    async with asyncio.timeout(20):
        for page in range(PAGE_LIMIT):
            params = {'closed': 'false', 'categories': 'crypto', 'limit': 100, 'offset': page * 100}
            doc, observed = await read_json(client, POLYMARKET_REST + '/v1/markets', trace,
                                            'early_discovery', 'markets', params=params)
            rows = doc['markets']
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError('invalid catalog')
            for raw in rows:
                market = polymarket_market(raw, observed['ts_utc'])
                if market is None:
                    continue
                start = source_timestamp(market['payload']['start'])[1]
                if start not in (trace.epoch - 900, trace.epoch):
                    continue
                prior = found.get(start)
                if prior and (prior['market_id'], prior['payload']['slug']) != (market['market_id'], market['payload']['slug']):
                    raise ValueError('ambiguous market')
                found[start] = market
            if len(rows) < 100:
                return found
    raise ValueError('incomplete catalog')


def classify(raw, market, observed, route):
    event = polymarket_bbo(raw, market, observed['ts_utc'], route=route)
    if not event:
        return 'empty', {}
    payload = event['payload']
    both = payload['best_bid'] is not None and payload['best_ask'] is not None
    return 'quote', {'best_bid': payload['best_bid'], 'best_ask': payload['best_ask'],
                     'sides': 'two' if both else 'one', 'source_time': event['source_time'],
                     'source_time_role': event['provenance']['source_time_role']}


async def rest_once(client, trace):
    slug = quote(trace.market['payload']['slug'], safe='')
    for route in ('bbo', 'book'):
        try:
            doc, observed = await read_json(client, f'{POLYMARKET_REST}/v1/markets/{slug}/{route}',
                                            trace, 'early_rest', route)
        except HttpStatus as exc:
            if route == 'bbo' and exc.code == 404:
                continue
            raise
        stage, fields = classify(doc, trace.market, observed, route)
        trace.emit('early_rest', stage, observed=observed, route=route, **fields)
        return


async def repeat_http(action, trace, reader, interval):
    backoff = 1
    while True:
        try:
            await action()
            backoff = 1
        except HttpStatus as exc:
            if exc.code == 429:
                trace.emit(reader, 'rate_limited', wait_seconds=max(interval, backoff))
                await asyncio.sleep(max(interval, backoff))
                backoff = min(backoff * 2, 60)
                continue
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            trace.emit(reader, 'error', reason=getattr(exc, 'category', type(exc).__name__))
        await asyncio.sleep(interval)


def signing_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    def get(name):
        path = os.environ.get(name + '_FILE')
        return Path(path).read_text().strip() if path else os.environ.get(name)
    key_id, secret = get('POLYMARKET_KEY_ID'), get('POLYMARKET_SECRET_KEY')
    if not key_id or not secret:
        raise ValueError('US markets WebSocket credentials missing; explicit --rest-only is available')
    decoded = base64.b64decode(secret, validate=True)
    if len(decoded) not in (32, 64):
        raise ValueError('unexpected Ed25519 signing key length')
    return key_id, Ed25519PrivateKey.from_private_bytes(decoded[:32])


def headers(keypair):
    key_id, key = keypair
    ms = str(time.time_ns() // 1_000_000)
    signature = base64.b64encode(key.sign((ms + 'GET/v1/ws/markets').encode())).decode()
    return {'X-PM-Access-Key': key_id, 'X-PM-Timestamp': ms, 'X-PM-Signature': signature}


async def check_market_socket():
    """Verify one authenticated market-data handshake using mounted secrets."""
    if not all(os.environ.get(name + '_FILE') for name in
               ('POLYMARKET_KEY_ID', 'POLYMARKET_SECRET_KEY')):
        return {'status': 'pp_key_files_unbound'}
    try:
        keypair = signing_key()
        auth = headers(keypair)
    except (OSError, ValueError):
        return {'status': 'pp_key_files_unusable'}
    try:
        async with connect(WS_URL, additional_headers=auth, proxy=None,
                           open_timeout=5, close_timeout=2,
                           max_size=MAX_RESPONSE_BYTES, max_queue=16):
            return {'status': 'pp_market_socket_authenticated'}
    except InvalidStatus as error:
        return {'status': 'pp_market_socket_rejected', 'http_status': error.response.status_code}
    except (OSError, TimeoutError, WebSocketException):
        return {'status': 'pp_market_socket_unavailable'}


async def websocket(trace, found, keypair):
    slugs = [m['payload']['slug'] for m in found.values()]
    wanted = trace.market['payload']['slug']
    backoff = 1
    while True:
        try:
            trace.emit('websocket', 'connect')
            async with connect(WS_URL, additional_headers=headers(keypair), proxy=None,
                               open_timeout=5, close_timeout=2, ping_timeout=15,
                               max_size=MAX_RESPONSE_BYTES, max_queue=16) as sock:
                request_id = str(uuid.uuid4())
                trace.emit('websocket', 'subscribe', slugs=slugs, request_id=request_id)
                await sock.send(json.dumps({'subscribe': {'requestId': request_id,
                    'subscriptionType': 'SUBSCRIPTION_TYPE_MARKET_DATA', 'marketSlugs': slugs}}))
                while True:
                    message = await asyncio.wait_for(sock.recv(), 45)
                    observed = stamp()
                    doc = json.loads(message, parse_float=Decimal)
                    if not isinstance(doc, dict):
                        raise ValueError('invalid WS message')
                    if doc.get('error') is not None:
                        trace.emit('websocket', 'subscription_error', request_id=request_id)
                        break
                    data = doc.get('marketData')
                    if not isinstance(data, dict):
                        trace.ws_sample('control', {}, observed)
                        continue
                    if data.get('marketSlug') != wanted:
                        stage = 'other_subscribed_market' if data.get('marketSlug') in slugs else 'unexpected_market'
                        trace.ws_sample(stage, {}, observed)
                        continue
                    stage, fields = classify(doc, trace.market, observed, 'book')
                    trace.ws_sample(stage, fields, observed)
                    backoff = 1
        except InvalidStatus as exc:
            code = exc.response.status_code
            trace.emit('websocket', 'handshake_rejected', status=code)
            if code in (401, 403):
                return
        except (OSError, TimeoutError, WebSocketException, ValueError, KeyError, TypeError) as exc:
            trace.emit('websocket', 'error', reason=getattr(exc, 'category', type(exc).__name__))
        trace.emit('websocket', 'reconnect', wait_seconds=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


async def discover_and_read(client, trace, keypair):
    delay = 10
    while True:
        try:
            found = await catalog(client, trace)
            trace.market = found.get(trace.epoch)
            if trace.market:
                break
            trace.emit('early_discovery', 'not_listed')
        except HttpStatus as exc:
            trace.emit('early_discovery', 'error', status=exc.code)
            if exc.code == 429:
                delay = min(60, delay * 2)
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            trace.emit('early_discovery', 'error', reason=type(exc).__name__)
        await asyncio.sleep(delay)
    trace.emit('early_discovery', 'market_identified')
    async with asyncio.TaskGroup() as group:
        group.create_task(repeat_http(lambda: rest_once(client, trace), trace, 'early_rest', 5))
        if keypair:
            group.create_task(websocket(trace, found, keypair))
        else:
            trace.emit('websocket', 'not_configured')


async def dashboard_once(client, trace, url):
    doc, observed = await read_json(client, url, trace, 'dashboard_api', 'state')
    if doc.get('environment') != 'preprod' or doc.get('data_mode') != 'pp_live':
        trace.emit('dashboard_api', 'unexpected_scope', observed=observed)
        return
    market = doc.get('market') or {}
    if not market or source_timestamp(market['start'])[1] != trace.epoch:
        trace.emit('dashboard_api', 'other_or_missing_market', observed=observed)
        return
    quote_data = doc.get('polymarket') or {}
    feed = (doc.get('feeds') or {}).get('polymarket_rest', {})
    market_id = str(market['id'])
    fields = {'market_id': market_id, 'slug': market.get('slug')}
    if feed.get('status') != 'fresh' or not feed.get('market_match') or str(quote_data.get('market_id')) != market_id:
        trace.emit('dashboard_api', 'missing_or_stale', observed=observed, **fields)
        return
    fields.update({name: quote_data.get(name) for name in ('received_at', 'event_id')})
    for side in ('best_bid', 'best_ask'):
        value = quote_data.get(side)
        fields[side] = None if value is None else str(value)
    if fields['best_bid'] is None and fields['best_ask'] is None:
        trace.emit('dashboard_api', 'missing_or_stale', observed=observed, **fields)
        return
    trace.emit('dashboard_api', 'quote', observed=observed, **fields)


async def run(args):
    first = boundary_epoch(args.first_boundary_utc)
    if not time.time() + LEAD_SECONDS <= first <= time.time() + 3600:
        raise ValueError('first boundary must be 2..60 minutes ahead')
    u = httpx.URL(args.api_url)
    if (u.scheme != 'http' or u.host not in ('127.0.0.1', 'localhost', '::1')
            or u.path != '/state/current' or u.username or u.password or u.query or u.fragment):
        raise ValueError('expected loopback /state/current URL')
    keypair = None if args.rest_only else signing_key()
    with evidence_file(args.output) as stream:
        async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
            for epoch in range(first, first + 3600, 900):
                await asyncio.sleep(max(0, epoch - LEAD_SECONDS - time.time()))
                trace = Boundary(epoch, stream)
                trace.emit('observer', 'window_begin', websocket_enabled=bool(keypair))
                remaining = epoch + TAIL_SECONDS - time.time()
                try:
                    async with asyncio.timeout(max(0, remaining)):
                        async with asyncio.TaskGroup() as group:
                            group.create_task(discover_and_read(client, trace, keypair))
                            group.create_task(repeat_http(lambda: dashboard_once(client, trace, str(u)),
                                                         trace, 'dashboard_api', 1))
                except TimeoutError:
                    pass
                counts = {f'{reader}.{stage}': n for (reader, stage), n in trace.counts.items()}
                trace.emit('observer', 'window_end', counts=counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-boundary-utc')
    parser.add_argument('--api-url', help='PP VM loopback /state/current')
    parser.add_argument('--output', help='new private JSONL file')
    parser.add_argument('--rest-only', action='store_true', help='incomplete comparison; does not measure WebSocket')
    parser.add_argument('--check-auth', action='store_true', help='one signed market handshake using mounted files')
    args = parser.parse_args()
    capture = (args.first_boundary_utc, args.api_url, args.output)
    if args.check_auth:
        if any(capture) or args.rest_only:
            parser.error('--check-auth cannot be combined with scheduled capture')
        result = asyncio.run(check_market_socket())
        print(json.dumps(result))
        return int(result['status'] != 'pp_market_socket_authenticated')
    if not all(capture):
        parser.error('--first-boundary-utc, --api-url and --output are required for capture')
    asyncio.run(run(args))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
