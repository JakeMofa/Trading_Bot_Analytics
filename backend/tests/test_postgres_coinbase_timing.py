"""Offline-only diagnostic clocks and actual loopback queue backpressure."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from websockets.asyncio.server import serve
from postgres.coinbase_timing import CoinbaseTiming, configured_timing
from postgres.live_ingest import coinbase_session
from postgres.live_diagnostics import LiveDiagnostic


class TimingTests(unittest.TestCase):
    def test_default_off_and_exact_opt_in(self):
        self.assertIsNone(configured_timing({}))
        self.assertIsNotNone(configured_timing({'TRADEBOT_PP_COINBASE_TIMING':'true'}))
        for value in ('1', 'TRUE', '', True):
            with self.assertRaises(ValueError):
                configured_timing({'TRADEBOT_PP_COINBASE_TIMING':value})

    def test_worker_dispatch_is_separate_from_actual_ingest(self):
        now=[100.0]
        sink=[]
        timing=CoinbaseTiming(clock=lambda:now[0],emit=sink.append)
        timing.read_started()
        now[0]=101
        timing.parser_ingress()
        now[0]=102
        timing.read_completed()
        timing.parsed({'event_id':'exchange-trade-1','source_time':'2026-11-19T07:10:00Z',
                       'received_at':'2026-11-19T07:10:40Z','price':'secret-price'})
        now[0]=106
        timing.saved(submitted=102,worker=dict(started=103,completed=105),outcome='returned')
        result=sink[0]
        self.assertEqual(result['metrics']['worker_queue_ms']['max'],1000)
        self.assertEqual(result['metrics']['save_ms']['max'],2000)
        self.assertEqual(result['metrics']['resume_ms']['max'],1000)
        self.assertEqual(result['metrics']['parser_queue_ms']['max'],1000)
        self.assertNotIn('secret-price',json.dumps(result))

    def test_metadata_overflow_marks_queue_timing_unavailable_without_dropping_data(self):
        timing=CoinbaseTiming(emit=lambda _:None)
        for _ in range(timing.MAX_PENDING_MESSAGES+1):
            timing.parser_ingress()
        self.assertTrue(timing.queue_metadata_lost)
        self.assertEqual(len(timing.pending),0)
        timing.read_started()
        timing.read_completed()
        self.assertIsNone(timing.last_read['parser_queue_ms'])
        self.assertEqual(timing.last_read['ingress_basis'],'unavailable')
        timing.connection_attempt()
        self.assertFalse(timing.queue_metadata_lost)

    def test_logging_failure_is_observational(self):
        def broken(_):
            raise OSError('private output details')
        timing=CoinbaseTiming(emit=broken)
        timing.flush('interval')
        self.assertEqual(timing.emit_failures,1)
        captured=[]
        timing.emit=captured.append
        timing.reconnect('coinbase_stream.timeout',1,1)
        self.assertEqual(captured[0]['prior_emit_failures'],1)
        self.assertEqual(captured[0]['details'],dict(code='coinbase_stream.timeout',attempt=1,delay_seconds=1))


class LoopbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_diagnostics_keep_fixed_reason_and_original_budget(self):
        stop=asyncio.Event()
        sink=[]
        timing=CoinbaseTiming(emit=sink.append)
        store=SimpleNamespace(settings=SimpleNamespace(environment='preprod',data_mode='pp_live',origin_id='pp-live-fixture'))
        async def source(_):
            raise OSError('private provider data')
            yield
        async def pause(_,delay):
            self.assertEqual(delay,1)
            stop.set()
        await coinbase_session(store,stop,source=source,pause=pause,timing=timing)
        reconnect=next(row for row in sink if row['reason']=='reconnect')
        self.assertEqual(reconnect['details'],dict(code='coinbase_stream.transport',attempt=1,delay_seconds=1))
        self.assertNotIn('private provider data',json.dumps(sink))

    async def test_failed_write_has_timing_and_is_not_retried(self):
        stop=asyncio.Event()
        sink=[]
        timing=CoinbaseTiming(emit=sink.append)
        def fail(_):
            time.sleep(.01)
            raise RuntimeError('private storage data')
        store=SimpleNamespace(settings=SimpleNamespace(environment='preprod',data_mode='pp_live',origin_id='pp-live-fixture'),ingest=fail)
        async def source(_):
            yield {'event_id':'exchange-trade-1'}
        with self.assertRaises(LiveDiagnostic) as caught:
            await coinbase_session(store,stop,source=source,timing=timing)
        self.assertEqual(caught.exception.code,'coinbase_write.unexpected')
        self.assertEqual(sink[-1]['counts']['save_raised'],1)
        self.assertGreaterEqual(sink[-1]['metrics']['save_ms']['max'],5)
        self.assertNotIn('private storage data',json.dumps(sink))

    async def test_real_parser_queue_wait_and_true_save_duration_preserve_every_tick(self):
        stop=asyncio.Event()
        loop=asyncio.get_running_loop()
        sink=[]
        timing=CoinbaseTiming(emit=sink.append)
        raw=[]
        events=[]
        class Store:
            settings=SimpleNamespace(environment='preprod',data_mode='pp_live',origin_id='pp-live-fixture')
            def ingest(self,event):
                time.sleep(.03)
                events.append(event)
                if len(events)==3:
                    loop.call_soon_threadsafe(stop.set)
                return {'duplicate':False}
        async def handler(socket):
            await socket.recv()
            for index in range(3):
                message=json.dumps(dict(type='ticker',product_id='BTC-USD',trade_id=index+1,
                    time=datetime.now(timezone.utc).isoformat(),price='100.2300',last_size='0.0000100'))
                raw.append(message)
                if index == 0:
                    await socket.send([message[:10],message[10:]])
                    await socket.send(json.dumps({'type':'heartbeat'}))
                else:
                    await socket.send(message)
            await socket.wait_closed()
        async with serve(handler,'127.0.0.1',0) as server:
            address='ws://127.0.0.1:'+str(server.sockets[0].getsockname()[1])
            with patch('postgres.live_sources.COINBASE_WS',address):
                await asyncio.wait_for(coinbase_session(Store(),stop,timing=timing),3)
        self.assertEqual([r['event_id'] for r in events],['exchange-trade-1','exchange-trade-2','exchange-trade-3'])
        self.assertEqual([r['raw_payload'] for r in events],raw)
        self.assertTrue(all(r['price']=='100.2300' and r['size']=='0.0000100' for r in events))
        self.assertTrue(all('timing' not in r and '_timing' not in r for r in events))
        result=sink[-1]
        self.assertEqual(result['counts']['messages_read'],4)
        self.assertEqual(result['counts']['non_price_messages'],1)
        self.assertEqual(result['counts']['save_attempts'],3)
        self.assertEqual(result['counts']['save_returned'],3)
        self.assertGreaterEqual(result['metrics']['save_ms']['max'],20)
        self.assertGreaterEqual(result['metrics']['parser_queue_ms']['max'],30)
        self.assertFalse(result['queue_metadata_lost'])


if __name__=='__main__':
    unittest.main()
