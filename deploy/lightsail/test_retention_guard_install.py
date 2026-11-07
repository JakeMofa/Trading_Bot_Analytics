import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('guard_install',Path(__file__).with_name('install_retention_guards.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
GUARDS=Path(__file__).resolve().parents[2]/'backend/app/retention_timestamp_guards.py'


class GuardInstallTests(unittest.TestCase):
    def fixture(self,path,invalid=False):
        db=sqlite3.connect(path)
        db.executescript('CREATE TABLE observations(id INTEGER PRIMARY KEY,received_at TEXT);CREATE TABLE stream_events(source,event_id,received_at TEXT,PRIMARY KEY(source,event_id));')
        stamp='invalid' if invalid else '2026-10-01T00:00:00.000000+00:00'
        db.execute('INSERT INTO observations VALUES(1,?)',(stamp,));db.execute("INSERT INTO stream_events VALUES('coinbase','0007',?)",(stamp,));db.commit();db.close()
    def test_one_explicit_transaction_preserves_raw_rows_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            first=module.install(p,GUARDS,2);second=module.install(p,GUARDS,2)
            self.assertEqual(first['status'],'PASS');self.assertTrue(first['committed'])
            self.assertEqual(second['status'],'PASS');self.assertTrue(all(second['preexisting'].values()))
            db=sqlite3.connect(p)
            try:self.assertEqual(db.execute('SELECT source,event_id FROM stream_events').fetchall(),[('coinbase','0007')])
            finally:db.close()
    def test_invalid_row_rolls_back_both_indexes_without_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p,True)
            result=module.install(p,GUARDS,2)
            self.assertEqual(result['status'],'STOP');self.assertFalse(result['committed'])
            self.assertEqual(result['reason'],'invalid_current_raw_timestamp')
            self.assertTrue(all(not v['present'] for v in result['schema_after'].values()))
            db=sqlite3.connect(p)
            try:self.assertEqual(db.execute('SELECT received_at FROM observations').fetchone()[0],'invalid')
            finally:db.close()
    def test_storage_reserve_stops_without_committing(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            with patch.object(module,'CAP_BYTES',1):result=module.install(p,GUARDS,2)
            self.assertEqual(result['status'],'STOP');self.assertEqual(result['reason'],'storage_reserve')
            self.assertFalse(result['committed'])

    def test_commit_overrun_preserves_and_reports_committed_indexes(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            original=module.sqlite3.connect;clock=[0.0]
            class Connection:
                def __init__(self,db):self.db=db
                def __getattr__(self,name):return getattr(self.db,name)
                def commit(self):self.db.commit();clock[0]=3
            def connect(*args,**kwargs):
                db=original(*args,**kwargs)
                return db if kwargs.get('uri') else Connection(db)
            with patch.object(module.sqlite3,'connect',side_effect=connect),patch.object(module.time,'monotonic',side_effect=lambda:clock[0]):
                result=module.install(p,GUARDS,2)
            self.assertEqual(result['status'],'STOP');self.assertTrue(result['committed'])
            self.assertEqual(result['reason'],'committed_after_deadline')
            self.assertTrue(all(v['present'] for v in result['schema_after'].values()))

    def test_deadline_stops_before_schema_change(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            result=module.install(p,GUARDS,-1)
            self.assertEqual(result['status'],'STOP');self.assertFalse(result['committed'])
            self.assertTrue(all(not v['present'] for v in result['schema_after'].values()))


if __name__=='__main__':unittest.main()
