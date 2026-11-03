"""Generated A/B/core only. Linux root additionally proves full FD drainage."""
import sys,os,tempfile,unittest,json,sqlite3,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from raw_generations import Store,MemoryArchive,Stop,Unproven,iso
T=datetime(2026,1,1,tzinfo=timezone.utc)
def observation(at,market='m'):
    return {'market_id':market,'received_at':iso(at),'source_time':iso(at),'kind':'book','payload':'{"price":12345.1234567890123456789,"venue":"polymarket.us"}'}
def ticker(at,event='1',source=None):
    return {'source':'coinbase','event_id':event,'received_at':iso(at),'source_time':iso(source or at),'price':'12345.1234567890123456789','size':'0.00000001','side':'buy','payload':'{"provenance":"coinbase","n":0.1234567890123456789}'}

class Tests(unittest.TestCase):
    def setup_two(self,folder):
        store=Store(folder);oid=store.save('observations','book1',observation(T))
        sid=store.save('stream_events','coinbase:1',ticker(T))
        a=store.active()['id'];store.save('observations','book2',observation(T+timedelta(hours=72),'next'))
        return store,a,oid
    def test_real_core_a_b_and_receipt_boundary_reads_exact_precision(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,a,oid=self.setup_two(f)
            try:
                self.assertEqual(len(list(Path(f).glob('raw-*.db'))),2);self.assertTrue((Path(f)/'core.db').exists())
                rows=s.history('observations',T,T+timedelta(hours=73));self.assertEqual([r['id'] for r in rows],[oid,3])
                self.assertEqual({r['generation_id'] for r in rows},{a,s.active()['id']})
                self.assertIn('12345.1234567890123456789',rows[0]['payload'])
                self.assertEqual(s.core.execute("SELECT COUNT(*) FROM generations WHERE state='active'").fetchone()[0],1)
                self.assertEqual(s.core.execute("SELECT state FROM generations WHERE id=?",(a,)).fetchone()[0],'sealed')
                self.assertEqual(s.inputs(T,T+timedelta(hours=73))['mean'],'12345.1234567890123456789')
                self.assertEqual(s.core.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:s.close()
    def test_late_source_no_lookahead_and_duplicates_across_rotation(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f)
            try:
                one=s.save('stream_events','coinbase:1',ticker(T))
                s.save('stream_events','coinbase:2',ticker(T+timedelta(hours=72),'2',T-timedelta(hours=100)))
                s.save('stream_events','coinbase:3',ticker(T+timedelta(hours=72,seconds=1),'3',T+timedelta(hours=74)))
                self.assertEqual(s.inputs(T,T+timedelta(hours=73))['count'],2)
                self.assertEqual(s.save('stream_events','coinbase:1',ticker(T+timedelta(hours=73),source=T)),one)
                bad=ticker(T,event='1');bad['price']='9'
                with self.assertRaises(Stop):s.save('stream_events','coinbase:1',bad)
                with self.assertRaises(Stop):s.save('observations','oldreceipt',observation(T))
                with self.assertRaises(Stop):s.history('stream_events',T,T+timedelta(hours=75),limit=1)
            finally:s.close()
    def test_full_slots_archive_outage_backpressure_not_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,a,oid=self.setup_two(f);cloud=MemoryArchive()
            try:
                cloud.available=False
                with self.assertRaises(Stop):s.archive_hour(cloud,T+timedelta(hours=73))
                before={p.name:p.stat().st_size for p in Path(f).glob('raw-*.db')}
                with self.assertRaisesRegex(Stop,'both slots'):s.save('observations','third',observation(T+timedelta(hours=144)))
                self.assertEqual(before,{p.name:p.stat().st_size for p in Path(f).glob('raw-*.db')})
                self.assertEqual(s.core.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)
            finally:s.close()
    def test_incremental_hourly_archive_uses_existing_exact_verifier(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f);cloud=MemoryArchive()
            try:
                s.save('observations','one',observation(T));self.assertEqual(s.archive_hour(cloud,T+timedelta(minutes=59)),0)
                self.assertEqual(s.archive_hour(cloud,T+timedelta(hours=1)),1)
                self.assertEqual(s.archive_hour(cloud,T+timedelta(hours=1)),0)
                s.save('observations','two',observation(T+timedelta(hours=1)));self.assertEqual(s.archive_hour(cloud,T+timedelta(hours=2)),1)
                self.assertEqual(len(cloud.objects),2)
            finally:s.close()
    def test_refuse_corrupt_missing_young_active_readers_and_unprotected_evidence(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,a,oid=self.setup_two(f);cloud=MemoryArchive()
            try:
                with self.assertRaises(Stop):s.retire(s.active()['id'],cloud,T+timedelta(days=10))
                with self.assertRaisesRegex(Stop,'strict72'):s.retire(a,cloud,T+timedelta(hours=72))
                with self.assertRaisesRegex(Stop,'coverage'):s.retire(a,cloud,T+timedelta(hours=145))
                s.archive_hour(cloud,T+timedelta(hours=145))
                with s.reader(a):
                    with self.assertRaisesRegex(Stop,'reader'):s.retire(a,cloud,T+timedelta(hours=145))
                key=next(k for k in cloud.objects if k.startswith(a+'/'))
                original=cloud.objects[key];cloud.objects[key]=original+b'x'
                with self.assertRaises(ValueError):s.retire(a,cloud,T+timedelta(hours=145))
                cloud.objects[key]=original
                with s.core:s.core.execute('INSERT INTO required_evidence VALUES(?)',(oid,))
                with self.assertRaisesRegex(Stop,'protected'):s.retire(a,cloud,T+timedelta(hours=145))
                self.assertTrue(s.path(a).exists())
                s.protect(oid,'prediction','m',T+timedelta(seconds=1));self.assertEqual(s.core.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:s.close()
    def test_budget_guard_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f)
            try:
                s.ceiling=s.allocation()['total_bytes']
                with self.assertRaisesRegex(Stop,'guard'):s.save('observations','one',observation(T))
                self.assertEqual(s.core.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
            finally:s.close()
        with self.assertRaises(Exception):Store('/opt/tradebot')
    def test_restart_after_each_rotation_and_write_handoff_stage(self):
        for phase in ('rotation_planned','rotation_file_created','rotation_published','intent_committed','raw_committed','intent_acknowledged'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                s=Store(f)
                def crash(at):
                    if at==phase:raise RuntimeError('generated crash')
                s.fault=crash
                with self.assertRaises(RuntimeError):s.save('observations','event',observation(T))
                s.close();s=Store(f)
                try:
                    eid=s.save('observations','event',observation(T));s.close();s=Store(f)
                    self.assertEqual(s.save('observations','event',observation(T)),eid)
                    self.assertEqual(s.core.execute("SELECT COUNT(*) FROM events WHERE status='pending'").fetchone()[0],0)
                    self.assertEqual(len(s.history('observations',T,T)),1)
                finally:s.close()
    def test_real_process_exit_after_raw_commit_replays_exactly_once(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            code='import sys,os;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]/'prototype'))+');from raw_generations import Store;s=Store('+repr(f)+');s.fault=lambda phase:os._exit(17) if phase=="raw_committed" else None;s.save("observations","event",'+repr(observation(T))+')'
            p=__import__('subprocess').run([sys.executable,'-c',code],timeout=10);self.assertEqual(p.returncode,17)
            s=Store(f)
            try:self.assertEqual(len(s.history('observations',T,T)),1);self.assertEqual(s.save('observations','event',observation(T)),1)
            finally:s.close()
    def test_archive_crash_is_idempotent_and_future_evidence_refused(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f);cloud=MemoryArchive();eid=s.save('observations','one',observation(T))
            with self.assertRaisesRegex(Stop,'future'):s.protect(eid,'p','m',T-timedelta(seconds=1))
            def crash(phase):
                if phase=='archive_readback_verified':raise RuntimeError('generated crash')
            s.fault=crash
            with self.assertRaises(RuntimeError):s.archive_hour(cloud,T+timedelta(hours=1))
            s.close();s=Store(f)
            try:
                self.assertEqual(s.archive_hour(cloud,T+timedelta(hours=1)),1)
                self.assertEqual(len(cloud.objects),1);self.assertEqual(s.archive_hour(cloud,T+timedelta(hours=1)),0)
            finally:s.close()
    def test_worker_owned_connections_do_not_add_another_raw_writer(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f);cloud=MemoryArchive();s.save('observations','one',observation(T))
            def archive():
                with s.worker_session():
                    with self.assertRaisesRegex(Stop,'one raw writer'):s.save('observations','two',observation(T))
                    return s.archive_hour(cloud,T+timedelta(hours=1))
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:self.assertEqual(pool.submit(archive).result(),1)
                self.assertEqual(s.worker_count,0)
            finally:s.close()
    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'Full OS descriptor proof uses Linux root in separate generated CI step')
    def test_retire_real_file_keep_protected_evidence_and_reuse_role_fresh_identity(self):
        for phase in (None,'retirement_authorized','retirement_normal_close','retirement_file_removed'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                s,a,oid=self.setup_two(f);cloud=MemoryArchive();s.archive_hour(cloud,T+timedelta(hours=145));s.protect(oid,'p','m',T+timedelta(seconds=1))
                if phase:
                    def crash(at):
                        if at==phase:raise RuntimeError('generated crash')
                    s.fault=crash
                    with self.assertRaises(RuntimeError):s.retire(a,cloud,T+timedelta(hours=145))
                    s.close();s=Store(f)
                if s.path(a).exists():s.retire(a,cloud,T+timedelta(hours=145))
                self.assertFalse(s.path(a).exists());self.assertEqual(s.core.execute('SELECT COUNT(*) FROM predictions').fetchone()[0],1)
                s.save('observations','third',observation(T+timedelta(hours=145)))
                self.assertNotEqual(s.active()['id'],a);self.assertEqual(s.active()['slot'],'A');s.close()

    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'Linux root descriptor proof')
    def test_unmanaged_open_handle_blocks_actual_retirement(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,a,oid=self.setup_two(f);cloud=MemoryArchive();s.archive_hour(cloud,T+timedelta(hours=145))
            db=sqlite3.connect(s.path(a));db.execute('SELECT COUNT(*) FROM observations').fetchone()
            try:
                with self.assertRaisesRegex(Stop,'handles'):s.retire(a,cloud,T+timedelta(hours=145))
                self.assertTrue(s.path(a).exists())
            finally:db.close();s.close()

    def test_qualification_timeline_activates_at_zero_and_crosses72h(self):
        from qualify_ab import event_at
        self.assertEqual(event_at(0,4000),T)
        self.assertEqual(event_at(2000,4000),T+timedelta(hours=72))
        self.assertLess(event_at(1999,4000),T+timedelta(hours=72))
    def test_input_projection_matches_flat_reference_with_late_and_future_sources(self):
        from decimal import Decimal
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f);rows=[]
            for i,(at,price,source) in enumerate([(T,'1.100000000000000001',T),(T+timedelta(hours=72),'3.100000000000000001',T),(T+timedelta(hours=72,seconds=1),'9.9',T+timedelta(hours=74))]):
                r=ticker(at,str(i),source);r['price']=price;rows.append(r);s.save('stream_events','coinbase:'+str(i),r)
            asof=T+timedelta(hours=73)
            expected=[r for r in rows if r['received_at']<=iso(asof) and r['source_time']<=iso(asof)]
            actual=s.inputs(T,asof)
            self.assertEqual(actual['count'],len(expected));self.assertEqual(actual['mean'],str(sum(Decimal(r['price']) for r in expected)/len(expected)))
            s.close()

    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'Scaled Linux qualification runs in generated-only CI step')
    def test_one_fixed_scaled_linux_profile(self):
        script=Path(__file__).resolve().parents[1]/'prototype/qualify_ab.py'
        result=subprocess.run([sys.executable,str(script)],text=True,capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout);self.assertEqual(report['status'],'PASS_SCALED',result.stdout)
        self.assertTrue(report['workload_complete']);self.assertEqual(report['rows'],4000)
        self.assertEqual(set(report['generation_files']),{'A','B'})
        self.assertEqual(report['errors'],[])
        path=os.getenv('AB_REPORT_PATH')
        if path:Path(path).write_text(json.dumps(report))

    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'Linux root drain and retirement interference')
    def test_retiring_previous_generation_while_current_writer_advances(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,a,oid=self.setup_two(f);cloud=MemoryArchive();s.archive_hour(cloud,T+timedelta(hours=74))
            def retire():
                with s.worker_session():s.retire(a,cloud,T+timedelta(hours=73))
            worst=0
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(retire)
                    for i in range(100):
                        before=time.monotonic();s.save('stream_events','coinbase:'+str(100+i),ticker(T+timedelta(hours=73,seconds=i),str(100+i)));worst=max(worst,time.monotonic()-before)
                    future.result(timeout=10)
                self.assertLess(worst,1);self.assertFalse(s.path(a).exists())
                self.assertEqual(len(s.history('stream_events',T+timedelta(hours=72),T+timedelta(hours=74))),100)
            finally:s.close()
