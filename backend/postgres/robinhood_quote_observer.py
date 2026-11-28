"""Bounded read-only Robinhood Crypto v2 BTC/USD comparison observer."""
import argparse
import asyncio
import base64
import binascii
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from email.utils import parsedate_to_datetime
import json
import os
import time

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HOST = 'https://trading.robinhood.com'
PATH = '/api/v2/crypto/marketdata/best_bid_ask/?symbol=BTC-USD'
MAX_BYTES = 16_384


def signing_material(env):
    key_id = env.get('ROBINHOOD_API_KEY', '')
    if not key_id or len(key_id) > 256 or not key_id.isascii() or not all(32 < ord(c) < 127 for c in key_id):
        raise ValueError('ROBINHOOD_API_KEY is missing or invalid')
    try:
        seed = base64.b64decode(env.get('ROBINHOOD_PRIVATE_KEY', ''), validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(seed)
    except (ValueError, TypeError, binascii.Error):
        raise ValueError('ROBINHOOD_PRIVATE_KEY must contain a base64 32-byte Ed25519 seed') from None
    if key_id in (base64.b64encode(seed).decode('ascii'),
                  base64.b64encode(private_key.public_key().public_bytes_raw()).decode('ascii')):
        raise ValueError('ROBINHOOD_API_KEY needs the issued API identifier for the registered public key')
    return key_id, private_key


def signed_headers(keypair, epoch_seconds):
    key_id, key = keypair
    stamp = str(epoch_seconds)
    signature = key.sign((key_id + stamp + PATH + 'GET').encode('ascii'))
    return {'x-api-key': key_id, 'x-timestamp': stamp, 'x-signature': base64.b64encode(signature).decode('ascii')}


def book(payload):
    def positive(value):
        if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
            raise ValueError('invalid quote')
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or not -60 <= number.as_tuple().exponent <= 60 or len(number.as_tuple().digits) > 60:
            raise ValueError('invalid quote')
        return number

    rows = json.loads(payload, parse_float=Decimal)['results']
    if not isinstance(rows, list) or len(rows) != 1 or rows[0]['symbol'] != 'BTC-USD':
        raise ValueError('missing BTC-USD quote')
    bid, ask = positive(rows[0]['bid']), positive(rows[0]['ask'])
    provider_timestamp = rows[0].get('timestamp')
    if provider_timestamp is not None:
        try:
            parsed = datetime.fromisoformat(provider_timestamp)
            if parsed.tzinfo is None:
                provider_timestamp = None
        except (ValueError, TypeError):
            provider_timestamp = None
    with localcontext() as ctx:
        ctx.prec = 200
        return {'symbol': 'BTC-USD', 'bid': str(bid), 'ask': str(ask), 'midpoint': str((bid + ask) / 2) if bid <= ask else None,
                'book_status': 'two_sided' if bid <= ask else 'crossed',
                'provider_timestamp': provider_timestamp, 'source_time': None}


def retry_delay(header, now):
    try:
        return max(1, int(header))
    except (ValueError, TypeError):
        try:
            return max(1, (parsedate_to_datetime(header).timestamp() - now))
        except (ValueError, OverflowError, TypeError):
            return 30


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


async def sample(client, headers):
    sent, start = time.time(), time.monotonic()
    async with client.stream('GET', HOST + PATH, headers=headers) as response:
        status = response.status_code
        if status != 200:
            return {'requested_at': iso(sent), 'status': 'http_error', 'http_status': status}, retry_delay(
                response.headers.get('retry-after'), time.time()) if status == 429 else 0
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            if len(payload) + len(chunk) > MAX_BYTES:
                raise ValueError('response too large')
            payload.extend(chunk)
        received, end = time.time(), time.monotonic()
    quote = book(payload)
    return {'requested_at': iso(sent), 'received_at': iso(received),
            'http_round_trip_ms': round((end-start)*1000, 3),
            'receipt_age_ms_at_sample': round((time.monotonic()-end)*1000, 3),
            'status': 'quote', **quote}, 0


async def observe(keypair, duration, interval, *, emit, transport=None):
    deadline = time.monotonic() + duration
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5, transport=transport) as client:
        while (remaining := deadline - time.monotonic()) > 0:
            start = time.monotonic()
            delay = 0
            try:
                async with asyncio.timeout(min(5, remaining)):
                    row, delay = await sample(client, signed_headers(keypair, int(time.time())))
            except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
                # Never emit a response body or signing data.
                row = {'at': iso(time.time()), 'status': 'unavailable', 'reason': type(exc).__name__}
            emit({'source': 'robinhood_crypto_v2_best_bid_ask', **row})
            if row.get('http_status') in (401, 403):
                return
            until_next = max(delay, interval - (time.monotonic() - start))
            await asyncio.sleep(max(0, min(deadline - time.monotonic(), until_next)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration-seconds', type=int, default=60)
    parser.add_argument('--interval-seconds', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.duration_seconds <= 1200 or not 2 <= args.interval_seconds <= 60:
        parser.error('duration must be 1–1200 seconds and interval 2–60 seconds')
    try:
        keypair = signing_material(os.environ)
    except ValueError as exc:
        parser.error(str(exc))
    asyncio.run(observe(keypair, args.duration_seconds, args.interval_seconds,
                        emit=lambda row: print(json.dumps(row, allow_nan=False), flush=True)))


if __name__ == '__main__':
    main()
