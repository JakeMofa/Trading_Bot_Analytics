import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qualification_lock_gate import LockGate,LockGateFailure,TraceUnavailable

class Tests(unittest.TestCase):
    def markers(self,event,t):
        payload='LOCKDIAG '+json.dumps({'pid':7,'event':event,'real_ns':int(t*1e9),'mono_ns':int(t*1e9)})+'\n'
        return f'{t:.6f} write(2<pipe:[1]>, {json.dumps(payload)}, 120) = 120 <0.000001>'
    def lines(self,path=None,release=2.2):
        path=path or str(Path('/tmp/generated-retention-test/fixture.db-shm').resolve())
        return [self.markers('begin_entry',2),
            f'2.001000 fcntl(5<{path}>, F_SETLK, {{l_type=F_WRLCK, l_whence=SEEK_SET, l_start=120, l_len=1}}) = 0 <0.000010>',
            self.markers('commit_entry',2.01),
            f'{release:.6f} fcntl(5<{path}>, F_SETLK, {{l_type=F_UNLCK, l_whence=SEEK_SET, l_start=120, l_len=1}}) = 0 <0.000010>',
            self.markers('commit_return',2.8)]
    def gate(self):
        g=LockGate('unused','/tmp/generated-retention-test/fixture.db',7);g.enabled=True;return g
    def test_occupancy_is_independent_from_commit_and_post_release_delay(self):
        g=self.gate()
        for line in self.lines():g.consume(line)
        self.assertAlmostEqual(g.rows[0]['occupancy_upper_seconds'],.199012)
        self.assertAlmostEqual(g.rows[0]['commit_call_seconds'],.79)
        self.assertAlmostEqual(g.rows[0]['post_release_seconds'],.59999)
    def test_overrun_wrong_file_duplicate_and_missing_fail_closed(self):
        g=self.gate()
        with self.assertRaises(LockGateFailure):
            for line in self.lines(release=2.6):g.consume(line)
        for lines in (self.lines(path='/tmp/other.db-shm'),self.lines()[:2]+self.lines()[1:]):
            g=self.gate()
            with self.assertRaises(TraceUnavailable):
                for line in lines:g.consume(line)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'trace';p.write_text('');g=LockGate(p,'/tmp/generated-retention-test/fixture.db',7);g.arm()
            with self.assertRaises(TraceUnavailable):g.batch(1)
    def test_unfinished_syscall_exit_brackets_and_rounding_reserve(self):
        g=self.gate();lines=self.lines();g.consume(lines[0]);g.consume(lines[1]);g.consume(lines[2])
        g.consume('2.200000 fcntl(5<'+str(Path('/tmp/generated-retention-test/fixture.db-shm').resolve())+'>, F_SETLK, {l_type=F_UNLCK, l_whence=SEEK_SET, l_start=120, l_len=1} <unfinished ...>')
        g.consume('2.200020 <... fcntl resumed>) = 0 <0.000010>');g.consume(lines[-1])
        self.assertAlmostEqual(g.rows[0]['occupancy_upper_seconds'],.199022)
    def test_total_gate_and_production_constant_are_separate(self):
        g=self.gate();lines=self.lines()
        lines[0]=self.markers('begin_entry',1.7)
        with self.assertRaises(LockGateFailure):
            for line in lines:g.consume(line)
        backend=Path(__file__).resolve().parents[1]
        self.assertIn('MAX_WRITE_SECONDS = 0.5',(backend/'app/retention.py').read_text())
    def test_source_guard_rejects_replays_mismatch_and_expiry(self):
        from datetime import datetime,timedelta,timezone
        import qualify_retention_sql as q
        now=datetime.now(timezone.utc)
        state={'market':{'id':'1','slug':'m','start':(now-timedelta(seconds=5)).isoformat(),'end':(now+timedelta(seconds=60)).isoformat()},
               'polymarket':{'slug':'m','source_time':now.isoformat()},'coinbase':{'source_time':now.isoformat()}}
        self.assertTrue(q.require_current_sources(state,now))
        state['coinbase']['source_time']=(now-timedelta(seconds=31)).isoformat()
        with self.assertRaises(q.ProductionGuardStop):q.require_current_sources(state,now)
        state['coinbase']['source_time']=now.isoformat();state['polymarket']['slug']='old'
        with self.assertRaises(q.ProductionGuardStop):q.require_current_sources(state,now)
        state['polymarket']['slug']='m';state['market']['end']=now.isoformat()
        with self.assertRaises(q.ProductionGuardStop):q.require_current_sources(state,now)
    @unittest.skipUnless(sys.platform=='linux' and shutil.which('strace'),'Linux installed strace required; no install')
    def test_tiny_real_split_gate_qualification_full_and_complete(self):
        backend=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='tradebot-qualification-') as folder:
            result=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
                '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
                '--work-dir',folder,'--observations','100','--stream-events','100',
                '--require-indexed','--trade-id-base','1000000000','--batch-size','500','--split-gate','--trials','1'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report['qualification_result'],'PASS')
            self.assertEqual(report['sqlite_settings']['synchronous'],2)
            self.assertEqual(report['sqlite_settings']['wal_autocheckpoint'],1000)
            self.assertEqual(report['apply']['datasets']['observations']['deleted_rows'],98)
            self.assertEqual(report['apply']['datasets']['stream_events']['deleted_rows'],99)
            self.assertEqual(report['lock_evidence']['transactions'],2)
            self.assertLessEqual(report['lock_evidence']['max_occupancy_upper_seconds'],.5)
