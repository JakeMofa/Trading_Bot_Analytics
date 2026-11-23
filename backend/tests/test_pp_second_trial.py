"""Exact second trial qualification; preserve archived first-trial data and authority."""
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.cloud_origin_binding import (LEGACY_ORIGIN,TRIAL_ORIGIN,NEXT_TRIAL_ORIGIN,
    TRIAL_WRITER,TRIAL_READER,NEXT_TRIAL_WRITER,NEXT_TRIAL_READER,cloud_binding)
from postgres.cloud_runtime_profile import selected_cloud_origin,cloud_files,require_trial_files
from postgres.rehearsal_profile import cycle_anchor,CYCLE_LEASE_CAP_SECONDS
from postgres.lifecycle import LifecycleHold
import test_pp_initial_trial_drain as initial_fixture


class SecondTrialControls(unittest.TestCase):
    def test_explicit_profiles_preserve_old_roles_and_require_cycle_identity(self):
        self.assertEqual(cloud_binding(TRIAL_ORIGIN).writer_role,TRIAL_WRITER)
        self.assertEqual(cloud_binding(TRIAL_ORIGIN).reader_role,TRIAL_READER)
        self.assertEqual(cloud_binding(NEXT_TRIAL_ORIGIN).writer_role,NEXT_TRIAL_WRITER)
        self.assertEqual(cloud_binding(NEXT_TRIAL_ORIGIN).reader_role,NEXT_TRIAL_READER)
        self.assertNotEqual(cloud_binding(TRIAL_ORIGIN).raw_prefix,cloud_binding(NEXT_TRIAL_ORIGIN).raw_prefix)
        anchor=str(uuid.uuid4())
        env=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
            TRADEBOT_ORIGIN_ID=NEXT_TRIAL_ORIGIN,TRADEBOT_PP_CYCLE_INITIAL_A=anchor,
            TRADEBOT_PP_WINDOW_POLICY='two-official-markets-cycle')
        self.assertEqual(selected_cloud_origin(env),NEXT_TRIAL_ORIGIN)
        self.assertEqual(cycle_anchor(env),anchor)
        for changes in ({'TRADEBOT_ORIGIN_ID':'pp-live-pp-trial-20261119-06'},
                        {'TRADEBOT_PP_WINDOW_POLICY':'two-official-markets'},
                        {'TRADEBOT_ENVIRONMENT':'production'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):selected_cloud_origin(env|changes)
        require_trial_files(env|cloud_files(NEXT_TRIAL_ORIGIN),NEXT_TRIAL_ORIGIN,structured=True,storage=True)
        with self.assertRaises(ValueError):require_trial_files(env,NEXT_TRIAL_ORIGIN,structured=True)

    def test_second_transport_rejects_first_roles_and_retains_reader_prohibition(self):
        from postgres.history_v2_transport import HistoryV2PostgresTransport
        generation=str(uuid.uuid4())
        for role in (TRIAL_READER,TRIAL_WRITER,'tradebot_pp_history'):
            with self.subTest(role=role),self.assertRaises(ValueError):
                HistoryV2PostgresTransport(lambda **kw:None,origin_id=NEXT_TRIAL_ORIGIN,
                    generation_id=generation,expected_role=role,expected_database='postgres')
        reader=HistoryV2PostgresTransport(lambda **kw:None,origin_id=NEXT_TRIAL_ORIGIN,
            generation_id=generation,expected_role=NEXT_TRIAL_READER,expected_database='postgres',retain_revisions=True)
        self.assertTrue(reader._read_only)
        writer=HistoryV2PostgresTransport(lambda **kw:None,origin_id=NEXT_TRIAL_ORIGIN,
            generation_id=generation,expected_role=NEXT_TRIAL_WRITER,expected_database='postgres',
            retain_revisions=True,sync_barriers=True)
        self.assertTrue(writer.sync_barriers)


class SecondTrialNative(unittest.TestCase):
    setUpClass=classmethod(initial_fixture.InitialSealNative.setUpClass.__func__)
    tearDownClass=classmethod(initial_fixture.InitialSealNative.tearDownClass.__func__)
    admin=classmethod(initial_fixture.InitialSealNative.admin.__func__)
    setUp=initial_fixture.InitialSealNative.setUp
    fixture_on=initial_fixture.InitialSealNative.fixture_on
    cleanup=initial_fixture.InitialSealNative.cleanup

    @property
    def migrator_dsn(self):
        return f'host={self.socket} user=tradebot_migrator dbname=tradebot_pp'

    def old_snapshot(self):
        from psycopg import sql
        with self.admin() as db:
            result=[]
            for table in ('archive.generations','archive.checkpoints','archive.manifests','ops.writer_state',
                          'ops.outbox','ops.dedup','core.current_prices','raw.events'):
                rows=db.execute(sql.SQL('SELECT to_jsonb(t)::text AS row FROM {} t '
                    'WHERE origin_id=ANY(%s) ORDER BY to_jsonb(t)::text').format(
                    sql.Identifier(*table.split('.'))),([LEGACY_ORIGIN,TRIAL_ORIGIN],)).fetchall()
                result.append(rows)
            return result

    def preserve_initial(self):
        from postgres.pp_initial_trial_drain import seal_initial_a
        from postgres.pp_sealed_archive import cycle
        seal_initial_a(self.repo,self.target,execute=True)
        cycle(self.repo,self.raw,origin=TRIAL_ORIGIN)
        self.assertEqual(self.repo.generation(self.anchor)['state'],'verified')

    def prepare_second(self):
        from postgres.pp_trial_prepare import prepare
        self.second=str(uuid.uuid4());self.origins.append(NEXT_TRIAL_ORIGIN)
        result=prepare(self.repo,self.second,'c'*40,execute=True,origin_id=NEXT_TRIAL_ORIGIN)
        self.children.append(self.second)
        return result

    def test_fresh_second_preparation_preserves_old_archived_a_and_cannot_reset_it(self):
        from postgres.pp_trial_prepare import prepare
        self.preserve_initial();before=self.old_snapshot()
        result=self.prepare_second()
        self.assertEqual((result['origin_id'],result['generation_id'],result['collector_enabled']),
                         (NEXT_TRIAL_ORIGIN,self.second,False))
        self.assertEqual(prepare(self.repo,self.second,'c'*40,execute=True,origin_id=NEXT_TRIAL_ORIGIN),result)
        for origin,anchor in ((TRIAL_ORIGIN,self.anchor),(TRIAL_ORIGIN,str(uuid.uuid4())),
                             (NEXT_TRIAL_ORIGIN,str(uuid.uuid4()))):
            with self.subTest(origin=origin),self.assertRaises(LifecycleHold):
                prepare(self.repo,anchor,'c'*40,execute=True,origin_id=origin)
        with self.factory() as db:
            for table in ('raw.events','ops.outbox'):
                self.assertEqual(db.execute('SELECT count(*) AS n FROM '+table+' WHERE origin_id=%s',
                                            (NEXT_TRIAL_ORIGIN,)).fetchone()['n'],0)
        self.assertEqual(self.old_snapshot(),before)

    def test_global_collector_fence_both_directions_and_second_requires_anchor(self):
        self.preserve_initial();self.prepare_second()
        legacy=self.repo.collector_state(LEGACY_ORIGIN)['generation_id']
        with self.assertRaisesRegex(LifecycleHold,'two-leg'):
            self.repo.enable_collector(NEXT_TRIAL_ORIGIN,session_id=str(uuid.uuid4()),
                expected_generation_id=self.second,max_seconds=60)
        with patch('postgres.lifecycle.pp_space.sample',return_value={'space_hold':None}):
            self.repo.enable_collector(LEGACY_ORIGIN,session_id=str(uuid.uuid4()),
                expected_generation_id=legacy,max_seconds=60)
        with patch('postgres.lifecycle.require_cycle_alignment'), patch('postgres.lifecycle.pp_space.sample',return_value={'space_hold':None}):
            with self.assertRaisesRegex(LifecycleHold,'another PP'):
                self.repo.enable_collector(NEXT_TRIAL_ORIGIN,session_id=str(uuid.uuid4()),
                    expected_generation_id=self.second,max_seconds=CYCLE_LEASE_CAP_SECONDS,rehearsal_anchor=self.second)
            self.repo.disable_collector(LEGACY_ORIGIN)
            self.repo.enable_collector(NEXT_TRIAL_ORIGIN,session_id=str(uuid.uuid4()),
                expected_generation_id=self.second,max_seconds=CYCLE_LEASE_CAP_SECONDS,rehearsal_anchor=self.second)
            with self.assertRaisesRegex(LifecycleHold,'another PP'):
                self.repo.enable_collector(LEGACY_ORIGIN,session_id=str(uuid.uuid4()),
                    expected_generation_id=legacy,max_seconds=60)
        self.repo.disable_collector(NEXT_TRIAL_ORIGIN)

    def test_second_actual_market_pair_cycle_preserves_old_archived_origin(self):
        from test_postgres_cycle_integration import NativeCycleTests
        self.preserve_initial();before=self.old_snapshot()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,
            TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp')
        case=NativeCycleTests('test_exact_finite_cycle_retained_rejection_and_successor_writes')
        with patch.dict(os.environ,env):
            try:case._exercise_cycle(origin=NEXT_TRIAL_ORIGIN)
            finally:case.doCleanups()
        self.assertEqual(self.old_snapshot(),before)

    def test_second_exact_two_handoffs_use_real_sql_retirement_gates(self):
        from test_postgres_lifecycle_integration import PostgreSQLLifecycleIntegration
        self.preserve_initial();before=self.old_snapshot()
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,
            TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp',PATH=str(self.bin)+os.pathsep+os.environ['PATH'])
        case=PostgreSQLLifecycleIntegration('test_exact_trial_origin_uses_two_market_permits_without_legacy_origin_aliasing')
        with patch.dict(os.environ,env):
            try:
                case.setUp()
                case._exercise_exact_pp_permits(NEXT_TRIAL_ORIGIN)
            finally:case.doCleanups()
        self.assertEqual(self.old_snapshot(),before)
