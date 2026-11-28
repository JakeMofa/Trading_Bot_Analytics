"""Execute the release SQL against a disposable PostgreSQL temp relation."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
from linux_actions import LinuxActions


@unittest.skipUnless(all(os.getenv(key) for key in ('TRADEBOT_TEST_HISTORY_V2_DSN',
    'TRADEBOT_TEST_READER_DSN')), 'isolated PostgreSQL admin and reader required')
class LifetimeInventoryTests(unittest.TestCase):
    def test_synced_history_pending_limit_and_recovery_digest(self):
        import psycopg
        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']) as db:
            db.execute("""CREATE TEMP TABLE inventory_fixture AS SELECT
                       n::bigint AS id, 'pp-live-pp'::text AS origin_id,
                       n::text AS payload, n::text AS event_id, 'feed' AS source, 'gen' AS generation_id, 'hash' AS content_hash, CASE WHEN n<=10100 THEN now() END AS acknowledged_at
                       FROM generate_series(1,10103) n""")
            class FixtureActions(LinuxActions):
                def _sql(self, budget, query):
                    value = db.execute(query.replace('ops.outbox', 'pg_temp.inventory_fixture').replace('raw.events','pg_temp.inventory_fixture')).fetchone()[0]
                    if isinstance(value, bool):
                        return 't' if value else 'f'
                    return json.dumps(value)
                def _reader_sql(self, budget, query):
                    # The outbox fixture uses the admin session's temp table;
                    # generated-storage preservation uses its real reader ACL.
                    with psycopg.connect(os.environ['TRADEBOT_TEST_READER_DSN'],connect_timeout=5,
                                         options='-c default_transaction_read_only=on') as reader:
                        identity=reader.execute("SELECT current_user,current_setting('transaction_read_only')").fetchone()
                        if identity!=('tradebot_reader','on'):
                            raise AssertionError('inventory fixture reader identity/read-only mismatch')
                        value=reader.execute(query).fetchone()[0]
                    return ('t' if value else 'f') if isinstance(value,bool) else json.dumps(value)
            actions = FixtureActions()
            actions._outbox_release_preflight(None)
            initial_inventory = actions._inventory(None)
            self.assertEqual(initial_inventory['raw.events']['count'], 10103)
            db.execute("UPDATE inventory_fixture SET event_id='altered' WHERE id=10102")
            self.assertNotEqual(actions._inventory(None)['raw.events'], initial_inventory['raw.events'])
            initial = actions._ack_state(None)
            self.assertEqual(initial['pp-live-pp']['count'], 10103)
            self.assertEqual(initial['pp-live-pp']['pending'], 3)
            db.execute("UPDATE inventory_fixture SET payload='changed' WHERE id=10001")
            self.assertNotEqual(initial, actions._ack_state(None))
            db.execute("UPDATE inventory_fixture SET payload=id::text WHERE id=10001")
            self.assertEqual(initial, actions._ack_state(None))
            db.execute("UPDATE inventory_fixture SET acknowledged_at=NULL WHERE id>100")
            with self.assertRaises(DeploymentHold):
                actions._outbox_release_preflight(None)
            with self.assertRaises(DeploymentHold):
                actions._ack_state(None)


# Preserve the deployed digest definition independently of its execution plan.
ORIGINAL_DIGEST = """SELECT json_build_object('count',sum(n),'pending',sum(pending),'digest',
        encode(sha256(convert_to(string_agg(page_hash,'' ORDER BY page),'UTF8')),'hex'))
    FROM (SELECT id / 1024 AS page, count(*) AS n,
        count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending,
        encode(sha256(convert_to(string_agg(
            encode(sha256(convert_to(to_jsonb(o)::text,'UTF8')),'hex'),
            '' ORDER BY id),'UTF8')),'hex') AS page_hash
        FROM inventory_fixture o WHERE origin_id=%s GROUP BY id / 1024) pages"""


class OutboxFixture(LinuxActions):
    def __init__(self, connection, relation='inventory_fixture'):
        super().__init__()
        self.db = connection
        self.relation = relation
        self.queries = []

    def _sql(self, budget, query):
        query = query.replace('ops.outbox', self.relation)
        self.queries.append(query)
        return json.dumps(self.db.execute(query).fetchone()[0])


@unittest.skipUnless(os.getenv('TRADEBOT_TEST_HISTORY_V2_DSN'), 'isolated PostgreSQL admin required')
class BoundedOutboxTests(unittest.TestCase):
    def test_sparse_extreme_ids_and_origins_match_old_digest(self):
        import psycopg
        from linux_actions import OUTBOX_ORIGINS
        origins = sorted(OUTBOX_ORIGINS)[:7]
        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']) as db:
            db.execute("""CREATE TEMP TABLE inventory_fixture(
                id bigint PRIMARY KEY, origin_id text, payload jsonb, acknowledged_at timestamptz)""")
            self.assertEqual(OutboxFixture(db)._ack_state(None), {})
            ids = [-2**63, -1024, -7, 1, 1023, 1024, 8001, 2**63-1]
            with db.cursor() as cur:
                cur.executemany("INSERT INTO inventory_fixture VALUES (%s,%s,'{}',now())",
                                [(key, origins[0]) for key in ids] +
                                [(3000+i, origin) for i, origin in enumerate(origins[1:])])
            db.execute("UPDATE inventory_fixture SET acknowledged_at=NULL WHERE id=1023")
            actions = OutboxFixture(db)
            before = actions._ack_state(None)
            expected = {origin: db.execute(ORIGINAL_DIGEST, (origin,)).fetchone()[0] for origin in origins}
            self.assertEqual(before, expected)
            self.assertEqual(before[origins[0]]['pending'], 1)
            db.execute("UPDATE inventory_fixture SET payload='{\"changed\":true}' WHERE id=1023")
            after = actions._ack_state(None)
            self.assertNotEqual(before[origins[0]]['digest'], after[origins[0]]['digest'])
            self.assertEqual(after[origins[0]], db.execute(ORIGINAL_DIGEST, (origins[0],)).fetchone()[0])
            db.execute("UPDATE inventory_fixture SET acknowledged_at=timestamptz '2026-11-20Z' WHERE id=1023")
            acknowledged = actions._ack_state(None)[origins[0]]
            self.assertEqual(acknowledged['pending'], 0)
            self.assertNotEqual(acknowledged['digest'], after[origins[0]]['digest'])
            self.assertEqual(acknowledged, db.execute(ORIGINAL_DIGEST, (origins[0],)).fetchone()[0])
            db.execute("INSERT INTO inventory_fixture VALUES(42,'zzz-unapproved','{}',NULL)")
            with self.assertRaisesRegex(DeploymentHold, 'unexpected_outbox_origin'):
                actions._ack_state(None)

    def test_large_full_envelopes_under_temp_limit(self):
        import hashlib
        import itertools
        import psycopg
        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']) as db:
            db.execute("SET LOCAL work_mem='2MB'")
            db.execute("SET LOCAL temp_file_limit='64MB'")
            db.execute("SET LOCAL statement_timeout='19s'")
            db.execute("SET LOCAL max_parallel_workers_per_gather=0")
            db.execute("""CREATE TEMP TABLE inventory_fixture(
                id bigint PRIMARY KEY, origin_id text, payload jsonb, acknowledged_at timestamptz)""")
            # Inline envelopes deliberately make a wide whole-origin sort spill.
            db.execute("""INSERT INTO inventory_fixture
                SELECT n,'pp-live-pp',jsonb_build_object('body',repeat(md5(n::text),36)),
                       CASE WHEN n%100<>0 THEN timestamptz '2026-11-28 00:00:00Z' END
                FROM generate_series(1,98058) n""")
            db.execute('ANALYZE inventory_fixture')
            with self.assertRaises(psycopg.errors.ConfigurationLimitExceeded), db.transaction():
                db.execute(ORIGINAL_DIGEST, ('pp-live-pp',)).fetchone()
            actions = OutboxFixture(db)
            proof = actions._ack_state(None)['pp-live-pp']
            # A PK-ordered cursor acts as an independent, bounded-memory oracle.
            outer = hashlib.sha256()
            rows = pending = 0
            with db.cursor(name='oracle') as cur:
                cur.execute("""SELECT id/1024, acknowledged_at IS NULL,
                    encode(sha256(convert_to(to_jsonb(o)::text,'UTF8')),'hex')
                    FROM inventory_fixture o WHERE origin_id='pp-live-pp' ORDER BY id""")
                for _, page in itertools.groupby(cur, key=lambda row: row[0]):
                    inner = hashlib.sha256()
                    for _, is_pending, row_hash in page:
                        rows += 1
                        pending += is_pending
                        inner.update(row_hash.encode('ascii'))
                    outer.update(inner.hexdigest().encode('ascii'))
            self.assertEqual(proof, dict(count=rows, pending=pending, digest=outer.hexdigest()))
            self.assertEqual(rows, 98058)
            plan = db.execute('EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) '+actions.queries[-1]).fetchone()[0][0]
            nodes = []
            def collect(node):
                nodes.append(node)
                for child in node.get('Plans', []):
                    collect(child)
            collect(plan['Plan'])
            self.assertTrue(any('Index Cond' in n and 'id >=' in n['Index Cond'] and
                                'id <=' in n['Index Cond'] and n['Actual Loops'] > 90 for n in nodes))
            self.assertFalse(any(n['Node Type']=='Seq Scan' and n['Actual Loops']>1 and
                                 n.get('Relation Name')=='inventory_fixture' for n in nodes))

    def test_one_statement_snapshot_across_id_ranges(self):
        import concurrent.futures
        import time
        import uuid
        import psycopg
        dsn = os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']
        schema = 'outbox_fixture_'+uuid.uuid4().hex
        key = uuid.uuid4().int % (2**63)
        with psycopg.connect(dsn, autocommit=True) as writer, psycopg.connect(dsn, autocommit=True) as reader:
            writer.execute(f'CREATE SCHEMA {schema}')
            try:
                writer.execute(f"""CREATE TABLE {schema}.entries(
                    id bigint PRIMARY KEY, origin_id text, payload text, acknowledged_at timestamptz)""")
                writer.execute(f"""INSERT INTO {schema}.entries VALUES
                    (1,'pp-live-pp','one',NULL),(4096,'pp-live-pp','two',NULL)""")
                writer.execute(f"""CREATE FUNCTION {schema}.gate(p text) RETURNS text LANGUAGE plpgsql AS
                    'BEGIN PERFORM pg_advisory_xact_lock({key}); RETURN p; END'""")
                writer.execute(f"""CREATE VIEW {schema}.observed AS SELECT id,origin_id,
                    CASE WHEN id=1 THEN {schema}.gate(payload) ELSE payload END AS payload,
                    acknowledged_at FROM {schema}.entries""")
                expected = OutboxFixture(writer,schema+'.entries')._ack_state(None)
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    writer.execute("SELECT pg_advisory_lock(%s)",(key,))
                    try:
                        class SelectedOrigin(OutboxFixture):
                            # The production origin catalog is a separate statement.
                            # Block in the digest statement itself.
                            def _approved_outbox_origins(self, budget):
                                return ['pp-live-pp']
                        actions = SelectedOrigin(reader, schema+'.observed')
                        future = pool.submit(actions._ack_state,None)
                        deadline = time.monotonic()+5
                        while not writer.execute("""SELECT EXISTS(SELECT 1 FROM pg_locks
                            WHERE locktype='advisory' AND pid=%s AND NOT granted)""",
                            (reader.info.backend_pid,)).fetchone()[0]:
                            if time.monotonic()>=deadline:
                                self.fail('inventory did not reach the fixture barrier')
                            time.sleep(0.01)
                        writer.execute(f"UPDATE {schema}.entries SET acknowledged_at=now(),payload='new' WHERE id=4096")
                    finally:
                        writer.execute("SELECT pg_advisory_unlock(%s)",(key,))
                    self.assertEqual(future.result(timeout=5),expected)
                    self.assertEqual(len(actions.queries), 1)
                self.assertNotEqual(OutboxFixture(writer,schema+'.entries')._ack_state(None),expected)
            finally:
                writer.execute(f'DROP SCHEMA {schema} CASCADE')
