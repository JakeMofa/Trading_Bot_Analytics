"""Execute the release SQL against a disposable PostgreSQL temp relation."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
from linux_actions import LinuxActions
from outbox_inventory import origin_digest


def fixture_digest(db, relation, origin, queries):
    def exchange(statement):
        query = statement.replace('ops.outbox', relation)
        queries.append(query)
        if not db.autocommit:
            # Keep the connection-private temp fixture and the test's enclosing
            # transaction alive. The two-connection test uses real BEGIN/COMMIT.
            if query.startswith('BEGIN '):
                return []
            if query == 'CLOSE outbox_pages; COMMIT;':
                query = 'CLOSE outbox_pages'
        cursor = db.execute(query)
        return [row[0] for row in cursor.fetchall()] if cursor.description else []
    return origin_digest(exchange, origin)



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
                def _origin_digest(self, budget, origin):
                    return fixture_digest(db,'pg_temp.inventory_fixture',origin,[])

                def _metadata_digest(self,budget,table,identity,staging):
                    from controller import Budget
                    from metadata_inventory import metadata_digest
                    scoped=table=='archive.generated_outbox_storage'
                    connection=(psycopg.connect(os.environ['TRADEBOT_TEST_READER_DSN'],autocommit=True)
                                if scoped else db)
                    def exchange(statement):
                        if not scoped:
                            if statement.startswith('BEGIN '):return []
                            if statement=='CLOSE metadata_hashes; COMMIT;':statement='CLOSE metadata_hashes;'
                            statement=statement.replace('raw.events','pg_temp.inventory_fixture')
                        cursor=connection.execute(statement)
                        return [row[0] for row in cursor.fetchall()] if cursor.description else []
                    try:return metadata_digest(exchange,table,identity,Budget(30),directory)
                    finally:
                        if scoped:connection.close()

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
            from tempfile import TemporaryDirectory
            directory=self.enterContext(TemporaryDirectory())
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
    def _origin_digest(self, budget, origin):
        return fixture_digest(self.db,self.relation,origin,self.queries)

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
                FROM generate_series(1,235755) n""")
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
            self.assertEqual(rows, 235755)
            pages = [q for q in actions.queries if 'WITH hashes AS MATERIALIZED' in q]
            self.assertEqual(len(pages),231)
            plan = db.execute('EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) '+pages[-1]).fetchone()[0][0]
            nodes = []
            def collect(node):
                nodes.append(node)
                for child in node.get('Plans', []):
                    collect(child)
            collect(plan['Plan'])
            self.assertTrue(any('Index Cond' in n and 'id >=' in n['Index Cond'] and
                                'id <=' in n['Index Cond'] and n['Actual Loops'] == 1 for n in nodes))
            self.assertFalse(any(n['Node Type']=='Seq Scan' and n['Actual Loops']>1 and
                                 n.get('Relation Name')=='inventory_fixture' for n in nodes))

    def test_one_repeatable_read_snapshot_across_page_statements(self):
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
                    self.assertEqual(sum('WITH hashes AS MATERIALIZED' in q for q in actions.queries),2)
                self.assertNotEqual(OutboxFixture(writer,schema+'.entries')._ack_state(None),expected)
            finally:
                writer.execute(f'DROP SCHEMA {schema} CASCADE')


@unittest.skipUnless(os.getenv('TRADEBOT_TEST_INVENTORY_CONTAINER'),
                     'isolated Linux qualification container required')
