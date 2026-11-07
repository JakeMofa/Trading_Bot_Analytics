import json, os, pathlib, subprocess, sys, tempfile, unittest

BACKEND=pathlib.Path(__file__).resolve().parents[1]

class LockTraceTests(unittest.TestCase):
    def test_markers_opt_in_and_private_paths(self):
        import importlib.util, sqlite3
        spec=importlib.util.spec_from_file_location('lock_markers',BACKEND/'diagnostics/sitecustomize.py')
        module=importlib.util.module_from_spec(spec)
        original=sqlite3.connect
        spec.loader.exec_module(module)
        self.assertIs(sqlite3.connect,original)
        for path in ('/opt/tradebot/data/fixture.db','/tmp/fixture.db',':memory:'):
            with self.assertRaises(ValueError):module.connect(path)

    def test_syscall_lock_ranges_and_unfinished_exit_validation(self):
        def trace(path):
            lines=[]
            def marker(t,event):
                message='LOCKDIAG '+json.dumps({'pid':7,'event':event,'real_ns':int(t*1e9),'mono_ns':int(t*1e9)})+'\n'
                lines.append(f'7 {t:.6f} write(2<pipe:[1]>, {json.dumps(message)}, 100) = 100 <0.000001>')
            for base in (1,2): # setup BEGIN then one retention BEGIN
                marker(base,'begin_entry')
                lines.append(f'7 {base+.001:.6f} fcntl(5<{path}>, F_SETLK, {{l_type=F_WRLCK, l_whence=SEEK_SET, l_start=120, l_len=1}}) = 0 <0.000010>')
                marker(base+.01,'commit_entry')
                lines.append(f'7 {base+.02:.6f} fcntl(5<{path}>, F_SETLK, {{l_type=F_UNLCK, l_whence=SEEK_SET, l_start=120, l_len=1}}) = 0 <0.000010>')
                marker(base+.04,'commit_return')
            return '\n'.join(lines)+'\n'
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)
            (p/'stdout.jsonl').write_text(json.dumps({'timestamp_engine':'indexed_invalid_v1','collector':{},'elapsed_seconds':1,'production_guard_errors':[]}))
            def run():return subprocess.run([sys.executable,str(BACKEND/'analyze_retention_lock_trace.py'),folder],capture_output=True,text=True)
            (p/'trace.txt').write_text(trace('/tmp/generated-retention-x/fixture.db-shm'))
            self.assertEqual(run().returncode,0)
            report=json.loads((p/'analysis.json').read_text())
            self.assertEqual(report['batch_count'],1)
            self.assertAlmostEqual(report['slowest']['post_release_ms'],19.99,places=3)
            (p/'trace.txt').write_text(trace('/tmp/generated-retention-x/fixture.db'))
            self.assertNotEqual(run().returncode,0) # unrelated lock is not occupancy
            (p/'trace.txt').write_text(trace('/tmp/generated-retention-x/fixture.db-shm')+'7 3.000000 fdatasync(4<fixture.db-wal> <unfinished ...>\n')
            self.assertNotEqual(run().returncode,0)
