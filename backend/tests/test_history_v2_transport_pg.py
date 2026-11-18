"""Disposable isolated PostgreSQL proof; never connects to Supabase."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, encoded, sha256
from postgres.history_v2_transport import HistoryV2PostgresTransport


DSN = os.environ.get('TRADEBOT_TEST_HISTORY_V2_DSN')


def envelope(outbox_id, table, payload, generation_id):
    from postgres.history_v2_envelope import TABLE_KEYS
    return {'id': outbox_id, 'origin_id': payload['origin_id'],
            'generation_id': generation_id, 'entity_type': table,
            'entity_id': encoded([payload[key] for key in TABLE_KEYS[table]]).decode(),
            'content_hash': payload['content_hash'], 'payload': payload}


@unittest.skipUnless(DSN, 'isolated generated history_v2 DSN not supplied')
class HistoryV2TransportPostgresTests(unittest.TestCase):
    def test_atomic_revisions_receipts_retry_and_conflict(self):
        import psycopg
        from psycopg.rows import dict_row

        factory = lambda: psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
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
        with factory() as connection:
            connection.execute('''UPDATE history_v2.current_prices SET price='100.2400'
                WHERE origin_id=%s''', (origin,))
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

        factory = lambda: psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
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
