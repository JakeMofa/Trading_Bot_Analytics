"""Dense archive coverage can use a freshly verified unique integer capacity."""
import sqlite3
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention


class RangeCapacityTests(unittest.TestCase):
    def snapshot(self,definition):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        db.execute(definition)
        snapshot=object.__new__(retention._ValidationSnapshot)
        snapshot.db=db;snapshot.dataset='observations'
        return snapshot

    def test_dense_integer_capacity_avoids_payload_scan_but_preserves_sparse_check(self):
        s=self.snapshot('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
        s.range_count=Mock(side_effect=AssertionError('payload scan'))
        self.assertFalse(s.range_exceeds_manifest((195001,),(198243,),3243))
        s.range_count=Mock(return_value=3243)
        self.assertTrue(s.range_exceeds_manifest((195001,),(198243,),3242))
        s.range_count.assert_called_once_with((195001,),(198243,))

    def test_non_rowid_primary_keys_fall_back_even_when_declared_integer(self):
        for definition in (
            'CREATE TABLE observations(id INTEGER PRIMARY KEY DESC,payload TEXT)',
            'CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT) WITHOUT ROWID',
            'CREATE TABLE observations(id INT PRIMARY KEY,payload TEXT)',
            'CREATE TABLE observations(id INTEGER,payload TEXT,PRIMARY KEY(id,payload))',
            'CREATE TABLE observations(id INTEGER,payload TEXT)',
        ):
            with self.subTest(definition=definition):
                s=self.snapshot(definition);s.range_count=Mock(return_value=4)
                self.assertTrue(s.range_exceeds_manifest((1,),(3,),3))
                s.range_count.assert_called_once()

    def test_schema_is_freshly_rechecked_after_replacement(self):
        s=self.snapshot('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
        s.range_count=Mock(return_value=4)
        self.assertFalse(s.range_exceeds_manifest((1,),(3,),3))
        s.db.execute('DROP TABLE observations')
        s.db.execute('CREATE TABLE observations(id INTEGER,payload TEXT)')
        self.assertTrue(s.range_exceeds_manifest((1,),(3,),3))

    def test_stream_ranges_always_use_original_current_count(self):
        s=self.snapshot('CREATE TABLE observations(id INTEGER PRIMARY KEY)')
        s.dataset='stream_events';s.range_count=Mock(return_value=4)
        self.assertTrue(s.range_exceeds_manifest(('a',),('z',),3))

    def test_deleted_dense_rows_and_late_reinsert_cannot_exceed_integer_capacity(self):
        s=self.snapshot('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
        s.db.executemany('INSERT INTO observations VALUES(?,?)',[(1,'a'),(3,'c')])
        self.assertFalse(s.range_exceeds_manifest((1,),(3,),3))
        s.db.execute("INSERT INTO observations VALUES(2,'late')")
        self.assertFalse(s.range_exceeds_manifest((1,),(3,),3))
        self.assertEqual(s.range_count((1,),(3,)),3)
        with self.assertRaises(sqlite3.IntegrityError):s.db.execute("INSERT INTO observations VALUES(2,'duplicate')")
