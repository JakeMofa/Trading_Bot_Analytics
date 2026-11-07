"""Logical corruption and schema faults must hold activation/reads, never remove data."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy,ApplicationStore,Stop,T,iso,timedelta
from application_validation import LAYOUT_VERSION,logical_size


class ValidationTests(unittest.TestCase):
    def test_historical_epoch_is_schema_specific(self):
        from application_validation import row_check
        row_check('historical_market_prices',{'source_time':1760000000})
        for value in (True,'1760000000',float('nan'),10**30):
            with self.assertRaises((ValueError,OverflowError,OSError)):
                row_check('historical_market_prices',{'source_time':value})
        with self.assertRaises(ValueError):row_check('stream_events',{'source_time':1760000000})

    def test_malformed_missing_and_unknown_legacy_inputs_block_activation(self):
        faults=(
            ("UPDATE markets SET target='NaN'",'decimal'),
            ("UPDATE observations SET received_at='2026-01-01' WHERE id=41",'timezone'),
            ("UPDATE observations SET payload='not json' WHERE id=41",'JSON'),
            ("DELETE FROM observations WHERE id=90",'protected'),
            ("UPDATE feature_snapshots SET evidence_json='{}'",'metadata'),
            ("UPDATE feature_snapshots SET market_id='absent'",'foreign'),
            ("UPDATE predictions SET probability_up='Infinity'",'decimal'),
            ('PRAGMA user_version=99','version'),
        )
        for sql,reason in faults:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                path=Path(root)/'generated-legacy.db';legacy(path)
                with closing(sqlite3.connect(path)) as db,db:db.execute(sql)
                before=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises((Stop,ValueError,sqlite3.Error)):
                    ApplicationStore(root,path,routing=True,fresh_b=True)
                self.assertTrue(path.exists());self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                with closing(sqlite3.connect(Path(root)/'core.db')) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM ab_generations WHERE state='active'").fetchone()[0],0)

    def test_all_acknowledged_fields_are_verified_after_corruption_and_restart(self):
        faults=("UPDATE stream_events SET price='99999.00000001'",
                "UPDATE stream_events SET received_at='2026-01-02T00:00:00+00:00'",
                'DELETE FROM stream_events',
                'PRAGMA user_version=77',
                "UPDATE stream_events SET source_key='2099-01-01T00:00:00.000000+00:00'",
                "UPDATE generation SET id='00000000000000000000000000000000'")
        for sql in faults:
            with self.subTest(sql=sql),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                path=Path(root)/'generated-legacy.db';legacy(path)
                store=ApplicationStore(root,path,routing=True,fresh_b=True)
                with closing(store.connection()) as db:
                    db.save_stream_event(dict(source='coinbase',event_id='protected',received_at=iso(T+timedelta(seconds=2)),source_time=iso(T),price='12345.1234567890123456789',size='0.00000001',side='buy',payload='{"precision":0.1234567890123456789}'))
                raw=store.protocol.path(store.protocol.active()['id']);store.close()
                with closing(sqlite3.connect(raw)) as broken,broken:broken.execute(sql)
                with self.assertRaises((Stop,ValueError,sqlite3.Error)):
                    ApplicationStore(root,path,routing=True,fresh_b=True)
                self.assertTrue(raw.exists());self.assertTrue(path.exists())

    def test_live_raw_read_and_archive_reject_changed_commit_body(self):
        import cloud_memory
        from test_ab_application import Cloud
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    db.save_stream_event(dict(source='coinbase',event_id='new',received_at=iso(T+timedelta(seconds=2)),source_time=iso(T),price='12345.00000001',size='1',side='buy',payload='{}'))
                raw=store.protocol.path(store.protocol.active()['id'])
                with closing(sqlite3.connect(raw)) as broken,broken:broken.execute("UPDATE stream_events SET payload='{} ',price='9'")
                with closing(store.connection()) as db:
                    with self.assertRaises(sqlite3.OperationalError):db.latest_tick_event()
                    cloud=Cloud()
                    with self.assertRaises(sqlite3.OperationalError):cloud_memory.archive_raw_batch(db,cloud,'stream_events',100)
                    self.assertEqual(cloud.objects,{})
                self.assertTrue(raw.exists())
            finally:store.close()

    def test_protected_core_copy_and_layout_version_reject_tampering(self):
        for sql in ("UPDATE observations SET payload='{}' WHERE id=41",
                    'UPDATE ab_layout_version SET version=999'):
            with self.subTest(sql=sql),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                path=Path(root)/'generated-legacy.db';legacy(path)
                store=ApplicationStore(root,path,routing=True,fresh_b=True);store.close()
                with closing(sqlite3.connect(Path(root)/'core.db')) as db,db:
                    db.create_function('ab72_writer_enabled',0,lambda:1);db.create_function('ab72_layout_version',0,lambda:LAYOUT_VERSION);db.create_function('ab72_logical_size',-1,logical_size);db.execute(sql)
                with self.assertRaises((Stop,ValueError)):
                    ApplicationStore(root,path,routing=True,fresh_b=True)
                self.assertTrue(path.exists());self.assertTrue((Path(root)/'core.db').exists())

    def test_retirement_holds_on_corrupt_ack_proof_even_with_verified_archive(self):
        from raw_generations import FileArchive
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    eid=db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{},iso(T))
                gid=store.protocol.active()['id'];store.rotation_tick(T+timedelta(hours=72,seconds=2))
                archive=FileArchive(Path(root)/'archive');store.protocol.archive_hour(archive,T+timedelta(hours=145))
                with store.protocol.core:store.protocol.core.execute('UPDATE raw_receipts SET sha256=? WHERE id=?',('0'*64,eid))
                with self.assertRaisesRegex(Stop,'acknowledged row proof'):
                    store.protocol.retire(gid,archive,T+timedelta(hours=145))
                self.assertTrue(store.protocol.path(gid).exists())
            finally:store.close()

    def test_old_adapter_writer_flag_cannot_modify_v2_registry(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True)
            with closing(store.connection()) as db:db.save_observation('m',iso(T),'book',{},iso(T))
            store.close()
            with closing(sqlite3.connect(Path(root)/'core.db')) as db:
                db.create_function('ab72_writer_enabled',0,lambda:1)
                with self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE ab_events SET status='pending'")
                self.assertEqual(db.execute("SELECT count(*) FROM ab_events WHERE status='committed'").fetchone()[0],1)

    def test_required_evidence_and_generation_binding_are_checked_at_startup(self):
        for fault in ('missing','generation'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                path=Path(root)/'generated-legacy.db';legacy(path)
                store=ApplicationStore(root,path,routing=True,fresh_b=True)
                with closing(store.connection()) as db:
                    eid=db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{},iso(T))
                gid=store.protocol.active()['id']
                with store.protocol.reader(gid) as raw:
                    row=dict(raw.execute('SELECT * FROM observations WHERE id=?',(eid,)).fetchone())
                with store.protocol.core:store.protocol.pin_record(eid,dict(generation_id=gid,dataset='observations',row=row))
                raw_path=store.protocol.path(gid);store.close()
                with closing(sqlite3.connect(Path(root)/'core.db')) as db,db:
                    db.create_function('ab72_writer_enabled',0,lambda:1);db.create_function('ab72_layout_version',0,lambda:LAYOUT_VERSION)
                    if fault=='missing':db.execute('DELETE FROM ab_evidence WHERE id=?',(eid,))
                    else:
                        body=json.loads(db.execute('SELECT record FROM ab_evidence WHERE id=?',(eid,)).fetchone()[0]);body['generation_id']='wrong-generation'
                        text=json.dumps(body,sort_keys=True,separators=(',',':'))
                        db.execute('UPDATE ab_evidence SET record=?,sha256=? WHERE id=?',(text,hashlib.sha256(text.encode()).hexdigest(),eid))
                with self.assertRaisesRegex((Stop,ValueError),'protected evidence'):
                    ApplicationStore(root,path,routing=True,fresh_b=True)
                self.assertTrue(raw_path.exists());self.assertTrue(path.exists())
