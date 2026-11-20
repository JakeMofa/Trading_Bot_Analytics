"""Owned PG17 exact03 admission/retirement; retained02 archive is never reset."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_postgres_failed_trial_drain as failed
from postgres.cloud_origin_binding import (LEGACY_ORIGIN,TRIAL_ORIGIN,NEXT_TRIAL_ORIGIN,
    THIRD_TRIAL_ORIGIN,THIRD_TRIAL_WRITER,THIRD_TRIAL_READER,cloud_binding)
from postgres.lifecycle import LifecycleHold

class ThirdTrialControls(unittest.TestCase):
    def test_exact_third_binding_preserves_both_prior_principals_and_normal_limits(self):
        from postgres.cloud_runtime_profile import selected_cloud_origin,cloud_files,require_trial_files
        from postgres.rehearsal_profile import lease_cap,cycle_anchor
        self.assertEqual(cloud_binding(THIRD_TRIAL_ORIGIN).writer_role,THIRD_TRIAL_WRITER)
        self.assertEqual(cloud_binding(THIRD_TRIAL_ORIGIN).reader_role,THIRD_TRIAL_READER)
        origins=(TRIAL_ORIGIN,NEXT_TRIAL_ORIGIN,THIRD_TRIAL_ORIGIN)
        self.assertEqual(len({cloud_binding(o).raw_prefix for o in origins}),3)
        self.assertEqual(len({cloud_binding(o).writer_role for o in origins}),3)
        anchor=str(uuid.uuid4());env=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
            TRADEBOT_ORIGIN_ID=THIRD_TRIAL_ORIGIN,TRADEBOT_PP_WINDOW_POLICY='two-official-markets-cycle',TRADEBOT_PP_CYCLE_INITIAL_A=anchor)
        self.assertEqual(selected_cloud_origin(env),THIRD_TRIAL_ORIGIN);self.assertEqual(cycle_anchor(env),anchor)
        self.assertEqual((lease_cap(),lease_cap(anchor)),(4560,6600))
        require_trial_files(env|cloud_files(THIRD_TRIAL_ORIGIN),THIRD_TRIAL_ORIGIN,structured=True,storage=True)
        for bad in ('pp-live-pp-trial-20261119-04','pp-live-pp-trial-anything'):
            with self.assertRaises(ValueError):selected_cloud_origin(env|{'TRADEBOT_ORIGIN_ID':bad})
        from postgres import pp_failed_trial_drain,pp_final_trial_drain
        self.assertEqual((pp_failed_trial_drain.ORIGIN,pp_final_trial_drain.ORIGIN),(NEXT_TRIAL_ORIGIN,NEXT_TRIAL_ORIGIN))

class ThirdTrialNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        failed.Native.setUpClass.__func__(cls)
        if not cls.external:cls.migrator_dsn=f'host={cls.socket} user=tradebot_migrator dbname=tradebot_pp'
    tearDownClass=classmethod(failed.Native.tearDownClass.__func__)
    admin=classmethod(failed.Native.admin.__func__)
    setUp=failed.Native.setUp
    fixture_on=failed.Native.fixture_on
    cleanup=failed.Native.cleanup
    evidence=failed.Native.evidence
    def archive_second(self):
        from postgres.pp_failed_trial_drain import seal_failed_initial_a
        from postgres.pp_sealed_archive import cycle
        seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(cycle(self.repo,self.raw,origin=NEXT_TRIAL_ORIGIN)['status'],'archived')
    def prior_snapshot(self):
        from psycopg import sql
        with self.admin() as db:
            return {table:db.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM {} t '
                'WHERE origin_id=ANY(%s) ORDER BY to_jsonb(t)::text').format(sql.Identifier(*table.split('.'))),
                ([LEGACY_ORIGIN,TRIAL_ORIGIN,NEXT_TRIAL_ORIGIN],)).fetchall()
                for table in ('archive.generations','archive.checkpoints','archive.manifests','ops.writer_state',
                    'ops.outbox','ops.dedup','core.current_prices','raw.events')}
    def prepare_third(self):
        from postgres.pp_trial_prepare import prepare
        self.third=str(uuid.uuid4());self.origins.append(THIRD_TRIAL_ORIGIN);self.children.append(self.third)
        return prepare(self.repo,self.third,'c'*40,execute=True,origin_id=THIRD_TRIAL_ORIGIN)
    def test_third_requires_retained_second_archive_before_preparation(self):
        before=self.prior_snapshot()
        with self.assertRaisesRegex(LifecycleHold,'second trial archive'):self.prepare_third()
        self.assertEqual(self.prior_snapshot(),before)
    def test_third_preparation_preserves_archives_and_cannot_recycle_second_or_third(self):
        from postgres.pp_trial_prepare import prepare
        self.archive_second();before=self.prior_snapshot();result=self.prepare_third()
        self.assertEqual(result['origin_id'],THIRD_TRIAL_ORIGIN);self.assertFalse(result['collector_enabled'])
        self.assertEqual(prepare(self.repo,self.third,'c'*40,execute=True,origin_id=THIRD_TRIAL_ORIGIN),result)
        for origin in (NEXT_TRIAL_ORIGIN,THIRD_TRIAL_ORIGIN):
            with self.assertRaises(LifecycleHold):prepare(self.repo,str(uuid.uuid4()),'c'*40,execute=True,origin_id=origin)
        self.assertEqual(self.prior_snapshot(),before)
    def test_third_rejects_unacknowledged_retained_second(self):
        self.archive_second()
        with self.admin() as db:db.execute('UPDATE ops.outbox SET acknowledged_at=NULL WHERE origin_id=%s',(NEXT_TRIAL_ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'acknowledgements incomplete'):self.prepare_third()
    def test_detached_retained_second_partition_blocks_fresh_third(self):
        from psycopg import sql
        self.archive_second();before=self.repo.collector_state(NEXT_TRIAL_ORIGIN)
        child=self.repo.generation(failed.helper.FAILED_INITIAL_A)['partition_name']
        with self.admin() as db:
            db.execute(sql.SQL('ALTER TABLE raw.events DETACH PARTITION raw.{}').format(sql.Identifier(child)))
            self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child',('raw.'+child,)).fetchone()['child'])
        with self.assertRaisesRegex(LifecycleHold,'partition attachment changed'):self.prepare_third()
        self.assertEqual(self.repo.collector_state(NEXT_TRIAL_ORIGIN),before)

    def test_wrong_bound_retained_second_partition_blocks_fresh_third(self):
        from psycopg import sql
        self.archive_second();child=self.repo.generation(failed.helper.FAILED_INITIAL_A)['partition_name']
        with self.admin() as db:
            db.execute(sql.SQL('ALTER TABLE raw.events DETACH PARTITION raw.{}').format(sql.Identifier(child)))
            db.execute(sql.SQL('TRUNCATE TABLE raw.{}').format(sql.Identifier(child)))
            db.execute(sql.SQL('ALTER TABLE raw.events ATTACH PARTITION raw.{} FOR VALUES IN ({})').format(
                sql.Identifier(child),sql.Literal(str(uuid.uuid4()))))
        with self.assertRaisesRegex(LifecycleHold,'partition attachment changed'):self.prepare_third()

    def test_third_actual_pair_cycle_preserves_both_prior_archives(self):
        from test_postgres_cycle_integration import NativeCycleTests
        self.archive_second();before=self.prior_snapshot()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp')
        case=NativeCycleTests('test_exact_finite_cycle_retained_rejection_and_successor_writes')
        with patch.dict(os.environ,env):
            try:case._exercise_cycle(origin=THIRD_TRIAL_ORIGIN)
            finally:case.doCleanups()
        self.assertEqual(self.prior_snapshot(),before)
    def test_third_both_real_sql_retirements_preserve_both_prior_archives(self):
        from test_postgres_lifecycle_integration import PostgreSQLLifecycleIntegration
        self.archive_second();before=self.prior_snapshot()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp',PATH=str(self.bin)+os.pathsep+os.environ['PATH'])
        case=PostgreSQLLifecycleIntegration('test_exact_trial_origin_uses_two_market_permits_without_legacy_origin_aliasing')
        with patch.dict(os.environ,env):
            try:case.setUp();case._exercise_exact_pp_permits(THIRD_TRIAL_ORIGIN)
            finally:case.doCleanups()
        self.assertEqual(self.prior_snapshot(),before)
