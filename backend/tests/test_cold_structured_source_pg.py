"""Real PG17 source qualification in an explicitly disposable local database."""
from pathlib import Path
import os
import sys
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from postgres.cold_structured_source import ReadOnlyStructuredSource, READER_ROLE
from postgres.cold_structured_history import ORIGIN, MAX_BYTES
from test_cold_structured_history import envelope, GENERATION

DSN = os.getenv('TRADEBOT_TEST_COLD_HISTORY_ADMIN_DSN')


@unittest.skipUnless(DSN, 'disposable local cold-history PG17 DSN not supplied')
class NativeColdSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        from psycopg.rows import dict_row
        values = conninfo_to_dict(DSN)
        if (values.get('dbname') != 'tradebot_cold_history_test'
                or not values.get('host', '').startswith('/tmp/tradebot-cold-')):
            raise ValueError('only disposable local cold-history fixture is allowed')
        cls.admin = staticmethod(lambda: psycopg.connect(DSN, row_factory=dict_row))
        cls.reader = staticmethod(lambda **_: psycopg.connect(
            make_conninfo(DSN, user=READER_ROLE), row_factory=dict_row))
        cls.record = envelope(1)
        with cls.admin() as db:
            db.execute('CREATE ROLE tradebot_pp_history_reader LOGIN')
            db.execute('CREATE SCHEMA history_v2')
            db.execute('''CREATE TABLE history_v2.structured_receipts (
                origin_id text,generation_id text,outbox_id bigint,
                entity_type text,entity_id text,content_hash text,payload_hash text,
                envelope_hash text, PRIMARY KEY(origin_id,generation_id,outbox_id))''')
            db.execute('''CREATE TABLE history_v2.structured_revision_payloads (
                origin_id text,generation_id text,outbox_id bigint,envelope bytea,
                PRIMARY KEY(origin_id,generation_id,outbox_id),
                FOREIGN KEY(origin_id,generation_id,outbox_id) REFERENCES
                    history_v2.structured_receipts(origin_id,generation_id,outbox_id))''')
            for table in ('structured_receipts', 'structured_revision_payloads'):
                db.execute(f'ALTER TABLE history_v2.{table} ENABLE ROW LEVEL SECURITY')
                db.execute(f'''CREATE POLICY reader_scope ON history_v2.{table}
                    FOR SELECT TO tradebot_pp_history_reader USING(origin_id='pp-live-pp')''')
                db.execute(f'GRANT SELECT ON history_v2.{table} TO tradebot_pp_history_reader')
            db.execute('GRANT USAGE ON SCHEMA history_v2 TO tradebot_pp_history_reader')
            r = cls.record
            for origin in (ORIGIN, 'prod-live'):
                db.execute('INSERT INTO history_v2.structured_receipts VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (origin, GENERATION, 1, r['entity_type'], r['entity_id'], r['content_hash'],
                     sha256(encoded(r['payload'])), sha256(encoded(r))))
                db.execute('INSERT INTO history_v2.structured_revision_payloads VALUES (%s,%s,1,%s)',
                           (origin, GENERATION, encoded(r)))

    def source(self, factory=None):
        return ReadOnlyStructuredSource(factory or self.reader, origin_id=ORIGIN,
            generation_id=GENERATION, expected_database='tradebot_cold_history_test')

    def test_native_dedicated_reader_exact_bytes_and_origin_policy(self):
        self.assertEqual(self.source().read_revisions([1], max_bytes=MAX_BYTES,
                                                      timeout_seconds=4), [self.record])
        with self.reader() as db:
            rows = db.execute('SELECT origin_id FROM history_v2.structured_receipts').fetchall()
        self.assertEqual(rows, [dict(origin_id=ORIGIN)])

    def test_native_effective_mutation_grant_fails_closed(self):
        for privilege in ('INSERT', 'UPDATE(payload_hash)', 'REFERENCES(outbox_id)', 'MAINTAIN'):
            with self.admin() as db:
                db.execute(f'GRANT {privilege} ON history_v2.structured_receipts TO tradebot_pp_history_reader')
            try:
                with self.subTest(privilege=privilege), self.assertRaises(ArchiveIntegrityError):
                    self.source().read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)
            finally:
                with self.admin() as db:
                    db.execute(f'REVOKE {privilege} ON history_v2.structured_receipts FROM tradebot_pp_history_reader')

    def test_native_privileged_login_and_corrupt_receipt_fail_closed(self):
        with self.assertRaises(ArchiveIntegrityError):
            self.source(lambda **_: self.admin()).read_revisions([1], max_bytes=MAX_BYTES,
                                                                timeout_seconds=4)
        with self.admin() as db:
            db.execute("UPDATE history_v2.structured_receipts SET payload_hash=%s WHERE origin_id=%s",
                       ('b'*64, ORIGIN))
        try:
            with self.assertRaises(ArchiveIntegrityError):
                self.source().read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)
        finally:
            with self.admin() as db:
                db.execute('UPDATE history_v2.structured_receipts SET payload_hash=%s WHERE origin_id=%s',
                           (sha256(encoded(self.record['payload'])), ORIGIN))

    def test_native_read_only_transaction_and_whole_transaction_deadline(self):
        source = self.source()
        original = source._decoder._read_revisions
        def assert_read_only(connection, ids, max_bytes):
            self.assertEqual(connection.execute('SHOW transaction_read_only').fetchone(),
                             dict(transaction_read_only='on'))
            return original(connection, ids, max_bytes)
        source._decoder._read_revisions = assert_read_only
        self.assertEqual(source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4),
                         [self.record])
        source._decoder._read_revisions = lambda db, ids, size: db.execute('SELECT pg_sleep(1)')
        started = time.monotonic()
        with self.assertRaises(ArchiveUnavailable):
            source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=.05)
        self.assertLess(time.monotonic()-started, .75)

    def test_native_oversized_receipt_text_is_suppressed_before_client_fetch(self):
        selected = ('entity_type', 'entity_id', 'content_hash', 'payload_hash', 'envelope_hash')
        original = dict(entity_type=self.record['entity_type'], entity_id=self.record['entity_id'],
            content_hash=self.record['content_hash'], payload_hash=sha256(encoded(self.record['payload'])),
            envelope_hash=sha256(encoded(self.record)))
        fetched = []

        class CapturedConnection:
            def __init__(self, inner):
                object.__setattr__(self, 'inner', inner)
            def __getattr__(self, name):
                return getattr(self.inner, name)
            def __setattr__(self, name, value):
                setattr(self.inner, name, value)
            def __enter__(self):
                self.inner.__enter__()
                return self
            def __exit__(self, *args):
                return self.inner.__exit__(*args)
            def execute(self, statement, values=None):
                cursor = self.inner.execute(statement, values)
                if 'WITH sizes' in statement:
                    rows = cursor.fetchall()
                    fetched.extend(rows)
                    return SimpleNamespace(fetchall=lambda: rows)
                return cursor

        for column in selected:
            with self.admin() as db:
                db.execute(f'UPDATE history_v2.structured_receipts SET {column}=%s WHERE origin_id=%s',
                           ('x' * 1024**2, ORIGIN))
            try:
                fetched.clear()
                source = self.source(lambda **_: CapturedConnection(self.reader()))
                with self.subTest(column=column), self.assertRaises(ArchiveLimit):
                    source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)
                self.assertEqual(len(fetched), 1)
                self.assertGreaterEqual(fetched[0]['metadata_total'], 1024**2)
                self.assertLess(fetched[0]['total'], MAX_BYTES)
                self.assertTrue(all(fetched[0][field] is None for field in (*selected, 'envelope')))
                self.assertFalse(any(isinstance(value, (str, bytes, memoryview))
                                     for value in fetched[0].values()))
            finally:
                with self.admin() as db:
                    db.execute(f'UPDATE history_v2.structured_receipts SET {column}=%s WHERE origin_id=%s',
                               (original[column], ORIGIN))

    def test_native_receipt_metadata_budget_is_aggregate_across_requested_rows(self):
        second = envelope(2)
        # Each row's receipt text fits individually; their combined metadata
        # exceeds the independent aggregate budget while both envelopes fit.
        metadata = 'x' * (MAX_BYTES // 2 + 1)
        with self.admin() as db:
            db.execute('UPDATE history_v2.structured_receipts SET entity_id=%s WHERE origin_id=%s',
                       (metadata, ORIGIN))
            db.execute('INSERT INTO history_v2.structured_receipts VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (ORIGIN, GENERATION, 2, second['entity_type'], metadata, second['content_hash'],
                 sha256(encoded(second['payload'])), sha256(encoded(second))))
            db.execute('INSERT INTO history_v2.structured_revision_payloads VALUES (%s,%s,2,%s)',
                       (ORIGIN, GENERATION, encoded(second)))
        fetched = []
        try:
            with self.reader() as db:
                class QueryCapture:
                    def execute(self, statement, values):
                        rows = db.execute(statement, values).fetchall()
                        fetched.extend(rows)
                        return SimpleNamespace(fetchall=lambda: rows)
                with self.assertRaises(ArchiveLimit):
                    self.source()._decoder._read_revisions(QueryCapture(), [1, 2], MAX_BYTES)
            self.assertEqual(len(fetched), 2)
            for row in fetched:
                self.assertGreater(row['metadata_total'], MAX_BYTES)
                self.assertLess(row['total'], MAX_BYTES)
                self.assertTrue(all(row[field] is None for field in ('envelope', 'entity_type',
                    'entity_id', 'content_hash', 'payload_hash', 'envelope_hash')))
        finally:
            with self.admin() as db:
                db.execute('DELETE FROM history_v2.structured_revision_payloads WHERE origin_id=%s AND outbox_id=2',
                           (ORIGIN,))
                db.execute('DELETE FROM history_v2.structured_receipts WHERE origin_id=%s AND outbox_id=2',
                           (ORIGIN,))
                db.execute('UPDATE history_v2.structured_receipts SET entity_id=%s WHERE origin_id=%s',
                           (self.record['entity_id'], ORIGIN))


if __name__ == '__main__':
    unittest.main()
