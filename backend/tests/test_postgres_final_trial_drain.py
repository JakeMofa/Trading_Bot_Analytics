"""Terminal02 archive maintenance uses real generated two-leg retirement gates."""
from dataclasses import replace
from datetime import datetime,timezone
import os
from pathlib import Path
import sys
import shutil
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.pp_final_trial_drain import SealTarget,seal_final_a,audit_final_a,CONSUMER,main
from postgres.cloud_origin_binding import NEXT_TRIAL_ORIGIN as ORIGIN,NEXT_TRIAL_READER,cloud_binding
from postgres.lifecycle import LifecycleHold
from postgres.archive_codec import ArchiveUnavailable,ArchiveIntegrityError,encoded
import test_pp_second_trial as second_fixture


class FinalControls(unittest.TestCase):
    def test_initial_a_and_default_off_are_rejected_without_credentials(self):
        anchor=str(uuid.uuid4());fresh=str(uuid.uuid4())
        target=SealTarget(fresh,anchor,4,2,1,'a'*40,str(uuid.uuid4()),'b'*40)
        target.validate()
        for change in ({'generation':anchor},{'trial_source':'main'},{'outbox_count':0},{'writer_epoch':True}):
            with self.subTest(change=change),self.assertRaises((ValueError,LifecycleHold)):
                replace(target,**change).validate()
        class Repo:environment='preprod'
        with self.assertRaises(LifecycleHold):seal_final_a(Repo(),target)
        with patch('postgres.pp_final_trial_drain.private_dsn') as secret:
            self.assertEqual(main(['--generation',fresh,'--initial-a',anchor,'--writer-epoch','4',
                '--raw-count','2','--outbox-count','1','--trial-source','a'*40,
                '--operation',target.operation,'--source','b'*40]),1)
            secret.assert_not_called()


