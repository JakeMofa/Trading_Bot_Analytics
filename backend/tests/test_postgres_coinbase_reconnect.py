"""Network-free reconnect bounds; no real feed or database access."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidStatus
from websockets.frames import Close
from websockets.datastructures import Headers
from websockets.http11 import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_diagnostics import LiveDiagnostic
from postgres.live_ingest import _pause_or_stop, coinbase_session
from postgres.store import StorageHold


class Store:
    def __init__(self):
        self.settings = SimpleNamespace(environment='preprod', data_mode='pp_live',
                                        origin_id='pp-live-reconnect-fixture')
        self.rows = {}
        self.acknowledgements = 0

    def ingest(self, event):
        previous = self.rows.get(event['event_id'])
        if previous is not None and previous != event:
            raise ValueError('conflicting identity')
        if previous is None:
            self.rows[event['event_id']] = event
            self.acknowledgements += 1
        return {'event_id': event['event_id']}


def closed_error():
    return ConnectionClosedError(Close(1011, 'secret-close'),
                                 Close(1011, 'secret-close'), True)


class CoinbaseReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_transient_disconnects_have_finite_retry_budget(self):
        store, stop = Store(), asyncio.Event()
        opens, delays = [], []

        async def source(_stop):
            opens.append(len(opens) + 1)
            raise closed_error()
            yield  # pragma: no cover

        async def pause(_stop, delay):
            delays.append(delay)

        with self.assertRaises(LiveDiagnostic) as caught:
            await coinbase_session(store, stop, source=source, pause=pause,
                                   clock=lambda: 0)
        self.assertEqual(caught.exception.code, 'coinbase_stream.ws_closed_error')
        self.assertEqual(opens, [1, 2, 3, 4])
        self.assertEqual(delays, [1, 2, 4])
        self.assertEqual(store.rows, {})
        self.assertNotIn('secret', str(caught.exception))

    async def test_stop_during_backoff_prevents_reconnect(self):
        store, stop = Store(), asyncio.Event()
        opens = []

        async def source(_stop):
            opens.append(1)
            raise ConnectionClosedOK(Close(1000, 'secret-close'),
                                     Close(1000, 'secret-close'), True)
            yield  # pragma: no cover

        async def pause(_stop, delay):
            self.assertEqual(delay, 1)
            stop.set()

        await coinbase_session(store, stop, source=source, pause=pause)
        self.assertEqual(opens, [1])
        self.assertEqual(store.rows, {})

    async def test_total_retry_cap_survives_window_expiry(self):
        store, stop = Store(), asyncio.Event()
        opens, delays = [], []
        instant = [0]

        async def source(_stop):
            opens.append(1)
            raise EOFError('private-url')
            yield  # pragma: no cover

        async def pause(_stop, delay):
            delays.append(delay)
            instant[0] += 61

        with self.assertRaises(LiveDiagnostic) as caught:
            await coinbase_session(store, stop, source=source, pause=pause,
                                   clock=lambda: instant[0])
        self.assertEqual(caught.exception.code, 'coinbase_stream.transport')
        self.assertEqual(len(opens), 13)
        self.assertEqual(delays, [1] * 12)
        self.assertEqual(store.rows, {})

    async def test_real_backoff_is_cancelled_promptly(self):
        store, stop = Store(), asyncio.Event()
        paused = asyncio.Event()

        async def source(_stop):
            raise EOFError('secret-transport')
            yield  # pragma: no cover

        async def pause(source_stop, delay):
            paused.set()
            await _pause_or_stop(source_stop, delay)

        task = asyncio.create_task(coinbase_session(store, stop, source=source,
                                                    pause=pause))
        await asyncio.wait_for(paused.wait(), 1)
        stop.set()
        await asyncio.wait_for(task, 0.2)

    async def test_replay_after_reconnect_has_one_durable_identity(self):
        store, stop = Store(), asyncio.Event()
        opened, delays = 0, []
        event = {'event_id': 'same-source-identity', 'source_time': '2026-11-17T12:00:00Z',
                 'price': '100.0000', 'provenance': 'official-source'}

        async def source(_stop):
            nonlocal opened
            opened += 1
            yield dict(event)
            if opened == 1:
                raise EOFError('secret-url')

        async def pause(_stop, delay):
            delays.append(delay)

        await coinbase_session(store, stop, source=source, pause=pause)
        self.assertEqual(opened, 2)
        self.assertEqual(delays, [1])
        self.assertEqual(store.acknowledgements, 1)
        self.assertEqual(store.rows, {event['event_id']: event})

    async def test_fatal_handshake_payload_and_write_errors_do_not_retry(self):
        failures = (
            (InvalidStatus(Response(401, 'secret', Headers(), b'secret-body')),
             'coinbase_stream.http_4xx'),
            (ValueError('secret-invalid-payload'), 'coinbase_stream.invalid_or_unavailable'),
            (RuntimeError('secret-unknown-failure'), 'coinbase_stream.unexpected'),
            (LiveDiagnostic('coinbase_write', 'write_rejected'),
             'coinbase_write.write_rejected'),
        )
        for failure, code in failures:
            with self.subTest(code=code):
                store, stop = Store(), asyncio.Event()
                opens = []

                async def source(_stop):
                    opens.append(1)
                    raise failure
                    yield  # pragma: no cover

                async def no_pause(*_args):
                    self.fail('fatal failure must not retry')

                with self.assertRaises(LiveDiagnostic) as caught:
                    await coinbase_session(store, stop, source=source, pause=no_pause)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(opens, [1])
                self.assertNotIn('secret', str(caught.exception))

    async def test_actual_storage_hold_is_not_retried(self):
        store, stop = Store(), asyncio.Event()
        opens = []

        def held(_event):
            raise StorageHold('private-storage-state')

        store.ingest = held

        async def source(_stop):
            opens.append(1)
            yield {'event_id': 'tick'}

        async def no_pause(*_args):
            self.fail('storage hold must not reconnect')

        with self.assertRaises(LiveDiagnostic) as caught:
            await coinbase_session(store, stop, source=source, pause=no_pause)
        self.assertEqual(caught.exception.code, 'coinbase_write.write_rejected')
        self.assertEqual(opens, [1])
        self.assertNotIn('private', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