class ContainerOutboxChannelTests(unittest.TestCase):
    def test_abrupt_docker_attach_loss_cannot_release_the_flock_over_a_live_backend(self):
        import concurrent.futures
        import subprocess
        import time
        from unittest.mock import patch
        import psycopg
        from controller import Budget
        from linux_actions import WATCH_DIAGNOSTIC_LOCK

        container = os.environ['TRADEBOT_TEST_INVENTORY_CONTAINER']
        self.assertRegex(container,r'^[a-f0-9]{12,64}$')
        actions = LinuxActions(watch_diagnostics=True)
        actions.pg_id = container
        popen = subprocess.Popen
        children = []
        def capture(*args,**kwargs):
            proc = popen(*args,**kwargs)
            children.append(proc)
            return proc
        dsn = os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']
        with psycopg.connect(dsn, autocommit=True) as admin:
            try:
                with patch('outbox_inventory.subprocess.Popen', side_effect=capture), \
                     actions._outbox_channel(Budget(65)) as exchange:
                    pid,role,ro=exchange("SELECT json_build_array(pg_backend_pid(),session_user,current_setting('transaction_read_only'));")[0]
                    self.assertEqual((role,ro),('tradebot_reader','on'))
                    # Launch exactly one slow, read-only query, and require it to
                    # be active in the server before killing the Docker client.
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pending=pool.submit(exchange,'SELECT json_build_array(1) FROM pg_sleep(8);')
                        deadline = time.monotonic()+4
                        while not admin.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=%s AND wait_event='PgSleep')",(pid,)).fetchone()[0]:
                            self.assertLess(time.monotonic(),deadline)
                            time.sleep(.02)
                        children[0].kill()
                        with self.assertRaises((DeploymentHold,BrokenPipeError)):
                            pending.result(timeout=4)
                    raise RuntimeError('deliberate test unwind')
            except RuntimeError as exc:
                self.assertEqual(str(exc),'deliberate test unwind')
            # An independent ordinary holder acquires the same gate; its first
            # action runs inside the PG namespace and checks the original PID.
            reap=subprocess.run(['docker','exec',container,'flock','-w','25','-F',
                                 WATCH_DIAGNOSTIC_LOCK,'sh','-ec',
                                 'test ! -e "/proc/$1"','check-released',str(pid)],
                                capture_output=True,timeout=28)
            self.assertEqual(reap.returncode,0)
            self.assertIsNone(admin.execute("SELECT pid FROM pg_stat_activity WHERE pid=%s",(pid,)).fetchone())

    def test_real_container_reader_reports_the_expected_page_identity(self):
        import psycopg
        import uuid
        from controller import Budget
        actions=LinuxActions(watch_diagnostics=True)
        actions.pg_id=os.environ['TRADEBOT_TEST_INVENTORY_CONTAINER']
        schema='outbox_cursor_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN'],autocommit=True) as admin:
            try:
                admin.execute(f'CREATE SCHEMA {schema}')
                admin.execute(f'CREATE TABLE {schema}.fixture(id bigint PRIMARY KEY,origin_id text,payload jsonb,acknowledged_at timestamptz)')
                admin.execute(f"INSERT INTO {schema}.fixture SELECT n,'pp-live-pp',jsonb_build_object('value',n),NULL FROM generate_series(1,2200) n")
                admin.execute(f'GRANT USAGE ON SCHEMA {schema} TO tradebot_reader')
                admin.execute(f'GRANT SELECT ON {schema}.fixture TO tradebot_reader')
                expected=admin.execute(ORIGINAL_DIGEST.replace('inventory_fixture',schema+'.fixture'),('pp-live-pp',)).fetchone()[0]
                with actions._outbox_channel(Budget(50)) as exchange:
                    result=origin_digest(lambda q:exchange(q.replace('ops.outbox',schema+'.fixture')),'pp-live-pp')
                self.assertEqual(result,expected)
            finally:
                admin.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')

    def test_normal_controller_hashes_with_the_original_restricted_roles(self):
        from tempfile import TemporaryDirectory
        import psycopg
        import uuid
        from controller import Budget
        from metadata_inventory import metadata_digest
        actions=LinuxActions()
        actions.pg_id=os.environ['TRADEBOT_TEST_INVENTORY_CONTAINER']
        schema='metadata_cursor_'+uuid.uuid4().hex
        dsn=os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']
        with psycopg.connect(dsn,autocommit=True) as admin, TemporaryDirectory() as directory:
            try:
                admin.execute(f'CREATE SCHEMA {schema}')
                admin.execute(f'GRANT USAGE ON SCHEMA {schema} TO tradebot_reader,tradebot_app')
                for force,role in ((False,'tradebot_app'),(True,'tradebot_reader')):
                    table=f'{schema}.{role}'
                    admin.execute(f'CREATE TABLE {table} AS SELECT n AS id FROM generate_series(1,1100)n')
                    admin.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC,tradebot_reader,tradebot_app')
                    admin.execute(f'GRANT SELECT ON TABLE {table} TO {role}')
                    budget=Budget(50)
                    with actions._outbox_channel(budget,require_reader=force) as exchange:
                        self.assertEqual(exchange("SELECT json_build_array(session_user,current_setting('transaction_read_only'));"),[[role,'on']])
                        digest=metadata_digest(exchange,table,'id',budget,directory)
                    self.assertEqual(digest['count'],1100)
                    if not force:original=digest
                    else:self.assertEqual(digest,original)
            finally:
                admin.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')

    def test_signal_before_pid_registration_keeps_gate_until_login_exits(self):
        import concurrent.futures
        import subprocess
        import time
        import uuid
        from unittest.mock import patch
        import psycopg
        from controller import Budget
        from linux_actions import WATCH_DIAGNOSTIC_LOCK
        from outbox_inventory import RELAY

        container = os.environ['TRADEBOT_TEST_INVENTORY_CONTAINER']
        actions = LinuxActions(watch_diagnostics=True)
        actions.pg_id = container
        key=uuid.uuid4().int % (2**62)
        relay_pid_file=f'/tmp/generated-inventory-relay-{key}.pid'
        sql=f'SELECT pg_advisory_lock({key}) /* generated-startup-{key} */'
        real_popen=subprocess.Popen
        def delay_handshake(args, **kwargs):
            # Prepend a login-only barrier in the disposable PG. The production
            # relay is otherwise identical, including its pre-registration trap.
            argv=list(args)
            code=next(i for i,x in enumerate(argv) if RELAY in x)
            argv[code]=f'echo $$ > {relay_pid_file}; '+argv[code].replace('child=$!',f'child=$!; echo "$child" > {relay_pid_file}.frontend')
            return real_popen([*argv,'-c',sql,'-f','-'],**kwargs)
        def blocked():
            # Only replace the initial Docker launch, not the independent
            # serialized cleanup command that uses the same module.
            with patch('outbox_inventory.subprocess.Popen',side_effect=lambda argv,**kw:
                       delay_handshake(argv,**kw) if 'outbox-inventory' in argv else real_popen(argv,**kw)):
                with actions._outbox_channel(Budget(65)) as exchange:
                    exchange('SELECT 1;')

        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN'],autocommit=True) as admin:
            admin.execute('SELECT pg_advisory_lock(%s)',(key,))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                pending=pool.submit(blocked)
                try:
                    deadline=time.monotonic()+6
                    while True:
                        row=admin.execute("""SELECT pid FROM pg_stat_activity WHERE query=%s
                                           AND state='active' AND wait_event='advisory'""",(sql,)).fetchone()
                        if row:break
                        self.assertLess(time.monotonic(),deadline)
                        time.sleep(.025)
                    pid=row[0]
                    # Churn unrelated sibling backends while the unregistered
                    # login stays alive. The Linux task/children traversal is
                    # specifically unreliable during concurrent child exits.
                    def churn_siblings():
                        n=0
                        until=time.monotonic()+2
                        while time.monotonic()<until:
                            with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']):
                                n+=1
                        return n
                    churn=pool.submit(churn_siblings)
                    # Deliberately suspend the disposable login's server process
                    # and remove psql before checking exclusion. A lock merely
                    # inherited by the frontend would reopen here.
                    subprocess.run(['docker','exec',container,'sh','-ec',
                                    f'kill -STOP "$1"; kill -TERM "$(cat {relay_pid_file})"; '
                                    f'front=$(cat {relay_pid_file}.frontend); kill -TERM "$front"; '
                                    'for n in 1 2 3 4 5 6 7 8 9 10; do '
                                    '[ ! -e "/proc/$front" ] && exit 0; sleep .1; done; exit 1',
                                    'pause-private-login',str(pid)],check=True,timeout=4)
                    conflict=subprocess.run(['docker','exec',container,'flock','-n','-E','75','-F',
                                              WATCH_DIAGNOSTIC_LOCK,'true'],timeout=3)
                    self.assertEqual(conflict.returncode,75)
                    self.assertGreater(churn.result(timeout=4),1)
                finally:
                    if 'pid' in locals():
                        subprocess.run(['docker','exec',container,'sh','-ec',
                                        'kill -CONT "$1" 2>/dev/null || true','resume-fixture',str(pid)],
                                       check=True,timeout=4)
                    admin.execute('SELECT pg_advisory_unlock(%s)',(key,))
                with self.assertRaises(DeploymentHold):
                    pending.result(timeout=25)
            probe=subprocess.run(['docker','exec',container,'flock','-w','5','-F',WATCH_DIAGNOSTIC_LOCK,
                                  'sh','-ec','test ! -e "/proc/$1"; rm -f "$2" "$2.frontend"','check-registration',str(pid),relay_pid_file],
                                 timeout=7)
            self.assertEqual(probe.returncode,0)