class FinalNative(second_fixture.SecondTrialNative):
    # Inherit the already-owned temp PG17 harness, not unrelated test cases.
    test_fresh_second_preparation_preserves_old_archived_a_and_cannot_reset_it=None
    test_global_collector_fence_both_directions_and_second_requires_anchor=None
    test_second_actual_market_pair_cycle_preserves_old_archived_origin=None
    test_second_exact_two_handoffs_use_real_sql_retirement_gates=None

    @classmethod
    def setUpClass(cls):
        cls.external=all(os.environ.get('TRADEBOT_TEST_'+role+'_DSN')
                         for role in ('LIFECYCLE','APP','MIGRATOR','READER'))
        if cls.external:
            if (os.environ.get('TRADEBOT_DATA_MODE'),os.environ.get('TRADEBOT_ORIGIN_ID'))!=('generated','generated-pp'):
                raise RuntimeError('final seal tests require owned generated scope')
            cls.lifecycle_dsn=os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']
            cls.app_dsn=os.environ['TRADEBOT_TEST_APP_DSN']
            cls.migrator_dsn=os.environ['TRADEBOT_TEST_MIGRATOR_DSN']
            cls.reader_dsn=os.environ['TRADEBOT_TEST_READER_DSN']
            psql=shutil.which('psql')
            if not psql:raise RuntimeError('real retirement issuer requires psql')
            cls.bin=Path(psql).parent
        else:
            super().setUpClass()
            cls.reader_dsn=f'host={cls.socket} user=tradebot_reader dbname=tradebot_pp'

    @classmethod
    def admin(cls,database='tradebot_pp'):
        if cls.external:
            if database!='tradebot_pp':raise ValueError('exact owned PP test database required')
            from postgres.connection import connect_migrator
            return connect_migrator(cls.migrator_dsn,environment='preprod')
        return super().admin(database)

    @classmethod
    def tearDownClass(cls):
        if not cls.external:super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.preserve_initial();self.retained_before=self.old_snapshot()
        from test_postgres_lifecycle_integration import PostgreSQLLifecycleIntegration
        from postgres.pp_trial_prepare import prepare
        from postgres.config import Settings
        from postgres.store import Store
        from postgres.active_structured import ActiveStructuredWorker
        env=dict(TRADEBOT_TEST_LIFECYCLE_DSN=self.lifecycle_dsn,TRADEBOT_TEST_APP_DSN=self.app_dsn,
            TRADEBOT_TEST_MIGRATOR_DSN=self.migrator_dsn,TRADEBOT_DATA_MODE='generated',TRADEBOT_ORIGIN_ID='generated-pp',
            PATH=str(self.bin)+os.pathsep+os.environ['PATH'])
        self.case=PostgreSQLLifecycleIntegration('test_exact_trial_origin_uses_two_market_permits_without_legacy_origin_aliasing')
        def cleanup_case():
            with patch.dict(os.environ,env):self.assertTrue(self.case.doCleanups())
        self.addCleanup(cleanup_case)
        with patch.dict(os.environ,env):
            self.case.setUp()
            def prepared(origin,*args):
                anchor=str(uuid.uuid4())
                prepare(self.case.repository,anchor,'a'*40,execute=True,origin_id=origin)
                with patch('postgres.lifecycle.require_cycle_alignment'),patch('postgres.lifecycle.pp_space.sample',return_value={'space_hold':None}):
                    self.case.repository.enable_collector(origin,session_id=str(uuid.uuid4()),expected_generation_id=anchor,
                        max_seconds=6600,rehearsal_anchor=anchor)
                return self.case.repository.generation(anchor)
            from postgres.lifecycle import RotationPolicy
            def rotate():
                result=self.case.repository.switch_if_due(ORIGIN,RotationPolicy(1))
                self.assertEqual(result['status'],'switched')
                return result
            with patch.object(self.case.repository,'bootstrap',side_effect=prepared), \
                    patch.object(self.case,'rotate',side_effect=rotate):
                self.case._exercise_exact_pp_permits(ORIGIN)
        self.final_store=Store(Settings(environment='preprod',data_mode='pp_live',origin_id=ORIGIN,dsn=self.app_dsn))
        self.final_store.ingest(self.event(9001))
        self.archive=self.case.transport
        ActiveStructuredWorker(self.repo,self.archive,origin_id=ORIGIN).cycle(self.repo.collector_state(ORIGIN)['generation_id'])
        self.repo.disable_collector(ORIGIN)
        with self.admin() as db:
            generations=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s ORDER BY created_at,generation_id',(ORIGIN,)).fetchall()
            self.assertEqual([g['state'] for g in generations],['retired','retired','collecting'])
            final=generations[-1]['generation_id'];initial=generations[0]['generation_id']
            counts=db.execute('SELECT (SELECT count(*) FROM raw.events WHERE generation_id=%s) AS raw, '
                              '(SELECT count(*) FROM ops.outbox WHERE generation_id=%s) AS outbox',(final,final)).fetchone()
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.pp_retirement_permits WHERE sealed_id=ANY(%s) AND used_at IS NOT NULL',
                ([g['generation_id'] for g in generations[:2]],)).fetchone()['n'],2)
        self.target=SealTarget(final,initial,self.repo.collector_state(ORIGIN)['epoch'],counts['raw'],counts['outbox'],
                               'a'*40,str(uuid.uuid4()),'b'*40)
        self.addCleanup(self.cleanup_final_sources)

    def cleanup_final_sources(self):
        with self.admin() as db:
            for table in ('ops.outbox','ops.dedup','core.current_prices'):
                db.execute('DELETE FROM '+table+' WHERE origin_id=%s',(ORIGIN,))

    def final_state(self):
        with self.admin() as db:
            return (db.execute('SELECT * FROM archive.generations WHERE origin_id=%s ORDER BY created_at',(ORIGIN,)).fetchall(),
                db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(ORIGIN,)).fetchall(),
                db.execute('SELECT * FROM raw.events WHERE origin_id=%s ORDER BY source,event_id',(ORIGIN,)).fetchall(),
                db.execute('SELECT * FROM ops.outbox WHERE origin_id=%s ORDER BY id',(ORIGIN,)).fetchall())

    def test_final_seal_archive_and_independent_readback_have_no_fourth_generation(self):
        from postgres.pp_sealed_archive import cycle
        from postgres.connection import connect
        from postgres.pp_retirement_verify import RetirementTransport
        before=self.final_state()
        result=seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(result['status'],'sealed_for_final_trial_archive')
        self.assertFalse(result['retirement_authorized'])
        self.assertTrue(result['two_leg_retirement_chain_verified'])
        self.assertEqual(seal_final_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        self.archive.fail_get=True
        with self.assertRaises(ArchiveUnavailable):cycle(self.repo,self.archive,origin=ORIGIN)
        self.archive.fail_get=False
        self.assertEqual(cycle(self.repo,self.archive,origin=ORIGIN)['status'],'archived')
        self.archive._reader=True;self.archive._origin_binding=cloud_binding(ORIGIN)
        raw=self.archive;generation=self.target.generation
        class Reader:
            expected_role=NEXT_TRIAL_READER
            origin_id=ORIGIN
            generation_id=generation
            def read_retirement_revisions(inner,records,*,max_bytes,timeout_seconds):
                result=raw.read_structured_authenticated(records,max_bytes=max_bytes,timeout_seconds=timeout_seconds)
                return result,max(len(encoded(records)),len(encoded(result)))
        transport=RetirementTransport(raw,Reader(),origin_id=ORIGIN,generation_id=generation)
        reader=lambda:connect(self.reader_dsn,readonly=True)
        digest=self.repo.generation(generation)['seal_hash']
        with patch('postgres.pp_retained_archive_audit.remote_preflight'):
            audited=audit_final_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
            self.assertEqual(audited['status'],'final_trial_archive_audit_verified')
            raw.corrupt_structured=True
            with self.assertRaises(ArchiveIntegrityError):
                audit_final_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
        self.assertEqual(self.old_snapshot(),self.retained_before)
        after=self.final_state()
        self.assertEqual(before[2:],after[2:])
        self.assertEqual(len(after[0]),3)
        self.assertEqual([g['state'] for g in after[0]],['retired','retired','verified'])
        self.assertEqual(after[1][0]['generation_id'],generation)
        self.assertFalse(after[1][0]['collector_enabled'])
        self.assertIsNone(after[0][-1]['retired_at'])

    def test_faults_preserve_collecting_final_a(self):
        from psycopg.types.json import Jsonb
        before=self.final_state()
        for change in ({'raw_count':self.target.raw_count+1},{'outbox_count':self.target.outbox_count+1},
                       {'writer_epoch':self.target.writer_epoch+1},{'trial_source':'c'*40}):
            with self.subTest(change=change),self.assertRaises(LifecycleHold):
                seal_final_a(self.repo,replace(self.target,**change),execute=True)
        with patch.object(self.repo,'_checkpoint',side_effect=RuntimeError('journal failure')):
            with self.assertRaises(RuntimeError):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.final_state(),before)
        with self.admin() as db:
            proof=db.execute("SELECT cursor FROM archive.checkpoints WHERE generation_id=%s AND consumer='retirement:pp-fresh-readback'",
                             (self.target.initial_a,)).fetchone()['cursor']
            db.execute("UPDATE archive.checkpoints SET cursor=%s WHERE generation_id=%s AND consumer='retirement:pp-fresh-readback'",
                       (Jsonb(proof|{'active_new_rows':0}),self.target.initial_a))
        with self.assertRaisesRegex(LifecycleHold,'two actual'):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')

    def test_missing_retirement_or_attached_predecessor_metadata_holds(self):
        from datetime import timedelta
        before=self.final_state()
        with self.admin() as db:
            prior=db.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                             (self.target.initial_a,)).fetchone()
            db.execute("UPDATE archive.generations SET retired_at=sealed_at+interval '30 minutes' WHERE generation_id=%s",
                       (self.target.initial_a,))
        with self.assertRaisesRegex(LifecycleHold,'two actual'):seal_final_a(self.repo,self.target,execute=True)
        with self.admin() as db:
            db.execute('UPDATE archive.generations SET retired_at=%s WHERE generation_id=%s',
                       (prior['retired_at'],self.target.initial_a))
            db.execute("UPDATE archive.generations SET state='verified' WHERE origin_id=%s AND slot='B'",(ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'two actual'):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')

    def test_pending_structured_and_enabled_or_expired_collector_hold(self):
        with self.admin() as db:
            db.execute('UPDATE ops.outbox SET acknowledged_at=NULL WHERE origin_id=%s',(ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'fully acknowledged'):seal_final_a(self.repo,self.target,execute=True)
        with self.admin() as db:
            db.execute('UPDATE ops.outbox SET acknowledged_at=clock_timestamp() WHERE origin_id=%s',(ORIGIN,))
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",
                       (str(uuid.uuid4()),ORIGIN))
        with self.assertRaisesRegex(LifecycleHold,'durably OFF'):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')
