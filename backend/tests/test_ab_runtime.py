"""Real entrypoint routing and archive-driven drainage on generated legacy data."""
import asyncio
from contextlib import closing
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from test_ab_application import legacy, market, T, iso, Cloud
from datetime import timedelta
from application_store import ApplicationStore
from raw_generations import Stop
from storage_runtime import configured_runtime
import collector
import streaming


def environment(root,retirement=False):
    return dict(ENABLE_AB_STORAGE='true',AB_STORAGE_ROOT=str(root),
                SQLITE_DB_PATH=str(Path(root)/'generated-legacy.db'),
                AB_GENERATION_BYTES=str(128*1024),
                ENABLE_AB_RETIREMENT=str(retirement).lower(),
                ENABLE_LOCAL_RETENTION='false',ENABLE_OPENAI_ANALYST='false',
                ENABLE_CLOUD_LIFECYCLE='true',ENABLE_SUPABASE_SYNC='true',
                SUPABASE_URL='https://fixture.invalid',SUPABASE_SECRET_KEY='generated-only')


class RuntimeTests(unittest.TestCase):
    def test_default_holds_and_rejects_inconsistent_enablement(self):
        self.assertIsNone(configured_runtime({}))
        for changes in ({'ENABLE_OPENAI_ANALYST':'true'},
                        {'ENABLE_LOCAL_RETENTION':'true'},{'AB_GENERATION_BYTES':'0'}):
            env=environment('/opt/tradebot')
            env.update(changes)
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):
                configured_runtime(env)
        runtime=configured_runtime(environment('/opt/tradebot'))
        with self.assertRaises(Exception):
            runtime.open('collector')

    def test_real_api_startup_selects_adapter_and_routes_history_and_dashboard(self):
        from api import create_app
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            legacy(Path(root)/'generated-legacy.db')
            started=threading.Event()
            async def collector_loop(*args,storage_adapter=None,**kwargs):
                with closing(storage_adapter.connection()) as db:
                    db.save_observation('m',iso(T),'book',{'padding':'x'*(128*1024)},iso(T))
                    db.save_observation('m',iso(T+timedelta(seconds=1)),'book',{'B':True},iso(T))
                started.set()
                await asyncio.Event().wait()
            with patch.dict(os.environ,environment(root),clear=True),patch('api.run_collectors',side_effect=collector_loop):
                app=create_app()
                with TestClient(app) as client:
                    self.assertTrue(started.wait(3))
                    self.assertEqual(client.get('/system/status').json()['active_buffer']['slot'],'B')
                    self.assertEqual(client.get('/history/predictions').json()['items'][0]['id'],1)
                    self.assertNotEqual(client.get('/history/context').json().get('status'),'unavailable')
                    self.assertEqual(client.get('/health').status_code,200)

    def test_lifecycle_wakes_for_seal_and_respects_default_retirement_hold(self):
        import run_cloud_lifecycle
        from generated_cloud import GeneratedRemote
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db'
            legacy(path)
            owner=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
            worker=None
            try:
                with closing(owner.connection()) as db:
                    db.save_observation('m',iso(T),'book',{'A':True},iso(T))
                a=owner.protocol.active()['id']
                remote=GeneratedRemote(Path(root)/'cloud')
                def native(config):
                    return remote.client(time.monotonic()+30).cloud
                with patch.dict(os.environ,environment(root),clear=True),patch.object(run_cloud_lifecycle,'SupabaseHTTP',side_effect=native):
                    worker=run_cloud_lifecycle.build_worker(path)
                    self.assertEqual(worker.run_cycle(force=True)['status'],'ok')
                    for key in worker._next_due:
                        worker._next_due[key]=time.monotonic()+3600
                    with closing(owner.connection()) as db:
                        db.save_observation('m',iso(T+timedelta(seconds=1)),'book',{'padding':'x'*(128*1024)},iso(T))
                    owner.rotation_tick(T+timedelta(seconds=2))
                    result=worker.run_cycle()
                    self.assertEqual(result['status'],'ok',result)
                    self.assertTrue(result['archive'])
                    self.assertEqual(result['generation_retirement']['status'],'disabled')
                    self.assertTrue(owner.protocol.path(a).exists())
            finally:
                if worker:worker.storage_runtime.close()
                owner.close()

    def test_verified_lifecycle_drains_persistent_readers_before_retirement(self):
        if sys.platform!='linux' or os.geteuid()!=0:
            self.skipTest('full descriptor proof requires Linux root')
        import run_cloud_lifecycle
        from generated_cloud import GeneratedRemote
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db'
            legacy(path)
            owner=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
            db=owner.connection()
            worker=None
            reader=None
            try:
                db.save_market(market(),iso(T+timedelta(seconds=1)))
                a=owner.protocol.active()['id']
                db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{'padding':'x'*(128*1024)},iso(T))
                owner.rotation_tick(T+timedelta(seconds=3))
                db.save_observation('m',iso(T+timedelta(seconds=4)),'book',{'B':True},iso(T))
                reader=owner.worker_connection('history')
                self.assertIn(a,reader.signature)
                remote=GeneratedRemote(Path(root)/'cloud')
                def native(config):
                    return remote.client(time.monotonic()+30).cloud
                with patch.dict(os.environ,environment(root,True),clear=True),patch.object(run_cloud_lifecycle,'SupabaseHTTP',side_effect=native):
                    worker=run_cloud_lifecycle.build_worker(path)
                    result=worker.run_cycle(force=True)
                    self.assertEqual(result['generation_retirement']['status'],'held',result)
                    self.assertEqual(owner.protocol.core.execute('SELECT state FROM generations WHERE id=?',(a,)).fetchone()[0],'draining')
                    self.assertTrue(owner.protocol.path(a).exists())
                    # Timer refresh detaches the long-lived collector. A history
                    # transaction remains pinned until its own caller ends it.
                    owner.rotation_tick(T+timedelta(seconds=5))
                    self.assertNotIn(a,db.signature)
                    reader.close();reader=None
                    result=worker.run_cycle()
                    self.assertEqual(result['generation_retirement']['status'],'ok',result)
                    self.assertFalse(owner.protocol.path(a).exists())
                    self.assertTrue(db.execute('SELECT id FROM observations WHERE id>90').fetchone())
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:
                if reader:reader.close()
                db.close()
                if worker:worker.storage_runtime.close()
                owner.close()

    def test_duplicate_lifecycle_startup_has_one_lock_owner(self):
        from cloud_lifecycle import lifecycle_lock,LifecycleLockError
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'core.db'
            with lifecycle_lock(path):
                with self.assertRaises(LifecycleLockError):
                    with lifecycle_lock(path):
                        self.fail('second lifecycle acquired lock')

    def test_drain_restart_retains_core_evidence_and_rejects_new_raw_reader(self):
        from raw_generations import FileArchive
        from application_store import RetirementProtocol
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db'
            legacy(path)
            store=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
            try:
                with closing(store.connection()) as db:
                    eid=db.save_observation('m',iso(T),'book',{'padding':'x'*(128*1024)},iso(T))
                    with db:
                        db.protect_observation(eid)
                a=store.protocol.active()['id']
                store.rotation_tick(T+timedelta(seconds=1))
                # Use the protocol archive representation through the existing
                # file transport. A crash in draining never authorizes unlink.
                archive=FileArchive(Path(root)/'archives')
                store.protocol.archive_hour(archive,T+timedelta(hours=1))
                def crash(phase):
                    if phase=='retirement_draining':
                        raise RuntimeError('drain crash')
                store.protocol.fault=crash
                with self.assertRaisesRegex(RuntimeError,'drain crash'):
                    store.protocol.retire(a,archive,T+timedelta(hours=1))
                self.assertTrue(store.protocol.path(a).exists())
                with self.assertRaisesRegex(Stop,'unavailable'):
                    with store.protocol.reader(a):
                        self.fail('new reader entered draining generation')
                store.close()
                store=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
                with closing(store.reader_connection()) as db:
                    self.assertIsNotNone(db.execute('SELECT id FROM observations WHERE id=?',(eid,)).fetchone())
                    self.assertNotIn(a,db.signature)
            finally:
                store.close()

    def test_cross_process_shared_lease_blocks_retirement(self):
        import subprocess
        from raw_generations import FileArchive
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db'
            legacy(path)
            store=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
            child=None
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m',iso(T),'book',{'padding':'x'*(128*1024)},iso(T))
                a=store.protocol.active()['id']
                store.rotation_tick(T+timedelta(seconds=1))
                archive=FileArchive(Path(root)/'archives')
                store.protocol.archive_hour(archive,T+timedelta(hours=1))
                lock=Path(root)/('lease-'+store.protocol.path(a).stem+'.lock')
                code="import fcntl,sys; f=open(sys.argv[1]); fcntl.flock(f,fcntl.LOCK_SH); print('ready',flush=True); sys.stdin.read(1)"
                child=subprocess.Popen([sys.executable,'-c',code,str(lock)],
                                       stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
                self.assertEqual(child.stdout.readline().strip(),'ready')
                with self.assertRaisesRegex(Stop,'reader leases'):
                    store.protocol.retire(a,archive,T+timedelta(hours=1))
                self.assertTrue(store.protocol.path(a).exists())
            finally:
                if child:
                    child.communicate('x',timeout=3)
                store.close()

    def test_changed_protected_body_at_drain_boundary_blocks_unlink(self):
        import hashlib
        import json
        from raw_generations import FileArchive,canonical
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db'
            legacy(path)
            store=ApplicationStore(root,path,routing=True,generation_bytes=128*1024)
            try:
                with closing(store.connection()) as db:
                    eid=db.save_observation('m',iso(T),'book',{'padding':'x'*(128*1024)},iso(T))
                    with db:db.protect_observation(eid)
                gid=store.protocol.active()['id']
                store.rotation_tick(T+timedelta(seconds=1))
                archive=FileArchive(Path(root)/'archives')
                store.protocol.archive_hour(archive,T+timedelta(hours=1))
                def corrupt(phase):
                    if phase!='retirement_draining':return
                    body=json.loads(store.protocol.core.execute('SELECT record FROM evidence WHERE id=?',(eid,)).fetchone()[0])
                    body['row']['payload']='{}'
                    text=canonical(body)
                    with store.protocol.core:
                        store.protocol.core.execute('UPDATE evidence SET record=?,sha256=? WHERE id=?',
                            (text,hashlib.sha256(text.encode()).hexdigest(),eid))
                store.protocol.fault=corrupt
                with self.assertRaisesRegex(Stop,'differs from sealed raw'):
                    store.protocol.retire(gid,archive,T+timedelta(hours=1))
                self.assertTrue(store.protocol.path(gid).exists())
                self.assertEqual(store.protocol.core.execute('SELECT state FROM generations WHERE id=?',(gid,)).fetchone()[0],'draining')
            finally:store.close()
