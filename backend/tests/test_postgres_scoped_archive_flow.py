"""Isolated PostgreSQL A→B archive handoff with generated HTTP only.

The fixture is destroyed by Linux CI. It proves no PP or Supabase runtime gate.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, ArchiveUnavailable, encoded
from postgres.archive_transport import ScopedArchiveTransport
from postgres.connection import connect
from postgres.config import Settings
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.store import Store
from postgres.supabase_storage import SupabaseStorageTransport
from postgres import pp_raw_archive_probe
from postgres_lifecycle_fixtures import ImmutableMemoryTransport, generated_rows


ENABLED = bool(os.getenv('TRADEBOT_TEST_LIFECYCLE_DSN') and os.getenv('TRADEBOT_TEST_APP_DSN'))


@unittest.skipUnless(ENABLED, 'isolated generated PostgreSQL DSNs not supplied')
class ScopedArchivePostgresFlowTests(unittest.TestCase):
    def test_outage_and_corrupt_readback_preserve_sealed_a_until_retry(self):
        lifecycle = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'],
                                    environment='preprod')
        application = lambda: connect(os.environ['TRADEBOT_TEST_APP_DSN'],
                                      environment='preprod')
        repository = LifecycleRepository(lifecycle)
        origin = 'generated-archive-fault-' + uuid.uuid4().hex
        first = repository.bootstrap(origin)
        first_id = str(first['generation_id'])
        rows = generated_rows(first_id, 26, origin)
        row = rows[0]
        columns = list(row)
        placeholders = ','.join('%s::jsonb' if column == 'payload' else '%s'
                                for column in columns)
        def insert_rows(events):
            with application() as database:
                for event in events:
                    values = [encoded(event[col]).decode() if col == 'payload' else event[col]
                              for col in columns]
                    database.execute(f'INSERT INTO raw.events({",".join(columns)}) VALUES({placeholders})',
                                     values)

        insert_rows(rows)
        with lifecycle() as database:
            threshold = database.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                ('raw.' + first['partition_name'],)).fetchone()['bytes']
        switched = repository.switch_if_due(origin, RotationPolicy(threshold))
        self.assertEqual((switched['status'], switched['reason']), ('switched', 'qualified_size'))
        second_id = str(switched['generation_id'])

        class FaultTransport(ImmutableMemoryTransport):
            corrupt = False

            def read_authenticated(self, key, *, max_bytes, timeout_seconds):
                original = super().read_authenticated(key, max_bytes=max_bytes,
                                                       timeout_seconds=timeout_seconds)
                return b'corrupt archive bytes' if self.corrupt else original

        raw = FaultTransport()
        worker = ArchiveWorker(repository,
            ScopedArchiveTransport(raw, ImmutableMemoryTransport(),
                origin_id=origin, generation_id=first_id), ArchiveLimits(max_rows=5))
        # Drive the same bounded wrapper that the host launches. Keep the
        # object store across attempts, but reopen local state for each page.
        def page(progress):
            with patch.object(pp_raw_archive_probe, 'ORIGIN', origin):
                return pp_raw_archive_probe.archive_once(LifecycleRepository(lifecycle),
                    worker.transport, generation_id=first_id, expected_seal_count=len(rows),
                    expected_manifest_count=progress)

        first_page = page(0)
        self.assertEqual((first_page['raw_coverage'], first_page['raw_rows']), ('partial', 25))
        active_rows = iter(generated_rows(second_id, 3, origin))
        read = raw.read_authenticated

        def reading_while_b_collects(key, **kwargs):
            insert_rows([next(active_rows)])
            return read(key, **kwargs)

        raw.read_authenticated = reading_while_b_collects
        raw.fail_get = True
        with self.assertRaises(ArchiveUnavailable):
            page(1)
        raw.fail_get = False
        raw.corrupt = True
        with self.assertRaises(ArchiveIntegrityError):
            page(1)
        self.assertEqual(repository.generation(first_id)['state'], 'sealed')
        self.assertEqual(len(repository.manifests(first_id)), 1)
        raw.corrupt = False
        outcome = page(1)
        self.assertEqual((outcome['raw_coverage'], outcome['raw_rows']), ('archived', 1))
        self.assertEqual([manifest['row_count'] for manifest in repository.manifests(first_id)],
                         [25, 1])
        self.assertEqual(len(raw.objects), 2)
        self.assertEqual(repository.generation(first_id)['state'], 'verified')
        with self.assertRaisesRegex(LifecycleHold, 'runtime retirement disabled'):
            worker.retire_generated(first_id, qualification_enabled=True)
        with lifecycle() as database:
            saved = database.execute('SELECT generation_id,event_id FROM raw.events WHERE origin_id=%s',
                                     (origin,)).fetchall()
        self.assertEqual({(str(event['generation_id']), event['event_id']) for event in saved},
                         {(event['generation_id'], event['event_id'])
                          for event in [*rows, *generated_rows(second_id, 3, origin)]})

    def test_size_switch_keeps_b_writing_during_a_authenticated_readback(self):
        lifecycle = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'],
                                    environment='preprod')
        application = lambda: connect(os.environ['TRADEBOT_TEST_APP_DSN'],
                                      environment='preprod')
        repository = LifecycleRepository(lifecycle)
        origin = 'generated-archive-switch-' + uuid.uuid4().hex
        first = repository.bootstrap(origin)
        first_id = str(first['generation_id'])

        def allocation():
            with lifecycle() as database:
                return database.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                                        ('raw.' + first['partition_name'],)).fetchone()['bytes']

        initial_bytes = allocation()
        threshold = initial_bytes + 8192
        inserted = 0
        for index, row in enumerate(generated_rows(first_id, 256, origin)):
            columns = list(row)
            placeholders = ','.join('%s::jsonb' if column == 'payload' else '%s'
                                    for column in columns)
            values = [encoded(row[column]).decode() if column == 'payload' else row[column]
                      for column in columns]
            with application() as database:
                with database.transaction():
                    database.execute(f'INSERT INTO raw.events({",".join(columns)}) VALUES({placeholders})',
                                     values)
            inserted = index + 1
            if inserted % 8 == 0 and allocation() >= threshold:
                break
        measured_bytes = allocation()
        self.assertGreaterEqual(measured_bytes, threshold, 'fixture did not cross its measured size')
        with lifecycle() as database:
            wal_before = database.execute('SELECT pg_current_wal_lsn() AS lsn').fetchone()['lsn']
        switch = repository.switch_if_due(origin, RotationPolicy(threshold))
        self.assertEqual((switch['status'], switch['reason'], switch['slot']),
                         ('switched', 'qualified_size', 'B'))
        second_id = str(switch['generation_id'])
        self.assertEqual(switch['seal_count'], inserted)

        store = Store(Settings(origin_id=origin, dsn=os.environ['TRADEBOT_TEST_APP_DSN']))
        now = datetime.now(timezone.utc)
        b_event = {
            'source': 'coinbase', 'event_id': 'b-during-a-readback-' + uuid.uuid4().hex,
            'kind': 'price', 'symbol': 'BTC-USD',
            'source_time': now.isoformat(), 'received_at': now.isoformat(),
            'price': '100000.1234567890123456789',
            'payload': {'type': 'ticker', 'product_id': 'BTC-USD',
                        'price': '100000.1234567890123456789'},
            'provenance': {'data_mode': 'generated', 'fixture': 'archive_switch',
                           'price_role': 'reference_not_settlement'},
        }
        objects = {}
        calls = []
        b_ack = []

        def handle(request):
            calls.append(request.method)
            key = request.url.path.split('/market-raw/', 1)[-1]
            if request.method == 'POST':
                if key in objects:
                    return httpx.Response(409, json={'code': 'KeyAlreadyExists'})
                objects[key] = request.content
                return httpx.Response(200, json={'Key': key})
            # A is sealed and being read back. B's acknowledgement must finish
            # before the authenticated A read returns to the archive worker.
            b_ack.append(store.ingest(b_event))
            return httpx.Response(200, content=objects[key])

        with httpx.Client(transport=httpx.MockTransport(handle), trust_env=False) as client:
            raw = SupabaseStorageTransport('generated-public-project-key',
                                           'generated-private-access-token', client=client)
            worker = ArchiveWorker(repository,
                ScopedArchiveTransport(raw, ImmutableMemoryTransport(),
                    origin_id=origin, generation_id=first_id), ArchiveLimits(max_rows=500))
            result = worker.archive_cycle(first_id)
            self.assertEqual(result['status'], 'archived')
            with self.assertRaisesRegex(LifecycleHold, 'runtime retirement disabled'):
                worker.retire_generated(first_id, qualification_enabled=True)

        self.assertEqual(calls, ['POST', 'GET'])
        self.assertEqual(len(b_ack), 1)
        self.assertEqual(str(b_ack[0]['generation_id']), second_id)
        self.assertFalse(b_ack[0]['duplicate'])
        with lifecycle() as database:
            counts = database.execute('''SELECT generation_id,count(*) AS count FROM raw.events
                WHERE origin_id=%s GROUP BY generation_id''', (origin,)).fetchall()
            states = database.execute('''SELECT generation_id,state FROM archive.generations
                WHERE origin_id=%s''', (origin,)).fetchall()
            wal_bytes = database.execute('SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),%s) AS bytes',
                                         (wal_before,)).fetchone()['bytes']
        self.assertEqual({str(row['generation_id']): row['count'] for row in counts},
                         {first_id: inserted, second_id: 1})
        self.assertEqual({str(row['generation_id']): row['state'] for row in states},
                         {first_id: 'verified', second_id: 'collecting'})
        self.assertGreater(wal_bytes, Decimal(0))

    def test_b_write_survives_a_archive_and_unqualified_retirement_is_blocked(self):
        lifecycle = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'],
                                    environment='preprod')
        application = lambda: connect(os.environ['TRADEBOT_TEST_APP_DSN'],
                                      environment='preprod')
        repository = LifecycleRepository(lifecycle)
        origin = 'generated-archive-' + uuid.uuid4().hex
        first = repository.bootstrap(origin, datetime.now(timezone.utc) - timedelta(hours=73))

        def insert(generation_id, suffix):
            row = generated_rows(str(generation_id), 1, origin)[0]
            row['event_id'] = 'event-' + suffix
            row['content_hash'] = suffix.zfill(64)
            columns = list(row)
            placeholders = ','.join('%s::jsonb' if column == 'payload' else '%s'
                                    for column in columns)
            values = [encoded(row[column]).decode() if column == 'payload' else row[column]
                      for column in columns]
            with application() as database:
                with database.transaction():
                    database.execute(f'INSERT INTO raw.events({",".join(columns)}) VALUES({placeholders})',
                                     values)

        insert(first['generation_id'], '1')
        switched = repository.switch_if_due(origin)
        self.assertEqual(switched['status'], 'switched')
        second = switched['generation_id']
        insert(second, '2')  # A is sealed while B acknowledges a new raw write.

        objects = {}
        calls = []
        def handle(request):
            calls.append(request.method)
            key = request.url.path.split('/market-raw/', 1)[-1]
            if request.method == 'POST':
                if key in objects:
                    return httpx.Response(409, json={'code':'KeyAlreadyExists'})
                objects[key] = request.content
                return httpx.Response(200, json={'Key':key})
            return httpx.Response(200, content=objects[key]) if key in objects else httpx.Response(404)

        with httpx.Client(transport=httpx.MockTransport(handle), trust_env=False) as client:
            raw = SupabaseStorageTransport('generated-public-project-key',
                                           'generated-private-access-token', client=client)
            transport = ScopedArchiveTransport(raw, ImmutableMemoryTransport(),
                origin_id=origin, generation_id=str(first['generation_id']))
            worker = ArchiveWorker(repository, transport, ArchiveLimits(max_rows=5))
            result = worker.archive_cycle(str(first['generation_id']))
            self.assertEqual(result['status'], 'archived')
            self.assertEqual(calls, ['POST', 'GET'])
            with self.assertRaisesRegex(LifecycleHold, 'runtime retirement disabled'):
                worker.retire_generated(str(first['generation_id']), qualification_enabled=True)

        with lifecycle() as database:
            counts = database.execute('''SELECT generation_id,count(*) AS count FROM raw.events
                WHERE origin_id=%s GROUP BY generation_id''', (origin,)).fetchall()
            self.assertEqual({str(row['generation_id']):row['count'] for row in counts},
                             {str(first['generation_id']):1, str(second):1})
            states = database.execute('''SELECT generation_id,state FROM archive.generations
                WHERE origin_id=%s''', (origin,)).fetchall()
            self.assertEqual({str(row['generation_id']):row['state'] for row in states},
                             {str(first['generation_id']):'verified', str(second):'collecting'})


if __name__ == '__main__':
    unittest.main()
