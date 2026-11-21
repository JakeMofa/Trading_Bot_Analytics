"""Failed03 stopped-B maintenance qualification, owned native PG17 only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres import pp_trial_failed_b_drain as helper
from postgres.archive_codec import encoded, manifest_set_hash, pack_chunk, sha256, wire
from postgres.lifecycle import LifecycleHold, LifecycleRepository
import test_pp_initial_trial_drain as fixture


class Controls(unittest.TestCase):
    def test_actual_reviewed_scope_and_default_off_before_secret_access(self):
        self.assertEqual((helper.A_RAW_ROWS, helper.A_ACK_ROWS, helper.B_RAW_ROWS, helper.B_ACK_ROWS),
                         (24649, 26480, 12301, 13210))
        self.assertEqual(helper.A_SEAL_HASH, '2d13fca5162dba62169331c3aa9e87cfca9939d03e256a9054776d6871d8d083')
        target = helper.SealTarget(helper.FAILED_B, helper.INITIAL_A, 4, 12301, 13210,
                                   helper.TRIAL_SOURCE, str(uuid.uuid4()), 'a' * 40)
        target.validate()
        for change in ({'initial_a': str(uuid.uuid4())}, {'generation': str(uuid.uuid4())},
                       {'writer_epoch': True}, {'writer_epoch': 5}, {'raw_count': 12300},
                       {'outbox_count': 13209}, {'outbox_count': 64001}, {'trial_source': 'b' * 40},
                       {'source': helper.TRIAL_SOURCE}, {'operation': '00000000-0000-0000-0000-000000000000'}):
            with self.subTest(change=change), self.assertRaises(LifecycleHold):
                replace(target, **change).validate()
        with patch.object(helper, 'private_dsn', side_effect=AssertionError('no secret access')):
            self.assertEqual(helper.main(['--generation', target.generation, '--initial-a', target.initial_a,
                '--writer-epoch', '4', '--raw-count', '12301', '--outbox-count', '13210',
                '--trial-source', target.trial_source, '--operation', target.operation, '--source', target.source]), 1)
        self.assertEqual((helper.LIMITS.max_seconds, helper.MAX_ROWS), (20, 64000))
        class Repository:
            environment = 'production'
            pending_outbox_limit = 10000
        with self.assertRaises(LifecycleHold):helper.seal_failed_b(Repository(), target, execute=True)

    def test_guard_diagnostics_are_fixed_and_arbitrary_details_are_removed(self):
        with self.assertRaises(helper.FailedBGuard) as guard:
            helper.require(False, 'exact lifecycle database identity required')
        public = helper.public_failure(guard.exception)
        self.assertEqual(public['reason'], 'failed03_exact_lifecycle_database_identity_required')
        secret = 'postgresql://user:password@private.invalid/private-response'
        for error in (RuntimeError(secret), helper.FailedBGuard(secret)):
            self.assertNotIn(secret, json.dumps(helper.public_failure(error)))
        args = ['--execute', '--generation', helper.FAILED_B, '--initial-a', helper.INITIAL_A,
                '--writer-epoch', '4', '--raw-count', '12301', '--outbox-count', '13210',
                '--trial-source', helper.TRIAL_SOURCE, '--operation', str(uuid.uuid4()), '--source', 'c'*40]
        env = dict(TRADEBOT_PP_FAILED_B_DRAIN='true', TRADEBOT_ENVIRONMENT='preprod',
                   TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID=helper.ORIGIN,
                   TRADEBOT_DATABASE_DSN_FILE=str(helper.LOCAL_DSN))
        with patch.dict(os.environ, env, clear=True), patch.object(os.path, 'lexists', return_value=False), \
                patch.object(helper, 'private_dsn', side_effect=RuntimeError(secret)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(helper.main(args), 1)
        self.assertNotIn(secret, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['reason'], 'failed03_maintenance_failed')


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.external = all(os.environ.get('TRADEBOT_TEST_' + role + '_DSN')
                           for role in ('LIFECYCLE', 'APP', 'MIGRATOR', 'READER'))
        if cls.external:
            if (os.getenv('TRADEBOT_DATA_MODE'), os.getenv('TRADEBOT_ORIGIN_ID')) != ('generated', 'generated-pp'):
                raise RuntimeError('native fixture requires owned generated scope')
            cls.lifecycle_dsn = os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']
            cls.migrator_dsn = os.environ['TRADEBOT_TEST_MIGRATOR_DSN']
        else:
            fixture.InitialSealNative.setUpClass.__func__(cls)

    @classmethod
    def admin(cls, database='tradebot_pp'):
        if cls.external:
            from postgres.connection import connect_migrator
            return connect_migrator(cls.migrator_dsn, environment='preprod')
        return fixture.InitialSealNative.admin.__func__(cls, database)

    @classmethod
    def tearDownClass(cls):
        if not cls.external:fixture.InitialSealNative.tearDownClass.__func__(cls)

    def assert_fresh_scope(self):
        # Supplied test DSNs are not proof that these real identifiers are ours.
        # Refuse all existing03 data/orphan partitions before registering cleanup.
        tables = ('archive.generations', 'ops.writer_state', 'raw.events', 'ops.outbox',
                  'archive.checkpoints', 'archive.manifests', 'archive.reader_leases',
                  'core.markets', 'core.candles', 'core.current_prices', 'core.protected_evidence',
                  'core.feature_snapshots', 'core.snapshot_evidence', 'core.predictions', 'core.outcomes',
                  'ops.feed_health', 'ops.worker_checkpoints', 'ops.dedup')
        with self.admin() as db, db.transaction():
            db.execute('SET TRANSACTION READ ONLY')
            for table in tables:
                if db.execute('SELECT 1 FROM '+table+' WHERE origin_id=%s LIMIT 1', (helper.ORIGIN,)).fetchone():
                    raise RuntimeError('refusing preexisting03 scope; no fixture ownership or cleanup')
            for generation in (helper.INITIAL_A, helper.FAILED_B):
                if db.execute('SELECT to_regclass(%s) AS child', ('raw.events_g_'+generation.replace('-', ''),)).fetchone()['child'] is not None:
                    raise RuntimeError('refusing preexisting03 partition; no fixture ownership or cleanup')

    def setUp(self):
        from postgres.connection import connect
        self.owned = False
        self.owner_token = str(uuid.uuid4())
        self.assert_fresh_scope()
        self.repo = LifecycleRepository(lambda: connect(self.lifecycle_dsn, environment='preprod'))
        self.patch = patch.multiple(helper, A_RAW_ROWS=2, A_ACK_ROWS=3, B_RAW_ROWS=1, B_ACK_ROWS=2)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.addCleanup(self.cleanup)
        self.load_fixture()

    def cleanup(self):
        if not self.owned:
            return
        from psycopg import sql
        with self.admin() as db, db.transaction():
            marker = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                                "AND generation_id=%s AND consumer='test:failed03-b-owner-v1' FOR UPDATE",
                                (helper.ORIGIN, helper.INITIAL_A)).fetchone()
            if not marker or marker['cursor'] != dict(owner=self.owner_token):
                raise RuntimeError('fixture ownership marker mismatch; cleanup refused')
            for table in ('core.snapshot_evidence', 'core.predictions', 'core.feature_snapshots',
                          'core.protected_evidence', 'core.markets', 'ops.outbox', 'archive.reader_leases',
                          'archive.manifests', 'archive.checkpoints', 'ops.writer_state'):
                db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=%s').format(sql.Identifier(*table.split('.'))),
                           (helper.ORIGIN,))
            for generation in (helper.INITIAL_A, helper.FAILED_B):
                db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(sql.Identifier('events_g_' + generation.replace('-', ''))))
            db.execute('DELETE FROM archive.generations WHERE origin_id=%s', (helper.ORIGIN,))
        self.owned = False

    def load_fixture(self, *, large=False):
        self.assert_fresh_scope()
        from psycopg.types.json import Jsonb
        now = datetime.now(timezone.utc);start = now - timedelta(hours=1)
        self.started_a = start;self.handoff = start + timedelta(minutes=31)
        if large:
            self.patch.stop();self.patch = patch.multiple(helper, A_RAW_ROWS=24649, A_ACK_ROWS=26480,
                                                         B_RAW_ROWS=12301, B_ACK_ROWS=13210)
            self.patch.start();self.addCleanup(self.patch.stop)
        # A failed duplicate INSERT rolls back everything before ownership is set.
        with self.admin() as db, db.transaction():
            for generation, slot, started in ((helper.INITIAL_A, 'A', start), (helper.FAILED_B, 'B', self.handoff)):
                db.execute("INSERT INTO archive.generations(origin_id,generation_id,slot,state,partition_name,created_at,started_at) "
                           "VALUES(%s,%s,%s,'prepared',%s,%s,%s)",
                           (helper.ORIGIN, generation, slot, 'events_g_' + generation.replace('-', ''), started, started))
                db.execute('SELECT archive.create_generation_partition(%s,%s)', (helper.ORIGIN, generation))
            for generation, count in ((helper.INITIAL_A, helper.A_RAW_ROWS), (helper.FAILED_B, helper.B_RAW_ROWS)):
                db.execute("INSERT INTO raw.events(generation_id,origin_id,source,event_id,kind,received_at,available_at,payload,content_hash) "
                           "SELECT %s,%s,'generated_fixture',lpad(n::text,8,'0'),'price',%s,%s,'{}','" + 'a' * 64 + "' FROM generate_series(1,%s)n",
                           (generation, helper.ORIGIN, start, start, count))
            a_rows = db.execute('SELECT * FROM raw.events WHERE generation_id=%s ORDER BY source,event_id',
                                (helper.INITIAL_A,)).fetchall()
            after = None;catalog = []
            for index in range(0, len(a_rows), 500):
                _, manifest = pack_chunk(a_rows[index:index+500], origin_id=helper.ORIGIN,
                                         generation_id=helper.INITIAL_A, after=after, limits=helper.LIMITS)
                manifest['manifest_id'] = f'raw.events:{len(catalog):012d}'
                manifest['object_key'] = 'raw-v1/' + sha256(helper.ORIGIN.encode()) + '/' + helper.INITIAL_A + '/' + manifest['sha256'] + '.jsonl.gz'
                db.execute('INSERT INTO archive.manifests(origin_id,generation_id,manifest_id,format_version,object_key,sha256,row_count,byte_count,coverage,created_at,verified_at,verification) '
                           'VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (helper.ORIGIN, helper.INITIAL_A, manifest['manifest_id'], manifest['object_key'],
                            manifest['sha256'], manifest['row_count'], manifest['byte_count'], Jsonb(manifest['coverage']),
                            self.handoff, self.handoff, Jsonb(dict(method='fresh_authenticated_readback'))))
                catalog.append(manifest);after = manifest['coverage']['last']
            # Generated fixture bytes cannot reproduce the real retained cloud hash.
            # Only that attested constant is substituted; production pin is tested above.
            self.digest_patch = patch.object(helper, 'A_SEAL_HASH', manifest_set_hash(catalog))
            self.digest_patch.start();self.addCleanup(self.digest_patch.stop)
            db.execute("UPDATE archive.generations SET state='verified',sealed_at=%s,verified_at=%s,seal_count=%s,seal_hash=%s WHERE generation_id=%s",
                       (self.handoff, self.handoff, helper.A_RAW_ROWS, helper.A_SEAL_HASH, helper.INITIAL_A))
            db.execute("UPDATE archive.generations SET state='collecting' WHERE generation_id=%s", (helper.FAILED_B,))
            db.execute('INSERT INTO ops.writer_state(origin_id,generation_id,epoch,collector_enabled,updated_at) VALUES(%s,%s,4,false,%s)',
                       (helper.ORIGIN, helper.FAILED_B, now))
            for generation, count in ((helper.INITIAL_A, helper.A_ACK_ROWS), (helper.FAILED_B, helper.B_ACK_ROWS)):
                db.execute("INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at,acknowledged_at) "
                           "SELECT %s,%s,'core.candles',%s||n::text,'" + 'b' * 64 + "','{}',%s,%s FROM generate_series(1,%s)n",
                           (helper.ORIGIN, generation, generation, start, now, count))
            for generation in (helper.INITIAL_A, helper.FAILED_B):
                protected_count = 512 if large else 1
                db.execute("INSERT INTO core.protected_evidence(origin_id,evidence_id,generation_id,source,event_id,kind,received_at,available_at,payload,content_hash) "
                           "SELECT %s,%s||lpad(to_hex(n),63,'0'),%s,'generated_fixture',n::text,'price',%s,%s,'{}','" + 'e' * 64 + "' FROM generate_series(1,%s)n",
                           (helper.ORIGIN, 'a' if generation==helper.INITIAL_A else 'b', generation, start, start, protected_count))
                db.execute("UPDATE ops.outbox o SET entity_type='core.protected_evidence',payload=to_jsonb(p),content_hash=p.content_hash,"
                           "entity_id='['||to_json(p.origin_id)::text||','||to_json(p.evidence_id)::text||']' "
                           "FROM core.protected_evidence p WHERE p.origin_id=%s AND p.generation_id=%s "
                           "AND o.origin_id=p.origin_id AND o.generation_id=p.generation_id AND o.entity_id=p.generation_id::text||p.event_id",
                           (helper.ORIGIN, generation))
            prepared = dict(policy=helper.PREPARE_CONSUMER, initial_a=helper.INITIAL_A, source_sha=helper.TRIAL_SOURCE)
            admission = dict(initial_a=helper.INITIAL_A, session_id=helper.SESSION_ID, lease_seconds=6600,
                             admitted_at=(start+timedelta(minutes=1)).isoformat(),
                             lease_expires_at=(start+timedelta(minutes=111)).isoformat())
            for consumer, cursor in ((helper.PREPARE_CONSUMER, prepared), (helper.ADMISSION_CONSUMER, admission)):
                db.execute('INSERT INTO archive.checkpoints(origin_id,generation_id,consumer,cursor,acknowledged_at) VALUES(%s,%s,%s,%s,%s)',
                           (helper.ORIGIN, helper.INITIAL_A, consumer, Jsonb(cursor), now))
            db.execute('INSERT INTO archive.checkpoints(origin_id,generation_id,consumer,cursor,acknowledged_at) '
                       "VALUES(%s,%s,'test:failed03-b-owner-v1',%s,%s)",
                       (helper.ORIGIN, helper.INITIAL_A, Jsonb(dict(owner=self.owner_token)), now))
        self.owned = True
        self.target = helper.SealTarget(helper.FAILED_B, helper.INITIAL_A, 4, helper.B_RAW_ROWS,
                                        helper.B_ACK_ROWS, helper.TRIAL_SOURCE, str(uuid.uuid4()), 'c' * 40)

    def retained(self):
        with self.admin() as db:
            return wire(dict(generation=db.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                                                    (helper.INITIAL_A,)).fetchone(),
                             manifests=db.execute('SELECT * FROM archive.manifests WHERE generation_id=%s ORDER BY manifest_id',
                                                  (helper.INITIAL_A,)).fetchall(),
                             checkpoints=db.execute('SELECT * FROM archive.checkpoints WHERE generation_id=%s ORDER BY consumer',
                                                    (helper.INITIAL_A,)).fetchall(),
                             protected=db.execute('SELECT * FROM core.protected_evidence WHERE origin_id=%s ORDER BY evidence_id', (helper.ORIGIN,)).fetchall()))

    def test_seal_exact_retry_preserves_a_and_pointer_and_existing_worker_can_archive_b(self):
        from postgres.pp_sealed_archive import cycle
        from postgres_lifecycle_fixtures import ImmutableMemoryTransport
        before = self.retained();result = helper.seal_failed_b(self.repo, self.target, execute=True)
        self.assertEqual(result['status'], 'sealed_for_failed03_b_archive')
        self.assertEqual((result['retirement_authorized'], result['original_trial_satisfied'], result['successor_created']), (False, False, False))
        again = helper.seal_failed_b(self.repo, self.target, execute=True)
        self.assertEqual(again['status'], 'already_sealed');self.assertEqual(again['sealed_at'], result['sealed_at'])
        raw = ImmutableMemoryTransport();archived = cycle(self.repo, raw, origin=helper.ORIGIN)
        self.assertEqual(archived['status'], 'archived')
        self.assertEqual(helper.seal_failed_b(self.repo, self.target, execute=True)['status'], 'already_sealed')
        self.assertEqual(self.retained(), before)
        state = self.repo.collector_state(helper.ORIGIN)
        self.assertEqual((state['generation_id'], state['epoch'], state['collector_enabled']), (helper.FAILED_B, 5, False))
        with self.assertRaises(LifecycleHold):helper.seal_failed_b(self.repo, replace(self.target, operation=str(uuid.uuid4())), execute=True)
        with self.admin() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.generations WHERE origin_id=%s', (helper.ORIGIN,)).fetchone()['n'], 2)
            for generation in (helper.INITIAL_A, helper.FAILED_B):
                self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child', ('raw.events_g_'+generation.replace('-', ''),)).fetchone()['child'])

    def test_guard_failures_roll_back_without_sealing_b(self):
        mutations = (
            ("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,collector_lease_expires_at=clock_timestamp()+interval '60 seconds' WHERE origin_id=%s", (str(uuid.uuid4()), helper.ORIGIN)),
            ("UPDATE archive.generations SET seal_hash=%s WHERE generation_id=%s", ('d' * 64, helper.INITIAL_A)),
            ("UPDATE ops.outbox SET acknowledged_at=NULL WHERE generation_id=%s", (helper.FAILED_B,)),
            ("UPDATE ops.outbox SET payload=jsonb_set(payload,'{kind}', '\"tampered\"'::jsonb) WHERE generation_id=%s AND entity_type='core.protected_evidence'", (helper.FAILED_B,)),
            ("UPDATE core.protected_evidence SET evidence_id='nonhex-☃' WHERE generation_id=%s", (helper.FAILED_B,)),
            ("UPDATE ops.outbox SET entity_id='wrong identity with same content hash' WHERE generation_id=%s AND entity_type='core.protected_evidence'", (helper.FAILED_B,)),
            ("INSERT INTO archive.reader_leases(lease_id,origin_id,generation_id,holder,expires_at) VALUES('fixture',%s,%s,'fixture',clock_timestamp()+interval '60 seconds')", (helper.ORIGIN, helper.FAILED_B)),
        )
        for statement, parameters in mutations:
            with self.subTest(statement=statement):
                with self.admin() as db:
                    with db.transaction():
                        db.execute(statement, parameters)
                        # This fixture connection is committed only for the test;
                        # restore by rebuilding the tiny owned generation chain.
                with self.assertRaises(LifecycleHold):helper.seal_failed_b(self.repo, self.target, execute=True)
                self.assertEqual(self.repo.generation(helper.FAILED_B)['state'], 'collecting')
                self.cleanup();self.digest_patch.stop();self.load_fixture()

    def test_preexisting_generated_sentinel_is_never_adopted_or_cleaned(self):
        before = self.retained();b_before = self.repo.generation(helper.FAILED_B)
        newcomer = Native('test_guard_failures_roll_back_without_sealing_b')
        with self.assertRaisesRegex(RuntimeError, 'preexisting03'):
            newcomer.setUp()
        self.assertFalse(newcomer.owned);self.assertEqual(newcomer._cleanups, [])
        newcomer.cleanup();newcomer.doCleanups()
        self.assertEqual(self.retained(), before)
        self.assertEqual(self.repo.generation(helper.FAILED_B), b_before)
        with self.admin() as db:
            self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child',
                                           ('raw.events_g_'+helper.FAILED_B.replace('-', ''),)).fetchone()['child'])

    def test_wrong_login_checkpoint_failure_and_origin_lock_leave_b_unchanged(self):
        original = self.repo.generation(helper.FAILED_B);retained = self.retained()
        wrong_role = LifecycleRepository(lambda: self.admin())
        with self.assertRaisesRegex(LifecycleHold, 'database_identity'):
            helper.seal_failed_b(wrong_role, self.target, execute=True)
        with patch.object(self.repo, '_checkpoint', side_effect=RuntimeError('synthetic checkpoint failure')):
            with self.assertRaises(RuntimeError):helper.seal_failed_b(self.repo, self.target, execute=True)
        with self.admin() as db:
            db.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))', ('tradebot-raw-archive:'+helper.ORIGIN,))
            try:
                with self.assertRaises(LifecycleHold):helper.seal_failed_b(self.repo, self.target, execute=True)
            finally:db.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', ('tradebot-raw-archive:'+helper.ORIGIN,))
        self.assertEqual(self.repo.generation(helper.FAILED_B), original)
        self.assertEqual(self.repo.collector_state(helper.ORIGIN)['epoch'], 4)
        self.assertEqual(self.retained(), retained)
        with self.admin() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.checkpoints WHERE generation_id=%s AND consumer=%s',
                                        (helper.FAILED_B, helper.CONSUMER)).fetchone())

    def test_actual_reviewed_row_count_workload_stays_within_existing_20_second_budget(self):
        self.cleanup();self.digest_patch.stop();self.load_fixture(large=True)
        # Inspect the actual closure statement, without changing indexes or timeouts.
        tree = ast.parse(Path(helper.__file__).read_text())
        query = next(node.args[0].value for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                     and node.func.attr == 'execute' and node.args
                     and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                     and 'jsonb_populate_record' in node.args[0].value)
        with self.repo.connection_factory() as db:
            db.execute("SET LOCAL statement_timeout='5000ms'")
            plan = db.execute('EXPLAIN (ANALYZE, FORMAT JSON) '+query,
                              (helper.ORIGIN, helper.INITIAL_A, helper.FAILED_B)).fetchone()['QUERY PLAN'][0]['Plan']
        def indexes(node):
            return ([node['Index Name']] if 'Index Name' in node else []) + [name for child in node.get('Plans', []) for name in indexes(child)]
        used_indexes = indexes(plan)
        self.assertIn('outbox_origin_id_entity_type_entity_id_content_hash_key', used_indexes)
        def unique_conditions(node):
            return ([node.get('Index Cond', '')] if node.get('Index Name') == 'outbox_origin_id_entity_type_entity_id_content_hash_key' else []) + [condition for child in node.get('Plans', []) for condition in unique_conditions(child)]
        self.assertTrue(any('entity_id' in condition and 'content_hash' in condition for condition in unique_conditions(plan)), repr(unique_conditions(plan)))

        began = time.monotonic();result = helper.seal_failed_b(self.repo, self.target, execute=True)
        elapsed = time.monotonic() - began
        self.assertEqual(result['status'], 'sealed_for_failed03_b_archive');self.assertLess(elapsed, 20)
        print(json.dumps(dict(qualification='generated_owned_pg17_exact_row_counts', seal_work_seconds=round(elapsed, 3),
                              a_raw=24649, a_ack=26480, b_raw=12301, b_ack=13210, cloud_calls=0, closure_indexes=used_indexes, closure_execution_ms=plan['Actual Total Time'])), flush=True)


if __name__ == '__main__':
    unittest.main()
