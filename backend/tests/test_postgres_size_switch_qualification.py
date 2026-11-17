"""Isolated PostgreSQL size-switch qualification; never chooses a PP threshold.

The fixture uses generated provenance and test DSNs. Its tiny measured threshold
proves the A/B mechanism only, not capacity, cloud archival, or retirement.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.api import create_app
from postgres.config import Settings
from postgres.connection import connect
from postgres.lifecycle import LifecycleRepository, RotationPolicy
from postgres.live_state import LiveState
from postgres.store import Store


ENABLED = bool(os.getenv('TRADEBOT_TEST_LIFECYCLE_DSN') and os.getenv('TRADEBOT_TEST_APP_DSN'))


@unittest.skipUnless(ENABLED, 'isolated generated PostgreSQL lifecycle/app DSNs not supplied')
class SizeSwitchQualification(unittest.TestCase):
    def test_concurrent_acknowledgements_and_dashboard_binding(self):
        origin = 'generated-size-' + uuid.uuid4().hex
        lifecycle = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'], environment='preprod')
        repository = LifecycleRepository(lifecycle)
        store = Store(Settings(origin_id=origin, dsn=os.environ['TRADEBOT_TEST_APP_DSN']))
        first = repository.bootstrap(origin)
        first_id = str(first['generation_id'])
        now = datetime.now(timezone.utc)
        start = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
        market_id = 'fixture-' + uuid.uuid4().hex
        market = store.ingest({
            'source': 'polymarket_us', 'event_id': 'market-' + market_id,
            'kind': 'market', 'market_id': market_id, 'received_at': now.isoformat(),
            'source_time': now.isoformat(), 'payload': {
                'slug': market_id, 'start': start.isoformat(),
                'end': (start + timedelta(minutes=15)).isoformat(),
                'duration': 900, 'status': 'MARKET_STATUS_OPEN',
                'target_usd': '100000.1234567890123456789'},
            'provenance': {'data_mode': 'generated', 'fixture': 'size_switch'},
        })
        self.assertEqual(str(market['generation_id']), first_id)
        with lifecycle() as db:
            before = db.execute('SELECT pg_current_wal_lsn() AS lsn').fetchone()['lsn']
            size_before = db.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                                     ('raw.' + first['partition_name'],)).fetchone()['bytes']

        acknowledgements = []
        lock = threading.Lock()
        started = threading.Event()
        switched = threading.Event()

        def write(worker):
            for index in range(12):
                sequence = worker * 12 + index
                at = now - timedelta(seconds=20) + timedelta(milliseconds=sequence)
                ack = store.ingest({
                    'source': 'coinbase', 'event_id': f'fixture-tick-{worker}-{index}',
                    'kind': 'price', 'symbol': 'BTC-USD',
                    'source_time': at.isoformat(), 'received_at': now.isoformat(),
                    'price': f'100000.{sequence:020d}',
                    'payload': {'type': 'ticker', 'product_id': 'BTC-USD',
                                'trade_id': f'{worker}-{index}', 'price': f'100000.{sequence:020d}'},
                    'provenance': {'data_mode': 'generated', 'fixture': 'live_shaped_ticker',
                                   'price_role': 'reference_not_settlement'},
                })
                with lock:
                    acknowledgements.append(ack)
                    if len(acknowledgements) >= 4:
                        started.set()
                if index == 5:
                    self.assertTrue(switched.wait(10), 'switch did not finish while writers were active')
                time.sleep(.003)

        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(write, worker) for worker in range(2)]
            self.assertTrue(started.wait(10), 'no concurrent fixture acknowledgements')
            # This fixture threshold is the measured local partition allocation.
            # It is intentionally never written into a PP runtime profile.
            result = repository.switch_if_due(origin, RotationPolicy(size_before))
            switched.set()
            for task in tasks:
                task.result(timeout=15)

        self.assertEqual((result['status'], result['reason'], result['slot']),
                         ('switched', 'qualified_size', 'B'))
        second_id = str(result['generation_id'])
        self.assertEqual(len(acknowledgements), 24)
        self.assertEqual(len({ack['event_id'] for ack in acknowledgements}), 24)
        self.assertTrue(all(not ack['duplicate'] for ack in acknowledgements))
        self.assertIn(first_id, {str(ack['generation_id']) for ack in acknowledgements})
        self.assertIn(second_id, {str(ack['generation_id']) for ack in acknowledgements})
        self.assertEqual(repository.switch_if_due(origin, RotationPolicy(1))['reason'],
                         'other_slot_not_retired')

        with lifecycle() as db:
            rows = db.execute("SELECT event_id,generation_id FROM raw.events WHERE origin_id=%s AND kind='price'",
                              (origin,)).fetchall()
            size_after = db.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                                    ('raw.' + first['partition_name'],)).fetchone()['bytes']
            second = repository.generation(second_id)
            second_size = db.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                                     ('raw.' + second['partition_name'],)).fetchone()['bytes']
            wal_bytes = db.execute('SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),%s) AS bytes',
                                   (before,)).fetchone()['bytes']
            state = db.execute('SELECT generation_id FROM ops.writer_state WHERE origin_id=%s',
                               (origin,)).fetchone()
        self.assertEqual(str(state['generation_id']), second_id)
        self.assertEqual({row['event_id']: str(row['generation_id']) for row in rows},
                         {ack['event_id']: str(ack['generation_id']) for ack in acknowledgements})
        self.assertGreaterEqual(size_after, size_before)
        self.assertGreater(second_size, 0)
        self.assertGreater(wal_bytes, 0)

        active = store.active_market()
        price, quote, feature, prediction = store.hydrate(market_id)
        self.assertEqual(active['id'], market_id)
        self.assertEqual(str(price['generation_id']), second_id)
        live = LiveState(store.settings)
        live.discover(active)
        live.publish(market_id, price, quote, feature, prediction)
        with TestClient(create_app(settings=store.settings, store=store, state=live, refresh=False)) as client:
            state_response = client.get('/state/current')
            dashboard = client.get('/dashboard')
            self.assertEqual(state_response.status_code, 200)
            self.assertEqual(dashboard.status_code, 200)
            self.assertEqual(state_response.json()['coinbase']['generation_id'], second_id)
            self.assertIn('latest_coinbase_tick:state.coinbase', dashboard.text)

        print('SIZE_SWITCH_QUALIFICATION=' + json.dumps({
            'scope': 'isolated_generated_postgres', 'capacity_qualified': False,
            'cloud_enabled': False, 'retirement_enabled': False,
            'fixture_threshold_bytes': size_before,
            'first_partition_before_bytes': size_before,
            'first_partition_after_bytes': size_after,
            'second_partition_bytes': second_size, 'wal_generated_bytes': str(wal_bytes),
            'acknowledged': len(acknowledgements), 'ack_gaps': len(acknowledgements) - len(rows),
            'first_generation_acks': sum(str(a['generation_id']) == first_id for a in acknowledgements),
            'second_generation_acks': sum(str(a['generation_id']) == second_id for a in acknowledgements),
            'occupied_slot_hold': True, 'api_price_generation_is_active': True,
            'dashboard_price_binding': True, 'dashboard_generation_label': 'unsupported',
        }, sort_keys=True), flush=True)
