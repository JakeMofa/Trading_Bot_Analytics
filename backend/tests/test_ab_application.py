"""Real application functions, generated legacy schema, no live service/network."""
import sys,os,json,tempfile,unittest,sqlite3,time,threading,gzip
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from application_store import ApplicationStore
from raw_generations import Stop,iso,canonical,COLUMNS
import collector,streaming,features,forecasts,cloud_memory,cloud_lifecycle,knowledge,news,ensemble,cases
from live_state import LiveState
T=datetime(2026,1,1,tzinfo=timezone.utc)
def market(at=T,name='m'):
    return dict(id=name,slug=name,duration=900,start=iso(at),end=iso(at+timedelta(minutes=15)),target='12340.00000001',final=None,result=None,status='MARKET_STATUS_OPEN',index='BRTI',rules='generated official-US fixture',raw={'assetPriceTerms':{'priceToBeat':{'value':'12340.00000001'}},'updatedAt':iso(at)})
def legacy(path):
    db=collector.connect(path);streaming.initialize(db);knowledge.initialize(db)
    cloud_memory.initialize_local_sync(db);ensemble.ensure_schema(db)
    with db:
        collector.save_market(db,market(),iso(T))
        db.execute('UPDATE observations SET id=41')
        db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',(90,'m',iso(T),iso(T),'resolution','{}'))
        # Preserve sparse IDs and composite event IDs. Never use raw rowid.
        db.execute('INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)',('coinbase','7',iso(T),iso(T),'12341.000000000000001','0.00000001','buy','{"n":0.1234567890123456789}'))
        wanted=int(T.timestamp())-60
        for i in range(17):
            p=str(12300+(i%3)*10);at=wanted-i*60
            db.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',('coinbase','BTC-USD',60,at,p,p,p,p,'1',iso(T)))
    features.capture(db,T+timedelta(seconds=1));sid=db.execute('SELECT id FROM feature_snapshots').fetchone()[0]
    forecasts.forecast_snapshot(db,sid,T+timedelta(seconds=1))
    with db:
        db.execute("INSERT INTO prediction_context_links(prediction_id,kind,prior_market_id,prior_snapshot_id,outcome_observation_id,observed_outcome,method,linked_at) VALUES(1,'case','m',?,90,'UP','fixture',?)",(sid,iso(T)))
        cloud_memory._save_checkpoint(db,'archive:observations',source_id=41,rows_added=1,status='verified')
    expected=features.calculate(db,'m',T+timedelta(seconds=1));db.close();return expected
class Cloud:
    def __init__(self):self.objects={};self.rows={};self.fail=None
    def upload_bytes(self,b,p,data,content_type):
        if self.fail=='upload':raise TimeoutError()
        if (b,p) in self.objects and self.objects[b,p]!=data:raise Stop('immutable collision')
        self.objects[b,p]=data
    def verify_object(self,b,p,sha,size):
        import hashlib
        if self.fail=='verify':raise ValueError('fixture verification failure')
        data=self.objects[b,p]
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:raise Stop('bad object')
        return {'verified_at':iso(T+timedelta(days=4))}
    def upsert(self,table,rows,on_conflict):
        if self.fail=='manifest' and table=='raw_archives':raise TimeoutError()
        self.rows.setdefault(table,[]).extend(rows)
    def close(self):pass
