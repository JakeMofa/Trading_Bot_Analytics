from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention
import retention_trial as trial
import retention_recovery as recovery
import test_retention as fixtures
CUTOFF_DT=fixtures.CUTOFF_DT
ts=fixtures.ts


class ProvedTrialTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RetentionTests();self.fixture.setUp();self.db=self.fixture.db
        self.db.execute('PRAGMA foreign_keys=ON')
        self.fixture.seed_observations()
        self.db.execute('CREATE TABLE prediction_context_links(outcome_observation_id INTEGER REFERENCES observations(id))')
        self.db.execute('INSERT INTO prediction_context_links VALUES(1)');self.db.commit()
        self.fixture.archive_all('observations',100)
        cloud=self.fixture.cloud;cloud.download_bytes=lambda bucket,path:cloud.uploads[(bucket,path)]
        self.proof=recovery.prepare_scope(self.db,cloud,cloud.manifests,'observations',ts(CUTOFF_DT),limit=3)
        self.db.execute('BEGIN');retention.timestamp_guards.create_indexes(self.db);self.db.commit()
    def tearDown(self):self.fixture.tearDown()
    def test_exact_committed_identity_log_does_not_inflate_total_changes(self):
        result=trial.apply_proved_scope(self.db,self.proof)
        self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['committed_rows'],3)
        self.assertEqual(result['deleted_identities'],[(2,),(3,),(4,)])
        self.assertEqual(result['apply']['datasets']['observations']['deleted_rows'],3)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM observations WHERE id=1').fetchone())
        self.assertEqual(self.db.execute('SELECT count(*) FROM predictions').fetchone()[0],1)
        self.assertEqual(result['affected_fk_tables_checked'],['prediction_context_links'])
    def test_mutation_after_warming_aborts_and_does_not_claim_callbacks_committed(self):
        warm=trial.warm_scope
        def mutate(*args):
            warm(*args);self.db.execute("UPDATE observations SET payload='changed' WHERE id=3");self.db.commit()
        with patch.object(trial,'warm_scope',side_effect=mutate):result=trial.apply_proved_scope(self.db,self.proof)
        self.assertEqual(result['status'],'STOP');self.assertEqual(result['committed_rows'],0)
        self.assertEqual(result['deleted_identities'],[])
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],30)
    def test_late_reference_is_freshly_protected_and_skip_is_reported(self):
        warm=trial.warm_scope
        def reference(*args):
            warm(*args);self.db.execute('INSERT INTO prediction_context_links VALUES(2)');self.db.commit()
        with patch.object(trial,'warm_scope',side_effect=reference):result=trial.apply_proved_scope(self.db,self.proof)
        self.assertEqual(result['status'],'PASS',result);self.assertEqual(result['committed_rows'],2)
        self.assertEqual(result['skipped_rows'],1);self.assertEqual(result['deleted_identities'],[(3,),(4,)])
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM observations WHERE id=2').fetchone())
    def test_late_commit_overrun_reports_rows_without_restoring_data(self):
        def overrun(*args,**kwargs):
            self.db.execute('BEGIN IMMEDIATE')
            self.db.executemany('DELETE FROM observations WHERE id=?',[(2,),(3,),(4,)])
            self.db.commit()
            error=retention.RetentionBudgetError('commit',.6,3)
            error.retention_progress={'datasets':{'observations':{'committed_rows_seen':3}}}
            raise error
        with patch.object(retention,'apply_retention',side_effect=overrun):result=trial.apply_proved_scope(self.db,self.proof)
        self.assertEqual(result['status'],'STOP');self.assertEqual(result['committed_rows'],3)
        self.assertEqual(result['deleted_identities'],[(2,),(3,),(4,)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],27)

    def test_runtime_authorizer_denies_structured_delete(self):
        def wrong(*args,**kwargs):self.db.execute('DELETE FROM predictions')
        with patch.object(retention,'apply_retention',side_effect=wrong):result=trial.apply_proved_scope(self.db,self.proof)
        self.assertEqual(result['status'],'STOP');self.assertEqual(result['committed_rows'],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM predictions').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],30)


if __name__=='__main__':unittest.main()
