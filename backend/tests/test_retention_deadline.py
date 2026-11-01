"""Writer budget failure must preserve rows and release the database lock."""
from pathlib import Path
import sys
import unittest
import sqlite3
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention
import test_retention as safety


class WriterDeadlineTests(unittest.TestCase):
    def test_global_guard_detects_null_case_and_new_strings_with_optional_index(self):
        for bad in (None, '2026-10-01t00:00:00.000000+00:00', '2026-02-30T00:00:00.000000+00:00'):
            for indexed in (False, True):
                with self.subTest(bad=bad, indexed=indexed), sqlite3.connect(':memory:') as db:
                    db.executescript('CREATE TABLE observations(id INTEGER PRIMARY KEY,market_id TEXT,kind TEXT,received_at TEXT COLLATE NOCASE); CREATE TABLE stream_events(received_at TEXT);')
                    if indexed:
                        db.execute('CREATE INDEX observations_market_kind_received ON observations(market_id,kind,received_at)')
                    good='2026-10-01T00:00:00.000000+00:00'
                    db.execute('INSERT INTO observations VALUES(1,?,?,?)',('m','book',good));db.commit()
                    cache=retention._validated_timestamp_cache(db)
                    db.execute('INSERT INTO observations VALUES(2,?,?,?)',('m','book',bad));db.commit()
                    db.execute('BEGIN IMMEDIATE')
                    with self.assertRaises(retention.RetentionError):
                        retention._validate_current_timestamps(db,cache)
                    db.rollback()

    def test_global_guard_validates_unknown_only_once(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE observations(received_at TEXT); CREATE TABLE stream_events(received_at TEXT);')
            cache=retention._validated_timestamp_cache(db)
            value='2026-10-01T00:00:00.000000+00:00'
            db.executemany('INSERT INTO observations VALUES(?)',[(value,)]*3);db.commit()
            seen=[];db.set_trace_callback(seen.append)
            db.execute('BEGIN IMMEDIATE')
            with patch.object(retention,'canonical_time',wraps=retention.canonical_time) as valid:
                retention._validate_current_timestamps(db,cache)
                self.assertEqual(valid.call_count,1)
                retention._validate_current_timestamps(db,cache)
                self.assertEqual(valid.call_count,1)
            db.rollback()

    def test_case_distinct_malformed_timestamp_cannot_match_validity_cache(self):
        fixture=safety.RetentionTests(methodName='test_verified_old_observations_are_eligible_and_new_are_kept')
        fixture.setUp()
        try:
            fixture.seed_observations();fixture.archive_all('observations',10)
            plan=fixture.plan();original=retention._validated_timestamp_cache
            def prepare(db):
                cache=original(db)
                db.execute("UPDATE observations SET received_at=replace(received_at,'T','t') WHERE id=1")
                db.commit()
                return cache
            with patch.object(retention,'_validated_timestamp_cache',side_effect=prepare):
                with self.assertRaises(retention.RetentionError):
                    retention.apply_retention(fixture.db,plan,fixture.config,confirm=True)
            self.assertEqual(fixture.count('observations'),30)
        finally:fixture.tearDown()

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
            self.assertIn('commit',caught.exception.phase_seconds)
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