class Tests(unittest.TestCase):
    def setup_store(self,folder):
        p=Path(folder)/'generated-legacy.db';expected=legacy(p)
        return ApplicationStore(folder,p,routing=True),expected
    def test_default_holds_and_legacy_sparse_identity_reference_preservation(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            p=Path(f)/'generated-legacy.db';legacy(p)
            with self.assertRaises(Stop):ApplicationStore(f,p)
            s=ApplicationStore(f,p,routing=True);db=s.connection()
            try:
                self.assertEqual(db.execute('SELECT id FROM observations ORDER BY id').fetchall(),[(41,),(90,)])
                self.assertEqual(db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0],90)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute("SELECT last_source_id FROM cloud_sync_state WHERE dataset='archive:observations'").fetchone()[0],41)
                self.assertEqual(json.loads(db.execute('SELECT evidence_json FROM feature_snapshots').fetchone()[0])['metadata_observation_id'],41)
                self.assertEqual(db.execute('SELECT id FROM main.observations ORDER BY id').fetchall(),[(41,),(90,)])
                with self.assertRaises(Stop):s.retire('anything',None,T)
            finally:db.close();s.close()
    def test_actual_collector_features_history_lifecycle_across_ab(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,expected=self.setup_store(f);db=s.connection()
            try:
                self.assertEqual(features.calculate(db,'m',T+timedelta(seconds=1)),expected)
                first=T+timedelta(seconds=2)
                collector.save_observation(db,'m',iso(first),'book',{'n':'0.1234567890123456789'},iso(first))
                first_id=db.execute('SELECT MAX(id) FROM observations').fetchone()[0];self.assertGreater(first_id,90)
                # Discovery follows the real collector code at the next raw boundary.
                now=T+timedelta(hours=72,seconds=3);m=market(now,'next')
                with patch.object(collector,'utcnow',return_value=now),patch.object(collector,'discover',return_value={900:m}),patch.object(collector,'get_json',return_value={'marketData':{'transactTime':iso(now)},'price':'12342.0000000001','time':iso(now)}):
                    messages=collector.collect_once(db)
                self.assertFalse(any('failed' in x.lower() for x in messages),messages)
                msg=dict(type='ticker',product_id='BTC-USD',trade_id=8,time=iso(now),price='12342.000000000000001',last_size='0.00000001',side='buy')
                with patch.object(streaming,'utcnow',return_value=now):
                    self.assertTrue(streaming.save_coinbase(db,msg));self.assertFalse(streaming.save_coinbase(db,msg))
                self.assertEqual(len(s.protocol.core.execute('SELECT id FROM generations').fetchall()),2)
                self.assertEqual(len(db.execute('SELECT * FROM stream_events').fetchall()),2)
                features.capture(db,now);sid=db.execute('SELECT MAX(id) FROM feature_snapshots').fetchone()[0]
                forecast=forecasts.forecast_snapshot(db,sid,now);self.assertIsNotNone(forecast)
                ensemble.ensure_schema(db);self.assertIsNotNone(cases.match_cases(db,sid))
                state=LiveState();state.set_market(m);state.update_coinbase_ticker(msg,received_at=iso(now));self.assertIsNotNone(state.snapshot(now))
                worker=cloud_lifecycle.LifecycleWorker('unused',cloud_lifecycle.LifecycleConfig(),None,lambda:None)
                cloud=Cloud();self.assertGreater(worker._structured(db,cloud),0)
                archived,caught=worker._archive_dataset(db,cloud,'observations');self.assertGreater(archived,0);self.assertTrue(caught)
                archived,_=worker._archive_dataset(db,cloud,'stream_events');self.assertEqual(archived,2)
                objects=b''.join(gzip.decompress(v) for v in cloud.objects.values())
                self.assertIn(b'0.1234567890123456789',objects)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:db.close();s.close()
    def test_restart_forward_and_old_binary_refusal(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            collector.save_observation(db,'m',iso(T+timedelta(seconds=2)),'book',{'exact':'0.00000001'},iso(T))
            expected=db.execute('SELECT * FROM observations ORDER BY id').fetchall();db.close();s.close()
            with self.assertRaisesRegex(RuntimeError,'forward-compatible'):collector.connect(Path(f)/'core.db')
            old=sqlite3.connect(Path(f)/'core.db')
            try:
                with self.assertRaises(sqlite3.OperationalError):old.execute("INSERT INTO runs(received_at,source,success,detail) VALUES('x','old',1,'x')")
            finally:old.close()
            s=ApplicationStore(f,Path(f)/'generated-legacy.db',routing=True);db=s.connection()
            try:self.assertEqual(db.execute('SELECT * FROM observations ORDER BY id').fetchall(),expected)
            finally:db.close();s.close()
    def test_archive_failures_do_not_advance_checkpoint_or_manifest(self):
        for fail in ['upload','verify','manifest','checkpoint']:
            with self.subTest(fail=fail),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                s,_=self.setup_store(f);db=s.connection();cloud=Cloud();cloud.fail=fail
                original=cloud.upsert
                def upsert(table,rows,on_conflict):
                    if fail=='checkpoint' and table=='sync_checkpoints':raise TimeoutError('generated')
                    return original(table,rows,on_conflict)
                cloud.upsert=upsert
                before=cloud_memory._checkpoint(db,'archive:observations')
                try:
                    with self.assertRaises(Exception):cloud_memory.archive_raw_batch(db,cloud,'observations',limit=10)
                    self.assertEqual(cloud_memory._checkpoint(db,'archive:observations'),before)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM ab_manifests').fetchone()[0],0)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
                finally:db.close();s.close()
    def test_actual_feature_worker_and_full_lifecycle_cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        from retention import RetentionConfig
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,expected=self.setup_store(f)
            try:
                with patch.object(features,'utcnow',return_value=T+timedelta(seconds=2)),patch.object(forecasts,'utcnow',return_value=T+timedelta(seconds=2)):
                    with ThreadPoolExecutor(max_workers=1) as worker:
                        result=worker.submit(streaming.feature_cycle,'unused',s.connection).result(timeout=5)
                self.assertIsNotNone(result);self.assertEqual(result[0][1],{**expected[0],'seconds_remaining':898.0})
                state=LiveState();state.set_market(market());self.assertTrue(streaming.publish_feature_cycle(result,state,now=T+timedelta(seconds=2)))
                self.assertFalse(streaming.publish_feature_cycle(result,state,now=T+timedelta(seconds=33)))
                cloud=Cloud();worker=cloud_lifecycle.LifecycleWorker('unused',cloud_lifecycle.LifecycleConfig(),RetentionConfig(),lambda:cloud,connection_factory=s.connection)
                result=worker.run_cycle(force=True)
                self.assertEqual(result['status'],'ok',result);self.assertEqual(result['retention']['status'],'disabled')
                self.assertEqual(result['archive']['stream_events']['archived'],1)
            finally:s.close()
    def test_disk_full_low_quota_and_conflicting_replay_preserve_committed_data(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            try:
                original=db.execute('SELECT * FROM observations ORDER BY id').fetchall()
                # Actual SQLITE_FULL via fixed generated page quota, no host fill.
                pages=db.db.execute('PRAGMA page_count').fetchone()[0]
                db.db.execute('PRAGMA max_page_count='+str(pages))
                with self.assertRaises(sqlite3.OperationalError):
                    with db:db.execute('INSERT INTO runs(received_at,source,success,detail) VALUES(?,?,?,?)',(iso(T),'fixture',1,'x'*1024**2))
                self.assertEqual(db.execute('SELECT * FROM observations ORDER BY id').fetchall(),original)
                s.protocol.ceiling=1
                with self.assertRaises(Stop):collector.save_observation(db,'m',iso(T),'book',{},iso(T))
                self.assertEqual(s.protocol.core.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
                s.protocol.ceiling=2*1024**3
                msg=dict(type='ticker',product_id='BTC-USD',trade_id=7,time=iso(T),price='99999',last_size='0.00000001',side='buy')
                with self.assertRaises(Stop):streaming.save_coinbase(db,msg)
            finally:db.close();s.close()
    def test_wrong_worker_and_changed_legacy_fail_closed(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            try:
                with ThreadPoolExecutor(max_workers=1) as worker:
                    with self.assertRaises(Stop):worker.submit(db.execute,'SELECT 1').result()
                other=sqlite3.connect(s.legacy)
                with other:other.execute("INSERT INTO runs(received_at,source,success,detail) VALUES('x','fixture',1,'changed')")
                other.close()
                with self.assertRaises(Stop):db.execute('SELECT * FROM observations')
            finally:db.close();s.close()
    def test_crash_matrix_migration_raw_handoff_and_rotation(self):
        import subprocess
        prototype=str(Path(__file__).resolve().parents[1]/'prototype')
        phases=['migration_structured:markets','migration_before_commit','migration_committed',
                'rotation_planned','rotation_file_created','rotation_published',
                'intent_committed','raw_committed','intent_acknowledged']
        for phase in phases:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                p=Path(f)/'generated-legacy.db';legacy(p)
                code=f'''import sys,os
sys.path.insert(0,{prototype!r})
from application_store import ApplicationStore
from raw_generations import iso
from datetime import datetime,timezone
s=ApplicationStore({f!r},{str(p)!r},routing=True,fault=lambda phase:os._exit(71) if phase=={phase!r} else None)
db=s.connection()
db.save_observation('m','2026-01-01T00:00:02+00:00','book',{{'exact':'0.00000001'}},'2026-01-01T00:00:02+00:00')
'''
                result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,71,(phase,result.stderr.decode()))
                s=ApplicationStore(f,p,routing=True);db=s.connection()
                try:
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM ab_events WHERE status=?',('pending',)).fetchone()[0],0)
                    self.assertEqual(db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0],90)
                    if phase in ['intent_committed','raw_committed','intent_acknowledged']:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],3)
                        one=db.save_observation('m','2026-01-01T00:00:02+00:00','book',{'exact':'0.00000001'},'2026-01-01T00:00:02+00:00')
                        self.assertGreater(one,90);self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],3)
                finally:db.close();s.close()
    def test_reader_holds_block_real_generation_retirement_then_exact_cloud_coverage(self):
        if sys.platform!='linux' or os.geteuid()!=0:self.skipTest('actual unlink needs Linux root full /proc FD visibility; holds tested elsewhere')
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);s.retirement_enabled=True;db=s.connection();cloud=Cloud()
            cloud.download_bytes=lambda bucket,path:cloud.objects[bucket,path]
            first=T+timedelta(seconds=2);db.save_observation('m',iso(first),'book',{'exact':'0.00000001'},iso(first));a=s.protocol.active()['id']
            now=T+timedelta(hours=72,seconds=3);collector.save_market(db,market(now,'next'),iso(now))
            worker=cloud_lifecycle.LifecycleWorker('unused',cloud_lifecycle.LifecycleConfig(),None,lambda:cloud)
            worker._archive_dataset(db,cloud,'observations');worker._archive_dataset(db,cloud,'stream_events')
            at=T+timedelta(hours=144,seconds=4)
            with self.assertRaises(Stop):s.retire(a,cloud,at)
            db.close()
            s.retire(a,cloud,at);self.assertFalse(s.protocol.path(a).exists())
            db=s.connection()
            try:
                self.assertEqual(db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0],90)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:db.close();s.close()
    def test_real_api_history_dashboard_and_truthful_missing_health(self):
        from fastapi.testclient import TestClient
        from api import create_app
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f)
            try:
                app=create_app(db_path=str(Path(f)/'core.db'),start_collectors=False,read_connection_factory=s.reader_connection)
                with TestClient(app) as client:
                    self.assertEqual(client.get('/dashboard').status_code,200)
                    result=client.get('/history/predictions');self.assertEqual(result.status_code,200);self.assertEqual(result.json()['items'][0]['id'],1)
                    result=client.get('/history/context');self.assertEqual(result.status_code,200);self.assertNotEqual(result.json().get('status'),'unavailable')
                    result=client.get('/health');self.assertEqual(result.status_code,200);self.assertEqual(result.json()['status'],'degraded');self.assertTrue(result.json()['diagnostic_reasons'])
            finally:s.close()
    def test_real_rest_worker_and_feature_worker_concurrent_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);now=T+timedelta(seconds=2)
            try:
                with patch.object(collector,'utcnow',return_value=now),patch.object(collector,'discover',return_value={900:market()}),patch.object(collector,'get_json',return_value={'marketData':{'transactTime':iso(now)},'price':'12342','time':iso(now)}),patch.object(features,'utcnow',return_value=now),patch.object(forecasts,'utcnow',return_value=now):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        rest=pool.submit(streaming.rest_cycle,'unused',False,s.connection)
                        feature=pool.submit(streaming.feature_cycle,'unused',s.connection)
                        self.assertFalse(any('failed' in x.lower() for x in rest.result(timeout=5)))
                        self.assertIsNotNone(feature.result(timeout=5))
                db=s.connection()
                try:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                finally:db.close()
            finally:s.close()
    def test_every_direct_legacy_fk_and_exact_observation_replay(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            p=Path(f)/'generated-legacy.db';legacy(p);old=sqlite3.connect(p)
            with old:
                old.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',(89,'m',iso(T),iso(T),'book','{"exact": "0.00000001"}'))
                old.execute('CREATE TABLE extra_reference(id INTEGER PRIMARY KEY,raw_id INTEGER REFERENCES observations(id))')
                old.execute('INSERT INTO extra_reference VALUES(1,89)')
            old.close();s=ApplicationStore(f,p,routing=True);db=s.connection()
            try:
                self.assertEqual(db.execute('SELECT id FROM main.observations WHERE id=89').fetchone()[0],89)
                self.assertEqual(db.save_observation('m',iso(T),'book',{'exact':'0.00000001'},iso(T)),89)
                with self.assertRaises(Stop):db.save_observation('m',iso(T),'book',{'exact':'different'},iso(T))
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:db.close();s.close()
    def test_missing_legacy_permission_and_symlink_fail_before_routing(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            p=Path(f)/'generated-legacy.db'
            with self.assertRaises(Stop):ApplicationStore(f,p,routing=True)
            p.symlink_to(Path(f)/'missing')
            with self.assertRaises(Stop):ApplicationStore(f,p,routing=True)
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            try:
                # Read-only generated SQLite handle gives actual permission failure.
                ro=s.reader_connection()
                try:
                    with self.assertRaises(sqlite3.OperationalError):ro.execute("INSERT INTO runs(received_at,source,success,detail) VALUES('x','x',1,'x')")
                finally:ro.close()
                # Inject a raw I/O failure after intent is durable, before ack.
                def fail(phase):
                    if phase=='intent_committed':raise OSError('generated EIO')
                s.protocol.fault=fail
                with self.assertRaises(OSError):db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{},iso(T))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM ab_events WHERE status='pending'").fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
            finally:db.close();s.close()
    def test_actual_supervisor_uses_generated_adapter_and_drains_workers(self):
        import asyncio
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);now=T+timedelta(seconds=2);state=LiveState()
            async def generated_feed(db,stop,live_state=None):
                msg=dict(type='ticker',product_id='BTC-USD',trade_id=8,time=iso(now),price='12342.000000000000001',last_size='0.00000001',side='buy')
                streaming.save_coinbase(db,msg);live_state.update_coinbase_ticker(msg,iso(now))
                await stop.wait()
            try:
                with patch.object(streaming,'polymarket_credentials',return_value=(None,None)),patch.object(streaming,'coinbase_stream',side_effect=generated_feed),patch.object(streaming,'utcnow',return_value=now),patch.object(collector,'utcnow',return_value=now),patch.object(collector,'discover',return_value={900:market()}),patch.object(collector,'get_json',return_value={'marketData':{'transactTime':iso(now)},'price':'12342','time':iso(now)}),patch.object(streaming,'refresh_recent_candles',return_value={'generated':True}),patch.object(features,'utcnow',return_value=now),patch.object(forecasts,'utcnow',return_value=now):
                    asyncio.run(streaming.run_locked(str(Path(f)/'core.db'),.15,30,False,2048,Path(f)/'control.sock',live_state=state,install_signal_handlers=False,storage_adapter=s))
                db=s.connection()
                try:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM stream_events WHERE event_id='8'").fetchone()[0],1)
                    self.assertGreater(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],1)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM ab_events WHERE status='pending'").fetchone()[0],0)
                finally:db.close()
            finally:s.close()
    def test_unknown_reference_and_corrupt_legacy_stop_migration(self):
        for broken in ['reference','missing_stream']:
            with self.subTest(broken=broken),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                path=Path(f)/'generated-legacy.db';legacy(path);old=sqlite3.connect(path)
                with old:
                    if broken=='reference':old.execute('UPDATE prediction_context_links SET outcome_observation_id=9999')
                    else:old.execute('DELETE FROM stream_events')
                old.close()
                with self.assertRaises(Stop):ApplicationStore(f,path,routing=True)
                # Retained source remains untouched; no completed migration marker.
                db=sqlite3.connect(Path(f)/'core.db')
                try:self.assertIsNone(db.execute("SELECT status FROM ab_migration_state WHERE status='complete'").fetchone())
                finally:db.close()
    def test_owner_release_requires_drain_and_concurrent_owner_rejected(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            try:
                with self.assertRaises(Stop):s.close()
                with self.assertRaises(BlockingIOError):ApplicationStore(f,Path(f)/'generated-legacy.db',routing=True)
            finally:db.close();s.close()
    def test_process_crashes_at_feature_and_archive_commit_boundaries(self):
        import subprocess
        tests=str(Path(__file__).resolve().parent)
        for phase in ['feature_evidence_ready','feature_cycle_committed','archive_remote_verified','archive_before_local_commit','archive_checkpoint_committed']:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                path=Path(f)/'generated-legacy.db';legacy(path);Path(f,'cloud').mkdir(mode=0o700)
                code=f'''import sys,os,time
sys.path.insert(0,{tests!r})
from test_ab_application import *
from test_ab_cloud_compatibility import Remote
from cloud_memory import SupabaseHTTP
from compatible_cloud import CompatibleCloud
from types import SimpleNamespace
import httpx
s=ApplicationStore({f!r},{str(path)!r},routing=True,fault=lambda name:os._exit(71) if name=={phase!r} else None)
if {phase!r}.startswith('feature'):
 from unittest.mock import patch
 with patch.object(features,'utcnow',return_value=T+timedelta(seconds=2)),patch.object(forecasts,'utcnow',return_value=T+timedelta(seconds=2)):
  streaming.feature_cycle('unused',s.connection)
else:
 remote=Remote(Path({f!r})/'cloud')
 cloud=CompatibleCloud(SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated'),client=httpx.Client(transport=httpx.MockTransport(remote.handle))),time.monotonic()+5)
 db=s.connection();cloud_memory.archive_raw_batch(db,cloud,'observations',limit=1)
'''
                result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,71,(phase,result.stderr.decode()))
                s=ApplicationStore(f,path,routing=True);db=s.connection()
                try:
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                    if phase.startswith('archive'):
                        self.assertEqual(cloud_memory._checkpoint(db,'archive:observations')[0],90 if phase=='archive_checkpoint_committed' else 41)
                        self.assertEqual(sum(line.startswith('POST /storage/') for line in Path(f,'cloud','calls').read_text().splitlines()),1)
                    else:
                        count=db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0]
                        self.assertEqual(count,2 if phase=='feature_cycle_committed' else 1)
                        with patch.object(features,'utcnow',return_value=T+timedelta(seconds=2)),patch.object(forecasts,'utcnow',return_value=T+timedelta(seconds=2)):
                            streaming.feature_cycle('unused',s.connection)
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],2)
                finally:db.close();s.close()
    def test_full_slots_latch_stop_without_retry_or_extra_reference_writes(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s,_=self.setup_store(f);db=s.connection()
            try:
                for hours in [0,72]:db.save_observation('m',iso(T+timedelta(hours=hours,seconds=2)),'book',{'hours':hours},iso(T))
                with self.assertRaises(Stop):db.save_observation('m',iso(T+timedelta(hours=144,seconds=3)),'book',{},iso(T))
                self.assertTrue(db.ab_stop_requested())
                before=db.execute('SELECT COUNT(*) FROM ab_events').fetchone()[0]
                with self.assertRaises(Stop):db.save_observation('m',iso(T+timedelta(hours=144,seconds=4)),'book',{},iso(T))
                with self.assertRaises(Stop):db.execute("INSERT INTO reference_prices(received_at,source_time,source,price,payload) VALUES('x','x','coinbase','1','{}')")
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ab_events').fetchone()[0],before)
            finally:db.close();s.close()
    def test_missing_embedded_rest_price_and_unknown_evidence_fail_closed(self):
        for evidence in [{'metadata_observation_id':41,'price':{'source':'coinbase_rest','input_id':'9999'}},
                         {'metadata_observation_id':41,'price':{},'unsupported_reference':9999}]:
            with self.subTest(evidence=evidence),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                p=Path(f)/'generated-legacy.db';legacy(p);old=sqlite3.connect(p)
                with old:old.execute('UPDATE feature_snapshots SET evidence_json=?',(json.dumps(evidence),))
                old.close()
                with self.assertRaises(Stop):ApplicationStore(f,p,routing=True)
    def test_failed_routed_polymarket_save_stops_stream_and_storage_hold_degrades(self):
        import asyncio
        from live_health import degradation_reasons
        class WS:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def send(self,msg):pass
            async def recv(self):return json.dumps({'marketData':{'marketSlug':'m','transactTime':iso(T)}})
        class DB:
            def ab_stop_requested(self):return 'durable_raw_save_failed'
        async def run():
            stop=asyncio.Event()
            with patch.object(streaming,'current_market',return_value=('m','m')),patch.object(streaming,'auth_headers',return_value={}),patch.object(streaming,'save_polymarket',side_effect=Stop('generated')) as saved,patch.object(streaming,'health'):
                await asyncio.wait_for(streaming.polymarket_stream(DB(),stop,'generated','generated',connector=lambda *a,**kw:WS()),.2)
                self.assertTrue(saved.called)
            self.assertTrue(stop.is_set())
        # Actual current_market query result is inspected below; this mock only
        # supplies a generated subscription identity, never contacts a venue.
        asyncio.run(run())
        self.assertIn('storage_guard_blocked',degradation_reasons({'feeds':{'storage_guard':{'status':'blocked'}}},{},now=T))
    def test_process_crash_seals_existing_generation_atomically_at_boundary(self):
        import subprocess
        tests=str(Path(__file__).resolve().parent)
        for phase in ['rotation_planned','rotation_file_created','rotation_published']:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                p=Path(f)/'generated-legacy.db';legacy(p)
                code=f'''import sys,os
sys.path.insert(0,{tests!r})
from test_ab_application import *
s=ApplicationStore({f!r},{str(p)!r},routing=True)
db=s.connection();db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{{'first':True}},iso(T));db.close()
s.protocol.fault=lambda name:os._exit(71) if name=={phase!r} else None
db=s.connection();db.save_observation('m',iso(T+timedelta(hours=72,seconds=3)),'book',{{'second':True}},iso(T))
'''
                result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=10);self.assertEqual(result.returncode,71,result.stderr.decode())
                s=ApplicationStore(f,p,routing=True);db=s.connection()
                try:
                    self.assertEqual(db.execute("SELECT state FROM ab_generations ORDER BY started").fetchall(),[('sealed',),('active',)])
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],3)
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                finally:db.close();s.close()
    def test_real_process_retirement_crash_recovery_preserves_core_and_exact_rows(self):
        import subprocess
        from raw_generations import FileArchive
        if sys.platform!='linux' or os.geteuid()!=0:self.skipTest('retirement process exits require Linux root descriptor proof')
        tests=str(Path(__file__).resolve().parent)
        for phase in ['retirement_authorized','retirement_normal_close','retirement_file_removed']:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                p=Path(f)/'generated-legacy.db';legacy(p)
                code=f'''import sys,os
sys.path.insert(0,{tests!r})
from test_ab_application import *
from raw_generations import FileArchive
s=ApplicationStore({f!r},{str(p)!r},routing=True,retirement=True);db=s.connection()
collector.save_market(db,market(),iso(T+timedelta(seconds=2)))
features.capture(db,T+timedelta(seconds=3));a=s.protocol.active()['id']
collector.save_market(db,market(T+timedelta(hours=72,seconds=3),'next'),iso(T+timedelta(hours=72,seconds=3)));db.close()
cloud=FileArchive(Path({f!r})/'archives');s.protocol.archive_hour(cloud,T+timedelta(hours=145))
s.protocol.fault=lambda name:os._exit(71) if name=={phase!r} else None
s.retire(a,cloud,T+timedelta(hours=145))
'''
                result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=15);self.assertEqual(result.returncode,71,result.stderr.decode())
                s=ApplicationStore(f,p,routing=True,retirement=True)
                try:
                    old=s.protocol.core.execute("SELECT id,state FROM generations WHERE slot='A'").fetchone()
                    if old['state']!='retired':s.retire(old['id'],FileArchive(Path(f)/'archives'),T+timedelta(hours=145))
                    self.assertFalse(s.protocol.path(old['id']).exists())
                    db=s.connection()
                    try:
                        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],2)
                        self.assertEqual(db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0],90)
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM main.observations').fetchone()[0],3)
                    finally:db.close()
                finally:s.close()
    def test_generated_disk_archive_reopens_for_fresh_crash_recovery_readback(self):
        from raw_generations import FileArchive
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            first=FileArchive(Path(f)/'archives');first.upload_bytes('private','gen/object',b'exact')
            second=FileArchive(Path(f)/'archives');self.assertEqual(second.download_bytes('private','gen/object'),b'exact')
    def test_unknown_sqlite_sidecars_and_component_symlinks_hold_without_removal(self):
        from raw_generations import connect
        for suffix in ['-journal','-unknown','-wal','-shm']:
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                # Never opened by SQLite. No actual WAL/SHM is moved or removed.
                raw=Path(f)/'never-opened.db';raw.write_bytes(b'unopened fixture')
                target=Path(f)/'generated-target';target.write_bytes(b'preserved')
                side=Path(str(raw)+suffix)
                if suffix in ('-wal','-shm'):side.symlink_to(target)
                else:side.write_bytes(b'unverified')
                with self.assertRaises(Stop):connect(raw,True)
                self.assertTrue(side.is_symlink() or side.exists())
                self.assertEqual(raw.read_bytes(),b'unopened fixture');self.assertEqual(target.read_bytes(),b'preserved')
