"""Bounded exact initial-A setup. Native cases use disposable test DSNs only."""
from datetime import datetime,timezone
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.lifecycle import LifecycleHold,LifecycleRepository,RotationPolicy
from postgres.pp_trial_prepare import prepare,main
from postgres.rehearsal_profile import TRIAL_ORIGIN

class PrepareControls(unittest.TestCase):
    def test_unexecuted_or_wrong_scope_does_not_open_database(self):
        class Repo:
            environment='production'
        for execute in (False,True):
            with self.assertRaises(LifecycleHold):prepare(Repo(),str(uuid.uuid4()),'a'*40,execute=execute)
        with patch('postgres.lifecycle_worker.read_dsn') as secret:
            with self.assertRaises(LifecycleHold):main(['--initial-a',str(uuid.uuid4()),'--source-sha','a'*40])
            secret.assert_not_called()

NATIVE=all(os.getenv('TRADEBOT_TEST_'+role+'_DSN') for role in ('LIFECYCLE','MIGRATOR'))
@unittest.skipUnless(NATIVE,'disposable native PostgreSQL DSNs required')
class NativePrepare(unittest.TestCase):
    def test_exact_allocated_a_preserves_historic_ab_and_refuses_stale_or_used_leases(self):
        from psycopg import sql
        from postgres.connection import connect,connect_migrator
        owner=lambda:connect_migrator(os.environ['TRADEBOT_TEST_MIGRATOR_DSN'])
        repo=LifecycleRepository(lambda:connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']))
        old='pp-live-pp';anchor=str(uuid.uuid4());children=[]
        with owner() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=ANY(%s)',([old,TRIAL_ORIGIN],)).fetchone())
        def cleanup():
            with owner() as db:
                for child in children:
                    db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(sql.Identifier(child)))
                for table in ('archive.checkpoints','ops.writer_state','archive.generations'):
                    db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=ANY(%s)').format(sql.Identifier(*table.split('.'))),([old,TRIAL_ORIGIN],))
        self.addCleanup(cleanup)
        a=repo.bootstrap(old);children.append(a['partition_name'])
        b=repo.switch_if_due(old,RotationPolicy(1))
        children.append(repo.generation(b['generation_id'])['partition_name'])
        with owner() as db:
            before=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s ORDER BY generation_id',(old,)).fetchall()
            # Even an expired stored-enabled lease must be explicitly stopped.
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",(str(uuid.uuid4()),old))
        with self.assertRaisesRegex(LifecycleHold,'durably OFF'):
            prepare(repo,anchor,'a'*40,execute=True)
        with owner() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s',(TRIAL_ORIGIN,)).fetchone())
        repo.disable_collector(old)
        result=prepare(repo,anchor,'a'*40,execute=True)
        children.append('events_g_'+anchor.replace('-',''))
        self.assertEqual((result['generation_id'],result['origin_id'],result['collector_enabled']),(anchor,TRIAL_ORIGIN,False))
        self.assertEqual(prepare(repo,anchor,'a'*40,execute=True),result)
        for initial,source in ((str(uuid.uuid4()),'a'*40),(anchor,'b'*40)):
            with self.assertRaisesRegex(LifecycleHold,'already exists'):
                prepare(repo,initial,source,execute=True)
        with owner() as db:
            self.assertEqual(db.execute('SELECT * FROM archive.generations WHERE origin_id=%s ORDER BY generation_id',(old,)).fetchall(),before)
            writer=db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(TRIAL_ORIGIN,)).fetchone()
            self.assertEqual(writer['epoch'],1)
            self.assertFalse(writer['collector_enabled'])
            self.assertIsNone(writer['collector_session_id'])
            db.execute('UPDATE ops.writer_state SET epoch=2 WHERE origin_id=%s',(TRIAL_ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'already exists'):
            prepare(repo,anchor,'a'*40,execute=True)
