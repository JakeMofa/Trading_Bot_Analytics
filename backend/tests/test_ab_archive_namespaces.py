"""Offline characterization of existing namespaces; no cloud policy assertions."""
import tempfile, unittest
from contextlib import closing
from pathlib import Path
from test_ab_application import ApplicationStore, legacy, T, timedelta, iso
from raw_generations import Stop
from test_ab_application import Cloud
import cloud_memory


class Tests(unittest.TestCase):
    def test_newer_generation_progress_never_skips_older_pending_generation(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True);cloud=Cloud()
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m',iso(T+timedelta(seconds=1)),'book',{'slot':'first'},iso(T))
                    old=store.protocol.active()['id']
                    store.rotation_tick(T+timedelta(hours=73))
                    db.save_observation('m',iso(T+timedelta(hours=73,seconds=1)),'book',{'slot':'second'},iso(T))
                    new=store.protocol.active()['id']
                    db.archive_generation_scope={new}
                    newer=cloud_memory.archive_raw_batch(db,cloud,'observations',limit=10)
                    db.archive_generation_scope=None
                    older=cloud_memory.archive_raw_batch(db,cloud,'observations',limit=10)
                    self.assertEqual(newer['metadata']['generation_id'],new)
                    self.assertEqual(older['metadata']['generation_id'],old)
                    self.assertLess(older['last_source_id'],newer['first_source_id'])
                    self.assertIsNone(cloud_memory.archive_raw_batch(db,cloud,'observations',limit=10))
                    name=db.archive_checkpoint_name('observations',old)
                    with db:db.execute('DELETE FROM cloud_sync_state WHERE dataset=?',(name,))
                    with self.assertRaisesRegex(Stop,'manifest reconciliation'):
                        cloud_memory.archive_raw_batch(db,cloud,'observations',limit=10)
                    self.assertTrue(store.protocol.path(old).exists())
            finally:store.close()

    def test_other_generation_backdated_rows_restart_duplicates_and_failed_readback(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True);cloud=Cloud()
            try:
                with closing(store.connection()) as db:
                    later=T+timedelta(hours=1)
                    db.save_observation('m',iso(later),'book',{'exact':'0.00000000001'},iso(later))
                    db.save_stream_event(dict(source='coinbase',event_id='new-1',received_at=iso(later),source_time=iso(later),price='123.00000000001',size='1',side='buy',payload='{}'))
                    old=store.protocol.active()['id']
                    for dataset in ('observations','stream_events'):
                        cloud_memory.archive_raw_batch(db,cloud,dataset,limit=10)
                    old_progress={d:cloud_memory._checkpoint(db,db.archive_checkpoint_name(d,old)) for d in ('observations','stream_events')}
                    store.rotation_tick(T+timedelta(hours=73))
                    new=store.protocol.active()['id'];self.assertNotEqual(old,new)
                    # Late source timestamps are valid; receipt clock cannot regress.
                    receipt=T+timedelta(hours=73,seconds=1)
                    db.save_observation('m',iso(receipt),'book',{'exact':'0.00000000002'},iso(T))
                    event=dict(source='coinbase',event_id='new-2',received_at=iso(receipt),source_time=iso(T),price='123.00000000002',size='1',side='buy',payload='{}')
                    db.save_stream_event(event);db.save_stream_event(event)
                store.close();store=ApplicationStore(root,path,routing=True,fresh_b=True)
                with closing(store.connection()) as db:
                    for dataset in ('observations','stream_events'):
                        name=db.archive_checkpoint_name(dataset,new)
                        cloud.fail='verify'
                        with self.assertRaises(ValueError):cloud_memory.archive_raw_batch(db,cloud,dataset,limit=10)
                        self.assertEqual(cloud_memory._checkpoint(db,name),(None,None,None,0))
                        self.assertTrue(store.protocol.path(old).exists());self.assertTrue(store.protocol.path(new).exists())
                        cloud.fail=None
                        manifest=cloud_memory.archive_raw_batch(db,cloud,dataset,limit=10)
                        self.assertEqual(manifest['metadata']['generation_id'],new)
                        self.assertEqual(manifest['event_count'],1)
                        self.assertEqual(cloud_memory._checkpoint(db,name)[3],1)
                        self.assertEqual(cloud_memory._checkpoint(db,db.archive_checkpoint_name(dataset,old)),old_progress[dataset])
                        self.assertIsNone(cloud_memory.archive_raw_batch(db,cloud,dataset,limit=10))
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:observations')[0],41)
            finally:store.close()

    def test_reused_numeric_identity_cannot_collide_with_legacy_object_path(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path = Path(root) / 'generated-legacy.db'
            legacy(path)
            store = ApplicationStore(root, path, routing=True, fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m', iso(T + timedelta(seconds=1)), 'book', {}, iso(T))
                    # Same byte-identical source row, different generation identity.
                    fields = ('id','market_id','received_at','source_time','kind','payload')
                    row = dict(zip(fields, db.execute('SELECT * FROM observations WHERE id=90').fetchone()))
                    row['source_id'] = row['id']
                    from unittest.mock import patch
                    gids = ['legacy', store.protocol.active()['id'], 'another-generation']
                    paths = []
                    for gid in gids:
                        with patch.object(db, '_row_generation', return_value=gid):
                            paths.append(db.archive_batch_object_path('observations', [row])[1])
                            self.assertEqual(db.archive_manifest_metadata('observations', [row])['generation_id'], gid)
                    self.assertEqual(len(set(paths)), 3)
                    self.assertTrue(paths[1].startswith(gids[1] + '/'))
                    self.assertTrue(paths[2].startswith(gids[2] + '/'))
                    with patch.object(db, '_row_generation', side_effect=gids[:2]):
                        with self.assertRaisesRegex(Stop, 'span generations'):
                            db.archive_manifest_metadata('observations', [row, row])
            finally:
                store.close()

    def test_checkpoint_is_separate_for_every_generation_and_legacy(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path = Path(root) / 'generated-legacy.db'
            legacy(path)
            store = ApplicationStore(root, path, routing=True, fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m', iso(T + timedelta(seconds=1)), 'book', {}, iso(T))
                    before = store.protocol.active()['id']
                    checkpoint = db.archive_checkpoint_name('observations',before)
                    self.assertEqual(checkpoint, 'archive:ab72:'+before+':observations')
                    self.assertNotEqual(checkpoint, 'archive:observations')
                    store.rotation_tick(T + timedelta(hours=72, seconds=10))
                    after=store.protocol.active()['id']
                    self.assertNotEqual(after, before)
                    self.assertNotEqual(db.archive_checkpoint_name('observations',after), checkpoint)
                    self.assertEqual(db.archive_checkpoint_name('observations','legacy'),'archive:observations')
            finally:
                store.close()
