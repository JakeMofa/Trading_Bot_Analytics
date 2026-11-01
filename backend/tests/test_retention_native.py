"""Native timestamps must equal the existing strict contract, never bypass it."""
import importlib.util
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention
import test_retention as safety


class NativeTimestampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='generated-native-test-')
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('build_retention_native',backend/'build_retention_native.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        cls.library=Path(cls.folder.name)/'_retention_time.so'
        cls.proof=builder.build(cls.library)
        assert cls.proof['source_sha256']==retention.NATIVE_TIME_SOURCE_SHA256

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def connection(self):
        db=sqlite3.connect(':memory:')
        with patch.object(retention,'_native_library_path',return_value=self.library):
            self.assertTrue(retention._load_native_time_validator(db))
        return db

    def test_strict_parser_equivalence_calendar_types_and_mutated_strings(self):
        rng=random.Random(175)
        values=[None,0,1.5,b'2026-10-31T00:00:00+00:00','0000-01-01T00:00:00+00:00']
        for _ in range(10000):
            text=f'{rng.randrange(10000):04d}-{rng.randrange(15):02d}-{rng.randrange(34):02d}T{rng.randrange(26):02d}:{rng.randrange(62):02d}:{rng.randrange(62):02d}'
            values.append(text+('.123456' if rng.randrange(2) else '')+'+00:00')
        for year in (1,4,100,400,1600,1900,2000,2100,9999):
            for month in range(1,13):
                for day in range(1,32):
                    values.extend(f'{year:04d}-{month:02d}-{day:02d}T23:59:59{fraction}+00:00' for fraction in ('','.000001'))
        good='2026-10-31T23:59:59.123456+00:00'
        values.extend(good[:i]+ch+good[i+1:] for i in range(len(good)) for ch in ('\x00','t','９','-','Z','9'))
        values.extend(good[:i] for i in range(len(good)))
        with self.connection() as db:
            for value in values:
                try:retention.canonical_time(value);expected=1
                except retention.RetentionError:expected=0
                actual=db.execute('SELECT retention_raw_time_valid_v1(?)',(value,)).fetchone()[0]
                self.assertEqual(actual,expected,repr(value))
        db.close()

    def test_native_loader_pins_artifact_and_disables_extension_loading(self):
        with self.connection() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('SELECT load_extension(?)',(str(self.library),))
        db.close()
        with tempfile.TemporaryDirectory() as folder:
            lib=Path(folder)/'_retention_time.so';lib.write_bytes(self.library.read_bytes());lib.chmod(0o644)
            meta=lib.with_suffix('.json');proof=dict(self.proof);proof['source_sha256']='0'*64
            meta.write_text(json.dumps(proof));meta.chmod(0o644)
            db=sqlite3.connect(':memory:')
            try:
                with patch.object(retention,'_native_library_path',return_value=lib):
                    with self.assertRaises(retention.RetentionError):retention._load_native_time_validator(db)
                    meta.write_text(json.dumps(self.proof));lib.write_bytes(b'wrong binary')
                    with self.assertRaises(retention.RetentionError):retention._load_native_time_validator(db)
                    lib.unlink();lib.symlink_to(self.library)
                    with self.assertRaises(retention.RetentionError):retention._load_native_time_validator(db)
            finally:db.close()

    def test_native_path_rechecks_null_unrelated_and_updated_rows_inside_transaction(self):
        db=sqlite3.connect(':memory:')
        try:
            db.executescript('CREATE TABLE observations(received_at TEXT); CREATE TABLE stream_events(received_at TEXT);')
            with patch.object(retention,'_native_library_path',return_value=self.library):
                cache=retention._validated_timestamp_cache(db)
            self.assertTrue(cache.native)
            for table in ('observations','stream_events'):
                db.execute(f'INSERT INTO {table} VALUES(NULL)');db.commit();db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(retention.RetentionError):retention._validate_current_timestamps(db,cache)
                db.rollback();db.execute(f'DELETE FROM {table}');db.commit()
                db.execute(f'INSERT INTO {table} VALUES(?)',('2026-10-31T00:00:00+00:00',));db.commit()
                db.execute('BEGIN IMMEDIATE');retention._validate_current_timestamps(db,cache);db.commit()
                db.execute(f'UPDATE {table} SET received_at=?',('2026-02-30T00:00:00+00:00',));db.commit()
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(retention.RetentionError):retention._validate_current_timestamps(db,cache)
                db.rollback();db.execute(f'DELETE FROM {table}');db.commit()
        finally:db.close()

    def test_existing_retention_safety_suite_with_native_validator(self):
        # Re-run all existing archive, mutation-race, protected-reference and
        # exact-identity cases using the native path, including tiny batches.
        names=unittest.defaultTestLoader.getTestCaseNames(safety.RetentionTests)
        with patch.object(retention,'_native_library_path',return_value=self.library):
            for name in names:
                with self.subTest(case=name):
                    case=safety.RetentionTests(methodName=name);case.setUp()
                    try:getattr(case,name)()
                    finally:case.tearDown()


if __name__=='__main__':unittest.main()
