"""Offline characterization of existing namespaces; no cloud policy assertions."""
import tempfile, unittest
from contextlib import closing
from pathlib import Path
from test_ab_application import ApplicationStore, legacy, T, timedelta, iso
from raw_generations import Stop


class Tests(unittest.TestCase):
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

    def test_checkpoint_is_separate_from_legacy_but_shared_across_new_generations(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path = Path(root) / 'generated-legacy.db'
            legacy(path)
            store = ApplicationStore(root, path, routing=True, fresh_b=True)
            try:
                with closing(store.connection()) as db:
                    db.save_observation('m', iso(T + timedelta(seconds=1)), 'book', {}, iso(T))
                    before = store.protocol.active()['id']
                    checkpoint = db.archive_checkpoint_name('observations')
                    self.assertEqual(checkpoint, 'archive:ab72:observations')
                    self.assertNotEqual(checkpoint, 'archive:observations')
                    store.rotation_tick(T + timedelta(hours=72, seconds=10))
                    self.assertNotEqual(store.protocol.active()['id'], before)
                    self.assertEqual(db.archive_checkpoint_name('observations'), checkpoint)
                    # This characterizes a gap; it does NOT prove per-generation cursors.
            finally:
                store.close()
