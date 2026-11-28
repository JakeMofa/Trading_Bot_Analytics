"""Check the production fingerprint stream against PostgreSQL's original digest."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Budget, DeploymentHold
from metadata_inventory import metadata_digest


ADMIN_DSN = os.getenv('TRADEBOT_TEST_HISTORY_V2_DSN')
IDENTITY = 'generation_id,origin_id,source,event_id,content_hash'
FIELDS = 'generation_id text,origin_id text,source text,event_id text,content_hash text'
FINGERPRINT = f"encode(sha256(convert_to(jsonb_build_array({IDENTITY})::text,'UTF8')),'hex')"
# Preserve the text comparator, ASCII hex encoding at both levels, and the
# placement of duplicate rows in the original *sorted* 1024-row groups.
ORIGINAL_SQL = f"""
    SELECT json_build_object('count',coalesce(sum(n),0),'digest',encode(sha256(
        convert_to(coalesce(string_agg(page_hash,'' ORDER BY page),''),'UTF8')),'hex'))
    FROM (
        SELECT page,count(*) n,encode(sha256(convert_to(
            string_agg(fingerprint,'' ORDER BY fingerprint),'UTF8')),'hex') page_hash
        FROM (
            SELECT fingerprint,(row_number() OVER (ORDER BY fingerprint)-1)/1024 AS page
            FROM (SELECT {FINGERPRINT} AS fingerprint FROM {{relation}}) hashes
        ) numbered GROUP BY page
    ) pages"""
HASH_LITERAL = re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')


def fixture_exchange(db, relation, comparisons, on_fetch=None):
    def exchange(statement):
        if on_fetch and statement.startswith('FETCH '):
            on_fetch()
        if 'WITH ORDINALITY' in statement.upper():
            comparisons.append(HASH_LITERAL.findall(statement))
        rows = db.execute(statement.replace('raw.events', relation))
        return [row[0] for row in rows] if rows.description else []
    return exchange


def fill_fixture(db, relation, count, distinct):
    db.execute(f"""INSERT INTO {relation}
        SELECT 'g','o','s',CASE WHEN n <= %s THEN n::text ELSE 'repeated' END,'digest'
        FROM generate_series(1,%s::integer) AS n""", (distinct, count))


@unittest.skipUnless(ADMIN_DSN, 'isolated PostgreSQL qualification database required')
class MetadataOrderTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.db = self.enterContext(psycopg.connect(ADMIN_DSN, autocommit=True))
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db.execute(f'CREATE TEMP TABLE fingerprint_rows ({FIELDS})')
        self.relation = 'pg_temp.fingerprint_rows'

    def digest(self, db=None, relation=None, on_fetch=None):
        self.comparisons = []
        exchange = fixture_exchange(db or self.db, relation or self.relation, self.comparisons, on_fetch)
        return metadata_digest(exchange, 'raw.events', IDENTITY, Budget(120), self.directory)

    def test_original_digest_at_each_page_boundary_with_repeated_rows(self):
        for count in (0, 1, 1023, 1024, 1025, 2051):
            with self.subTest(count=count):
                self.db.execute('TRUNCATE fingerprint_rows')
                fill_fixture(self.db, self.relation, count, 0)
                expected = self.db.execute(ORIGINAL_SQL.format(relation=self.relation)).fetchone()[0]
                self.assertEqual(self.digest(), expected)
                self.assertFalse(any(len(group) > 1 for group in self.comparisons))
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_native_sorted_cursor_matches_distinct_and_duplicate_page_carry(self):
        fill_fixture(self.db, self.relation, 2173, 113)
        expected = self.db.execute(ORIGINAL_SQL.format(relation=self.relation)).fetchone()[0]
        hashes = [r[0] for r in self.db.execute(
            f'SELECT DISTINCT {FINGERPRINT} AS fingerprint FROM {self.relation} ORDER BY fingerprint')]
        self.assertEqual(len(hashes), 114)
        self.assertEqual(self.digest(), expected)
        self.assertEqual(self.comparisons, [], 'native cursor needs no adjacent-pair round trips')
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_interleaved_duplicates_across_many_fetches(self):
        self.db.execute(f"""INSERT INTO {self.relation}
            SELECT 'g','o','s',(n%311)::text,'digest'
            FROM generate_series(1,16453) AS n""")
        expected = self.db.execute(ORIGINAL_SQL.format(relation=self.relation)).fetchone()[0]
        self.assertEqual(self.digest(), expected)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cursor_sees_one_snapshot_and_next_scan_sees_changed_identity(self):
        import psycopg
        relation = 'public.fingerprint_test_' + uuid.uuid4().hex
        writer = self.enterContext(psycopg.connect(ADMIN_DSN, autocommit=True))
        writer.execute(f'CREATE TABLE {relation} ({FIELDS})')
        self.addCleanup(writer.execute, 'DROP TABLE ' + relation)
        fill_fixture(writer, relation, 1081, 83)
        expected = writer.execute(ORIGINAL_SQL.format(relation=relation)).fetchone()[0]
        changed = False

        def change_one_row():
            nonlocal changed
            if not changed:
                writer.execute(f"UPDATE {relation} SET content_hash='changed' WHERE event_id='77'")
                changed = True

        self.assertEqual(self.digest(relation=relation, on_fetch=change_one_row), expected)
        self.assertTrue(changed)
        after = writer.execute(ORIGINAL_SQL.format(relation=relation)).fetchone()[0]
        self.assertNotEqual(after['digest'], expected['digest'])
        self.assertEqual(self.digest(relation=relation), after)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_actual_icu_numeric_database_uses_native_order_without_byte_assumption(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        from psycopg.sql import Identifier, SQL

        name = 'fingerprint_icu_' + uuid.uuid4().hex
        db_name = Identifier(name)
        self.db.execute(SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8' "
                            "LOCALE_PROVIDER icu ICU_LOCALE 'en-u-kn-true'").format(db_name))
        self.addCleanup(self.db.execute, SQL('DROP DATABASE {}').format(db_name))
        with psycopg.connect(make_conninfo(ADMIN_DSN, dbname=name), autocommit=True) as numeric:
            numeric.execute(f'CREATE TEMP TABLE fingerprint_rows ({FIELDS})')
            fill_fixture(numeric, self.relation, 211, 211)
            rows = [r[0] for r in numeric.execute(
                f'SELECT {FINGERPRINT} AS fingerprint FROM {self.relation} ORDER BY fingerprint')]
            self.assertNotEqual(rows, sorted(rows), 'fixture must exercise real numeric collation')
            expected = numeric.execute(ORIGINAL_SQL.format(relation=self.relation)).fetchone()[0]
            self.assertEqual(self.digest(db=numeric), expected)
            self.assertEqual(self.comparisons, [])
            self.assertEqual(list(self.directory.iterdir()), [])
