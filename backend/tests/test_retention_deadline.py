"""Writer budget failure must preserve rows and release the database lock."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention
import test_retention as safety


class WriterDeadlineTests(unittest.TestCase):
    def test_slow_commit_reports_committed_rows_instead_of_claiming_rollback(self):
        fixture=safety.RetentionTests(methodName='test_verified_old_observations_are_eligible_and_new_are_kept')
        fixture.setUp()
        try:
            fixture.seed_observations();fixture.archive_all('observations',10)
            plan=fixture.plan();before=fixture.count('observations');clock=[0.0];locked=[False]
            def trace(sql):
                if sql=='BEGIN IMMEDIATE':locked[0]=True
                elif sql=='COMMIT' and locked[0]:clock[0]=1.0
            fixture.db.set_trace_callback(trace)
            with patch.object(retention.time,'monotonic',side_effect=lambda:clock[0]):
                with self.assertRaises(retention.RetentionBudgetError) as caught:
                    retention.apply_retention(fixture.db,plan,retention.RetentionConfig(True,48,3),confirm=True)
            self.assertEqual(caught.exception.phase,'commit')
            self.assertEqual(caught.exception.committed_rows,3)
            self.assertEqual(before-fixture.count('observations'),3)
            self.assertFalse(fixture.db.in_transaction)
        finally:fixture.tearDown()

    def test_validation_deadline_rolls_back_and_drops_private_temp_state(self):
        fixture=safety.RetentionTests(methodName='test_verified_old_observations_are_eligible_and_new_are_kept')
        fixture.setUp()
        try:
            fixture.seed_observations();fixture.archive_all('observations',10)
            plan=fixture.plan();before=fixture.count('observations')
            with patch.object(retention,'MAX_WRITE_SECONDS',0):
                with self.assertRaises(retention.RetentionBudgetError) as caught:
                    retention.apply_retention(fixture.db,plan,fixture.config,confirm=True)
            self.assertEqual(caught.exception.committed_rows,0)
            self.assertEqual(fixture.count('observations'),before)
            self.assertFalse(fixture.db.in_transaction)
            self.assertFalse(fixture.db.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'retention_%'").fetchall())
        finally:fixture.tearDown()


if __name__=='__main__':unittest.main()
