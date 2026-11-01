"""Indexed invalid membership is fresh global proof, not a cached certificate."""
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import retention
import retention_timestamp_guards as guards
import test_retention as safety


class TimestampGuardTests(unittest.TestCase):
    def test_sql_predicate_matches_strict_parser_with_nul_blob_and_calendar_edges(self):
        rng=random.Random(175);values=[None,0,1.5,b'2026-10-31T00:00:00+00:00']
        for _ in range(10000):
            prefix=f'{rng.randrange(10000):04d}-{rng.randrange(15):02d}-{rng.randrange(34):02d}T{rng.randrange(26):02d}:{rng.randrange(62):02d}:{rng.randrange(62):02d}'
            values.append(prefix+('.123456' if rng.randrange(2) else '')+'+00:00')
        for year in (1,4,100,400,1600,1900,2000,2100,9999):
            for month in range(1,13):
                for day in range(1,32):
                    values.extend(f'{year:04d}-{month:02d}-{day:02d}T23:59:59{fraction}+00:00' for fraction in ('','.000001'))
        good='2026-10-31T23:59:59.123456+00:00'
        values.extend(good[:i]+x+good[i+1:] for i in range(len(good)) for x in ('\x00','９','t','Z','-','9'))
        values.extend(['2026-10-31T23:59:59+00:00\x00xxxxxx',good+'\x00',good[:-1]+'\x00'])
        db=sqlite3.connect(':memory:')
        try:
            db.executescript('CREATE TABLE observations(received_at COLLATE NOCASE);CREATE TABLE stream_events(received_at);')
            db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.commit()
            for value in values:
                try:retention.canonical_time(value);expected=False
                except retention.RetentionError:expected=True
                db.execute('DELETE FROM observations');db.execute('INSERT INTO observations VALUES(?)',(value,))
                self.assertEqual(guards.invalid_exists(db,'observations'),expected,repr(value))
        finally:db.close()

    def test_foreign_writer_updates_guard_and_definition_changes_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='generated-guard-race-') as folder:
            path=Path(folder)/'fixture.db';db=sqlite3.connect(path);other=sqlite3.connect(path)
            try:
                db.executescript('CREATE TABLE observations(received_at TEXT);CREATE TABLE stream_events(received_at TEXT);')
                db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.commit()
                marker=retention._validated_timestamp_cache(db);self.assertTrue(marker.indexed)
                # Writer imports no application/native validation code.
                other.execute('INSERT INTO stream_events VALUES(?)',('2026-02-30T00:00:00+00:00',));other.commit()
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(retention.RetentionError):retention._validate_current_timestamps(db,marker)
                db.rollback();other.execute('DELETE FROM stream_events');other.commit()
                other.execute('DROP INDEX '+guards.index_name('observations'))
                other.execute('CREATE INDEX '+guards.index_name('observations')+' ON observations(received_at) WHERE 0');other.commit()
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(ValueError):retention._validate_current_timestamps(db,marker)
                db.rollback()
            finally:other.close();db.close()

    def test_explicit_transaction_no_startup_install_and_empty_guard_query_plan(self):
        db=sqlite3.connect(':memory:')
        try:
            db.executescript('CREATE TABLE observations(received_at TEXT);CREATE TABLE stream_events(received_at TEXT);')
            with self.assertRaises(ValueError):guards.create_indexes(db)
            self.assertFalse(guards.available(db,'observations'))
            db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.commit()
            query=f'SELECT 1 FROM main.observations INDEXED BY {guards.index_name("observations")} WHERE {guards.INVALID_SQL} LIMIT 1'
            plan=[row[3] for row in db.execute('EXPLAIN QUERY PLAN '+query)]
            self.assertTrue(any(guards.index_name('observations') in row for row in plan),plan)
            self.assertFalse(guards.invalid_exists(db,'observations'))
            db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.rollback()
        finally:db.close()

    def test_split_range_count_equals_original_across_seconds_widths_and_sources(self):
        from datetime import datetime,timedelta,timezone
        db=sqlite3.connect(':memory:');rng=random.Random(175)
        try:
            db.executescript('CREATE TABLE observations(received_at TEXT);CREATE TABLE stream_events(source TEXT,event_id TEXT,received_at TEXT,PRIMARY KEY(source,event_id));CREATE INDEX stream_events_archive_cursor ON stream_events(received_at,source,event_id);')
            base=datetime(2026,10,31,23,59,55,tzinfo=timezone.utc);keys=[]
            for i in range(500):
                when=base+timedelta(seconds=rng.randrange(12),microseconds=rng.choice((0,1,100000,999999)))
                raw=when.isoformat() if i%2 else when.isoformat(timespec='microseconds')
                source=rng.choice(('aaa','coinbase','zzz'));event=str(i)
                db.execute('INSERT INTO stream_events VALUES(?,?,?)',(source,event,raw))
                keys.append((retention.canonical_time(raw),source,event))
            db.commit();db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.commit()
            marker=retention._validated_timestamp_cache(db);db.execute('BEGIN IMMEDIATE')
            retention._validate_current_timestamps(db,marker)
            for _ in range(300):
                lo,hi=sorted(rng.sample(keys,2))
                where,params=retention._between(retention.SPECS['stream_events'],lo,hi)
                expected=retention._count(db,retention.SPECS['stream_events'],where,params)
                self.assertEqual(retention._stream_range_count_validated(db,lo,hi),expected,(lo,hi))
            db.rollback()
        finally:db.close()

    def test_stream_cursor_delete_preserves_exact_text_identities(self):
        case=safety.RetentionTests(methodName='test_verified_old_observations_are_eligible_and_new_are_kept');case.setUp()
        try:
            from datetime import timedelta
            for event in ('001','1','2'):
                case.add_event('coinbase',event,safety.NOW-timedelta(days=3))
            case.archive_all('stream_events',3)
            case.add_event('coinbase','unapproved',safety.NOW-timedelta(days=3))
            plan=case.plan();seen=[];case.db.set_trace_callback(seen.append)
            result=retention.apply_retention(case.db,plan,retention.RetentionConfig(True,48,2),confirm=True)
            case.db.set_trace_callback(None)
            deleted=result['datasets']['stream_events']['deleted_rows']
            remaining={row[0] for row in case.db.execute('SELECT event_id FROM stream_events')}
            self.assertEqual(deleted,3);self.assertEqual(remaining,{'unapproved'})
            statements=[sql for sql in seen if sql.startswith('DELETE FROM stream_events')]
            self.assertEqual(len(statements),3)
            self.assertTrue(all('INDEXED BY stream_events_archive_cursor' in sql for sql in statements))
            self.assertFalse(case.db.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'retention_%'").fetchall())
        finally:case.tearDown()

    def test_warming_discards_rows_and_mutation_is_rechecked_under_writer(self):
        from datetime import timedelta
        from unittest.mock import patch
        case=safety.RetentionTests(methodName='test_verified_old_observations_are_eligible_and_new_are_kept');case.setUp()
        try:
            case.add_event('coinbase','001',safety.NOW-timedelta(days=3));case.archive_all('stream_events',10)
            case.db.execute('BEGIN IMMEDIATE');guards.create_indexes(case.db);case.db.commit()
            plan=case.plan();warm=retention._warm_stream_pages;states=[]
            def changed(db,size):
                states.append(db.in_transaction);warm(db,size)
                db.execute("UPDATE stream_events SET received_at='2026-02-30T00:00:00+00:00'");db.commit()
            with patch.object(retention,'_warm_stream_pages',side_effect=changed):
                with self.assertRaises(retention.RetentionError):
                    retention.apply_retention(case.db,plan,retention.RetentionConfig(True,48,1000),confirm=True)
            self.assertEqual(states,[False]);self.assertEqual(case.count('stream_events'),1)
            self.assertFalse(case.db.in_transaction)
        finally:case.tearDown()

    def test_full_existing_safety_suite_with_transactionally_maintained_guards(self):
        for name in unittest.defaultTestLoader.getTestCaseNames(safety.RetentionTests):
            with self.subTest(case=name):
                case=safety.RetentionTests(methodName=name);case.setUp()
                try:
                    case.db.execute('BEGIN IMMEDIATE');guards.create_indexes(case.db);case.db.commit()
                    getattr(case,name)()
                finally:case.tearDown()


if __name__=='__main__':unittest.main()
