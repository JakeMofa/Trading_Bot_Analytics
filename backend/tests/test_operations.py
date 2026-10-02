from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from operations import backup, collector_lock, paths, status, stop_collector, start_collector


class OperationsTests(unittest.TestCase):
    def test_backup_includes_committed_wal_and_recovery_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'live.db'
            saved = Path(folder) / 'backup.db'
            recovered = Path(folder) / 'recovered.db'
            db = sqlite3.connect(source)
            try:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, price TEXT)')
                db.execute("INSERT INTO evidence VALUES(1, '86109.54')")
                db.commit()
                self.assertTrue(Path(str(source) + '-wal').exists())
                backup(source, saved)
                db.execute("INSERT INTO evidence VALUES(2, 'later')")
                db.commit()
                backup(saved, recovered)
                with closing(sqlite3.connect(recovered)) as restored:
                    self.assertEqual(restored.execute('SELECT * FROM evidence').fetchall(), [(1, '86109.54')])
                    self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                with self.assertRaises(FileExistsError):
                    backup(source, saved)
                self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0], 2)
            finally:
                db.close()

    def test_corrupt_backup_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'bad.db'
            destination = Path(folder) / 'saved.db'
            source.write_bytes(b'corrupt sqlite')
            with self.assertRaises(sqlite3.DatabaseError):
                backup(source, destination)
            self.assertFalse(destination.exists())
            self.assertFalse(list(Path(folder).glob('.sqlite-backup-*')))

    def test_recovery_refuses_existing_wal_sidecar(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'source.db', Path(folder) / 'target.db'
            with closing(sqlite3.connect(source)) as db:
                db.execute('CREATE TABLE evidence(id INTEGER)')
            Path(str(target) + '-wal').write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):
                backup(source, target)

    def test_lock_release_after_crash_and_controlled_restart(self):
        module = str(Path(__file__).resolve().parents[1] / 'app')
        worker = '''import asyncio, sys
sys.path.insert(0, sys.argv[1])
from operations import collector_lock, control_server
async def run():
    with collector_lock(sys.argv[2]) as path:
        stop = asyncio.Event()
        server = await control_server(path, stop)
        await stop.wait()
        server.close()
        await server.wait_closed()
asyncio.run(run())
'''
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'evidence.db'
            for crash in (True, False):
                child = subprocess.Popen([sys.executable, '-c', worker, module, str(database)])
                try:
                    deadline = time.monotonic() + 5
                    while not (status(database)['running'] and paths(database)[1].exists()):
                        if child.poll() is not None or time.monotonic() > deadline:
                            self.fail('Worker failed to start')
                        time.sleep(.02)
                    with self.assertRaises(RuntimeError):
                        with collector_lock(database):
                            pass
                    if crash:
                        child.kill()
                    else:
                        self.assertFalse(stop_collector(database, timeout=5)['running'])
                    child.wait(timeout=5)
                    self.assertFalse(status(database)['running'])
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait()

    def test_legacy_heartbeat_prevents_duplicate_and_false_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'legacy.db'
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE feed_health(source TEXT,status TEXT,updated_at TEXT)')
                db.execute("INSERT INTO feed_health VALUES('rest_supervisor','running',strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                db.commit()
            with self.assertRaises(RuntimeError):
                start_collector(database)
            with self.assertRaises(RuntimeError):
                stop_collector(database)
