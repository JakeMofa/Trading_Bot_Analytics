"""Exact sealed-prefix reconciliation, never inherited shared cursor progress."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import tempfile,time,unittest
from test_ab_application import ApplicationStore,legacy,T,timedelta,iso,cloud_memory
from raw_generations import MemoryArchive,Stop

class Remote:
    def __init__(self,archive):self.archive=archive;self.rows={};self.corrupt=False
    def download_bytes(self,bucket,path):return b'corrupt' if self.corrupt else self.archive.objects[path]
    def upsert(self,table,rows,on_conflict):
        if table!='sync_checkpoints':raise AssertionError('unexpected write')
        for row in rows:
            prior=self.rows.get(row['dataset'])
            from compatible_cloud import same_row
            if prior and not same_row(prior,row):raise Stop('remote checkpoint conflict')
            self.rows[row['dataset']]=row

class Tests(unittest.TestCase):
    def fixture(self,root):
        path=Path(root)/'generated-legacy.db';legacy(path)
        store=ApplicationStore(root,path,routing=True,fresh_b=True)
        with closing(store.connection()) as db:
            for i in range(3):
                at=T+timedelta(seconds=i+1)
                db.save_stream_event(dict(source='coinbase',event_id='recover-'+str(i),received_at=iso(at),source_time=iso(at),price='123.00000000001',size='1',side='buy',payload='{}'))
        gid=store.protocol.active()['id'];now=T+timedelta(hours=73);store.rotation_tick(now)
        archive=MemoryArchive()
        for _ in range(2):store.protocol.archive_hour(archive,now,limit=1,sealed_generation=gid)
        return store,gid,Remote(archive)

    def test_verified_partial_prefix_restart_idempotency_and_remote_ack_crash(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,gid,remote=self.fixture(root)
            try:
                with closing(store.worker_connection('lifecycle')) as db:
                    name=db.archive_checkpoint_name('stream_events',gid)
                    with db:cloud_memory._save_checkpoint(db,'archive:ab72:stream_events',source_time=iso(T+timedelta(days=99)),source_key='["z","z"]',rows_added=999,status='verified')
                    with patch.object(cloud_memory,'_save_checkpoint',side_effect=RuntimeError('generated crash after remote acknowledgement')):
                        with self.assertRaises(RuntimeError):db.reconcile_archive_checkpoint(remote,gid,'stream_events',time.monotonic()+5)
                    self.assertEqual(cloud_memory._checkpoint(db,name),(None,None,None,0))
                with closing(store.worker_connection('lifecycle')) as db:
                    result=db.reconcile_archive_checkpoint(remote,gid,'stream_events',time.monotonic()+5)
                    self.assertEqual(result['rows'],2)
                    self.assertTrue(db.reconcile_archive_checkpoint(remote,gid,'stream_events',time.monotonic()+5)['idempotent'])
                    pending=db.raw_archive_rows('stream_events',10)
                    self.assertEqual([r['event_id'] for r in pending],['recover-2'])
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:ab72:stream_events')[3],999)
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:observations')[0],41)
            finally:store.close()

    def test_corrupt_missing_prefix_or_changed_receipt_never_advance_cursor(self):
        for mode in ('corrupt','gap','receipt'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                store,gid,remote=self.fixture(root)
                try:
                    with closing(store.worker_connection('lifecycle')) as db:
                        if mode=='corrupt':remote.corrupt=True
                        if mode=='gap':
                            with db:db.execute("DELETE FROM ab_manifests WHERE gen=? AND json_extract(metadata,'$.metadata.first_source_key')=?",(gid,'["coinbase","recover-0"]'))
                        if mode=='receipt':
                            with store.protocol.core:store.protocol.core.execute("UPDATE raw_receipts SET sha256='bad' WHERE id=(SELECT min(id) FROM events WHERE gen=?)",(gid,))
                        with self.assertRaises((Stop,ValueError)):db.reconcile_archive_checkpoint(remote,gid,'stream_events',time.monotonic()+5)
                        self.assertEqual(cloud_memory._checkpoint(db,db.archive_checkpoint_name('stream_events',gid)),(None,None,None,0))
                        self.assertTrue(store.protocol.path(gid).exists());self.assertFalse(remote.rows)
                finally:store.close()
