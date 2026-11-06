"""Small exact generated objects: restartable second verification, no live cloud."""
from contextlib import closing
import hashlib,os,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import ApplicationStore,legacy,T,iso,timedelta
from application_store import RetirementProtocol
from raw_generations import MemoryArchive,Stop,Unproven
from incremental_retirement import step
from retention_recovery import RecoveryError

class Remote(MemoryArchive):
    def __init__(self):super().__init__();self.reads=0;self.corrupt=False
    def download_bytes(self,*args):
        if self.corrupt:self.reads+=1;return b'corrupt'
        return super().download_bytes(*args)

class Tests(unittest.TestCase):
    def test_save_hold_keeps_sanitized_underlying_admission_reason(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root)
            try:
                store.protocol.fresh_event_limit=1
                with closing(store.connection()) as db,self.assertRaises(Stop):db.save_observation('m',iso(now),'book',{},iso(now))
                self.assertEqual(store.hold,'durable_raw_save_failed')
                self.assertEqual(store.last_save_failure['reason'],'fresh persistent event ledger limit STOP')
                self.assertIsNone(store.last_save_failure['sqlite_code'])
            finally:store.close()

    def test_expired_whole_operation_does_not_start_or_retire(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root);actor=RetirementProtocol(root,path)
            try:
                with self.assertRaisesRegex(Stop,'operation deadline'):step(actor,gid,remote,now,deadline=time.monotonic()-1)
                for bad in (float('nan'),float('inf'),'invalid',True):
                    with self.assertRaisesRegex(Stop,'operation deadline'):step(actor,gid,remote,now,deadline=bad)
                self.assertEqual(remote.reads,0);self.assertTrue(store.protocol.path(gid).exists())
            finally:actor.close();store.close()

    def fixture(self,root):
        path=Path(root)/'generated-legacy.db';legacy(path)
        store=ApplicationStore(root,path,routing=True,fresh_b=True)
        with closing(store.connection()) as db:
            for i in range(4):db.save_stream_event(dict(source='coinbase',event_id=str(100+i),received_at=iso(T+timedelta(seconds=2+i)),source_time=iso(T+timedelta(seconds=2+i)),price='12345.00000000001',size='1',side='buy',payload='{}'))
        gid=store.protocol.active()['id'];now=T+timedelta(hours=72,seconds=10);store.rotation_tick(now)
        cloud=Remote()
        for _ in range(2):store.protocol.archive_hour(cloud,now,limit=2,sealed_generation=gid)
        cloud.reads=0
        return store,path,gid,cloud,now
    def test_bounded_progress_survives_actor_restart_and_other_slot_writes(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root)
            try:
                actor=RetirementProtocol(root,path)
                try:self.assertEqual(step(actor,gid,remote,now,finalize=False)['status'],'verifying')
                finally:actor.close()
                self.assertEqual(remote.reads,1)
                with closing(store.connection()) as db:db.save_observation('m',iso(now+timedelta(seconds=1)),'book',{'new':'1'},iso(now))
                actor=RetirementProtocol(root,path)
                try:
                    self.assertEqual(step(actor,gid,remote,now,finalize=False)['status'],'ready')
                    self.assertEqual(step(actor,gid,remote,now,finalize=False)['objects_checked'],0)
                finally:actor.close()
                self.assertEqual(remote.reads,2);self.assertTrue(store.protocol.path(gid).exists())
            finally:store.close()
    def test_bad_readback_and_expired_receipts_preserve_raw(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root);actor=RetirementProtocol(root,path)
            try:
                step(actor,gid,remote,now,finalize=False);remote.corrupt=True
                with self.assertRaises(RecoveryError):step(actor,gid,remote,now,finalize=False)
                self.assertTrue(store.protocol.path(gid).exists());remote.corrupt=False
                self.assertEqual(step(actor,gid,remote,now,finalize=False)['status'],'ready')
                remote.corrupt=True
                with self.assertRaises(RecoveryError):step(actor,gid,remote,now+timedelta(seconds=301),finalize=False)
                self.assertTrue(store.protocol.path(gid).exists())
            finally:actor.close();store.close()
    def test_changed_receipt_cannot_reuse_previous_proof(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root);actor=RetirementProtocol(root,path)
            try:
                step(actor,gid,remote,now,max_objects=2,finalize=False)
                with store.protocol.core:store.protocol.core.execute("UPDATE raw_receipts SET sha256='bad' WHERE id=(SELECT min(id) FROM events WHERE gen=?)",(gid,))
                with self.assertRaises(Stop):step(actor,gid,remote,now,finalize=False)
                self.assertTrue(store.protocol.path(gid).exists())
            finally:actor.close();store.close()

    def test_changed_manifest_or_raw_body_invalidates_completed_progress(self):
        import sqlite3
        for fault in ('manifest','raw'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                store,path,gid,remote,now=self.fixture(root);actor=RetirementProtocol(root,path)
                try:
                    step(actor,gid,remote,now,max_objects=2,finalize=False)
                    if fault=='manifest':
                        import json
                        record=store.protocol.core.execute('SELECT path,metadata FROM manifests WHERE gen=? LIMIT 1',(gid,)).fetchone()
                        changed=json.loads(record[1]);changed['sha256']='0'*64
                        with store.protocol.core:store.protocol.core.execute('UPDATE manifests SET metadata=? WHERE path=?',(json.dumps(changed),record[0]))
                    else:
                        with closing(sqlite3.connect(store.protocol.path(gid))) as db,db:db.execute("UPDATE stream_events SET price='999999' WHERE event_id='100'")
                    with self.assertRaises((Stop,RecoveryError)):step(actor,gid,remote,now,max_objects=2)
                    self.assertTrue(store.protocol.path(gid).exists())
                finally:actor.close();store.close()

    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'actual retirement requires root descriptor proof')
    def test_runtime_retirement_off_then_enable_without_restarting_collector(self):
        from storage_runtime import StorageRuntime
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root)
            run=StorageRuntime(root,path,2*1024**2,fresh_b=True,verify_objects=8)
            try:
                original=store.protocol.active()['id'];self.assertEqual(run.retire_verified(remote,now),{'status':'disabled'})
                run.retirement=True # generated analogue of separately approved lifecycle enablement
                for i in range(3):
                    with closing(store.connection()) as db:db.save_observation('m',iso(now+timedelta(seconds=i+1)),'book',{'i':i},iso(now))
                    result=run.retire_verified(remote,now)
                    if result['status']=='ok':break
                self.assertEqual(result['status'],'ok',result);self.assertFalse(store.protocol.path(gid).exists())
                self.assertEqual(store.protocol.active()['id'],original)
                self.assertEqual(store.protocol.core.execute("SELECT count(*) FROM events WHERE status='pending'").fetchone()[0],0)
                self.assertTrue(path.exists())
            finally:store.close()

    def test_remote_change_after_cached_verification_blocks_final_retirement(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,remote,now=self.fixture(root);actor=RetirementProtocol(root,path)
            try:
                self.assertEqual(step(actor,gid,remote,now,max_objects=2,finalize=False)['status'],'ready')
                held=step(actor,gid,remote,now,max_objects=1)
                self.assertEqual(held['status'],'verifying');self.assertIn('exceeds object budget',held['reason'])
                remote.corrupt=True
                with self.assertRaises(RecoveryError):step(actor,gid,remote,now,max_objects=2)
                self.assertTrue(store.protocol.path(gid).exists())
                self.assertEqual(actor.core.execute('SELECT count(*) FROM ab_retire_checks WHERE gen=?',(gid,)).fetchone()[0],0)
            finally:actor.close();store.close()
