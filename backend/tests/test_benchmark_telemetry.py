import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from postgres.benchmark_telemetry import BenchmarkTelemetry, ORIGIN, heartbeat, issue, monitor_session, source_monitor, valid_counts

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'deploy/preprod'))
import benchmark_metrics as sender


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        source_monitor(None)

    def test_diagnostics_have_finite_labels_and_survive_dropped_datagrams(self):
        display = MagicMock(origin=ORIGIN)
        source_monitor(display)
        issue('robinhood_reference','auth')
        issue('robinhood_reference','auth')
        issue('x','token')
        heartbeat()
        packet = display.send.call_args.args[0]
        self.assertTrue(valid_counts(packet['counts']))
        self.assertEqual(packet['counts'],{'robinhood_reference/auth':2})
        self.assertFalse(valid_counts({'arbitrary/marketid':1}))
        self.assertFalse(valid_counts({'coinbase_stream/retry':-3}))

    def test_fence_heartbeat_remains_active_when_polymarket_is_paused(self):
        display = MagicMock(origin=ORIGIN)
        with patch('postgres.quote_display.DisplaySender', return_value=display), patch(
            'postgres.benchmark_telemetry.time.monotonic', side_effect=[10, 12, 21]
        ):
            with monitor_session(ORIGIN, 'session-a') as pulse:
                issue('robinhood_reference', 'auth')
                pulse()
                self.assertEqual(display.send.call_count, 2)
                pulse()
                self.assertEqual(display.send.call_args.args[0]['counts'], {'robinhood_reference/auth': 1})
                self.assertEqual(display.send.call_count, 3)
        display.socket.close.assert_called_once()
        issue('robinhood_reference', 'retry')
        self.assertEqual(display.send.call_count, 3)

    async def test_requests_share_a_single_read_and_failure_is_unknown(self):
        store = MagicMock(origin=ORIGIN)
        state = MagicMock(source_health=None, durable_quote_received_at=None)
        state.snapshot.return_value = {'quote_counts':None}
        monitor = BenchmarkTelemetry(store,state)
        with patch('postgres.benchmark_telemetry.archive_status',side_effect=RuntimeError) as read:
            results = await asyncio.gather(monitor.snapshot(),monitor.snapshot())
            self.assertEqual(read.call_count,1)
        self.assertTrue(all(r['windows'] is None for r in results))

    async def test_old_heartbeat_cannot_replace_successor_or_leak_its_identity(self):
        store = MagicMock(origin=ORIGIN)
        state = MagicMock(durable_quote_received_at=None)
        state.snapshot.return_value = {'quote_counts': None}
        state.source_health={'session':'prior','counts':{},'observed_at':100}
        monitor=BenchmarkTelemetry(store,state)
        active={'slot':'A','generation':'g','state':'collecting','observed_at':100,'current':True,
                'enabled':True,'session':'successor','watch_requested':True}
        with patch('postgres.benchmark_telemetry.archive_status', return_value=[active]):
            result=await monitor.snapshot()
            self.assertIsNone(result['source_health'])
            self.assertNotIn('session',result['windows'][0])
            self.assertEqual(state.health_session,'successor')
            state.source_health={'session':'successor','counts':{},'observed_at':101}
            self.assertEqual((await monitor.snapshot())['source_health'], {'counts':{},'observed_at':101})

    def test_missing_host_pressure_stays_unknown_at_startup(self):
        first=sender.host_measurements({'mem_available_kib':100}, 7, {})
        self.assertEqual([v[:3] for v in first],[('tradebot_pp_rollover_host_memory_available_kib',100.,7)])
        second=sender.host_measurements({'mem_available_kib':None}, 8, {'pswpout':0,'oom_kill':None})
        self.assertEqual([v[:3] for v in second],[('tradebot_pp_rollover_host_pswpout',0.,8)])

    def test_sampling_real_active_and_sealed_windows(self):
        active = dict(slot='B',generation='b',current=True,enabled=True,pending=5,acknowledged=19,oldest_age=2,observed_at=99)
        old = dict(slot='A',generation='a',current=False,enabled=True,pending=7,acknowledged=99,oldest_age=3,observed_at=99)
        source = dict(origin=ORIGIN,observed_at=100,windows=[active,old],reference_age={'coinbase':{'pp_receipt':1}})
        previous = {'a':(89,79),'b':(89,14),'obsolete':(0,0)}
        rows=sender.collect(source,100,previous,.015)
        known=lambda key:[(v,tags) for n,v,t,tags in rows if n==key]
        self.assertEqual([(v,t['slot']) for v,t in known('pp_archive_ack_rate')],[(.5,'B'),(2,'A')])
        self.assertEqual([t['slot'] for v,t in known('pp_collector_enabled')],['B'])
        self.assertEqual(len(known('tradebot_btc_feed_age_seconds')),1)
        self.assertNotIn('obsolete',previous)
        self.assertTrue(sender.encode(rows))
        unknown=sender.collect({},101,{},.01)
        self.assertNotIn('pp_collector_enabled',[n for n,*_ in unknown])
        self.assertIn('pp_benchmark_metrics_heartbeat',[n for n,*_ in unknown])
