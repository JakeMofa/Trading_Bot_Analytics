"""One optional Robinhood v1 BTC/USD reference poller per PP collector."""
import asyncio
from decimal import Decimal, InvalidOperation, localcontext
import json
import logging
import os
from pathlib import Path
import time

import httpx

from . import benchmark_telemetry as metrics
from .contract import content_hash, exact_decimal, source_timestamp
from .domain import timestamp
from .feed_writer import feed_writer
from .robinhood_quote_observer import V1_PATH, sample, signed_headers, signing_material

LOG = logging.getLogger(__name__)
SOURCE = 'robinhood_crypto'
FEED = 'robinhood_crypto_v1_best_bid_ask'


def credentials():
    values = {}
    for name in ('ROBINHOOD_API_KEY', 'ROBINHOOD_PRIVATE_KEY'):
        file = os.getenv(name + '_FILE')
        value = os.getenv(name)
        if value and file:
            raise ValueError('ambiguous Robinhood credential source')
        values[name] = Path(file).read_text().strip() if file else value or ''
    return signing_material(values)


def v1_book(payload):
    rows = json.loads(payload, parse_float=Decimal)['results']
    if (not isinstance(rows, list) or len(rows) != 1
            or not isinstance(rows[0], dict) or rows[0].get('symbol') != 'BTC-USD'):
        raise ValueError('missing BTC-USD quote')
    row = rows[0]

    def number(name, *, spread=False):
        raw = row.get(name)
        if raw is None:
            return None
        value = exact_decimal(raw)
        if abs(value.as_tuple().exponent) > 60 or len(value.as_tuple().digits) > 60:
            raise ValueError('Robinhood decimal exceeds bounds')
        if value < 0 or (not spread and value == 0):
            raise ValueError('invalid Robinhood quote')
        return str(value)

    provider_stamp = row.get('timestamp')
    if provider_stamp is not None:
        source_timestamp(provider_stamp)
    price = number('price')
    bid = number('bid_inclusive_of_sell_spread')
    ask = number('ask_inclusive_of_buy_spread')
    if price is None and bid is None and ask is None:
        raise ValueError('no usable price or side')
    status = 'partial'
    if bid is not None and ask is not None:
        status = 'crossed' if Decimal(bid) > Decimal(ask) else 'two_sided'
    return {'provider_price': price, 'bid': bid, 'ask': ask, 'book_status': status,
            'sell_spread': number('sell_spread', spread=True), 'buy_spread': number('buy_spread', spread=True),
            'provider_timestamp': provider_stamp, 'raw_payload': bytes(payload).decode('utf-8')}


def price_event(row):
    requested, received = row['requested_at'], row['received_at']
    if timestamp(received) < timestamp(requested):
        raise ValueError('Robinhood response before request')
    fields = {name: row[name] for name in (
        'provider_price', 'bid', 'ask', 'book_status', 'sell_spread', 'buy_spread',
        'provider_timestamp', 'requested_at', 'http_round_trip_ms')}
    # Two independent requests are distinct observations even when every venue
    # value repeats. Retrying the write for the same poll recovers the same ID.
    identity = 'rh-v1-' + content_hash([SOURCE, 'BTC-USD', requested])
    return {'source': SOURCE, 'kind': 'reference_quote', 'symbol': 'BTC-USD', 'event_id': identity,
            'price': row['provider_price'] if row['book_status'] != 'crossed' else None,
            'source_time': row['provider_timestamp'], 'received_at': received, 'payload': fields,
            'raw_payload': row['raw_payload'], 'provenance': {'data_mode': 'pp_live', 'feed': FEED, 'api_version': 'v1',
                'price_role': 'partner_market_maker_midpoint', 'source_time_role': 'retrieved_by_robinhood'}}


def quote_movement(previous, current):
    """Change from the preceding valid, recent poll on this collector session."""
    if not previous:
        return None
    now = timestamp(current['received_at'])
    for observation in (previous, current):
        if (observation['price_usd'] is None or observation['source_time'] is None
                or observation['book_status'] == 'crossed'):
            return None
        for t in ('source_time', 'received_at'):
            if not 0 <= (now - timestamp(observation[t])).total_seconds() <= 10:
                return None
    if source_timestamp(current['source_time'])[1] < source_timestamp(previous['source_time'])[1]:
        return None
    with localcontext() as ctx:
        # The input guard allows 60-digit coefficients and exponents up to 60.
        ctx.prec = 200
        difference = Decimal(current['price_usd']) - Decimal(previous['price_usd'])
    return {'delta_usd': format(difference, 'f'), 'previous_event_id': previous['event_id'],
            'previous_received_at': previous['received_at']}


async def pause(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except TimeoutError:
        pass


async def persist(store, event):
    from psycopg import OperationalError
    for attempt in range(3):
        try:
            await asyncio.to_thread(store.ingest, event)
            return
        except OperationalError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.2 * 2 ** attempt)


async def collect(store, stop, publish, *, transport=None, cadence=1, surface_write_failure=False):
    """Sequential HTTP reads, independent of Polymarket and dashboard viewer count."""
    if not 1 <= cadence <= 60:
        raise ValueError('invalid Robinhood polling cadence')
    try:
        key = credentials()
    except (ValueError, OSError):
        metrics.issue('robinhood_reference', 'auth')
        LOG.warning('pp_robinhood_reference_disabled reason=invalid_credentials')
        return
    async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False, transport=transport) as client, feed_writer(store):
        backoff = 0
        while not stop.is_set():
            if backoff:
                metrics.issue('robinhood_reference', 'retry')
            started = time.monotonic()
            delay = 0
            try:
                headers = signed_headers(key, int(time.time()), V1_PATH)
                async with asyncio.timeout(5):
                    row, delay = await sample(client, headers, path=V1_PATH, decode=v1_book)
                if row['status'] == 'quote':
                    event = price_event(row)
                    publish(event)
                    try:
                        await persist(store, event)
                    except Exception as exc:
                        # Stop only the auxiliary feed and identify the last
                        # displayed event if its commit could not be confirmed.
                        metrics.issue('robinhood_reference', 'write')
                        LOG.warning('pp_robinhood_reference_writer_stopped event=%s reason=%s',
                                    event['event_id'], type(exc).__name__)
                        if surface_write_failure:
                            raise RuntimeError('Robinhood write could not be confirmed') from exc
                        return
                    backoff = 0
                elif row['http_status'] in (401, 403):
                    metrics.issue('robinhood_reference', 'auth')
                    LOG.warning('pp_robinhood_reference_disabled http_status=%s', row['http_status'])
                    return
                else:
                    metrics.issue('robinhood_reference', metrics.classify_status(row['http_status']))
                    LOG.warning('pp_robinhood_reference_http_error status=%s', row['http_status'])
                    backoff = min(60, max(cadence, backoff * 2))
            except (httpx.HTTPError, OSError, ValueError, InvalidOperation, TypeError, KeyError, TimeoutError) as exc:
                metrics.issue('robinhood_reference', 'transport' if isinstance(exc, (httpx.HTTPError,OSError,TimeoutError)) else 'invalid')
                LOG.warning('pp_robinhood_reference_unavailable reason=%s', type(exc).__name__)
                backoff = min(60, max(cadence, backoff * 2))
            # Retry-After is authoritative even when longer than the backoff.
            await pause(stop, max(0, delay, backoff, cadence - (time.monotonic() - started)))
