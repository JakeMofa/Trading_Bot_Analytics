"""A bounded writer pipeline and a disposable latest-price view for PP."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import os
import time
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .boundary_trace import boundary_trace
from .boundary_shadow import WS_URL, headers, signing_key
from .contract import content_hash, source_timestamp
from .domain import timestamp
from .live_contract import polymarket_bbo
from .live_sources import MAX_RESPONSE_BYTES, discover_polymarket_15m
from .live_ingest import _pause_or_stop, _step, POLYMARKET_DISCOVERY_UNAVAILABLE
from .live_diagnostics import LiveDiagnostic
from .feed_writer import feed_writer
from .quote_display import DisplaySender
from .reference_prices import ONE_SECOND_ORIGINS, collect_reference


def utc():
    return datetime.now(timezone.utc).isoformat()


class QuotePipeline:
    def __init__(self, store, display):
        self.store = store
        self.display = display
        self.queue = asyncio.Queue(maxsize=32)
        self.current = self.upcoming = None
        self.quote = None
        self.received = self.saved = self.duplicates = 0
        self.started = utc()
        self.reference = None
        self.previous_robinhood = None
        self.last_commit = None
        self.first_event_id = None

    def broadcast(self):
        market = self.current
        if market:
            terms = market['payload']
            self.display.send({'market': {'id': market['market_id'], 'origin': self.store.settings.origin_id,
                                **{k: terms[k] for k in ('slug', 'start', 'end', 'target_usd', 'status')}},
                               'reference': self.reference, 'quote': self.quote, 'received': self.received, 'saved': self.saved,
                               'duplicates': self.duplicates, 'started_at': self.started, 'last_commit': self.last_commit})

    def publish_reference(self, event):
        if self.reference and timestamp(event['source_time']) < timestamp(self.reference['source_time']):
            return
        self.reference = {'price_usd': event['price'], 'source_time': event['source_time'],
                          'received_at': event['received_at'], 'event_id': event['event_id']}
        self.broadcast()

    def publish_robinhood(self, event):
        from .robinhood_history import quote_movement
        current = {'event_id': event['event_id'], 'price_usd': event['price'],
                   'received_at': event['received_at'], 'source_time': event['source_time'],
                   'book_status': event['payload']['book_status']}
        if self.previous_robinhood and current['event_id'] == self.previous_robinhood['event_id']:
            return
        movement = quote_movement(self.previous_robinhood, current)
        self.previous_robinhood = current
        self.display.send({'type': 'robinhood_reference', 'reference': {**current, 'movement': movement}})

    async def market(self, event):
        if self.current and self.current['event_id'] == event['event_id']:
            return
        if not self.current or self.current['market_id'] != event['market_id']:
            self.quote = None
            self.first_event_id = None
        # Enqueue the market before its socket subscription becomes visible.
        await self.queue.put(event)
        self.current = event
        self.broadcast()

    async def book(self, doc, *, received_at=None):
        event = self.current
        data = doc.get('marketData')
        if not data:
            return
        now = received_at or utc()
        upcoming = self.upcoming
        if (upcoming and data.get('marketSlug') == upcoming['payload']['slug']
                and timestamp(upcoming['payload']['start']) <= timestamp(now) < timestamp(upcoming['payload']['end'])):
            await self.market(upcoming)
            event = upcoming
        if not event or data.get('marketSlug') != event['payload']['slug']:
            return
        if not timestamp(event['payload']['start']) <= timestamp(now) < timestamp(event['payload']['end']):
            return
        # Transport request IDs change on reconnect. Use the venue book itself.
        quote = polymarket_bbo({'marketData': data}, event, now, route='book')
        if not quote:
            return
        quote['provenance']['feed'] = 'polymarket_us_websocket'
        if quote['source_time']:
            quote['event_id'] = 'ws-' + content_hash([event['market_id'], data])
            if self.quote and self.quote['source_time'] and source_timestamp(quote['source_time'])[1] < source_timestamp(self.quote['source_time'])[1]:
                return
        self.received += 1
        if self.quote and quote['event_id'] == self.quote['event_id']:
            self.duplicates += 1
            self.broadcast()
            return
        self.quote = {**quote['payload'], **{k: quote[k] for k in
                      ('market_id', 'event_id', 'source_time', 'received_at', 'provenance')}}
        if self.first_event_id is None:
            self.first_event_id = quote['event_id']
            boundary_trace('usable_receipt', event, quote=quote, reader='canonical_ws')
        self.broadcast()
        await self.queue.put(quote)

    async def write(self):
        async with feed_writer(self.store):
            await self._write_queue()

    async def _write_queue(self):
        next_trace = 0.0
        while True:
            event = await self.queue.get()
            ack = await asyncio.to_thread(self.store.ingest, event)
            if event['kind'] == 'quote':
                if not ack['duplicate']:
                    self.saved += 1
                else:
                    self.duplicates += 1
                self.last_commit = {'event_id': event['event_id'], 'at': utc()}
                if time.monotonic() >= next_trace:
                    boundary_trace('writer_sample', quote=event, reader='canonical_ws',
                                   queue_depth=self.queue.qsize(), queue_limit=self.queue.maxsize,
                                   committed_at=self.last_commit['at'], duplicate=ack['duplicate'])
                    next_trace = time.monotonic() + 5
                if event['event_id'] == self.first_event_id:
                    boundary_trace('write_complete', quote=event, reader='canonical_ws',
                                   generation_id=ack['generation_id'], content_hash=ack['content_hash'])
                self.broadcast()
            self.queue.task_done()


async def stream_books(pipe, stop, keypair, *, refresh_key=None):
    delay = 1
    next_reject_log = 0
    while not stop.is_set():
        try:
            if refresh_key:
                try:
                    keypair = refresh_key()
                except (ValueError, OSError):
                    logging.getLogger(__name__).warning('pp_websocket_signer_unavailable')
                    await _pause_or_stop(stop, delay)
                    delay = min(60, delay * 2)
                    continue
            async with connect(WS_URL, additional_headers=headers(keypair), proxy=None,
                               open_timeout=5, close_timeout=2, max_size=MAX_RESPONSE_BYTES,
                               max_queue=16) as sock:
                subscribed = set()
                while not stop.is_set():
                    wanted = {market['payload']['slug'] for market in (pipe.current, pipe.upcoming) if market}
                    missing = wanted - subscribed
                    if missing:
                        await sock.send(json.dumps({'subscribe': {'requestId': str(uuid4()),
                            'subscriptionType': 'SUBSCRIPTION_TYPE_MARKET_DATA', 'marketSlugs': sorted(missing)}}))
                        subscribed.update(missing)
                    try:
                        wire = await asyncio.wait_for(sock.recv(), .25)
                        received_at = utc()
                    except TimeoutError:
                        continue
                    try:
                        doc = json.loads(wire, parse_float=Decimal)
                        if not isinstance(doc,dict):
                            raise ValueError('unexpected WebSocket frame')
                        if doc.get('error'):
                            # Resubscribe with backoff; the writer retains already accepted quotes.
                            break
                        await pipe.book(doc, received_at=received_at)
                    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                        if time.monotonic() >= next_reject_log:
                            logging.getLogger(__name__).warning('pp_websocket_frame_rejected')
                            next_reject_log = time.monotonic() + 30
                        continue
                    delay = 1
        except InvalidStatus as exc:
            if exc.response.status_code not in (429, 500, 502, 503, 504) and not (
                refresh_key and exc.response.status_code in (401,403)
            ):
                raise
        except (OSError, TimeoutError, ConnectionClosed):
            pass
        await _pause_or_stop(stop, delay)
        delay = min(30, delay * 2)


async def run_robinhood(store, stop):
    from .robinhood_history import collect
    sender = DisplaySender(store.settings.origin_id)
    try:
        await collect(store, stop, QuotePipeline(store, sender).publish_robinhood, surface_write_failure=True)
    finally:
        sender.socket.close()


async def run(store, client, stop, interval, clock, *, include_robinhood=True):
    sender = DisplaySender(store.settings.origin_id)
    pipe = QuotePipeline(store, sender)
    try:
        from .quote_ack_counter import WATCH_ORIGIN, register
        if store.settings.origin_id == WATCH_ORIGIN:
            try:
                pipe.started = await asyncio.to_thread(register,store)
            except Exception:
                # A missing display counter remains unknown; keep market ingestion available.
                pass
        keypair = signing_key() if include_robinhood else None
        async with asyncio.TaskGroup() as tasks:
            writer = tasks.create_task(pipe.write())
            reader = tasks.create_task(stream_books(pipe, stop, keypair, refresh_key=None if include_robinhood else signing_key))
            if include_robinhood and os.getenv('TRADEBOT_PP_ROBINHOOD_REFERENCE') == '1':
                from .robinhood_history import collect
                tasks.create_task(collect(store, stop, pipe.publish_robinhood))
            cadence = 1 if store.settings.origin_id in ONE_SECOND_ORIGINS else 5
            tasks.create_task(collect_reference(store, client, stop, clock, pipe.publish_reference, cadence=cadence))
            while not stop.is_set():
                try:
                    market, upcoming = await _step('polymarket_discovery',
                        discover_polymarket_15m(client, clock(), include_next=True))
                except LiveDiagnostic as error:
                    if error.code not in POLYMARKET_DISCOVERY_UNAVAILABLE:
                        raise
                else:
                    pipe.upcoming = upcoming
                    if market and timestamp(market['payload']['end']) > clock():
                        await pipe.market(market)
                        pipe.broadcast()
                await _pause_or_stop(stop, interval)
            await reader
            await pipe.queue.join()
            writer.cancel()
    finally:
        sender.socket.close()
