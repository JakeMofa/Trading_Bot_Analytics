"""Sealed legacy + fresh B: no complete raw audit/map or legacy retirement."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy,ApplicationStore,Cloud,T,iso,timedelta,Stop
import collector,streaming,features,forecasts,dashboard,cloud_memory
from storage_runtime import configured_runtime
from test_ab_runtime import environment


class FreshBTests(unittest.TestCase):
    def make_legacy(self,root):
        path=Path(root)/'generated-legacy.db';legacy(path)
        with closing(sqlite3.connect(path)) as db,db:
            db.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                ((100+i,'m',iso(T),iso(T),'unprotected','{}') for i in range(20000)))
        return path

    def test_startup_reads_predictions_archive_and_unchanged_legacy(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=self.make_legacy(root);before=hashlib.sha256(path.read_bytes()).hexdigest()
            started=time.monotonic()
            store=ApplicationStore(root,path,routing=True,fresh_b=True,generation_bytes=2*1024**2)
            try:
                self.assertLess(store.import_metrics['rows'],10000)
                self.assertEqual(store.import_metrics['raw_audit'],'targeted protected/current inputs only')
                core=store.protocol.core.native
                self.assertEqual(core.execute('SELECT count(*) FROM ab_legacy_stream_ids').fetchone()[0],0)
                self.assertEqual(core.execute('SELECT count(*) FROM main.observations').fetchone()[0],2)
                self.assertEqual(core.execute('SELECT count(*) FROM ab_legacy_stream_pins').fetchone()[0],1)
                with self.assertRaises(BlockingIOError):ApplicationStore(root,path,routing=True,fresh_b=True)
                with closing(store.connection()) as db:
                    old_checkpoint=cloud_memory._checkpoint(db,'archive:observations')
                    old_prediction=db.execute('SELECT * FROM predictions WHERE id=1').fetchone()
                    msg=dict(source='coinbase',event_id='new-B',received_at=iso(T+timedelta(seconds=2)),source_time=iso(T+timedelta(seconds=2)),price='12342.000000000000001',size='0.00000001',side='buy',payload='{"B":true}')
                    self.assertTrue(db.save_stream_event(msg))
                    new=db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{'B':True},iso(T))
                    self.assertGreater(new,20099)
                    self.assertEqual(db.active_buffer()['slot'],'B')
                    self.assertEqual(db.active_buffer()['legacy_history'],'sealed_retirement_held')
                    self.assertEqual(db.latest_tick_event()['price_usd'],msg['price'])
                    self.assertEqual(len(db.chart_ticks(100)),2)
                    value=features.capture(db,T+timedelta(seconds=2));self.assertEqual(value[0],'m')
                    sid=db.execute('SELECT MAX(id) FROM feature_snapshots').fetchone()[0]
                    self.assertIsNotNone(forecasts.forecast_snapshot(db,sid,T+timedelta(seconds=2)))
                    self.assertEqual(db.execute('SELECT * FROM predictions WHERE id=1').fetchone(),old_prediction)
                    self.assertEqual(db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0],90)
                    self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0],20003)
                    cloud=Cloud()
                    for dataset in ('observations','stream_events'):
                        manifest=cloud_memory.archive_raw_batch(db,cloud,dataset,limit=100)
                        self.assertEqual(manifest['event_count'],1)
                        self.assertEqual(manifest['metadata']['generation_id'],store.protocol.active()['id'])
                        self.assertIsNone(cloud_memory.archive_raw_batch(db,cloud,dataset,limit=100))
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:observations'),old_checkpoint)
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:ab72:observations')[0],new)
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                b_id=store.protocol.active()['id']
                store.rotation_tick(T+timedelta(hours=72,seconds=2))
                self.assertEqual(store.protocol.active()['slot'],'A')
                self.assertNotEqual(store.protocol.active()['id'],b_id)
                print(json.dumps({'fresh_b_startup_and_function_seconds':time.monotonic()-started,
                                  'legacy_unprotected_rows_not_imported':20000,'allocation':store.protocol.allocation()}))
            finally:store.close()
            store=ApplicationStore(root,path,routing=True,fresh_b=True)
            try:
                self.assertEqual(store.protocol.active()['slot'],'A')
                with self.assertRaisesRegex(Stop,'not a sealed generation'):store.protocol.retire('legacy',Cloud(),T)
            finally:store.close()
            with self.assertRaisesRegex(Stop,'bootstrap mode changed'):ApplicationStore(root,path,routing=True)

    def test_real_runtime_and_api_fresh_b(self):
        from fastapi.testclient import TestClient
        from api import create_app
        import asyncio
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=self.make_legacy(root)
            env=environment(root);env['AB_STARTUP_MODE']='fresh-b'
            async def collect(*args,storage_adapter=None,**kwargs):
                with closing(storage_adapter.connection()) as db:
                    db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{'B':True},iso(T))
                await asyncio.Event().wait()
            with patch.dict(os.environ,env,clear=True),patch('api.run_collectors',side_effect=collect):
                with TestClient(create_app()) as client:
                    data=client.get('/system/status').json()
                    self.assertEqual(data['active_buffer']['slot'],'B')
                    self.assertEqual(client.get('/history/predictions').json()['items'][0]['id'],1)
                    self.assertEqual(client.get('/health').status_code,200)
                    self.assertEqual(data['active_buffer']['legacy_history'],'sealed_retirement_held')

    def test_archive_failure_retains_b_and_does_not_move_either_cursor(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=self.make_legacy(root);store=ApplicationStore(root,path,routing=True,fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{},iso(T))
                    old=cloud_memory._checkpoint(db,'archive:observations')
                    cloud=Cloud();cloud.fail='verify'
                    with self.assertRaises(ValueError):cloud_memory.archive_raw_batch(db,cloud,'observations',100)
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:observations'),old)
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:ab72:observations'),(None,None,None,0))
                    self.assertTrue(store.protocol.path(store.protocol.active()['id']).exists())
            finally:store.close()

    def test_guard_proposal_is_explicit_bound_and_shared_with_workers(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=self.make_legacy(root)
            store=ApplicationStore(root,path,routing=True,fresh_b=True,aggregate_bytes=8*1024**3)
            try:
                worker=store.worker_connection('history')
                try:
                    self.assertEqual(worker.protocol.ceiling,8*1024**3)
                    self.assertEqual(worker.protocol.core_ceiling,512*1024**2)
                    self.assertEqual(worker.protocol.fresh_layout_limit,2*1024**3)
                    # Retained legacy counts against aggregate, and is excluded
                    # only from the additional independent new-layout quota.
                    fake={'files':{'legacy-external/main':5369184256,'raw.db':2*1024**3},
                          'total_bytes':5369184256+2*1024**3,'peak_bytes':0}
                    with patch.object(worker.protocol,'allocation',return_value=fake):
                        with self.assertRaisesRegex(Stop,'fresh layout quota'):worker.protocol.guard()
                finally:worker.close()
            finally:store.close()
            with self.assertRaisesRegex(Stop,'guard binding changed'):
                ApplicationStore(root,path,routing=True,fresh_b=True)
