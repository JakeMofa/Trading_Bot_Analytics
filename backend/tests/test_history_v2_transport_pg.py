"""Disposable isolated PostgreSQL proof; never connects to Supabase."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
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


class DelayedConnection:
    """Generated 100ms round trips; pipelined commands share one wait."""
    def __init__(self, inner):
        self.inner, self.queries, self.roundtrips, self.depth = inner, 0, 0, 0

    def __enter__(self):
        self.inner.__enter__()
        return self

    def __exit__(self, *args):
        return self.inner.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def wait(self):
        self.roundtrips += 1
        time.sleep(0.1)

    def execute(self, *args, **kwargs):
        self.queries += 1
        if not self.depth:
            self.wait()
        return self.inner.execute(*args, **kwargs)

    @contextmanager
    def pipeline(self):
        self.depth += 1
        try:
            with self.inner.pipeline() as pipeline:
                yield pipeline
                self.wait()
        finally:
            self.depth -= 1


@unittest.skipUnless(DSN, 'isolated generated history_v2 DSN not supplied')
class HistoryV2TransportPostgresTests(unittest.TestCase):
    def setUp(self):
        # Isolated generated origins remain unique between tests. Production
        # constructors always require the exact PP origin.
        self.origin = 'pp-live-ci-' + uuid.uuid4().hex
        binding = patch('postgres.history_v2_transport.PP_STRUCTURED_ORIGIN',
                        self.origin)
        binding.start()
        self.addCleanup(binding.stop)

    def test_recurring_page_advances_exactly_fifty_after_authenticated_readback(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from postgres.pp_structured_drain import drain_bounded
        from postgres.pp_structured_service import RECURRING_LIMITS

        def local():
            return psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
                                   options='-c timezone=UTC')

        repository = LifecycleRepository(local)
        origin = self.origin
        generation = str(repository.bootstrap(origin)['generation_id'])
        start = datetime(2026, 11, 18, tzinfo=timezone.utc)
        with local() as db:
            identity = db.execute('SELECT current_database() AS db, current_user AS role').fetchone()
            for index in range(51):
                stamp = start + timedelta(seconds=index)
                price = dict(origin_id=origin, source='coinbase', symbol='BTC-USD',
                    event_id=f'trade-{index}', generation_id=generation, source_time=stamp.isoformat(),
                    source_epoch=str(int(stamp.timestamp())), received_at=stamp.isoformat(),
                    available_at=stamp.isoformat(), price=f'100.{index:04d}', size='1E-8',
                    payload={'generated': True, 'padding': 'p' * 700}, content_hash=f'{index+1:064x}')
                key = envelope(index + 1, 'core.current_prices', price, generation)['entity_id']
                db.execute("""INSERT INTO ops.outbox
                    (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                    VALUES (%s,%s,'core.current_prices',%s,%s,%s,%s)""",
                    (origin, generation, key, price['content_hash'], Jsonb(price), stamp))

        def transport(selected, *, timeout_seconds):
            self.assertEqual(selected, generation)
            return HistoryV2PostgresTransport(lambda *, timeout_seconds: DelayedConnection(local()),
                origin_id=origin, generation_id=selected, expected_database=identity['db'],
                expected_role=identity['role'], retain_revisions=True)

        with patch('postgres.active_structured.PP_STRUCTURED_ORIGIN', origin), \
                patch('postgres.pp_structured_drain.PP_STRUCTURED_ORIGIN', origin):
            result = drain_bounded(repository, transport, execute=True, limits=RECURRING_LIMITS)
        self.assertEqual((result['cycles'], result['acknowledged'], result['cloud_operations']), (1, 50, 2))
        with local() as db:
            rows = db.execute("""SELECT o.id,o.acknowledged_at,
                r.content_hash=o.content_hash AS exact_receipt,p.envelope IS NOT NULL AS exact_payload
                FROM ops.outbox o LEFT JOIN history_v2.structured_receipts r
                  ON (r.origin_id,r.generation_id,r.outbox_id)=(o.origin_id,o.generation_id,o.id)
                LEFT JOIN history_v2.structured_revision_payloads p
                  ON (p.origin_id,p.generation_id,p.outbox_id)=(o.origin_id,o.generation_id,o.id)
                WHERE o.generation_id=%s ORDER BY o.id""", (generation,)).fetchall()
        self.assertEqual(len(rows), 51)
        self.assertTrue(all(row['acknowledged_at'] and row['exact_receipt'] and row['exact_payload']
                            for row in rows[:50]))
        self.assertIsNone(rows[50]['acknowledged_at'])
        self.assertIsNone(rows[50]['exact_receipt'])
        self.assertFalse(rows[50]['exact_payload'])

    def test_full_path_session_reuse_commits_reads_and_acks_same_workload(self):
        import json
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from postgres.pp_history_session import ReusablePPHistoryConnectionFactory
        from postgres.pp_structured_drain import drain_bounded
        from postgres.pp_structured_service import RECURRING_LIMITS

        def local():
            return psycopg.connect(DSN,row_factory=dict_row)
        with local() as db:
            identity=db.execute('SELECT current_database() db,current_user role').fetchone()
        results=[]
        for reuse in (False,True):
            origin=self.origin+('-reused' if reuse else '-cold')
            repository=LifecycleRepository(local)
            generation=str(repository.bootstrap(origin)['generation_id'])
            with local() as db:
                start=datetime(2026,11,18,tzinfo=timezone.utc)
                for index in range(100):
                    stamp=start+timedelta(seconds=index)
                    price=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',
                        event_id=f'trade-{index}',generation_id=generation,
                        source_time=stamp.isoformat(),source_epoch=str(int(stamp.timestamp())),
                        received_at=stamp.isoformat(),available_at=stamp.isoformat(),
                        price=f'100.{index:04d}',size='1E-8',
                        payload={'generated':True,'padding':'p'*700},content_hash=f'{index+1:064x}')
                    candle=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',
                        granularity=60,time=int(start.timestamp())+index*60,
                        low='99.0000',high='101.0000',open='100.0000',close='100.1000',
                        volume='1.00000000',first_seen=stamp.isoformat(),
                        payload={'generated':True,'padding':'c'*500},content_hash=f'{index+1:064x}')
                    table,payload=('core.current_prices',price) if index%2 else ('core.candles',candle)
                    key=envelope(index+1,table,payload,generation)['entity_id']
                    db.execute('''INSERT INTO ops.outbox(origin_id,generation_id,entity_type,
                        entity_id,content_hash,payload,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                        (origin,generation,table,key,payload['content_hash'],Jsonb(payload),stamp))
            connections=[]
            transactions=[]
            class Traced(DelayedConnection):
                @contextmanager
                def transaction(self):
                    with self.inner.transaction():
                        transactions.append(self.inner.execute('SELECT txid_current() n').fetchone()['n'])
                        yield
            def opened(secret=None,deadline=None,**kwargs):
                time.sleep(.2)
                connection=Traced(local())
                connections.append(connection)
                return connection
            remote=ReusablePPHistoryConnectionFactory() if reuse else opened
            try:
                with (patch('postgres.history_v2_transport.PP_STRUCTURED_ORIGIN',origin),
                      patch('postgres.active_structured.PP_STRUCTURED_ORIGIN',origin),
                      patch('postgres.pp_structured_drain.PP_STRUCTURED_ORIGIN',origin),
                      patch.object(remote,'_validated_dsn',side_effect=lambda timeout:(b'generated',time.monotonic()+timeout)) if reuse else nullcontext(),
                      patch.object(remote,'_open',side_effect=opened) if reuse else nullcontext()):
                    transports=[]
                    def transport(selected,**kwargs):
                        result=HistoryV2PostgresTransport(remote,origin_id=origin,
                            generation_id=selected,expected_database=identity['db'],
                            expected_role=identity['role'],retain_revisions=True)
                        transports.append(result)
                        return result
                    started=time.monotonic()
                    pages=[drain_bounded(repository,transport,execute=True,limits=RECURRING_LIMITS)
                           for _ in range(2)]
                    elapsed=time.monotonic()-started
                    self.assertEqual(sum(page['acknowledged'] for page in pages),100)
                    self.assertEqual(len(connections),1 if reuse else 4)
                    self.assertEqual(len(set(transactions)),4)
                    with local() as db:
                        rows=db.execute('''SELECT o.*,p.envelope FROM ops.outbox o
                            JOIN history_v2.structured_revision_payloads p
                            ON(p.origin_id,p.generation_id,p.outbox_id)=(o.origin_id,o.generation_id,o.id)
                            WHERE o.generation_id=%s ORDER BY o.id''',(generation,)).fetchall()
                        self.assertEqual(len(rows),100)
                        for row in rows:
                            self.assertIsNotNone(row['acknowledged_at'])
                            canonical={key:row[key] for key in ('id','origin_id','generation_id',
                                'entity_type','entity_id','content_hash','payload')}
                            self.assertEqual(bytes(row['envelope']),encoded(canonical))
                        checkpoint=db.execute("SELECT row_count FROM history_v2.generation_checkpoints WHERE origin_id=%s AND generation_id=%s",(origin,generation)).fetchone()
                        self.assertEqual(checkpoint['row_count'],100)
                    results.append(dict(reuse=reuse,acknowledged=100,seconds=elapsed,
                        rows_per_second=100/elapsed,physical_connections=len(connections),
                        distinct_committed_transactions=len(set(transactions)),envelopes=100))
            finally:
                if reuse:remote.close()
        print('generated_full_sync_session_comparison '+json.dumps(results),flush=True)

    def test_reused_session_rollback_ambiguous_commit_and_role_failure_never_ack(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from postgres.active_structured import ActiveStructuredWorker
        from postgres.archive_codec import ArchiveLimits, ArchiveUnavailable
        from postgres.pp_history_session import ReusablePPHistoryConnectionFactory
        def local():
            return psycopg.connect(DSN,row_factory=dict_row)
        repository=LifecycleRepository(local)
        origin=self.origin
        generation=str(repository.bootstrap(origin)['generation_id'])
        with local() as db:
            identity=db.execute('SELECT current_database() db,current_user role').fetchone()
            for index in range(3):
                stamp=datetime(2026,11,18,tzinfo=timezone.utc)+timedelta(seconds=index)
                payload=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',
                    event_id=f'trade-{index}',generation_id=generation,
                    source_time=stamp.isoformat(),source_epoch=str(int(stamp.timestamp())),
                    received_at=stamp.isoformat(),available_at=stamp.isoformat(),
                    price=f'100.{index:04d}',size='1E-8',payload={'generated':True},
                    content_hash=f'{index+1:064x}')
                key=envelope(index+1,'core.current_prices',payload,generation)['entity_id']
                db.execute("INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at) VALUES(%s,%s,'core.current_prices',%s,%s,%s,%s)",
                    (origin,generation,key,payload['content_hash'],Jsonb(payload),stamp))
        connections=[]
        class ResponseLoss(DelayedConnection):
            def wait(self):
                self.roundtrips+=1
            @contextmanager
            def transaction(self):
                with self.inner.transaction():
                    yield
                if self.lose_response:
                    self.lose_response=False
                    raise RuntimeError('generated loss after durable commit')
        def opened(secret,deadline):
            connection=ResponseLoss(local())
            connection.lose_response=len(connections)==1
            connections.append(connection)
            return connection
        remote=ReusablePPHistoryConnectionFactory()
        try:
            with (patch('postgres.active_structured.PP_STRUCTURED_ORIGIN',origin),
                  patch.object(remote,'_validated_dsn',side_effect=lambda timeout:(b'generated',time.monotonic()+timeout)),
                  patch.object(remote,'_open',side_effect=opened)):
                transport=HistoryV2PostgresTransport(remote,origin_id=origin,generation_id=generation,
                    expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True)
                worker=ActiveStructuredWorker(repository,transport,origin_id=origin,
                    limits=ArchiveLimits(max_rows=3,max_requests=2,max_seconds=20,request_timeout_seconds=4))
                original=transport._insert_receipts
                def fail_before_commit(db,rows):
                    original(db,rows)
                    raise RuntimeError('generated failure before commit')
                with patch.object(transport,'_insert_receipts',side_effect=fail_before_commit), self.assertRaises(ArchiveUnavailable):
                    worker.cycle(generation)
                self.assertTrue(connections[0].closed)
                with local() as db:
                    self.assertEqual(db.execute("SELECT count(*) n FROM history_v2.structured_receipts WHERE origin_id=%s",(origin,)).fetchone()['n'],0)
                    self.assertEqual(db.execute("SELECT count(*) n FROM history_v2.current_prices WHERE origin_id=%s",(origin,)).fetchone()['n'],0)
                with self.assertRaises(ArchiveUnavailable):
                    worker.cycle(generation)
                self.assertTrue(connections[1].closed)
                transport.expected_role='generated_wrong_role'
                with self.assertRaises(ArchiveIntegrityError):
                    worker.cycle(generation)
                self.assertTrue(connections[2].closed)
                with local() as db:
                    self.assertEqual(db.execute("SELECT count(*) n FROM ops.outbox WHERE generation_id=%s AND acknowledged_at IS NOT NULL",(generation,)).fetchone()['n'],0)
                    self.assertEqual(db.execute("SELECT count(*) n FROM history_v2.structured_revision_payloads WHERE origin_id=%s",(origin,)).fetchone()['n'],3)
                transport.expected_role=identity['role']
                self.assertEqual(worker.cycle(generation)['acknowledged'],3)
                self.assertEqual(len(connections),4)
                with local() as db:
                    self.assertEqual(db.execute("SELECT count(*) n FROM history_v2.structured_receipts WHERE origin_id=%s",(origin,)).fetchone()['n'],3)
                    self.assertEqual(db.execute("SELECT row_count FROM history_v2.generation_checkpoints WHERE origin_id=%s",(origin,)).fetchone()['row_count'],3)
                    self.assertEqual(db.execute("SELECT count(*) n FROM ops.outbox WHERE generation_id=%s AND acknowledged_at IS NOT NULL",(generation,)).fetchone()['n'],3)
        finally:
            remote.close()

    def test_generated_a_pending_blocks_b_until_acknowledged(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda: psycopg.connect(DSN, row_factory=dict_row,
                                          connect_timeout=5)
        repository = LifecycleRepository(factory)
        origin = self.origin
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
            origin_id=self.origin,
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
        origin = self.origin
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
        origin = self.origin
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
            def _receipts(self, connection, records):
                first_at_receipt.set()
                if not release_first.wait(5):
                    raise AssertionError('first importer was not released')
                return super()._receipts(connection, records)

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
        origin = self.origin
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
        # Hash-only receipts from the prior release cannot reconstruct an
        # earlier revision. An opt-in, exact local backfill supplies the bytes
        # without rewriting today's projection or its generation checkpoint.
        previous=HistoryV2PostgresTransport(factory,origin_id=origin,generation_id=generation,
            expected_database=binding['database'],expected_role=binding['role'],retain_revisions=True)
        with self.assertRaises(ArchiveIntegrityError):
            previous.read_revisions([2],max_bytes=4096,timeout_seconds=5)
        from postgres.pp_revision_backfill import backfill, inventory
        def local_pages(after):
            return [r for r in records[:2] if r['id'] > after][:1]
        scope, _ = inventory(local_pages, 2)
        with factory() as connection:
            before = connection.execute("SELECT row_to_json(p) AS row FROM history_v2.current_prices p WHERE origin_id=%s", (origin,)).fetchall()
            checkpoint = connection.execute("SELECT row_to_json(c) AS row FROM history_v2.generation_checkpoints c WHERE origin_id=%s", (origin,)).fetchall()
        for _ in range(2):
            proof = backfill(local_pages, previous, 2, expected_count=2,
                             expected_sha256=scope['sha256'])
            self.assertEqual((proof['verified_rows'],proof['pages'],proof['cloud_operations']), (2,2,4))
        with factory() as connection:
            self.assertEqual(connection.execute("SELECT row_to_json(p) AS row FROM history_v2.current_prices p WHERE origin_id=%s", (origin,)).fetchall(), before)
            self.assertEqual(connection.execute("SELECT row_to_json(c) AS row FROM history_v2.generation_checkpoints c WHERE origin_id=%s", (origin,)).fetchall(), checkpoint)
        previous.put_structured(records,timeout_seconds=5)
        self.assertEqual(previous.read_revisions([2,3],max_bytes=8192,timeout_seconds=5),records[1:])
        # Explicitly simulate privileged mutation; normal PP cannot update.
        with factory() as connection:
            connection.execute("""UPDATE history_v2.structured_revision_payloads SET envelope=%s
                WHERE origin_id=%s AND generation_id=%s AND outbox_id=2""",
                (encoded(records[-1]),origin,generation))
        with self.assertRaises(ArchiveIntegrityError):
            previous.read_revisions([2],max_bytes=4096,timeout_seconds=5)
        with self.assertRaises(ArchiveIntegrityError):
            previous.read_structured_authenticated(records,max_bytes=16384,timeout_seconds=5)
        with factory() as connection:
            connection.execute("""UPDATE history_v2.structured_revision_payloads SET envelope=%s
                WHERE origin_id=%s AND generation_id=%s AND outbox_id=2""",
                (encoded(records[1]),origin,generation))
        with self.assertRaises(ArchiveLimit):
            previous.read_revisions([2,3],max_bytes=1,timeout_seconds=5)
        with self.assertRaises(ArchiveIntegrityError):
            previous.backfill_verified_revisions([dict(records[1],payload={**first,'price':'0.00'})],
                                                 timeout_seconds=5)
        with self.assertRaises(ArchiveIntegrityError):
            previous.backfill_verified_revisions([dict(records[1],id=999)],timeout_seconds=5)

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
        # PostgreSQL prevents a dangling envelope even for a privileged test writer.
        with self.assertRaises(psycopg.errors.ForeignKeyViolation), factory() as connection:
            connection.execute('''DELETE FROM history_v2.structured_receipts
                WHERE origin_id=%s AND outbox_id=2''', (origin,))
        # Simulate a privileged removal of both halves of the recovery evidence.
        with factory() as connection:
            connection.execute('''DELETE FROM history_v2.structured_revision_payloads
                WHERE origin_id=%s AND outbox_id=2''', (origin,))
            connection.execute('''DELETE FROM history_v2.structured_receipts
                WHERE origin_id=%s AND outbox_id=2''', (origin,))
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_structured(records, timeout_seconds=5)

    def test_expired_retained_audit_is_read_only_and_never_authorizes_retirement(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from psycopg.conninfo import make_conninfo
        from postgres.archive_codec import ArchiveLimits, encoded
        from postgres.lifecycle import ArchiveWorker
        from postgres.pp_retirement_verify import RetirementTransport
        from postgres import pp_retained_archive_audit as candidate
        from postgres.connection import connect
        from backend.tests.postgres_lifecycle_fixtures import ImmutableMemoryTransport, generated_rows

        def local(): return psycopg.connect(DSN,row_factory=dict_row,options='-c timezone=UTC')
        repo=LifecycleRepository(local)
        origin=self.origin
        a=str(repo.bootstrap(origin,datetime.now(timezone.utc)-timedelta(hours=73))['generation_id'])
        rawrow=generated_rows(a,1,origin)[0]
        with local() as db:
            cols=list(rawrow)
            db.execute('INSERT INTO raw.events('+','.join(cols)+') VALUES ('+
                ','.join('%s::jsonb' if c=='payload' else '%s' for c in cols)+')',
                [encoded(rawrow[c]).decode() if c=='payload' else rawrow[c] for c in cols])
            stamp=datetime.now(timezone.utc).replace(microsecond=0)
            payload=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',event_id='audit',
                generation_id=a,source_time=stamp.isoformat(),source_epoch=str(int(stamp.timestamp())),
                received_at=stamp.isoformat(),available_at=stamp.isoformat(),price='100.2300',
                size=None,payload={'generated':True},content_hash='a'*64)
            key=envelope(1,'core.current_prices',payload,a)['entity_id']
            index=db.execute('INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,\n                content_hash,payload,created_at,acknowledged_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                (origin,a,'core.current_prices',key,'a'*64,Jsonb(payload),stamp,stamp)).fetchone()['id']
            identity=db.execute('SELECT current_database() db,current_user role').fetchone()
        record=envelope(index,'core.current_prices',payload,a)
        remote=HistoryV2PostgresTransport(lambda **kwargs:local(),origin_id=origin,generation_id=a,
            expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True)
        remote.put_structured([record],timeout_seconds=4)
        b=str(repo.switch_if_due(origin,now=datetime.now(timezone.utc)-timedelta(hours=1))['generation_id'])
        raw=ImmutableMemoryTransport()
        ArchiveWorker(repo,raw,ArchiveLimits()).archive_cycle(a)
        generation=repo.generation(a)
        target=candidate.AuditTarget(a,b,generation['seal_hash'],1,1,1,1,
            (generation['sealed_at']+timedelta(minutes=30)).isoformat())
        reader_dsn=make_conninfo(DSN,user='tradebot_reader')
        reader=lambda:connect(reader_dsn,environment='preprod',readonly=True)
        scoped=RetirementTransport(raw,remote,origin_id=origin,generation_id=a)
        with patch.object(candidate,'ORIGIN',origin):
            result=candidate.audit(reader,scoped,target)
            self.assertEqual(result['status'],'retained_archive_audit_verified')
            self.assertTrue(result['original_seal_expired_at_audit_start'])
            self.assertFalse(result['original_trial_satisfied'])
            self.assertFalse(result['retirement_authorized'])
            self.assertEqual((result['raw_count'],result['structured_count'],result['requests']),(1,1,3))
            self.assertEqual(result['local_role'],'tradebot_reader')
            self.assertEqual(repo.generation(a)['seal_hash'],generation['seal_hash'])
            with local() as db:
                self.assertEqual(db.execute('SELECT count(*) n FROM raw.events WHERE generation_id=%s',(a,)).fetchone()['n'],1)
                self.assertEqual(db.execute('SELECT count(*) n FROM ops.outbox WHERE generation_id=%s',(a,)).fetchone()['n'],1)
            # Lifecycle/admin identity cannot be passed off as a reader, before
            # any raw/cloud call. No permission grant is attempted.
            calls=len(raw.calls)
            with self.assertRaises(LifecycleHold): candidate.audit(local,scoped,target)
            self.assertEqual(len(raw.calls),calls)
            # Wrong inventory refuses before authenticated cloud requests.
            from dataclasses import replace
            with self.assertRaises(LifecycleHold):
                candidate.audit(reader,scoped,replace(target,structured_rows=2))
            self.assertEqual(len(raw.calls),calls)
            # Missing existing local SELECT fails before any cloud/raw read.
            # This revoke/restore is fixture-only, never an audit operation.
            with local() as db: db.execute('REVOKE SELECT ON ops.outbox FROM tradebot_reader')
            try:
                with self.assertRaises(LifecycleHold): candidate.audit(reader,scoped,target)
            finally:
                with local() as db: db.execute('GRANT SELECT ON ops.outbox TO tradebot_reader')
            self.assertEqual(len(raw.calls),calls)
            # The same existing reader has no hosted-schema grants in this
            # fixture. Authenticated preflight rejects before any raw read.
            wrong_remote=HistoryV2PostgresTransport(lambda **kwargs:reader(),origin_id=origin,
                generation_id=a,expected_database='tradebot_pp',expected_role='tradebot_reader')
            with self.assertRaises(LifecycleHold):
                candidate.audit(reader,RetirementTransport(raw,wrong_remote,origin_id=origin,generation_id=a),target)
            self.assertEqual(len(raw.calls),calls)
            # Bind the original wall deadline independently from operation time.
            with self.assertRaises(LifecycleHold):
                candidate.audit(reader,scoped,replace(target,original_deadline_utc=(
                    generation['sealed_at']+timedelta(minutes=31)).isoformat()))
            self.assertEqual(len(raw.calls),calls)
            with patch.object(raw,'read_authenticated',return_value=b'corrupt'):
                with self.assertRaises(ArchiveIntegrityError) as caught:
                    candidate.audit(reader,scoped,target)
            self.assertEqual(caught.exception.retirement_accounting['failed_phase'],'raw_read_decode')
            self.assertEqual(repo.generation(a)['state'],'verified')
            # Reader snapshot itself denies data mutation at the SQL layer.
            from postgres.archive_codec import CycleBudget
            with CycleBudget(candidate.TwoMarketReadbackLimits()) as budget:
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    with candidate.local_snapshot(reader,budget) as db:
                        db.execute('UPDATE ops.outbox SET acknowledged_at=NULL WHERE generation_id=%s',(a,))

    def test_retirement_readback_reuses_session_with_fresh_snapshots_and_failure_discard(self):
        """Matched full readback worker, generated in-memory raw + real local PG.

        200ms setup delay models connection overhead, not a hosted speed claim.
        Both modes read identical sealed A bytes and a newer B envelope. Nothing
        writes/ACKs/consumes a permit during the timed readback.
        """
        import json
        import psycopg
        from psycopg.rows import dict_row
        from postgres.archive_codec import CycleBudget, ArchiveUnavailable
        from postgres.lifecycle import ArchiveWorker
        from postgres.pp_retirement_verify import RetirementTransport, TwoMarketReadbackLimits
        from postgres.pp_history_session import ReusablePPHistoryConnectionFactory
        from postgres.retirement_accounting import accounted, bind_budget
        from postgres_lifecycle_fixtures import MemoryRepository, generated_rows, ImmutableMemoryTransport

        def local():
            return psycopg.connect(DSN,row_factory=dict_row)
        with local() as db:
            identity=db.execute('SELECT current_database() db,current_user role').fetchone()
        a,b=str(uuid.uuid4()),str(uuid.uuid4())
        stamp=datetime(2026,11,18,tzinfo=timezone.utc)
        records=[]
        for index in range(1000):
            payload=dict(origin_id=self.origin,source='coinbase',symbol='BTC-USD',
                granularity=60,time=int(stamp.timestamp())+index*60,
                low='99.0000',high='101.0000',open='100.0000',close='100.1000',
                volume='1.00000000',first_seen=stamp.isoformat(),
                payload={'generated':True,'padding':'c'*500},content_hash=f'{index+1:064x}')
            if index == 999:
                payload=dict(origin_id=self.origin,source='coinbase',symbol='BTC-USD',
                    event_id='old-price',generation_id=a,source_time=stamp.isoformat(),
                    source_epoch=str(int(stamp.timestamp())),received_at=stamp.isoformat(),
                    available_at=stamp.isoformat(),price='100.1000',size=None,
                    payload={'generated':True,'padding':'p'*500},content_hash=f'{index+1:064x}')
            records.append(envelope(index+1,'core.current_prices' if index==999 else 'core.candles',payload,a))
        newer={**records[-1], 'id':1001,'generation_id':b,
            'content_hash':f'{1001:064x}', 'payload':{**records[-1]['payload'],
            'event_id':'new-price','generation_id':b,
            'source_time':(stamp+timedelta(seconds=1)).isoformat(),
            'source_epoch':str(int(stamp.timestamp())+1),
            'received_at':(stamp+timedelta(seconds=1)).isoformat(),
            'available_at':(stamp+timedelta(seconds=1)).isoformat(),
            'price':'100.2000','content_hash':f'{1001:064x}'}}
        def transport(factory,generation=a):
            return HistoryV2PostgresTransport(factory,origin_id=self.origin,generation_id=generation,
                expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True)
        writer=lambda **kwargs: local()
        transport(writer).put_structured(records[:500],timeout_seconds=20)
        with local() as db:
            db.execute('ANALYZE history_v2.candles')
            db.execute('ANALYZE history_v2.structured_receipts')
        transport(writer).put_structured(records[500:],timeout_seconds=20)
        transport(writer,b).put_structured([newer],timeout_seconds=20)
        with local() as db:
            db.execute('ANALYZE history_v2.candles')
            db.execute('ANALYZE history_v2.structured_receipts')
            db.execute('ANALYZE history_v2.structured_revision_payloads')
        rawrows=generated_rows(a,500,self.origin)
        repository=MemoryRepository(rawrows)
        repository.record['origin_id']=self.origin
        raw=ImmutableMemoryTransport()
        limits=TwoMarketReadbackLimits()
        archive=ArchiveWorker(repository,raw,limits)
        archive.archive_cycle(a)
        repository.outbox_rows=records
        results=[]
        for reuse in (False,True, True,False, False,True):
            connections=[]
            transactions=[]
            class Traced:
                def __init__(self,inner): self.inner=inner
                def __getattr__(self,name): return getattr(self.inner,name)
                def __enter__(self): self.inner.__enter__(); return self
                def __exit__(self,*args): return self.inner.__exit__(*args)
                @contextmanager
                def transaction(self):
                    with self.inner.transaction():
                        # Real unique snapshot/transaction evidence; no write.
                        yield
                        transactions.append(self.inner.execute('SELECT txid_current() n').fetchone()['n'])
            def opened(*args,**kwargs):
                time.sleep(.2)
                db=Traced(local());connections.append(db);return db
            remote=ReusablePPHistoryConnectionFactory() if reuse else opened
            scoped=RetirementTransport(raw,transport(remote),origin_id=self.origin,generation_id=a)
            worker=ArchiveWorker(repository,scoped,limits)
            @accounted
            def readback():
                with CycleBudget(limits) as budget:
                    bind_budget(budget)
                    return worker.fresh_retirement_readback(None,repository.record,repository.catalog,budget)
            try:
                with (patch.object(remote,'_validated_dsn',side_effect=lambda timeout:(b'generated',time.monotonic()+timeout)) if reuse else nullcontext(),
                      patch.object(remote,'_open',side_effect=opened) if reuse else nullcontext()):
                    started=time.monotonic();result=readback();elapsed=time.monotonic()-started
                    self.assertEqual(result['structured_count'],1000)
                    self.assertEqual(len(connections),1 if reuse else 2)
                    self.assertEqual(len(set(transactions)),2)
                    self.assertEqual(result['requests'],3)  # raw object + 2 structured pages
                    self.assertEqual(result['phase_accounting']['phases']['history_identity_checkpoint']['calls'],2)
                    results.append(dict(reuse=reuse,seconds=elapsed,connections=len(connections),
                        transactions=len(set(transactions)),requests=result['requests'],logical_bytes=result['bytes']))
                    if reuse:
                        # Physical disconnect is surfaced: no transparent retry,
                        # no proof continuation. Explicit next run rereads raw/A.
                        before=len(connections)
                        with local() as db:
                            db.execute('UPDATE history_v2.current_prices SET price=9 WHERE origin_id=%s',(self.origin,))
                        with self.assertRaises(ArchiveIntegrityError) as caught:
                            readback()
                        self.assertEqual(caught.exception.retirement_accounting['failed_phase'],'history_projections')
                        self.assertEqual(len(connections),before)
                        self.assertIsNone(remote._connection)
                        with local() as db:
                            db.execute('UPDATE history_v2.current_prices SET price=100.2000 WHERE origin_id=%s',(self.origin,))
                        readback()
                        original=scoped.structured._projection_rows
                        def disconnect(db, records):
                            db.inner.close()
                            return original(db,records)
                        before=len(connections)
                        with patch.object(scoped.structured,'_projection_rows',side_effect=disconnect):
                            with self.assertRaises(ArchiveUnavailable): readback()
                        self.assertEqual(len(connections),before)
                        self.assertIsNone(remote._connection)
                        with patch.object(scoped.structured,'_identity',side_effect=ArchiveIntegrityError('injected role')):
                            with self.assertRaises(ArchiveIntegrityError): readback()
                        self.assertIsNone(remote._connection)
                        before=len(raw.calls)
                        recovered=readback()
                        self.assertGreater(len(raw.calls),before)
                        self.assertEqual(recovered['structured_count'],1000)
                        self.assertEqual(repository.record['state'],'verified')
                        self.assertEqual(repository.retire_calls,0)
            finally:
                if reuse: remote.close()
        self.assertEqual(results[0]['requests'],results[1]['requests'])
        self.assertEqual(len({r['logical_bytes'] for r in results}),1)
        print('generated_retirement_worker_session_comparison '+json.dumps(results),flush=True)

    def test_b_price_update_preserves_a_revision_and_failed_append_rolls_back(self):
        import psycopg
        from psycopg.rows import dict_row
        from postgres.archive_codec import ArchiveUnavailable

        def connect(*, timeout_seconds=5):
            return psycopg.connect(DSN, row_factory=dict_row,
                                   connect_timeout=math.ceil(timeout_seconds))

        with connect() as connection:
            identity = connection.execute(
                'SELECT current_database() AS database, current_user AS role').fetchone()
        origin = self.origin

        def generation():
            return HistoryV2PostgresTransport(
                connect, origin_id=origin, generation_id=str(uuid.uuid4()),
                expected_database=identity['database'], expected_role=identity['role'],
                retain_revisions=True)

        def price(stream, index, value):
            at = datetime(2026, 11, 18, tzinfo=timezone.utc) + timedelta(seconds=index)
            event = dict(origin_id=origin, source='coinbase', symbol='BTC-USD',
                         event_id=f'tick-{index}', generation_id=stream.generation_id,
                         source_time=at.isoformat(), source_epoch=str(int(at.timestamp())),
                         received_at=at.isoformat(), available_at=at.isoformat(),
                         price=value, size=None, payload={'source':'generated'},
                         content_hash=f'{index:064x}')
            return envelope(index, 'core.current_prices', event, stream.generation_id)

        a, b = generation(), generation()
        first, second = price(a, 1, '100.2300'), price(b, 2, '100.2400')
        a.put_structured([first], timeout_seconds=5)
        with (patch.object(b, '_append_revisions', side_effect=RuntimeError('injected')),
              self.assertRaises(ArchiveUnavailable)):
            b.put_structured([second], timeout_seconds=5)
        with connect() as connection:
            current = connection.execute(
                'SELECT price::text AS price FROM history_v2.current_prices WHERE origin_id=%s',
                (origin,)).fetchone()
            count = connection.execute(
                'SELECT count(*) AS n FROM history_v2.structured_receipts WHERE origin_id=%s',
                (origin,)).fetchone()
        self.assertEqual((current['price'], count['n']), ('100.2300', 1))
        b.put_structured([second], timeout_seconds=5)
        self.assertEqual(b.read_structured_authenticated(
            [second], max_bytes=8192, timeout_seconds=5), [second])
        self.assertEqual(a.read_revisions([1], max_bytes=8192, timeout_seconds=5), [first])
        with self.assertRaises(ArchiveIntegrityError):
            b.read_revisions([1], max_bytes=8192, timeout_seconds=5)

        from postgres.archive_codec import ArchiveLimits, CycleBudget
        from postgres.pp_retirement_verify import RetirementTransport
        scoped = RetirementTransport(None, a, origin_id=origin, generation_id=a.generation_id)
        with CycleBudget(ArchiveLimits()) as budget:
            reserved = len(encoded([first]))
            timeout = budget.request(reserved)
            self.assertEqual(scoped.read_structured_authenticated(
                [first], max_bytes=8192, timeout_seconds=timeout), [first])
            self.assertEqual(budget.bytes, reserved + len(encoded(second)))
        with self.assertRaises(ArchiveLimit):
            a.read_retirement_revisions([first], max_bytes=reserved, timeout_seconds=5)
        # B's projection cannot authenticate itself. A's immutable envelope
        # survives, but the altered B price must hold retirement.
        with connect() as connection:
            connection.execute("UPDATE history_v2.current_prices SET price=9 WHERE origin_id=%s",
                               (origin,))
        with self.assertRaises(ArchiveIntegrityError):
            a.read_retirement_revisions([first], max_bytes=8192, timeout_seconds=5)
        with connect() as connection:
            connection.execute("UPDATE history_v2.current_prices SET price=100.2400 WHERE origin_id=%s",
                               (origin,))
            connection.execute("DELETE FROM history_v2.structured_revision_payloads WHERE origin_id=%s AND generation_id=%s",
                               (origin, b.generation_id))
        with self.assertRaises(ArchiveIntegrityError):
            a.read_retirement_revisions([first], max_bytes=8192, timeout_seconds=5)

    def test_parent_import_precedes_lower_id_dependent(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row,
            connect_timeout=max(1, math.ceil(timeout_seconds)),
            options='-c timezone=UTC')
        with factory() as connection:
            binding = connection.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        origin, generation = self.origin, str(uuid.uuid4())
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

    def test_25_row_remote_roundtrip_budget_preserves_fk_and_exact_readback(self):
        """Generated 100ms round trips model a remote pooler, not live proof."""
        import psycopg
        from psycopg.rows import dict_row

        origin, generation = self.origin, str(uuid.uuid4())
        plain = lambda: psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
                                        options='-c timezone=UTC')
        with plain() as connection:
            binding = connection.execute('SELECT current_database() AS database, '
                                         'current_user AS role').fetchone()
        used = []

        def factory(*, timeout_seconds):
            connection = DelayedConnection(plain())
            used.append(connection)
            return connection

        start = datetime(2026, 11, 18, tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        market = dict(origin_id=origin, market_id='market-25', source='polymarket-us',
            slug='market-25', duration=900, start_time=start.isoformat(),
            end_time=end.isoformat(), start_epoch=str(int(start.timestamp())),
            end_epoch=str(int(end.timestamp())), target='100.0000', final=None,
            result=None, status='open', index_symbol='BTC-USD', rules=None,
            first_seen=start.isoformat(), last_seen=start.isoformat(),
            payload={'source':'generated'}, content_hash='f' * 64)
        features = [dict(origin_id=origin, snapshot_id=f'snapshot-{index}',
            market_id='market-25', as_of=(start + timedelta(seconds=index)).isoformat(),
            version=1, values_json={'price':f'100.{index:04d}'}, quality_json={},
            evidence_json={'source_time':start.isoformat()},
            content_hash=f'{index:064x}') for index in range(1, 25)]
        # The lower outbox IDs refer to children; import must still insert the
        # market parent first while preserving the original outbox cursor.
        records = [envelope(index, 'core.feature_snapshots', feature, generation)
                   for index, feature in enumerate(features, 1)]
        records.append(envelope(25, 'core.markets', market, generation))
        transport = HistoryV2PostgresTransport(factory, origin_id=origin,
            generation_id=generation, expected_database=binding['database'],
            expected_role=binding['role'])
        started = time.monotonic()
        transport.put_structured(records, timeout_seconds=4)
        put_elapsed = time.monotonic() - started
        started = time.monotonic()
        self.assertEqual(transport.read_structured_authenticated(
            records, max_bytes=4 * 1024 * 1024, timeout_seconds=4), records)
        read_elapsed = time.monotonic() - started
        self.assertEqual(len(used), 2)
        print(f'generated_history_v2_roundtrips put_queries={used[0].queries} '
              f'put_roundtrips={used[0].roundtrips} put_seconds={put_elapsed:.3f} read_queries={used[1].queries} '
              f'read_roundtrips={used[1].roundtrips} read_seconds={read_elapsed:.3f}', flush=True)
        self.assertLessEqual(used[0].roundtrips, 16)
        self.assertLessEqual(used[1].roundtrips, 8)
        self.assertLessEqual(used[0].queries, 90)
        self.assertLessEqual(used[1].queries, 35)
        self.assertLess(put_elapsed, 4)
        self.assertLess(read_elapsed, 4)
        with plain() as connection:
            receipt_count = connection.execute('SELECT count(*) AS n FROM '
                'history_v2.structured_receipts WHERE origin_id=%s AND generation_id=%s',
                (origin, generation)).fetchone()['n']
            target = connection.execute('SELECT target::text AS value FROM '
                'history_v2.markets WHERE origin_id=%s AND market_id=%s',
                (origin, 'market-25')).fetchone()['value']
        self.assertEqual((receipt_count, target), (25, '100.0000'))

    def test_real_page_shape_at_100ms_with_exact_revision_retention(self):
        import psycopg
        from psycopg.rows import dict_row
        origin, generation = self.origin, str(uuid.uuid4())
        plain = lambda: psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
                                        options='-c timezone=UTC')
        with plain() as db:
            identity = db.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        used = []
        def factory(*, timeout_seconds):
            time.sleep(0.2)  # generated connection/TLS overhead inside the 4s request
            connection = DelayedConnection(plain())
            used.append(connection)
            return connection
        transport = HistoryV2PostgresTransport(factory, origin_id=origin,
            generation_id=generation, expected_database=identity['database'],
            expected_role=identity['role'], retain_revisions=True)
        start = datetime(2026, 11, 18, tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        records = []
        for index in range(12):
            moment = start + timedelta(seconds=index)
            candle = dict(origin_id=origin, source='coinbase', symbol='BTC-USD',
                granularity=60, time=int(start.timestamp()) + index * 60,
                low='99.0000', high='101.0000', open='100.0000', close='100.1000',
                volume='1.00000000', first_seen=moment.isoformat(),
                payload={'generated':True, 'padding':'c' * 500}, content_hash=f'{index+1:064x}')
            price = dict(origin_id=origin, source='coinbase', symbol='BTC-USD',
                event_id=f'trade-{index}', generation_id=generation,
                source_time=moment.isoformat(), source_epoch=str(int(moment.timestamp())),
                received_at=moment.isoformat(), available_at=moment.isoformat(),
                price=f'100.{index:04d}', size='1E-8',
                payload={'generated':True, 'padding':'p' * 700}, content_hash=f'{index+100:064x}')
            records.extend([envelope(len(records)+1,'core.candles',candle,generation),
                            envelope(len(records)+2,'core.current_prices',price,generation)])
        market = dict(origin_id=origin, market_id='page-market', source='polymarket-us',
            slug='page-market', duration=900, start_time=start.isoformat(), end_time=end.isoformat(),
            start_epoch=str(int(start.timestamp())), end_epoch=str(int(end.timestamp())),
            target='100.0000', final=None, result=None, status='open', index_symbol='BTC-USD',
            rules=None, first_seen=start.isoformat(), last_seen=start.isoformat(),
            payload={'generated':True, 'padding':'m' * 2000}, content_hash='f' * 64)
        records.append(envelope(25,'core.markets',market,generation))
        started = time.monotonic()
        transport.put_structured(records,timeout_seconds=4)
        elapsed = time.monotonic()-started
        started_read = time.monotonic()
        self.assertEqual(transport.read_structured_authenticated(
            records,max_bytes=4*1024**2,timeout_seconds=4),records)
        read_elapsed = time.monotonic()-started_read
        self.assertLess(read_elapsed,4)
        self.assertEqual(transport.read_revisions(list(range(1,26)),
            max_bytes=4*1024**2,timeout_seconds=4),records)
        self.assertLess(elapsed,4)
        self.assertLessEqual(used[0].roundtrips,16)
        print(f'generated_actual_shape_25 put_seconds={elapsed:.3f} '
              f'put_roundtrips={used[0].roundtrips} read_seconds={read_elapsed:.3f} '
              f'read_roundtrips={used[1].roundtrips} remote_rows_per_second={25/(elapsed+read_elapsed):.2f} '
              f'last_stage=authenticated_readback retained_envelopes=25 local_ack=unmeasured',flush=True)
        # Replay is idempotent despite twelve revisions sharing one price key.
        transport.put_structured(records,timeout_seconds=4)
        with plain() as db:
            row=db.execute('SELECT price::text AS price FROM history_v2.current_prices '
                'WHERE origin_id=%s',(origin,)).fetchone()
            count=db.execute('SELECT count(*) AS n FROM history_v2.structured_receipts '
                'WHERE origin_id=%s AND generation_id=%s',(origin,generation)).fetchone()['n']
        self.assertEqual((row['price'],count),('100.0011',25))

    def test_receipt_batch_failure_rolls_back_projection_and_checkpoint(self):
        import psycopg
        from psycopg.rows import dict_row
        from postgres.archive_codec import ArchiveUnavailable

        factory = lambda timeout_seconds=5: psycopg.connect(
            DSN, row_factory=dict_row, connect_timeout=5)
        with factory() as connection:
            binding = connection.execute('SELECT current_database() AS database, '
                                         'current_user AS role').fetchone()
        origin, generation = self.origin, str(uuid.uuid4())
        start = datetime(2026, 11, 18, tzinfo=timezone.utc)
        market = dict(origin_id=origin, market_id='rollback-market',
            source='polymarket-us', slug='rollback-market', duration=900,
            start_time=start.isoformat(),
            end_time=(start + timedelta(minutes=15)).isoformat(),
            start_epoch=str(int(start.timestamp())),
            end_epoch=str(int((start + timedelta(minutes=15)).timestamp())),
            target='100.0000', final=None, result=None, status='open',
            index_symbol='BTC-USD', rules=None, first_seen=start.isoformat(),
            last_seen=start.isoformat(), payload={'source':'generated'},
            content_hash='a' * 64)

        class FailAfterReceiptBatch(HistoryV2PostgresTransport):
            @staticmethod
            def _insert_receipts(connection, rows):
                HistoryV2PostgresTransport._insert_receipts(connection, rows)
                raise RuntimeError('generated failure after batch insert')

        transport = FailAfterReceiptBatch(factory, origin_id=origin,
            generation_id=generation, expected_database=binding['database'],
            expected_role=binding['role'])
        with self.assertRaises(ArchiveUnavailable):
            transport.put_structured([envelope(1, 'core.markets', market, generation)],
                                     timeout_seconds=4)
        with factory() as connection:
            counts = connection.execute('''SELECT
                (SELECT count(*) FROM history_v2.markets WHERE origin_id=%s) AS markets,
                (SELECT count(*) FROM history_v2.structured_receipts WHERE origin_id=%s)
                    AS receipts,
                (SELECT count(*) FROM history_v2.generation_checkpoints WHERE origin_id=%s)
                    AS checkpoints''', (origin, origin, origin)).fetchone()
        self.assertEqual(counts, {'markets':0, 'receipts':0, 'checkpoints':0})


if __name__ == '__main__':
    unittest.main()
