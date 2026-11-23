"""Exact04 admission and SQL gates; retained03 A/B are owned generated fixtures."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.cloud_origin_binding import (TRIAL_ORIGINS,THIRD_TRIAL_ORIGIN,FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN,
    FOURTH_TRIAL_WRITER,FOURTH_TRIAL_READER,cloud_binding)
from postgres.pp_trial_prepare import prepare,CONSUMER,RETAINED_FOURTH_A,RETAINED_FOURTH_SOURCE
from postgres.lifecycle import LifecycleHold
import test_postgres_trial_failed_b_drain as recovery


class FourthControls(unittest.TestCase):
    def test_exact_binding_and_finite_profiles_reject_future_origins(self):
        from postgres.cloud_runtime_profile import selected_cloud_origin,cloud_files,require_trial_files
        from postgres.rehearsal_profile import lease_cap,CYCLE_POLICY
        self.assertEqual((cloud_binding(FOURTH_TRIAL_ORIGIN).writer_role,cloud_binding(FOURTH_TRIAL_ORIGIN).reader_role),
                         (FOURTH_TRIAL_WRITER,FOURTH_TRIAL_READER))
        self.assertEqual(len(TRIAL_ORIGINS),5)
        self.assertEqual(len({cloud_binding(o).raw_prefix for o in TRIAL_ORIGINS}),5)
        anchor=str(uuid.uuid4());env=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
            TRADEBOT_ORIGIN_ID=FOURTH_TRIAL_ORIGIN,TRADEBOT_PP_WINDOW_POLICY=CYCLE_POLICY,TRADEBOT_PP_CYCLE_INITIAL_A=anchor)
        self.assertEqual(selected_cloud_origin(env),FOURTH_TRIAL_ORIGIN)
        require_trial_files(env|cloud_files(FOURTH_TRIAL_ORIGIN),FOURTH_TRIAL_ORIGIN,structured=True,storage=True)
        self.assertEqual((lease_cap(),lease_cap(anchor)),(4560,6600))
        for origin in ('pp-live-pp-trial-20261119-06','pp-live-pp-trial-anything','pp-live-pp-trial-20261119-%'):
            with self.assertRaises(ValueError):selected_cloud_origin(env|dict(TRADEBOT_ORIGIN_ID=origin))
        from postgres.history_v2_transport import HistoryV2PostgresTransport
        for role in (cloud_binding(THIRD_TRIAL_ORIGIN).reader_role,cloud_binding(THIRD_TRIAL_ORIGIN).writer_role):
            with self.assertRaises(ValueError):HistoryV2PostgresTransport(lambda **_:None,origin_id=FOURTH_TRIAL_ORIGIN,
                generation_id=anchor,expected_role=role,expected_database='postgres')

    def test_terminal_scope_preserves_old_bounds_and_does_not_admit_sixth(self):
        from postgres.pp_final_trial_drain import acknowledged_row_limit,SealTarget
        self.assertEqual(acknowledged_row_limit('pp-live-pp-trial-20261119-02'),10000)
        self.assertEqual(acknowledged_row_limit(THIRD_TRIAL_ORIGIN),64000)
        self.assertEqual(acknowledged_row_limit(FOURTH_TRIAL_ORIGIN),64000)
        anchor=str(uuid.uuid4());target=SealTarget(str(uuid.uuid4()),anchor,4,1,10001,'a'*40,str(uuid.uuid4()),'b'*40)
        target.validate(origin_id=FOURTH_TRIAL_ORIGIN)
        with self.assertRaises(LifecycleHold):acknowledged_row_limit('pp-live-pp-trial-20261119-06')


class FourthNative(recovery.Native):
    # Reuse only the fresh-scope/ownership-safe PG17 fixture, not its test cases.
    test_actual_reviewed_row_count_workload_stays_within_existing_20_second_budget=None
    test_guard_failures_roll_back_without_sealing_b=None
    test_preexisting_generated_sentinel_is_never_adopted_or_cleaned=None
    test_seal_exact_retry_preserves_a_and_pointer_and_existing_worker_can_archive_b=None
    test_wrong_login_checkpoint_failure_and_origin_lock_leave_b_unchanged=None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.external:
            cls.app_dsn=os.environ['TRADEBOT_TEST_APP_DSN']
        else:
            cls.migrator_dsn=f'host={cls.socket} user=tradebot_migrator dbname=tradebot_pp'

    def setUp(self):
        super().setUp()
        with self.admin() as db:
            if db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s LIMIT 1',(FOURTH_TRIAL_ORIGIN,)).fetchone():
                raise RuntimeError('refusing preexisting04 fixture scope; no cleanup registered')
        self.fourth_owned=False;self.fourth_anchor=None
        self.addCleanup(self.cleanup_fourth)

    def cleanup_fourth(self):
        if not self.fourth_owned:return
        from psycopg import sql
        with self.admin() as db,db.transaction():
            rows=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s',(FOURTH_TRIAL_ORIGIN,)).fetchall()
            if not rows:return
            proof=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s AND consumer=%s',
                (FOURTH_TRIAL_ORIGIN,self.fourth_anchor,CONSUMER)).fetchone()
            if not proof or proof['cursor'].get('initial_a')!=self.fourth_anchor:
                raise RuntimeError('04 ownership checkpoint changed; cleanup refused')
            for table in ('core.snapshot_evidence','core.predictions','core.outcomes','core.feature_snapshots',
                'core.protected_evidence','core.current_prices','core.markets','core.candles','ops.dedup','ops.outbox',
                'ops.feed_health','ops.worker_checkpoints','archive.reader_leases','archive.checkpoints','archive.manifests','ops.writer_state'):
                db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=%s').format(sql.Identifier(*table.split('.'))),(FOURTH_TRIAL_ORIGIN,))
            for row in rows:
                db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(sql.Identifier(row['partition_name'])))
            db.execute('DELETE FROM archive.generations WHERE origin_id=%s',(FOURTH_TRIAL_ORIGIN,))
        self.fourth_owned=False

    def archive_third(self):
        from postgres.pp_sealed_archive import cycle
        from postgres_lifecycle_fixtures import ImmutableMemoryTransport
        recovery.helper.seal_failed_b(self.repo,self.target,execute=True)
        self.assertEqual(cycle(self.repo,ImmutableMemoryTransport(),origin=THIRD_TRIAL_ORIGIN)['status'],'archived')

    def snapshot_third(self):
        from psycopg import sql
        with self.admin() as db:
            return {table:db.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM {} t WHERE origin_id=%s '
                'ORDER BY to_jsonb(t)::text').format(sql.Identifier(*table.split('.'))),(THIRD_TRIAL_ORIGIN,)).fetchall()
                for table in ('archive.generations','archive.checkpoints','archive.manifests','ops.writer_state',
                    'ops.outbox','core.protected_evidence','raw.events')}

    def prepare_fourth(self):
        anchor=str(uuid.uuid4())
        result=prepare(self.repo,anchor,'c'*40,execute=True,origin_id=FOURTH_TRIAL_ORIGIN)
        self.fourth_owned=True;self.fourth_anchor=anchor
        return result

    def test_fifth_initial_a_preserves_exact_stopped_fourth_evidence(self):
        from psycopg import sql
        from psycopg.types.json import Jsonb

        self.archive_third()
        prepare(self.repo,RETAINED_FOURTH_A,RETAINED_FOURTH_SOURCE,
                execute=True,origin_id=FOURTH_TRIAL_ORIGIN)
        self.fourth_owned=True;self.fourth_anchor=RETAINED_FOURTH_A
        anchor=str(uuid.uuid4())
        with self.assertRaisesRegex(LifecycleHold,'stopped fourth trial'):
            prepare(self.repo,anchor,'e'*40,execute=True,origin_id=FIFTH_TRIAL_ORIGIN)
        with self.admin() as db:
            db.execute('UPDATE ops.writer_state SET epoch=3 WHERE origin_id=%s',(FOURTH_TRIAL_ORIGIN,))
            db.execute('INSERT INTO archive.checkpoints VALUES(%s,%s,%s,%s,now())',
                       (FOURTH_TRIAL_ORIGIN,RETAINED_FOURTH_A,'rehearsal:two-leg-session',
                        Jsonb(dict(initial_a=RETAINED_FOURTH_A,lease_seconds=6600))))
            db.execute("INSERT INTO raw.events(generation_id,origin_id,source,event_id,kind,received_at,available_at,payload,content_hash) "
                       "SELECT %s,%s,'fixture',n::text,'price',now(),now(),'{}',%s FROM generate_series(1,659)n",
                       (RETAINED_FOURTH_A,FOURTH_TRIAL_ORIGIN,'a'*64))
            db.execute("INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at,acknowledged_at) "
                       "SELECT %s,%s,'fixture',n::text,%s,'{}',now(),now() FROM generate_series(1,705)n",
                       (FOURTH_TRIAL_ORIGIN,RETAINED_FOURTH_A,'b'*64))

        def retained():
            with self.admin() as db:
                return {table:db.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM {} t '
                    'WHERE origin_id=%s ORDER BY to_jsonb(t)::text').format(sql.Identifier(*table.split('.'))),
                    (FOURTH_TRIAL_ORIGIN,)).fetchall()
                    for table in ('archive.generations','archive.checkpoints','ops.writer_state','raw.events','ops.outbox')}

        before=retained()
        result=prepare(self.repo,anchor,'e'*40,execute=True,origin_id=FIFTH_TRIAL_ORIGIN)

        def cleanup():
            with self.admin() as db:
                owned=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s AND consumer=%s',
                                 (FIFTH_TRIAL_ORIGIN,anchor,CONSUMER)).fetchone()
                if owned is None or owned['cursor']['initial_a']!=anchor:
                    raise RuntimeError('fifth trial generated ownership checkpoint changed')
                db.execute('DELETE FROM ops.writer_state WHERE origin_id=%s AND generation_id=%s',(FIFTH_TRIAL_ORIGIN,anchor))
                db.execute('DELETE FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s',(FIFTH_TRIAL_ORIGIN,anchor))
                db.execute(sql.SQL('DROP TABLE raw.{}').format(sql.Identifier('events_g_'+anchor.replace('-',''))))
                db.execute('DELETE FROM archive.generations WHERE origin_id=%s AND generation_id=%s',(FIFTH_TRIAL_ORIGIN,anchor))
        self.addCleanup(cleanup)
        self.assertFalse(result['collector_enabled'])
        self.assertEqual(prepare(self.repo,anchor,'e'*40,execute=True,origin_id=FIFTH_TRIAL_ORIGIN),result)
        self.assertEqual(retained(),before)

    def test_both_retained_archives_required_and_exact_unused_preparation_preserves_them(self):
        before=self.snapshot_third()
        with self.assertRaisesRegex(LifecycleHold,'third trial A and B'):self.prepare_fourth()
        self.assertEqual(self.snapshot_third(),before)
        self.archive_third();before=self.snapshot_third();result=self.prepare_fourth()
        self.assertFalse(result['collector_enabled'])
        self.assertEqual(prepare(self.repo,self.fourth_anchor,'c'*40,execute=True,origin_id=FOURTH_TRIAL_ORIGIN),result)
        with self.assertRaises(LifecycleHold):prepare(self.repo,str(uuid.uuid4()),'c'*40,execute=True,origin_id=FOURTH_TRIAL_ORIGIN)
        self.assertEqual(self.snapshot_third(),before)
        with self.admin() as db:
            old_time=db.execute('SELECT verified_at FROM archive.manifests WHERE generation_id=%s ORDER BY manifest_id LIMIT 1',(recovery.helper.INITIAL_A,)).fetchone()['verified_at']
            db.execute("UPDATE archive.manifests SET verified_at=verified_at+interval '1 second' WHERE generation_id=%s",(recovery.helper.INITIAL_A,))
        with self.assertRaisesRegex(LifecycleHold,'unused initial-A'):prepare(self.repo,self.fourth_anchor,'c'*40,execute=True,origin_id=FOURTH_TRIAL_ORIGIN)
        with self.admin() as db:db.execute('UPDATE archive.manifests SET verified_at=%s WHERE generation_id=%s',(old_time,recovery.helper.INITIAL_A))
        self.assertEqual(self.snapshot_third(),before)
        with self.admin() as db:
            proof=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s AND consumer=%s',
                (FOURTH_TRIAL_ORIGIN,self.fourth_anchor,CONSUMER)).fetchone()['cursor']
            self.assertRegex(proof['retained_trial03_sha256'],'^[0-9a-f]{64}$')
            db.execute("UPDATE ops.outbox SET acknowledged_at=NULL WHERE generation_id=%s",(recovery.helper.FAILED_B,))
        with self.assertRaisesRegex(LifecycleHold,'acknowledgements'):prepare(self.repo,self.fourth_anchor,'c'*40,execute=True,origin_id=FOURTH_TRIAL_ORIGIN)

    def test_detached_or_changed_catalog_and_active_prior_writer_hold_without_new04(self):
        from psycopg import sql
        self.archive_third()
        for generation in (recovery.helper.INITIAL_A,recovery.helper.FAILED_B):
            child='events_g_'+generation.replace('-','')
            with self.admin() as db:db.execute(sql.SQL('ALTER TABLE raw.events DETACH PARTITION raw.{}').format(sql.Identifier(child)))
            with self.assertRaisesRegex(LifecycleHold,'attachment changed'):self.prepare_fourth()
            with self.admin() as db:db.execute(sql.SQL('ALTER TABLE raw.events ATTACH PARTITION raw.{} FOR VALUES IN ({})').format(sql.Identifier(child),sql.Literal(generation)))
        with self.admin() as db:
            original=db.execute('SELECT seal_hash FROM archive.generations WHERE generation_id=%s',(recovery.helper.FAILED_B,)).fetchone()['seal_hash']
            db.execute('UPDATE archive.generations SET seal_hash=%s WHERE generation_id=%s',('f'*64,recovery.helper.FAILED_B))
        with self.assertRaisesRegex(LifecycleHold,'catalog or coverage'):self.prepare_fourth()
        with self.admin() as db:
            db.execute('UPDATE archive.generations SET seal_hash=%s WHERE generation_id=%s',(original,recovery.helper.FAILED_B))
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,collector_lease_expires_at=clock_timestamp()+interval '60 seconds' WHERE origin_id=%s",
                (str(uuid.uuid4()),THIRD_TRIAL_ORIGIN))
        with self.assertRaisesRegex(LifecycleHold,'durably OFF'):self.prepare_fourth()
        self.assertFalse(self.fourth_owned)

    def test_exact_trial_two_market_cycle_keeps_retained03_byte_identical(self):
        from test_postgres_cycle_integration import NativeCycleTests
        self.archive_third();before=self.snapshot_third()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp')
        with patch.dict(os.environ,env):
            for origin in (FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN):
                with self.subTest(origin=origin):
                    case=NativeCycleTests('test_exact_finite_cycle_retained_rejection_and_successor_writes')
                    try:case._exercise_cycle(origin=origin)
                    finally:case.doCleanups()
        self.assertEqual(self.snapshot_third(),before)

    def test_fifth_retirement_requires_fresh_readback_and_an_independent_successor_commit(self):
        from test_postgres_lifecycle_integration import PostgreSQLLifecycleIntegration
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp')
        if not self.external:env['PATH']=str(self.bin)+os.pathsep+os.environ['PATH']
        case=PostgreSQLLifecycleIntegration('test_exact_trial_origin_uses_two_market_permits_without_legacy_origin_aliasing')
        with patch.dict(os.environ,env):
            try:
                case.setUp()
                case._exercise_exact_pp_permits(FIFTH_TRIAL_ORIGIN)
            finally:case.doCleanups()

    def test_both_real04_sql_retirements_and_terminal_scope_preserve03(self):
        from test_postgres_lifecycle_integration import PostgreSQLLifecycleIntegration
        from postgres.lifecycle import RotationPolicy
        self.archive_third();before=self.snapshot_third()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp')
        if not self.external:env['PATH']=str(self.bin)+os.pathsep+os.environ['PATH']
        case=PostgreSQLLifecycleIntegration('test_exact_trial_origin_uses_two_market_permits_without_legacy_origin_aliasing')
        with patch.dict(os.environ,env):
            try:
                case.setUp()
                def prepared(origin,*_):
                    anchor=str(uuid.uuid4());prepare(case.repository,anchor,'a'*40,execute=True,origin_id=origin)
                    self.fourth_owned=True;self.fourth_anchor=anchor
                    with patch('postgres.lifecycle.require_cycle_alignment'),patch('postgres.lifecycle.pp_space.sample',return_value={'space_hold':None}):
                        case.repository.enable_collector(origin,session_id=str(uuid.uuid4()),expected_generation_id=anchor,
                            max_seconds=6600,rehearsal_anchor=anchor)
                    return case.repository.generation(anchor)
                def rotate():return case.repository.switch_if_due(FOURTH_TRIAL_ORIGIN,RotationPolicy(1))
                with patch.object(case.repository,'bootstrap',side_effect=prepared),patch.object(case,'rotate',side_effect=rotate):
                    case._exercise_exact_pp_permits(FOURTH_TRIAL_ORIGIN)
                from postgres.pp_final_trial_drain import SealTarget,seal_final_a
                from postgres.pp_sealed_archive import cycle
                from postgres.archive_codec import ArchiveLimits,CycleBudget
                from postgres.lifecycle import ArchiveWorker
                state=case.repository.disable_collector(FOURTH_TRIAL_ORIGIN)
                fresh=case.repository.collector_state(FOURTH_TRIAL_ORIGIN)['generation_id']
                with self.admin() as db:
                    db.execute("INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at) VALUES(%s,%s,'fixture','final04',%s,'{}',clock_timestamp())",
                        (FOURTH_TRIAL_ORIGIN,fresh,'d'*64))
                worker=ArchiveWorker(case.repository,case.transport,ArchiveLimits())
                worker.sync_outbox(fresh,CycleBudget(worker.limits))
                with self.admin() as db:
                    counts=db.execute('SELECT (SELECT count(*) FROM raw.events WHERE generation_id=%s) AS raw, (SELECT count(*) FROM ops.outbox WHERE generation_id=%s) AS outbox',(fresh,fresh)).fetchone()
                target=SealTarget(fresh,self.fourth_anchor,case.repository.collector_state(FOURTH_TRIAL_ORIGIN)['epoch'],counts['raw'],counts['outbox'],'a'*40,str(uuid.uuid4()),'b'*40)
                sealed=seal_final_a(case.repository,target,execute=True,origin_id=FOURTH_TRIAL_ORIGIN)
                self.assertEqual(sealed['status'],'sealed_for_final_trial_archive')
                self.assertEqual(cycle(case.repository,case.transport,origin=FOURTH_TRIAL_ORIGIN)['status'],'archived')
                self.assertEqual(case.repository.generation(fresh)['state'],'verified')
                self.assertFalse(case.repository.collector_state(FOURTH_TRIAL_ORIGIN)['collector_enabled'])
                self.assertEqual(self.snapshot_third(),before)
            finally:
                if self.fourth_owned:
                    with self.admin() as db:db.execute('DELETE FROM ops.outbox WHERE origin_id=%s',(FOURTH_TRIAL_ORIGIN,))
                case.doCleanups()
