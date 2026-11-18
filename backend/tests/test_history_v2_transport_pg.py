"""Disposable isolated PostgreSQL proof; never connects to Supabase."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import math
import sys
import time
from threading import Barrier, Event
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded, sha256
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.lifecycle import LifecycleHold, LifecycleRepository


DSN = os.environ.get('TRADEBOT_TEST_HISTORY_V2_DSN')


def envelope(outbox_id, table, payload, generation_id):
    from postgres.history_v2_envelope import TABLE_KEYS
    return {'id': outbox_id, 'origin_id': payload['origin_id'],
            'generation_id': generation_id, 'entity_type': table,
            'entity_id': encoded([payload[key] for key in TABLE_KEYS[table]]).decode(),
            'content_hash': payload['content_hash'], 'payload': payload}


@unittest.skipUnless(DSN, 'isolated generated history_v2 DSN not supplied')
class HistoryV2TransportPostgresTests(unittest.TestCase):
    def test_generated_a_pending_blocks_b_until_acknowledged(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda: psycopg.connect(DSN, row_factory=dict_row,
                                          connect_timeout=5)
        repository = LifecycleRepository(factory)
        origin = 'pp-live-ci-' + uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        first = repository.bootstrap(origin, now - timedelta(hours=73))
        switched = repository.switch_if_due(origin, now=now)
        self.assertEqual(switched['status'], 'switched')
        first_id = str(first['generation_id'])
        second_id = str(switched['generation_id'])
        with factory() as connection:
            old_id = connection.execute('''INSERT INTO ops.outbox
                (origin_id,generation_id,entity_type,entity_id,content_hash,
                 payload,created_at) VALUES(%s,%s,'core.current_prices','old',%s,
                 '{}'::jsonb,%s) RETURNING id''',
                (origin, first_id, 'a' * 64, now)).fetchone()['id']
        self.assertTrue(repository.has_other_pending(origin, second_id))
        self.assertFalse(repository.has_other_pending(origin, first_id))
        with factory() as connection:
            connection.execute('UPDATE ops.outbox SET acknowledged_at=%s WHERE id=%s',
                               (now, old_id))
        self.assertFalse(repository.has_other_pending(origin, second_id))

    def test_pg17_whole_transaction_timeout_and_slow_connection_hold(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row, connect_timeout=5)
        with factory() as connection:
            with connection.transaction():
                HistoryV2PostgresTransport._limit(connection, 0.5)
                setting = connection.execute('SHOW transaction_timeout').fetchone()
                self.assertEqual(setting['transaction_timeout'], '500ms')
        slow = HistoryV2PostgresTransport(
            lambda *, timeout_seconds: (time.sleep(timeout_seconds + 0.02),
                                        factory())[1],
            origin_id='pp-live-ci-' + uuid.uuid4().hex,
            generation_id=str(uuid.uuid4()),
            expected_database='unused', expected_role='unused')
        # The validation path is exercised by other tests; isolate connection
        # time here so no SQL import can occur after its request deadline.
        with patch.object(slow, '_validate'), self.assertRaises(ArchiveLimit):
            slow.put_structured([{'id': 1}], timeout_seconds=0.01)

    def test_same_origin_session_lock_serializes_workers(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda: psycopg.connect(DSN, row_factory=dict_row,
                                          connect_timeout=5)
        first = LifecycleRepository(factory)
        second = LifecycleRepository(factory)
        origin = 'pp-live-ci-' + uuid.uuid4().hex
        with first.structured_sync_lock(origin):
            with self.assertRaises(LifecycleHold):
                with second.structured_sync_lock(origin):
                    self.fail('same-origin lock admitted a second worker')
            with second.structured_sync_lock(origin + '-other'):
                pass
        with second.structured_sync_lock(origin):
            pass

    def test_narrow_immutable_privileges_and_concurrent_replay(self):
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row

        # Model the separately reviewed NOLOGIN role's effective permissions
        # inside this disposable PG17 database; no live grant is installed.
        admin = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row, connect_timeout=max(1, math.ceil(timeout_seconds)),
            options='-c timezone=UTC')
        origin = 'pp-live-ci-' + uuid.uuid4().hex
        generation = str(uuid.uuid4())
        role = 'pp_receipt_ci_' + uuid.uuid4().hex

        def remove_generated_role():
            with admin() as connection:
                if connection.execute('SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s) '
                                      'AS present', (role,)).fetchone()['present']:
                    connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                    connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

        self.addCleanup(remove_generated_role)
        with admin() as connection:
            database = connection.execute('SELECT current_database() AS name').fetchone()['name']
            connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS').format(
                sql.Identifier(role)))
            connection.execute(sql.SQL('GRANT USAGE ON SCHEMA history_v2 TO {}').format(
                sql.Identifier(role)))
            connection.execute(sql.SQL('GRANT EXECUTE ON FUNCTION '
                'history_v2.source_epoch(text) TO {}').format(sql.Identifier(role)))
            for table in ('markets', 'feature_snapshots', 'generation_checkpoints',
                          'structured_receipts'):
                relation = sql.Identifier('history_v2', table)
                connection.execute(sql.SQL('GRANT SELECT, INSERT ON {} TO {}').format(
                    relation, sql.Identifier(role)))
                connection.execute(sql.SQL('CREATE POLICY {} ON {} '
                    'FOR SELECT TO {} USING (origin_id = {})').format(
                        sql.Identifier(role + '_select'), relation,
                        sql.Identifier(role), sql.Literal(origin)))
                connection.execute(sql.SQL('CREATE POLICY {} ON {} '
                    'FOR INSERT TO {} WITH CHECK (origin_id = {})').format(
                        sql.Identifier(role + '_insert'), relation,
                        sql.Identifier(role), sql.Literal(origin)))
            for table in ('markets', 'generation_checkpoints'):
                relation = sql.Identifier('history_v2', table)
                connection.execute(sql.SQL('GRANT UPDATE ON {} TO {}').format(
                    relation, sql.Identifier(role)))
                connection.execute(sql.SQL('CREATE POLICY {} ON {} '
                    'FOR UPDATE TO {} USING (origin_id = {}) WITH CHECK (origin_id = {})').format(
                        sql.Identifier(role + '_update'), relation,
                        sql.Identifier(role), sql.Literal(origin),
                        sql.Literal(origin)))
            for table in ('feature_snapshots', 'structured_receipts'):
                self.assertFalse(connection.execute(
                    'SELECT has_table_privilege(%s,%s,%s) AS allowed',
                    (role, 'history_v2.' + table, 'UPDATE')).fetchone()['allowed'])

        second_connected = Event()
        first_at_receipt = Event()
        release_first = Event()

        def factory(*, second=False, timeout_seconds=5):
            connection = admin(timeout_seconds)
            connection.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
            if second:
                second_connected.set()
            return connection

        with factory() as connection:
            for table in ('feature_snapshots', 'structured_receipts'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute(sql.SQL('SELECT * FROM {} FOR UPDATE').format(
                            sql.Identifier('history_v2', table))).fetchone()

        start = datetime(2026, 11, 18, tzinfo=timezone.utc)
        market = dict(origin_id=origin, market_id='market-1', source='polymarket-us',
            slug='market-1', duration=900, start_time=start.isoformat(),
            end_time=(start + timedelta(minutes=15)).isoformat(),
            start_epoch=str(int(start.timestamp())),
            end_epoch=str(int((start + timedelta(minutes=15)).timestamp())),
            target='100.0000', final=None, result=None, status='open',
            index_symbol='BTC-USD', rules=None, first_seen=start.isoformat(),
            last_seen=start.isoformat(), payload={'source':'generated'},
            content_hash='a' * 64)
        feature = dict(origin_id=origin, snapshot_id='snapshot-1',
            market_id='market-1', as_of=(start + timedelta(seconds=1)).isoformat(),
            version=1, values_json={'price':'100.0000'}, quality_json={},
            evidence_json={}, content_hash='b' * 64)
        records = [envelope(1, 'core.markets', market, generation),
                   envelope(2, 'core.feature_snapshots', feature, generation)]

        class PausedTransport(HistoryV2PostgresTransport):
            def _receipt(self, connection, record):
                first_at_receipt.set()
                if not release_first.wait(5):
                    raise AssertionError('first importer was not released')
                return super()._receipt(connection, record)

        binding = dict(origin_id=origin, generation_id=generation,
                       expected_database=database, expected_role=role)
        first = PausedTransport(factory, **binding)
        second = HistoryV2PostgresTransport(
            lambda *, timeout_seconds: factory(second=True, timeout_seconds=timeout_seconds),
            **binding)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(first.put_structured, records, timeout_seconds=10)
            self.assertTrue(first_at_receipt.wait(5))
            second_result = pool.submit(second.put_structured, records, timeout_seconds=10)
            self.assertTrue(second_connected.wait(5))
            release_first.set()
            first_result.result(timeout=10)
            second_result.result(timeout=10)

        self.assertEqual(second.read_structured_authenticated(
            records, max_bytes=4 * 1024 * 1024, timeout_seconds=10), records)
        changed = dict(records[1], content_hash='c' * 64,
                       payload={**feature, 'content_hash': 'c' * 64})
        with self.assertRaises(ArchiveIntegrityError):
            second.put_structured([changed], timeout_seconds=10)

        # Entity locks differ here, but the stream lock must serialize reuse
        # of one outbox ID so exactly one immutable entity can receive it.
        contenders = [envelope(3, 'core.feature_snapshots',
            {**feature, 'snapshot_id': 'snapshot-' + suffix,
             'as_of': (start + timedelta(seconds=int(suffix))).isoformat(),
             'content_hash': digest * 64}, generation)
            for suffix, digest in (('2', 'd'), ('3', 'e'))]
        start_together = Barrier(3)

        def import_contender(record):
            start_together.wait(timeout=5)
            try:
                second.put_structured([record], timeout_seconds=10)
                return 'accepted'
            except ArchiveIntegrityError:
                return 'rejected'

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [pool.submit(import_contender, contender)
                        for contender in contenders]
            start_together.wait(timeout=5)
            results = [outcome.result(timeout=10) for outcome in outcomes]
        self.assertCountEqual(results, ['accepted', 'rejected'])
        with admin() as connection:
            receipt_count = connection.execute('SELECT count(*) AS count FROM '
                'history_v2.structured_receipts WHERE origin_id=%s', (origin,)).fetchone()['count']
            checkpoint = connection.execute('SELECT row_count FROM '
                "history_v2.generation_checkpoints WHERE origin_id=%s AND dataset='structured:outbox'",
                (origin,)).fetchone()
        self.assertEqual(receipt_count, 3)
        self.assertEqual(checkpoint['row_count'], 3)

    def test_atomic_revisions_receipts_retry_and_conflict(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row,
            connect_timeout=max(1, math.ceil(timeout_seconds)),
            options='-c timezone=UTC')
        with factory() as connection:
            binding = connection.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        origin = 'pp-live-ci-' + uuid.uuid4().hex
        generation = str(uuid.uuid4())
        transport = HistoryV2PostgresTransport(factory, origin_id=origin,
            generation_id=generation, expected_database=binding['database'],
            expected_role=binding['role'])
        start = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        market = dict(origin_id=origin, market_id='market-1', source='polymarket-us',
            slug='market-1', duration=900, start_time=start.isoformat().replace('+00:00', 'Z'),
            end_time=end.isoformat().replace('+00:00', 'Z'),
            start_epoch=str(int(start.timestamp())), end_epoch=str(int(end.timestamp())),
            target='100.0000', final=None, result=None, status='open',
            index_symbol='BTC-USD', rules=None, first_seen=start.isoformat(),
            last_seen=start.isoformat(), payload={'source':'generated'},
            content_hash='a' * 64)
        first_time = start + timedelta(seconds=1)
        first = dict(origin_id=origin, source='coinbase', symbol='BTC-USD',
            event_id='tick-1', generation_id=generation,
            source_time=first_time.isoformat().replace('+00:00','Z'),
            source_epoch=str(int(first_time.timestamp())),
            received_at=first_time.isoformat(), available_at=first_time.isoformat(),
            price='100.2300', size=None, payload={'source':'generated'},
            content_hash='b' * 64)
        second_time = start + timedelta(seconds=2)
        second = {**first, 'event_id':'tick-2',
            'source_time':second_time.isoformat().replace('+00:00','Z'),
            'source_epoch':str(int(second_time.timestamp())),
            'received_at':second_time.isoformat(),
            'available_at':second_time.isoformat(), 'price':'100.2400',
            'content_hash':'c' * 64}
        records = [envelope(1, 'core.markets', market, generation),
                   envelope(2, 'core.current_prices', first, generation),
                   envelope(3, 'core.current_prices', second, generation)]
        transport.put_structured(records, timeout_seconds=5)
        self.assertEqual(transport.read_structured_authenticated(
            records, max_bytes=4 * 1024 * 1024, timeout_seconds=5), records)
        # Ambiguous post-commit response: replay must not overwrite or count
        # another receipt, and fresh readback still proves the first commit.
        transport.put_structured(records, timeout_seconds=5)
        with factory() as connection:
            receipts = connection.execute('''SELECT count(*) AS count FROM
                history_v2.structured_receipts WHERE origin_id=%s''', (origin,)).fetchone()
            checkpoint = connection.execute('''SELECT row_count FROM
                history_v2.generation_checkpoints WHERE origin_id=%s AND
                generation_id=%s AND dataset='structured:outbox' ''',
                (origin, generation)).fetchone()
            price = connection.execute('''SELECT price::text AS price,event_id
                FROM history_v2.current_prices WHERE origin_id=%s''', (origin,)).fetchone()
        self.assertEqual(receipts['count'], 3)
        self.assertEqual(checkpoint['row_count'], 3)
        self.assertEqual(price, {'price':'100.2400', 'event_id':'tick-2'})
        conflict = dict(records[-1], content_hash='d' * 64,
                        payload={**second, 'content_hash':'d' * 64})
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_structured([conflict], timeout_seconds=5)
        stale = {**first, 'event_id':'tick-stale', 'content_hash':'e' * 64}
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_structured([envelope(4, 'core.current_prices', stale,
                                               generation)], timeout_seconds=5)
        with factory() as connection:
            count = connection.execute('''SELECT count(*) AS count FROM
                history_v2.structured_receipts WHERE origin_id=%s''', (origin,)).fetchone()
        self.assertEqual(count['count'], 3)
        wrong = HistoryV2PostgresTransport(factory, origin_id=origin,
            generation_id=generation, expected_database='wrong_database',
            expected_role=binding['role'])
        with self.assertRaises(ArchiveIntegrityError):
            wrong.put_structured([records[0]], timeout_seconds=5)
        # Independent authenticated reads must detect a changed cloud
        # projection or receipt before any local outbox acknowledgement.
        with factory() as connection:
            connection.execute('''UPDATE history_v2.current_prices SET price='999.0000'
                WHERE origin_id=%s''', (origin,))
        with self.assertRaises(ArchiveIntegrityError):
            transport.read_structured_authenticated(records,
                max_bytes=4 * 1024 * 1024, timeout_seconds=5)
        forged_time = start + timedelta(seconds=3)
        with factory() as connection:
            connection.execute('''UPDATE history_v2.current_prices SET
                event_id='tick-forged',source_time=%s,source_epoch=%s,
                received_at=%s,available_at=%s,price='100.2500',content_hash=%s
                WHERE origin_id=%s''',
                (forged_time.isoformat().replace('+00:00','Z'),
                 str(int(forged_time.timestamp())), forged_time, forged_time,
                 'd' * 64, origin))
        with self.assertRaises(ArchiveIntegrityError):
            transport.read_structured_authenticated(records,
                max_bytes=4 * 1024 * 1024, timeout_seconds=5)
        with factory() as connection:
            connection.execute('''UPDATE history_v2.current_prices SET
                event_id=%s,source_time=%s,source_epoch=%s,
                received_at=%s,available_at=%s,price=%s,content_hash=%s
                WHERE origin_id=%s''',
                (second['event_id'], second['source_time'], second['source_epoch'],
                 second['received_at'], second['available_at'],
                 second['price'], second['content_hash'], origin))
            connection.execute('''UPDATE history_v2.structured_receipts
                SET envelope_hash=%s WHERE origin_id=%s AND outbox_id=2''',
                ('f' * 64, origin))
        with self.assertRaises(ArchiveIntegrityError):
            transport.read_structured_authenticated(records,
                max_bytes=4 * 1024 * 1024, timeout_seconds=5)
        with factory() as connection:
            connection.execute('''UPDATE history_v2.generation_checkpoints
                SET cursor='{"outbox_id":1}'::jsonb,content_hash=%s
                WHERE origin_id=%s AND generation_id=%s AND dataset='structured:outbox' ''',
                (sha256(encoded({'outbox_id': 1})), origin, generation))
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_structured(records, timeout_seconds=5)
        with factory() as connection:
            connection.execute('''UPDATE history_v2.generation_checkpoints
                SET cursor='{"outbox_id":3}'::jsonb,content_hash=%s
                WHERE origin_id=%s AND generation_id=%s AND dataset='structured:outbox' ''',
                (sha256(encoded({'outbox_id': 3})), origin, generation))
        with factory() as connection:
            connection.execute('''DELETE FROM history_v2.structured_receipts
                WHERE origin_id=%s AND outbox_id=2''', (origin,))
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_structured(records, timeout_seconds=5)

    def test_parent_import_precedes_lower_id_dependent(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row,
            connect_timeout=max(1, math.ceil(timeout_seconds)),
            options='-c timezone=UTC')
        with factory() as connection:
            binding = connection.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        origin, generation = 'pp-live-ci-' + uuid.uuid4().hex, str(uuid.uuid4())
        transport = HistoryV2PostgresTransport(factory, origin_id=origin,
            generation_id=generation, expected_database=binding['database'],
            expected_role=binding['role'])
        start = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        market = dict(origin_id=origin, market_id='market-1', source='polymarket-us',
            slug='market-1', duration=900,
            start_time=start.isoformat().replace('+00:00','Z'),
            end_time=end.isoformat().replace('+00:00','Z'),
            start_epoch=str(int(start.timestamp())),
            end_epoch=str(int(end.timestamp())), target='100.0000', final=None,
            result=None, status='open', index_symbol='BTC-USD', rules=None,
            first_seen=start.isoformat(), last_seen=start.isoformat(),
            payload={'source':'generated'}, content_hash='f' * 64)
        feature = dict(origin_id=origin, snapshot_id='snapshot-1',
            market_id='market-1', as_of=(start + timedelta(seconds=1)).isoformat(),
            version=1, values_json={'price':'100.0000'}, quality_json={},
            evidence_json={}, content_hash='e' * 64)
        records = [envelope(1, 'core.feature_snapshots', feature, generation),
                   envelope(2, 'core.markets', market, generation)]
        transport.put_structured(records, timeout_seconds=5)
        self.assertEqual(transport.read_structured_authenticated(
            records, max_bytes=4 * 1024 * 1024, timeout_seconds=5), records)


if __name__ == '__main__':
    unittest.main()
