"""CP3 generated app qualification, without touching the legacy SQLite runtime."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from postgres.api import create_app, event_stream
from postgres.calculation import baseline, calculate, forecast
from postgres.config import Settings
from postgres.domain import decimal_text, timestamp
from postgres.ingestion import generated_events
from postgres.live_state import LiveState
from postgres.store import IdentityConflict, Store
from postgres.worker import CalculationWorker

NOW = datetime(2026,11,12,12,5,tzinfo=timezone.utc)


def inputs(now=NOW):
    events = generated_events(now)
    market_event = events[0]
    market = dict(market_event['payload'],id=market_event['market_id'],first_seen=now.isoformat())
    tick = next(row for row in events if row['kind']=='price')
    price = dict(source=tick['source'],source_time=tick['source_time'],received_at=tick['received_at'],
                 price_usd=tick['price'],event_id=tick['event_id'],origin='generated-pp',provenance=tick['provenance'])
    candles = [dict(source=row['source'],symbol=row['symbol'],granularity=60,
                    start=datetime.fromtimestamp(row['payload']['time'],timezone.utc).isoformat(),
                    close=row['payload']['close'],volume=row['payload']['volume'],received_at=row['received_at'])
               for row in events if row['kind']=='candle']
    return market,price,candles


def state_fixture(now=NOW):
    current = [now]
    market,price,candles = inputs(now)
    values,quality,evidence = calculate(market,price,candles,now)
    snapshot = dict(market_id=market['id'],as_of=now.isoformat(),values=values,quality=quality,evidence=evidence)
    prediction = forecast(market,snapshot,now)
    quote = dict(market_id=market['id'],source_time=now.isoformat(),received_at=now.isoformat(),up_probability='0.52')
    state = LiveState(Settings(),clock=lambda:current[0])
    state.discover(market)
    state.publish(market['id'],price,quote,snapshot,prediction)
    state.storage_status('ok')
    return state,current,(market,price,quote,snapshot,prediction)


class NumericAndStateTests(unittest.TestCase):
    def test_generated_overlapping_seeds_have_identical_immutable_events(self):
        first={row['event_id']:row for row in generated_events(NOW)}
        second={row['event_id']:row for row in generated_events(NOW+timedelta(minutes=1))}
        overlaps=set(first)&set(second)
        self.assertGreater(len(overlaps),10)
        for identity in overlaps:
            self.assertEqual({k:v for k,v in first[identity].items() if k!='received_at'},
                             {k:v for k,v in second[identity].items() if k!='received_at'})

    def test_exact_feature_distance_and_deployed_model(self):
        market,price,candles = inputs()
        values,quality,_ = calculate(market,price,candles,NOW)
        self.assertEqual(values['distance_usd'],'25.0000000000000000000')
        self.assertEqual(values['volume_btc_15m'],'1.8518518351851851835')
        self.assertEqual(quality['candle_status'],'fresh')
        self.assertEqual(len(candles),17)
        # Same Gaussian baseline contract: price equal to target always gives 0.5.
        equal = dict(values,reference_price_usd=values['target_usd'])
        self.assertEqual(baseline(equal,quality),(0.5,None))
        self.assertGreater(baseline(values,quality)[0],0.5)
        self.assertIsNone(calculate(market,price,candles,timestamp(market['end'])))

    def test_gap_and_future_availability_are_missing_not_zero(self):
        market,price,candles = inputs()
        candles[-2]['received_at'] = (NOW+timedelta(seconds=1)).isoformat()
        values,quality,_ = calculate(market,price,candles,NOW)
        self.assertIsNone(values['realized_volatility_15m'])
        self.assertEqual(baseline(values,quality),(None,'required_feature_missing'))
        price['source_time'] = (NOW-timedelta(seconds=31)).isoformat()
        values,quality,_ = calculate(market,price,candles,NOW)
        self.assertIsNone(values['reference_price_usd'])
        self.assertEqual(baseline(values,quality),(None,'reference_price_not_fresh'))

    def test_strict_decimal_and_timezone(self):
        for value in ('NaN','Infinity',1.2,True):
            with self.assertRaises(ValueError):
                decimal_text(value)
        with self.assertRaises(ValueError):
            timestamp('2026-11-12T12:00:00')
        value = '100000.000000000000000000001'
        self.assertEqual(decimal_text(value),value)

    def test_source_age_not_receipt_or_connection_status(self):
        state,current,records = state_fixture()
        current[0] += timedelta(seconds=31)
        snapshot = state.snapshot()
        self.assertEqual(snapshot['feeds']['coinbase_stream']['status'],'stale')
        self.assertIsNone(snapshot['forecast'])
        self.assertIsNone(snapshot['feature_snapshot'])
        self.assertIn('coinbase_price',snapshot['missing_data'])
        # Read/request itself never refreshes evidence.
        self.assertEqual(snapshot['coinbase']['source_time'],records[1]['source_time'])

    def test_rollover_expiry_wrong_market_and_future_guards(self):
        state,current,records = state_fixture()
        market,price,quote,snapshot,prediction = records
        next_market = dict(market,id='next',start=market['end'],end=(timestamp(market['end'])+timedelta(minutes=15)).isoformat())
        state.discover(next_market)
        self.assertFalse(state.publish(market['id'],price,quote,snapshot,prediction))
        self.assertIsNone(state.snapshot()['forecast'])
        current[0] = timestamp(next_market['start'])
        self.assertTrue(state.publish('next',price,quote,snapshot,prediction))
        self.assertIsNone(state.snapshot()['polymarket'])
        self.assertIsNone(state.snapshot()['feature_snapshot'])
        current[0] = timestamp(next_market['end'])
        self.assertFalse(state.publish('next',price,None,None,None))
        self.assertIn('active_market',state.snapshot()['missing_data'])

    def test_future_and_reordered_price_do_not_replace_latest(self):
        state,current,records = state_fixture()
        market,price,quote,snapshot,prediction = records
        for seconds in (-5,5):
            candidate = dict(price,source_time=(NOW+timedelta(seconds=seconds)).isoformat(),price_usd='1')
            state.publish(market['id'],candidate,None,None,None)
            self.assertEqual(state.snapshot()['coinbase']['price_usd'],price['price_usd'])

    def test_future_and_reordered_quotes_do_not_refresh_health(self):
        state,current,records = state_fixture()
        market,price,quote,snapshot,prediction = records
        for seconds in (-5,5):
            candidate=dict(quote,source_time=(NOW+timedelta(seconds=seconds)).isoformat(),up_probability='0.99')
            state.publish(market['id'],None,candidate,None,None)
            self.assertEqual(state.snapshot()['polymarket']['up_probability'],'0.52')

    def test_live_config_is_rejected_without_secret_leak(self):
        for mode in ('live','production_preview'):
            with self.assertRaises(ValueError):
                Settings(data_mode=mode)
        with patch.dict(os.environ,{'TRADEBOT_COLLECTOR_ENABLED':'true'}):
            with self.assertRaises(ValueError):
                Settings.from_env()
        self.assertNotIn('dsn',Settings(dsn='secret').public())


class FakeStore:
    def verify(self):
        self.verified = True
    def predictions(self,limit):
        return []
    def chart(self):
        return {'status':'missing','market':None,'points':[]}


class ApiTests(unittest.TestCase):
    def test_actual_routes_dashboard_contract_and_request_bounds(self):
        from fastapi.testclient import TestClient
        state,_,_ = state_fixture()
        store = FakeStore()
        app = create_app(Settings(),store,state,refresh=False)
        with TestClient(app) as client:
            self.assertTrue(store.verified)
            for path in ('/','/health','/state/current','/api/state','/forecast/current','/models/current','/history/context',
                         '/history/coinbase-chart','/history/predictions','/system/status','/system/history','/cloud/status','/dashboard/plan'):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code,200,response.text)
            result = client.get('/state/current').json()
            self.assertEqual(result['data_mode'],'generated')
            self.assertFalse(result['collector']['enabled'])
            self.assertEqual(result['coinbase']['price_usd'],'100025.1234567890123456789')
            self.assertIn('distinct_confirmed_markets_by_checkpoint',client.get('/history/context').json()['evaluation'])
            dashboard = client.get('/dashboard').text
            for contract in ("new EventSource('/events')","getJSON('/state/current')","fetch('/history/coinbase-chart'",'environment-label'):
                self.assertIn(contract,dashboard)
            self.assertEqual(client.get('/history/predictions?limit=501').status_code,422)
            self.assertEqual(client.get('/history/archive/nope').status_code,503)
            self.assertEqual(client.post('/state/current').status_code,405)

    def test_real_http_sse_initial_frame_and_reconnect(self):
        import httpx
        import uvicorn
        state,_,_ = state_fixture()
        app = create_app(Settings(),FakeStore(),state,refresh=False)
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app,log_level='critical'))
        thread = threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+5
            while not server.started and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertTrue(server.started)
            for _ in range(2):
                with httpx.stream('GET',f'http://127.0.0.1:{port}/events',timeout=2,trust_env=False) as response:
                    self.assertEqual(response.status_code,200)
                    self.assertIn('text/event-stream',response.headers['content-type'])
                    lines = response.iter_lines()
                    self.assertTrue(next(lines).startswith('id: '))
                    data = json.loads(next(lines).removeprefix('data: '))
                    self.assertEqual(data['market']['id'],state.snapshot()['market']['id'])
                    self.assertFalse(data['collector']['enabled'])
        finally:
            server.should_exit = True
            thread.join(5)
            sock.close()
        self.assertFalse(thread.is_alive())

    def test_database_failure_is_not_empty_history(self):
        from fastapi.testclient import TestClient
        store = FakeStore()
        store.predictions = lambda limit:(_ for _ in ()).throw(RuntimeError('private diagnostic'))
        with TestClient(create_app(Settings(),store,refresh=False)) as client:
            result = client.get('/history/predictions')
            self.assertEqual(result.status_code,503)
            self.assertNotIn('private diagnostic',result.text)


class WorkerTests(unittest.TestCase):
    def test_discovery_is_independent_of_serial_calculation(self):
        class Worker(CalculationWorker):
            def __init__(self):
                self.discovery_count=0
                self.calculation_count=0
                self.started=threading.Event()
                self.release=threading.Event()
            def discover_once(self):
                self.discovery_count+=1
            def calculate_once(self):
                self.calculation_count+=1
                self.started.set()
                self.release.wait(5)
        worker=Worker()
        async def scenario():
            task=asyncio.create_task(worker.run())
            try:
                await asyncio.to_thread(worker.started.wait,2)
                await asyncio.sleep(.65)
                self.assertGreaterEqual(worker.discovery_count,2)
                self.assertEqual(worker.calculation_count,1)
            finally:
                worker.release.set()
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        asyncio.run(scenario())


def test_dsn(name):
    path=os.getenv(name+'_FILE')
    return Path(path).read_text().strip() if path else os.getenv(name)


@unittest.skipUnless(test_dsn('TRADEBOT_TEST_DSN'),'requires isolated generated PostgreSQL')
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings=Settings(origin_id=os.getenv('TRADEBOT_TEST_ORIGIN','generated-app-test'),dsn=test_dsn('TRADEBOT_TEST_DSN'))
        cls.store=Store(cls.settings)
        cls.store.verify()
        lifecycle_dsn=test_dsn('TRADEBOT_TEST_LIFECYCLE_DSN')
        if lifecycle_dsn:
            from postgres.connection import connect
            from postgres.lifecycle import LifecycleRepository
            LifecycleRepository(lambda:connect(lifecycle_dsn)).bootstrap(cls.settings.origin_id)

    def test_ack_replay_conflict_exact_values_and_forecast_evidence(self):
        now=datetime.now(timezone.utc)
        events=generated_events(now)
        acknowledgements=[self.store.ingest(event) for event in events]
        self.assertTrue(all(item['content_hash'] for item in acknowledgements))
        event=next(row for row in events if row['kind']=='price')
        retry=dict(event,received_at=(now+timedelta(seconds=1)).isoformat())
        self.assertTrue(self.store.ingest(retry)['duplicate'])
        with self.assertRaises(IdentityConflict):
            self.store.ingest(dict(event,price='99999'))
        market=self.store.active_market(now)
        price,candles=self.store.inputs(market['id'],now)
        self.assertEqual(price['price_usd'],event['price'])
        self.assertEqual(price['source_time'],event['source_time'])
        worker=CalculationWorker(self.store,clock=lambda:now)
        worker.discover_once()
        snapshot_id=worker.calculate_once()
        self.assertIsNotNone(snapshot_id)
        self.assertEqual(worker.calculate_once(),snapshot_id)
        with self.store.connection(True) as db:
            row=db.execute('''SELECT count(*) AS count FROM core.snapshot_evidence WHERE origin_id=%s AND snapshot_id=%s''',
                           (self.settings.origin_id,snapshot_id)).fetchone()
            self.assertGreaterEqual(row['count'],2)
            orphaned=db.execute('''SELECT count(*) AS count FROM ops.outbox WHERE origin_id=%s AND generation_id IS NULL''',
                                (self.settings.origin_id,)).fetchone()
            self.assertEqual(orphaned['count'],0)
            protected=db.execute('''SELECT payload FROM core.protected_evidence WHERE origin_id=%s AND source='coinbase'
                AND event_id=%s''',(self.settings.origin_id,event['event_id'])).fetchone()
            self.assertEqual(protected['payload']['normalized']['price'],event['price'])
        self.assertTrue(self.store.predictions(5))
        self.assertTrue(self.store.chart(now)['points'])


if __name__=='__main__':
    unittest.main()
