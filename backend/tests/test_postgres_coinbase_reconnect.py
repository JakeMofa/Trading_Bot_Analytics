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
    async def test_transient_storm_cools_down_without_ending_session(self):
        store, stop = Store(), asyncio.Event()
        opens, delays = [], []
        instant = [0.0]

        async def source(_stop):
            opens.append(instant[0])
            if len(opens) == 15:
                stop.set()
                return
            raise closed_error()
            yield

        async def pause(_stop, delay):
            delays.append(delay)
            instant[0] += delay

        await coinbase_session(store, stop, source=source, pause=pause,
                               clock=lambda: instant[0])
        self.assertEqual(opens[:5], [0, 1, 3, 7, 61])
        self.assertEqual(delays[:4], [1, 2, 4, 54])
        self.assertEqual(len(opens), 15)  # No arbitrary session-total 12 stop.
        retries = opens[1:]
        for at in retries:
            self.assertLessEqual(sum(at - 60 < other <= at for other in retries), 3)
        self.assertEqual(store.rows, {})

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

    async def test_separated_network_interruptions_survive_more_than_twelve_retries(self):
        store, stop = Store(), asyncio.Event()
        opens, delays = [], []
        instant = [0.0]
        async def source(_stop):
            opens.append(instant[0])
            if len(opens) == 16:
                stop.set()
                return
            raise EOFError('private-url')
            yield
        async def pause(_stop, delay):
            delays.append(delay)
            instant[0] += delay + 61
        await coinbase_session(store, stop, source=source, pause=pause, clock=lambda: instant[0])
        self.assertEqual(len(opens),16)
        self.assertEqual(delays[:6],[1,2,4,8,16,30])
        self.assertTrue(all(delay <= 30 for delay in delays))

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
        instant = [0.0]
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
            instant[0] += delay

        await coinbase_session(store, stop, source=source, pause=pause,clock=lambda:instant[0])
        self.assertEqual(opened, 2)
        self.assertEqual(delays, [1])
        self.assertEqual(store.acknowledgements, 1)
        self.assertEqual(store.rows, {event['event_id']: event})

    async def test_backoff_resets_only_on_fresh_new_durable_progress(self):
        from datetime import datetime,timezone
        for duplicate,source_time,expected in (
            (False,'2026-11-17T12:00:00Z',[1,1]),
            (True,'2026-11-17T12:00:00Z',[1,2]),
            (False,'2026-11-17T11:58:00Z',[1,2]),
            (False,'2026-11-17T12:00:02Z',[1,2]),
        ):
            with self.subTest(duplicate=duplicate,source_time=source_time):
                store,stop=Store(),asyncio.Event();instant=[0.0];opens=[];delays=[]
                store.ingest=lambda event:{'duplicate':duplicate}
                async def source(_stop):
                    opens.append(instant[0])
                    if len(opens)==3:
                        stop.set();return
                    if len(opens)==2:yield {'source_time':source_time}
                    raise closed_error()
                async def pause(_stop,delay):delays.append(delay);instant[0]+=delay
                await coinbase_session(store,stop,source=source,pause=pause,clock=lambda:instant[0],
                    wall_clock=lambda:datetime(2026,11,17,12,0,1,tzinfo=timezone.utc))
                self.assertEqual(delays,expected)

    async def test_rate_cooldown_is_stop_aware_without_reopening(self):
        store,stop=Store(),asyncio.Event();instant=[0.0];opens=[];delays=[]
        async def source(_stop):
            opens.append(instant[0]);raise closed_error();yield
        async def pause(_stop,delay):
            delays.append(delay)
            if delay>30:stop.set()
            instant[0]+=delay
        await coinbase_session(store,stop,source=source,pause=pause,clock=lambda:instant[0])
        self.assertEqual(opens,[0,1,3,7]);self.assertEqual(delays,[1,2,4,54])

    async def test_early_pause_does_not_open_before_actual_rate_slot(self):
        store,stop=Store(),asyncio.Event();opens=[];waits=[]
        async def source(_stop):opens.append(1);raise closed_error();yield
        async def pause(_stop,delay):
            waits.append(delay)
            if len(waits)==2:stop.set()
        await coinbase_session(store,stop,source=source,pause=pause,clock=lambda:0)
        self.assertEqual(opens,[1]);self.assertEqual(waits,[1,1])

    async def test_supervisor_deadline_still_disables_same_network_degraded_session(self):
        from postgres.live_supervisor import run_bounded
        store,stop=Store(),asyncio.Event();enabled=[True];off_calls=[];opens=[]
        store.collector_enabled=lambda:enabled[0]
        def disable():enabled[0]=False;off_calls.append(1);return False
        async def source(_stop):opens.append(1);raise closed_error();yield
        async def coinbase(_store,_stop):await coinbase_session(_store,_stop,source=source)
        async def idle(*_args,**_kw):await asyncio.Event().wait()
        with self.assertRaises(LiveDiagnostic) as caught:
            await run_bounded(store,None,stop,owner_check=lambda:True,disable_collector=disable,
                max_seconds=0.05,coinbase=coinbase,market=idle,candles=idle)
        self.assertEqual(caught.exception.code,'session.deadline_reached')
        self.assertEqual(opens,[1]);self.assertEqual(off_calls,[1]);self.assertFalse(enabled[0])

    async def test_lease_loss_during_network_backoff_still_disables_collector(self):
        from postgres.live_supervisor import run_bounded
        store,stop=Store(),asyncio.Event();owned=[True];off_calls=[];opens=[]
        store.collector_enabled=lambda:True
        def disable():off_calls.append(1);return False
        async def source(_stop):
            opens.append(1);raise closed_error();yield
        async def pause(_stop,delay):
            owned[0]=False
            await _pause_or_stop(_stop,delay)
        async def coinbase(_store,_stop):await coinbase_session(_store,_stop,source=source,pause=pause)
        async def idle(*_args,**_kw):await asyncio.Event().wait()
        with self.assertRaises(LiveDiagnostic) as caught:
            await run_bounded(store,None,stop,owner_check=lambda:owned[0],disable_collector=disable,
                max_seconds=3,coinbase=coinbase,market=idle,candles=idle)
        self.assertEqual(caught.exception.code,'ownership.lease_lost')
        self.assertEqual(off_calls,[1]);self.assertLessEqual(len(opens),2)

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
