"""CI smoke for a PP 15-minute boundary; generated input and no network."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from websockets.datastructures import Headers
from websockets.exceptions import (ConnectionClosedError, ConnectionClosedOK,
                                   InvalidMessage, InvalidStatus, ProtocolError)
from websockets.frames import Close
from websockets.http11 import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_diagnostics import SourceHTTPFailure, SourceTransportFailure
from postgres.live_ingest import coinbase_session, polymarket_cycle
from postgres.live_sources import coinbase_once
from postgres.live_supervisor import run_bounded
from postgres.operator_session import OperatorSession, SessionStopUnproven


BEFORE = datetime(2026, 11, 17, 12, 14, 59, tzinfo=timezone.utc)
AFTER = datetime(2026, 11, 17, 12, 15, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self):
        self.settings = SimpleNamespace(environment='preprod', data_mode='pp_live',
                                        origin_id='pp-live-boundary-fixture')
        self.events = []
        self.enabled = True
        self.off_calls = 0

    def ingest(self, event):
        if not self.enabled:
            raise AssertionError('write after durable OFF')
        self.events.append(dict(event))
        return {'event_id': event['event_id']}

    def collector_enabled(self):
        return self.enabled

    def disable(self):
        self.off_calls += 1
        self.enabled = False
        return {'collector_enabled': False}


class BoundarySmoke(unittest.IsolatedAsyncioTestCase):
    async def run_socket_failure(self, failure):
        store = Store()
        opens = []

        class Socket:
            async def __aenter__(self):
                if isinstance(failure, InvalidStatus):
                    raise failure
                return self

            async def __aexit__(self, *_args):
                return False

            async def send(self, _value):
                return None

            async def recv(self):
                raise failure

        def connector(url, **options):
            self.assertEqual(url, 'wss://ws-feed.exchange.coinbase.com')
            self.assertEqual(options['open_timeout'], 10)
            opens.append(url)
            return Socket()

        async def coinbase(_store, stop):
            await coinbase_session(store, stop, source=lambda source_stop:
                coinbase_once(source_stop, connector=connector))

        async def idle(*_args, **_kwargs):
            await asyncio.Event().wait()

        async def run(stop, seconds):
            return await run_bounded(store, None, stop, owner_check=lambda: True,
                                     disable_collector=store.disable, max_seconds=seconds,
                                     coinbase=coinbase, market=idle, candles=idle)

        session = OperatorSession(run, store.disable)
        await session.start(max_seconds=2)
        await asyncio.wait_for(session._task, 2)
        return session, store, opens

    async def test_coinbase_websocket_failures_have_fixed_codes_and_no_retry(self):
        def rejected(status):
            return InvalidStatus(Response(status, 'secret-provider-reason',
                                          Headers(), b'secret-provider-body'))

        failures = (
            (ConnectionClosedOK(Close(1000, 'secret-close'),
                                Close(1000, 'secret-close'), True), 'coinbase_stream.ws_closed_ok'),
            (ConnectionClosedError(Close(1011, 'secret-close'),
                                   Close(1011, 'secret-close'), True), 'coinbase_stream.ws_closed_error'),
            (rejected(401), 'coinbase_stream.http_4xx'),
            (rejected(429), 'coinbase_stream.http_429'),
            (rejected(503), 'coinbase_stream.http_5xx'),
            (InvalidMessage('secret-protocol'), 'coinbase_stream.ws_handshake_invalid'),
            (ProtocolError('secret-protocol'), 'coinbase_stream.ws_protocol'),
            (EOFError('secret-transport'), 'coinbase_stream.transport'),
            (RuntimeError('secret-unexpected'), 'coinbase_stream.unexpected'),
        )
        for failure, code in failures:
            with self.subTest(code=code):
                session, store, opens = await self.run_socket_failure(failure)
                self.assertEqual(session.state()['failure_code'], code)
                self.assertFalse(store.enabled)
                self.assertGreaterEqual(store.off_calls, 2)
                self.assertEqual(len(opens), 1)
                self.assertEqual(store.events, [])
                self.assertNotIn('secret', str(session.state()))
                await session.stop()
                self.assertEqual(session.state()['failure_code'], code)

    async def run_session(self, *, second_failure=None, discovery_failure=None,
                          missing_once=False):
        store = Store()
        crossed = asyncio.Event()
        second_tick = asyncio.Event()
        discoveries = 0

        async def coinbase(_store, _stop):
            await asyncio.to_thread(store.ingest, {'kind': 'coinbase', 'event_id': 'tick-before'})
            await crossed.wait()
            await asyncio.to_thread(store.ingest, {'kind': 'coinbase', 'event_id': 'tick-after'})
            second_tick.set()
            await _stop.wait()

        async def discover(_client, now):
            nonlocal discoveries
            discoveries += 1
            if discoveries == 1:
                self.assertEqual(now, BEFORE)
                return {'market_id': 'old', 'event_id': 'market-old'}
            self.assertEqual(now, AFTER)
            crossed.set()
            if missing_once and discoveries == 2:
                return None
            if discovery_failure is not None:
                await asyncio.wait_for(second_tick.wait(), 1)
                raise discovery_failure
            return {'market_id': 'new', 'event_id': 'market-new'}

        async def fetch(_client, market):
            if market['market_id'] == 'new':
                await asyncio.wait_for(second_tick.wait(), 1)
                if second_failure is not None:
                    raise second_failure
            return {'market_id': market['market_id'],
                    'event_id': 'quote-' + market['market_id']}

        async def market(_store, client, _stop, *, now):
            result = await polymarket_cycle(store, client, _stop, now=now,
                                            discover=discover, fetch=fetch)
            if result == 'new':
                _stop.set()

        async def candles(_store, _client, _stop, *, now):
            await _stop.wait()

        async def run(_stop, seconds):
            return await run_bounded(store, None, _stop, owner_check=lambda: True,
                                     disable_collector=store.disable, max_seconds=seconds,
                                     market_interval=1, candle_interval=60,
                                     coinbase=coinbase, market=market, candles=candles,
                                     clock=lambda: BEFORE if discoveries == 0 else AFTER)

        session = OperatorSession(run, store.disable)
        await session.start(max_seconds=5)
        await asyncio.wait_for(session._task, 4)
        return session, store

    async def test_missing_boundary_market_does_not_replay_old_quote(self):
        session, store = await self.run_session(missing_once=True)
        self.assertIsNone(session.state()['failure_code'])
        self.assertFalse(store.enabled)
        self.assertGreaterEqual(store.off_calls, 2)
        ids = [event['event_id'] for event in store.events]
        self.assertEqual(ids.count('quote-old'), 1)
        self.assertEqual(ids.count('quote-new'), 1)
        self.assertIn('tick-after', ids)
        self.assertLess(ids.index('quote-old'), ids.index('market-new'))

    async def test_new_market_errors_stop_durably_with_sanitized_code(self):
        failures = (
            ('discovery', SourceHTTPFailure(429, 'secret-provider-body'),
             'polymarket_discovery.http_429'),
            ('discovery', SourceTransportFailure(timeout=True, message='secret-url'),
             'polymarket_discovery.timeout'),
            ('bbo', SourceHTTPFailure(404, 'secret-provider-body'), 'polymarket_bbo.http_404'),
            ('bbo', SourceHTTPFailure(429, 'secret-provider-body'), 'polymarket_bbo.http_429'),
            ('bbo', SourceTransportFailure(timeout=True, message='secret-url'), 'polymarket_bbo.timeout'),
            ('bbo', ValueError('secret-invalid-payload'), 'polymarket_bbo.invalid_or_unavailable'),
        )
        for stage, failure, code in failures:
            with self.subTest(code=code):
                session, store = await self.run_session(
                    discovery_failure=failure if stage == 'discovery' else None,
                    second_failure=failure if stage == 'bbo' else None)
                self.assertEqual(session.state()['failure_code'], code)
                self.assertFalse(store.enabled)
                self.assertGreaterEqual(store.off_calls, 2)
                ids = [event['event_id'] for event in store.events]
                self.assertIn('tick-after', ids)
                self.assertEqual('market-new' in ids, stage == 'bbo')
                self.assertNotIn('quote-new', ids)
                self.assertEqual(ids.count('quote-old'), 1)
                self.assertNotIn('secret', str(session.state()))
                with self.assertRaises(SessionStopUnproven):
                    await session.start(max_seconds=5)
                await session.stop()
                self.assertEqual(session.state()['failure_code'], code)


if __name__ == '__main__':
    unittest.main()
