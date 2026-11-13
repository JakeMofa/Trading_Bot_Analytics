"""Generated PostgreSQL qualification. Requires isolated migrated preprod DSNs.

No cloud, real feeds, user databases, production, or blanket cleanup. Parent CI
owns disposal of its generated Compose project. Small fixtures are not capacity
or cloud-mutation-authority evidence.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, ArchiveUnavailable, encoded, wire
from postgres.history import ArchiveHistory
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, RotationPolicy
from postgres_lifecycle_fixtures import ImmutableMemoryTransport, generated_rows


ENABLED = bool(os.getenv('TRADEBOT_TEST_LIFECYCLE_DSN') and os.getenv('TRADEBOT_TEST_APP_DSN'))


@unittest.skipUnless(ENABLED, 'isolated generated PostgreSQL lifecycle/app DSNs not supplied')
class PostgreSQLLifecycleIntegration(unittest.TestCase):
    def setUp(self):
        from postgres.connection import connect
        self.connect = connect
        self.factory = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'], environment='preprod')
        self.app_factory = lambda: connect(os.environ['TRADEBOT_TEST_APP_DSN'], environment='preprod')
        self.repository = LifecycleRepository(self.factory)
        self.origin = 'generated-lifecycle-' + uuid.uuid4().hex
        self.started = datetime.now(timezone.utc) - timedelta(hours=73)
        self.first = self.repository.bootstrap(self.origin, self.started)
        self.transport = ImmutableMemoryTransport()
        self.limits = ArchiveLimits(max_rows=4)
        self.worker = ArchiveWorker(self.repository, self.transport, self.limits)

    def insert(self, index, *, wait=None, locked=None):
        with self.app_factory() as connection:
            with connection.transaction():
                writer = connection.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR SHARE',
                                            (self.origin,)).fetchone()
                generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                                                (writer['generation_id'],)).fetchone()
                self.assertEqual(generation['state'], 'collecting')
                if locked:
                    locked.set()
                if wait and not wait.wait(3):
                    raise TimeoutError('generated writer release deadline')
                row = generated_rows(writer['generation_id'], 1, self.origin)[0]
                row['event_id'] = f'event-{index:04d}'
                row['content_hash'] = f'{index:064x}'
                columns = list(row)
                json_columns = {'payload'}
                placeholders = ','.join('%s::jsonb' if key in json_columns else '%s' for key in columns)
                connection.execute(f'INSERT INTO raw.events({",".join(columns)}) VALUES({placeholders})',
                                   [encoded(row[key]).decode() if key in json_columns else row[key] for key in columns])
                return row

    def rotate(self):
        result = self.repository.switch_if_due(self.origin, now=datetime.now(timezone.utc))
        self.assertEqual(result['status'], 'switched')
        return result

    def archive_all(self, generation_id):
        for _ in range(8):
            result = self.worker.archive_cycle(generation_id)
            if result['status'] == 'archived':
                return
        self.fail('generated bounded archive did not complete')

    def assert_partition_present(self, generation):
        with self.factory() as connection:
            self.assertIsNotNone(connection.execute('SELECT to_regclass(%s) AS name',
                                                     ('raw.' + generation['partition_name'],)).fetchone()['name'])

    def test_atomic_switch_waits_for_acknowledged_write_then_late_events_use_b(self):
        locked, release, completed = threading.Event(), threading.Event(), threading.Event()
        failures, result = [], []
        def writer():
            try:
                result.append(self.insert(1, wait=release, locked=locked))
            except BaseException as error:
                failures.append(error)
        def rotate():
            try:
                result.append(self.rotate())
            except BaseException as error:
                failures.append(error)
            finally:
                completed.set()
        first = threading.Thread(target=writer)
        first.start()
        self.assertTrue(locked.wait(3))
        second = threading.Thread(target=rotate)
        second.start()
        self.assertFalse(completed.wait(0.1))
        release.set()
        first.join(3)
        second.join(3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(failures, [])
        sealed = self.repository.generation(self.first['generation_id'])
        self.assertEqual(sealed['seal_count'], 1)
        late = self.insert(2)  # old source_time, new receipt; routes B
        self.assertNotEqual(late['generation_id'], self.first['generation_id'])
        # Ingest B synchronously during A's authenticated readback.
        read = self.transport.read_authenticated
        wrote = []
        def concurrent_read(*args, **kwargs):
            if not wrote:
                wrote.append(self.insert(3))
            return read(*args, **kwargs)
        self.transport.read_authenticated = concurrent_read
        self.archive_all(self.first['generation_id'])
        self.assertEqual(wrote[0]['generation_id'], late['generation_id'])
        self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        with self.factory() as connection:
            self.assertEqual(connection.execute('SELECT count(*) AS count FROM raw.events WHERE generation_id=%s',
                                                (late['generation_id'],)).fetchone()['count'], 2)

    def test_a_b_a_reuse_new_generation_ids_and_history_after_real_drop(self):
        original = [self.insert(index) for index in range(7)]
        switched = self.rotate()
        self.assertEqual(switched['slot'], 'B')
        # Crash/restart between bounded pages uses durable manifest/checkpoint.
        self.worker.archive_cycle(self.first['generation_id'])
        self.worker = ArchiveWorker(LifecycleRepository(self.factory), self.transport, self.limits)
        self.archive_all(self.first['generation_id'])
        self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        with self.factory() as connection:
            self.assertIsNone(connection.execute('SELECT to_regclass(%s) AS name',
                                                 ('raw.' + self.first['partition_name'],)).fetchone()['name'])
        history = ArchiveHistory(self.repository, self.transport, self.limits)
        actual, cursor = [], None
        while True:
            page = history.read_generation(self.first['generation_id'], limit=3, after_event_id=cursor)
            actual.extend(page['rows'])
            cursor = page['next_cursor']
            if not cursor:
                break
        self.assertEqual(actual, wire(original))
        self.assertEqual(history.price_inputs(self.first['generation_id'], limit=1)['inputs'][0]['price'], original[0]['price'])
        # Exercise the supported HTTP path after the actual partition is absent.
        from fastapi.testclient import TestClient
        from postgres.api import create_app
        from postgres.config import Settings
        from postgres.store import Store
        settings = Settings(origin_id=self.origin, dsn=os.environ['TRADEBOT_TEST_APP_DSN'])
        with TestClient(create_app(settings=settings, store=Store(settings), history=history, refresh=False)) as client:
            response = client.get('/history/archive/' + self.first['generation_id'], params={'limit': 3})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['rows'], wire(original[:3]))
            self.assertEqual(response.json()['provenance']['tier'], 'authenticated_archive')
            self.assertTrue(response.json()['provenance']['historical_only'])
            self.assertEqual(response.json()['rows'][0]['source_time'], original[0]['source_time'])
        self.insert(100)
        switched_again = self.repository.switch_if_due(self.origin, RotationPolicy(1))
        self.assertEqual(switched_again['slot'], 'A')
        self.assertNotEqual(switched_again['generation_id'], self.first['generation_id'])
        second_id = switched['generation_id']
        self.archive_all(second_id)
        self.worker.retire_generated(second_id, qualification_enabled=True)
        self.insert(200)
        third = self.repository.switch_if_due(self.origin, RotationPolicy(1))
        self.assertEqual(third['slot'], 'B')
        self.assertEqual(len({self.first['generation_id'], switched['generation_id'], switched_again['generation_id'], third['generation_id']}), 4)
        self.archive_all(switched_again['generation_id'])
        self.worker.retire_generated(switched_again['generation_id'], qualification_enabled=True)

    def test_reader_drain_corruption_missing_object_and_default_hold_preserve_partition(self):
        self.insert(1)
        self.rotate()
        self.archive_all(self.first['generation_id'])
        with self.assertRaises(LifecycleHold):
            self.worker.retire_generated(self.first['generation_id'])
        with self.repository.reader_lease(self.first['generation_id'], 'generated-history-reader'):
            with self.assertRaises(LifecycleHold):
                self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        self.assert_partition_present(self.first)
        key = self.repository.manifests(self.first['generation_id'])[0]['object_key']
        blob = self.transport.objects[key]
        self.transport.objects[key] = blob[:-1]
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        del self.transport.objects[key]
        with self.assertRaises(ArchiveUnavailable):
            self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        self.assert_partition_present(self.first)
        self.transport.objects[key] = blob
        # Every retry rechecks remote bytes; prior proof never permits DROP.
        self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        self.assertEqual(self.repository.generation(self.first['generation_id'])['state'], 'retired')

    def test_protected_evidence_outbox_survives_partition_retirement(self):
        raw = self.insert(1)
        self.rotate()
        self.archive_all(self.first['generation_id'])
        protected = {key: raw[key] for key in ('origin_id', 'generation_id', 'source', 'event_id', 'kind',
                                               'market_id', 'source_time', 'source_epoch', 'received_at',
                                               'available_at', 'payload', 'raw_payload', 'content_hash')}
        protected['evidence_id'] = 'evidence-1'
        with self.app_factory() as connection:
            connection.execute('SELECT generation_id FROM archive.generations WHERE generation_id=%s FOR SHARE',
                               (self.first['generation_id'],))
            columns = list(protected)
            placeholders = ','.join('%s::jsonb' if key == 'payload' else '%s' for key in columns)
            connection.execute(f'INSERT INTO core.protected_evidence({",".join(columns)}) VALUES({placeholders})',
                               [encoded(protected[key]).decode() if key == 'payload' else protected[key] for key in columns])
        with self.assertRaises(LifecycleHold):
            self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        self.assert_partition_present(self.first)
        with self.app_factory() as connection:
            connection.execute('''INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,
                content_hash,payload,created_at) VALUES(%s,%s,'core.protected_evidence',%s,%s,%s::jsonb,%s)''',
                               (self.origin, self.first['generation_id'], encoded([self.origin, 'evidence-1']).decode(),
                                protected['content_hash'], encoded(protected).decode(), datetime.now(timezone.utc)))
        with self.assertRaises(LifecycleHold):
            self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        self.worker.archive_cycle(self.first['generation_id'])
        self.worker.retire_generated(self.first['generation_id'], qualification_enabled=True)
        with self.factory() as connection:
            row = connection.execute('SELECT * FROM core.protected_evidence WHERE origin_id=%s AND evidence_id=%s',
                                     (self.origin, 'evidence-1')).fetchone()
            self.assertEqual(wire(row), wire(protected))

    def test_occupied_slot_and_forged_cached_checkpoint_cannot_retire(self):
        self.insert(1)
        first_switch = self.rotate()
        held = self.repository.switch_if_due(self.origin, RotationPolicy(1))
        self.assertEqual(held['status'], 'held')
        self.assertEqual(held['generation_id'], first_switch['generation_id'])
        self.archive_all(self.first['generation_id'])
        generation = self.repository.generation(self.first['generation_id'])
        # A proof committed in an earlier transaction has no deletion authority.
        with self.factory() as connection:
            txid = connection.execute('SELECT txid_current() AS txid').fetchone()['txid']
            self.repository._checkpoint(connection, generation, 'retirement:fresh-readback',
                                        {'gate_scope': 'immutable-generated', 'authorized_txid': txid,
                                         'sha256': generation['seal_hash'], 'row_count': generation['seal_count'],
                                         'retirement_enabled': True})
        with self.assertRaises(Exception):
            with self.factory() as connection:
                connection.execute('SELECT archive.retire_generation_partition(%s,%s)',
                                   (self.origin, self.first['generation_id']))
        self.assert_partition_present(self.first)


if __name__ == '__main__':
    unittest.main()
