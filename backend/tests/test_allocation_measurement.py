import os,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from allocation_measurement import measure,process_binding
class Tests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux independent service descriptor proof')
    def test_bound_sibling_owner_temp_and_pid_reuse_hold(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            owner=subprocess.Popen([sys.executable,'-c',"import tempfile,time;f=tempfile.TemporaryFile();f.write(b'x'*262144);f.flush();print('ready',flush=True);time.sleep(20)"],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(owner.stdout.readline().strip(),'ready');binding=process_binding(owner.pid)
                # Inspector and owner are siblings: family-only traversal cannot see owner.
                code="import sys,json;sys.path.insert(0,sys.argv[1]);from allocation_measurement import measure;print(json.dumps(measure(sys.argv[2],require_family=True,owners=json.loads(sys.argv[3]))))"
                def inspect(value):return subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'prototype'),root,json.dumps(value)],capture_output=True,text=True,timeout=5)
                plain=inspect({});self.assertEqual(plain.returncode,0,plain.stderr)
                bound=inspect({'tradebot-lifecycle':binding});self.assertEqual(bound.returncode,0,bound.stderr)
                self.assertGreaterEqual(json.loads(bound.stdout)['unlinked_regular_bytes']-json.loads(plain.stdout)['unlinked_regular_bytes'],262144)
                stale=inspect({'tradebot-lifecycle':{**binding,'start_ticks':binding['start_ticks']+1}})
                self.assertNotEqual(stale.returncode,0);self.assertIn('identity changed',stale.stderr)
                owner.terminate();owner.wait()
                self.assertNotEqual(inspect({'tradebot-lifecycle':binding}).returncode,0)
            finally:
                if owner.poll() is None:owner.kill();owner.wait()
                owner.stdout.close()

    def test_sparse_length_hardlinks_and_open_fd_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'sparse.bin'
            with p.open('wb') as f:f.truncate(1024*1024)
            os.link(p,Path(root)/'alias.bin')
            with p.open('rb'):
                report=measure(root,[p]);self.assertEqual(report['named_bytes'],max(p.stat().st_size,p.stat().st_blocks*512))
    def test_unlinked_temp_is_included_without_reading_payload(self):
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryFile(dir=root) as f:
            f.write(b'x'*65536);f.flush();report=measure(root)
            self.assertGreaterEqual(report['unlinked_regular_bytes'],65536)
    def test_symlinks_hold(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'target';p.write_text('fixture');(Path(root)/'alias').symlink_to(p)
            with self.assertRaisesRegex(ValueError,'symlink'):measure(root)
    @unittest.skipUnless(sys.platform=='linux','Linux owned-child descriptor visibility')
    def test_worker_thread_child_unlinked_temp_is_included(self):
        import threading
        with tempfile.TemporaryDirectory() as root:
            children=[];ready=threading.Event();finish=threading.Event()
            code="import tempfile,time;f=tempfile.TemporaryFile();f.write(b'x'*131072);f.flush();print('ready',flush=True);time.sleep(10)"
            def launch():
                child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True);children.append(child);self.assertEqual(child.stdout.readline().strip(),'ready');ready.set();finish.wait(5)
            t=threading.Thread(target=launch);t.start();self.assertTrue(ready.wait(5))
            try:
                report=measure(root,require_family=True);self.assertGreaterEqual(report['observed_processes'],2);self.assertGreaterEqual(report['unlinked_regular_bytes'],131072)
            finally:
                finish.set();t.join()
                for child in children:child.kill();child.wait();child.stdout.close()

    def test_live_sqlite_disk_sort_temp_descriptor_is_measured(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as root:
            db=sqlite3.connect(Path(root)/'sort.db')
            try:
                db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA cache_size=10')
                if db.execute('PRAGMA temp_store').fetchone()[0]!=1:self.skipTest('SQLite build forces in-memory TEMP')
                db.execute('CREATE TABLE samples(value TEXT)')
                with db:db.executemany('INSERT INTO samples VALUES(?)',(('x'*2048+str(i),) for i in range(4096)))
                cursor=db.execute('SELECT value FROM samples ORDER BY value DESC');cursor.fetchone()
                try:self.assertGreater(measure(root)['unlinked_regular_bytes'],0)
                finally:cursor.close()
            finally:db.close()
