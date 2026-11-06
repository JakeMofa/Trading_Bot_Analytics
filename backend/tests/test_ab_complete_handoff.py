"""One bounded Linux joint handoff: real local HTTP/SSE + serial application paths.

Synthetic feed transport and simulated timestamps, not venue cadence/load proof.
"""
import asyncio
from contextlib import closing,ExitStack,contextmanager
import multiprocessing
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import resource
import socket
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy,market,ApplicationStore,iso,Stop
from test_ab_runtime import environment
import collector,streaming,features,forecasts,dashboard,live_state,live_health,system_monitoring
from generated_cloud import GeneratedRemote
import httpx
import uvicorn


@contextmanager
def guarded_fixture():
    from qualify_application import fixture_owners
    root=Path(tempfile.mkdtemp(prefix='generated-ab-',dir=os.environ.get('AB_JOINT_WORKSPACE')))
    try:yield str(root)
    finally:
        if fixture_owners(root):raise AssertionError('generated fixture owners remain; retained '+str(root))
        shutil.rmtree(root)


def lifecycle_child(root,connection,deadline):
    """Spawned main thread owns SQLite/cloud; no inherited API connections."""
    import run_cloud_lifecycle
    class SlowRemote(GeneratedRemote):
        def handle(self,request):
            if request.method=='GET' and '/storage/' in request.url.path:time.sleep(.06)
            return super().handle(request)
    remote=SlowRemote(Path(root)/'cloud')
    env=environment(root,True);env['AB_STARTUP_MODE']='fresh-b'
    worker=None
    try:
        with patch.dict(os.environ,env,clear=True),patch.object(run_cloud_lifecycle,'SupabaseHTTP',side_effect=lambda config:remote.client(time.monotonic()+30).cloud):
            worker=run_cloud_lifecycle.build_worker(Path(root)/'generated-legacy.db')
            connection.send({'ready':True})
            while time.monotonic()<deadline:
                if not connection.poll(max(0,deadline-time.monotonic())):raise TimeoutError('original lifecycle deadline')
                command=connection.recv()
                if command=='close':return
                connection.send(worker.run_cycle(force=command=='force'))
    except BaseException as error:
        try:connection.send({'status':'FAIL','error_type':type(error).__name__})
        except (BrokenPipeError,EOFError):pass
    finally:
        if worker:worker.storage_runtime.close()
        connection.close()


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'joint retirement/FD proof requires Linux root')
class CompleteHandoff(unittest.TestCase):
    def test_joint_fresh_b_a_b_a_http_sse_and_lifecycle(self):
        started=time.monotonic();deadline=started+170
        if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
        metrics={'scope':'generated joint fresh B0→A1→B2→A3; requested A→B→A included',
                 'simulated_clock':True,'real_venue_cadence':False,'errors':[],
                 'save_max_seconds':0.,'ack_interval_max_seconds':0.,'api_max_seconds':0.,
                 'sse_max_seconds':0.,'current_price_max_seconds':0.,'feature_max_seconds':0.,
                 'history_max_seconds':0.,'heartbeat_max_seconds':0.,'phases':[],'sse_generations':[],
                 'maximum_feature_workers':0,'retirement_readbacks_and_reader_hold':0}
        def maximum(key,value):metrics[key]=max(metrics[key],value)
        def guard():
            if time.monotonic()>deadline:raise TimeoutError('original joint work deadline')
        async def until(predicate,seconds=4):
            end=min(deadline,time.monotonic()+seconds)
            while not predicate():
                if time.monotonic()>=end:raise TimeoutError('generated barrier')
                await asyncio.sleep(.01)
        with guarded_fixture() as root:
            root=Path(root)
            import test_recovery_bootstrap as recovery_fixture
            from migration_budget import MigrationBudget
            path,capsule,expected_history,_,_=recovery_fixture.Tests().fixture(root,live_name='generated-legacy.db',deadline=deadline)
            store=ApplicationStore(root,path,routing=True,fresh_b=True,generation_bytes=2*1024**2,recovery=capsule,migration_budget=MigrationBudget(row_limit=60000,deadline=deadline))
            with closing(store.worker_connection('history')) as recovered:
                from test_ab_application import T
                self.assertEqual(features.calculate(recovered,'m',T+timedelta(seconds=1)),expected_history)
                self.assertEqual(recovered.execute('SELECT id,snapshot_id FROM predictions').fetchone(),(1,1))
            metrics['recovered_legacy_inputs']=2;metrics['historical_feature_equivalence']=True
            state=live_state.LiveState();clock=[datetime(2026,1,2,tzinfo=timezone.utc)+timedelta(seconds=2)]
            class Clock(datetime):
                @classmethod
                def now(cls,tz=None):return clock[0] if tz else clock[0].replace(tzinfo=None)
            worker=None;server=None;thread=None;main_db=None;history_hold=[None]
            lifecycle_pipe=None
            feature_original=streaming.feature_cycle;price_original=features._price
            active_features=[0];feature_lock=threading.Lock();published=[]
            publication_times={}
            def rotation_published(phase):
                if phase=='rotation_published':publication_times[store.protocol.active()['id']]=time.monotonic()
            store.protocol.fault=rotation_published
            publish_original=streaming.publish_feature_cycle
            def measured_feature(*args,**kwargs):
                before=time.monotonic()
                with feature_lock:
                    active_features[0]+=1;maximum('maximum_feature_workers',active_features[0])
                try:return feature_original(*args,**kwargs)
                finally:
                    active_features[0]-=1;maximum('feature_max_seconds',time.monotonic()-before)
            def measured_price(*args,**kwargs):
                before=time.monotonic()
                try:return price_original(*args,**kwargs)
                finally:maximum('current_price_max_seconds',time.monotonic()-before)
            def publish(cycle,*args,**kwargs):
                result=publish_original(cycle,*args,**kwargs)
                if result:published.append(cycle)
                return result
            try:
                with ExitStack() as stack:
                    for module in (collector,streaming,features,forecasts,live_state):stack.enter_context(patch.object(module,'utcnow',side_effect=lambda:clock[0]))
                    stack.enter_context(patch.object(live_health,'datetime',Clock));stack.enter_context(patch.object(dashboard,'datetime',Clock))
                    stack.enter_context(patch.object(system_monitoring,'datetime',Clock))
                    stack.enter_context(patch.object(streaming,'feature_cycle',side_effect=measured_feature))
                    stack.enter_context(patch.object(features,'_price',side_effect=measured_price))
                    stack.enter_context(patch.object(streaming,'publish_feature_cycle',side_effect=publish))
                    env=environment(root,True);env['AB_STARTUP_MODE']='fresh-b'
                    stack.enter_context(patch.dict(os.environ,env,clear=True))
                    context=multiprocessing.get_context('spawn')
                    lifecycle_pipe,child_pipe=context.Pipe()
                    worker=context.Process(target=lifecycle_child,args=(str(root),child_pipe,deadline));worker.start();child_pipe.close()
                    self.assertTrue(lifecycle_pipe.poll(5),'lifecycle startup deadline')
                    self.assertEqual(lifecycle_pipe.recv(),{'ready':True})
                    # The API uses the same real history worker factory as runtime.
                    with patch.dict(os.environ,{'ENABLE_AB_STORAGE':'false'}):
                        from api import create_app
                        app=create_app(state,db_path=str(root/'core.db'),start_collectors=False,
                                       read_connection_factory=lambda:store.worker_connection('history'))
                    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                    server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=1))
                    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
                    async def lifecycle_run(force=False):
                        lifecycle_pipe.send('force' if force else 'cycle')
                        return await asyncio.to_thread(lifecycle_pipe.recv)
                    async def scenario():
                        nonlocal main_db
                        await until(lambda:server.started)
                        main_db=store.connection();stop=asyncio.Event();feed_on=asyncio.Event();feed_on.set();feature_wake=asyncio.Event()
                        acknowledgements=[];last_ack=[None];current=[market(clock[0]-timedelta(seconds=2),'m0')]
                        def discover():
                            def wire(base,url):
                                if url.endswith('/ticker'):return {'price':'12342.000000000000001','time':iso(clock[0])}
                                if '/markets/' in url:return {'marketData':{'transactTime':iso(clock[0])}}
                                raise ValueError('synthetic delayed outcome unavailable')
                            with patch.object(collector,'discover',return_value={900:current[0]}),patch.object(collector,'get_json',side_effect=wire):
                                messages=collector.collect_once(main_db)
                            if any('failed' in x.lower() for x in messages):raise Stop('generated discovery failed')
                            streaming.sync_live_market(main_db,state,clock[0])
                        def candles():
                            wanted=int(clock[0].timestamp())//60*60-60
                            with main_db:
                                for k in range(18):
                                    p=str(12300+k%3*10)
                                    main_db.execute('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',('coinbase','BTC-USD',60,wanted-k*60,p,p,p,p,'1.00000001',iso(clock[0]-timedelta(hours=1))))
                        discover();candles()
                        async def feed():
                            index=0
                            while not stop.is_set():
                                await feed_on.wait();guard();index+=1
                                at=clock[0];before=time.monotonic()
                                msg={'type':'ticker','product_id':'BTC-USD','trade_id':50000+index,'time':iso(at),
                                     'price':str(12342+index)+'.000000000000001','last_size':'0.00000001','side':'buy'}
                                if not streaming.save_coinbase(main_db,msg):raise Stop('new synthetic tick not acknowledged')
                                state.update_coinbase_ticker(msg,iso(at))
                                book={'marketData':{'marketSlug':current[0]['slug'],'transactTime':iso(at),
                                      'stats':{'lastPriceSample':{'longPx':{'value':'0.51'},'shortPx':{'value':'0.49'}}}}}
                                if not streaming.save_polymarket(main_db,book):raise Stop('new book not acknowledged')
                                self.assertTrue(state.update_polymarket(book,iso(at)),'RAM rejected synthetic current-market quote')
                                for source in ('coinbase_stream','polymarket_stream'):streaming.health(main_db,source,'live',data=True,live_state=state)
                                maximum('save_max_seconds',time.monotonic()-before)
                                done=time.monotonic()
                                if last_ack[0] is not None:maximum('ack_interval_max_seconds',done-last_ack[0])
                                last_ack[0]=done;acknowledgements.append(str(msg['trade_id']))
                                clock[0]+=timedelta(microseconds=1)
                                await asyncio.sleep(.15)
                        original_pause=streaming.pause
                        async def pause(event,seconds):
                            if seconds==15:
                                await feature_wake.wait();feature_wake.clear()
                            else:await original_pause(event,seconds)
                        async def heartbeat():
                            previous=time.monotonic()
                            while not stop.is_set():
                                await asyncio.sleep(.05);now=time.monotonic();maximum('heartbeat_max_seconds',now-previous);previous=now
                        events=[]
                        async def sse(client):
                            async with client.stream('GET','/events') as response:
                                self.assertEqual(response.status_code,200)
                                async for line in response.aiter_lines():
                                    if line.startswith('data: '):
                                        value=json.loads(line[6:]);events.append((time.monotonic(),value))
                                        gid=(value.get('active_buffer') or {}).get('generation_id')
                                        if gid:metrics['sse_generations'].append(gid)
                        with patch.object(streaming,'pause',side_effect=pause):
                            producer=asyncio.create_task(feed());await until(lambda:len(acknowledgements)>0)
                            feature=asyncio.create_task(streaming.feature_loop('unused',main_db,stop,state,connection_factory=lambda:store.worker_connection('feature')))
                            rotation=asyncio.create_task(streaming.buffer_rotation_loop(store,main_db,stop,state))
                            beat=asyncio.create_task(heartbeat())
                            app.state.collector_task=producer
                            async with httpx.AsyncClient(base_url='http://127.0.0.1:'+str(port),timeout=2) as client:
                                event_task=asyncio.create_task(sse(client))
                                prices=[]
                                async def measured_get(path):
                                    before=time.monotonic()
                                    try:return await client.get(path)
                                    except httpx.TimeoutException:
                                        metrics['http_timeouts']=metrics.get('http_timeouts',0)+1
                                        raise
                                    finally:
                                        maximum('api_max_seconds',time.monotonic()-before)
                                        metrics['http_requests']=metrics.get('http_requests',0)+1
                                async def probe():
                                    before=time.monotonic();response=await measured_get('/system/status');maximum('api_max_seconds',time.monotonic()-before)
                                    self.assertEqual(response.status_code,200)
                                    self.assertEqual(response.json()['active_buffer']['generation_id'],store.protocol.active()['id'])
                                    self.assertEqual(response.json()['feeds']['coinbase']['status'],'live')
                                    self.assertEqual(response.json()['feeds']['polymarket']['status'],'live')
                                    current_state=(await measured_get('/state/current')).json()
                                    self.assertEqual(current_state['market']['id'],current[0]['id'])
                                    prices.append(current_state['coinbase']['price_usd'])
                                    self.assertEqual(current_state['polymarket']['slug'],current[0]['slug'])
                                    before=time.monotonic();history=await measured_get('/history/predictions');maximum('history_max_seconds',time.monotonic()-before)
                                    self.assertEqual(history.status_code,200);self.assertTrue(history.json()['items'])
                                try:
                                    await until(lambda:len(published)>=1);await probe()
                                    metrics['first_phase_baseline']={key:metrics[key] for key in ('save_max_seconds','api_max_seconds','current_price_max_seconds','feature_max_seconds','history_max_seconds')}
                                    metrics['phases'].append({'slot':store.protocol.active()['slot'],'id':store.protocol.active()['id'],'market':current[0]['id']})
                                    for phase in range(1,4):
                                        feed_on.clear();old=store.protocol.active()['id'];hold=store.worker_connection('history');history_hold[0]=hold
                                        raw=store.protocol.path(old)
                                        for padding in range(4):
                                            size=raw.stat().st_size+Path(str(raw)+'-wal').stat().st_size
                                            if size>=2*1024**2:break
                                            main_db.save_observation(current[0]['id'],iso(clock[0]),'padding-'+str(phase)+'-'+str(padding),{'padding':'x'*700000},iso(clock[0]));clock[0]+=timedelta(microseconds=1)
                                        metrics.setdefault('sealed_main_wal_peak_bytes',0)
                                        maximum('sealed_main_wal_peak_bytes',raw.stat().st_size+Path(str(raw)+'-wal').stat().st_size)
                                        change=time.monotonic();await until(lambda:store.protocol.active()['id']!=old)
                                        if phase==2:
                                            clock[0]=datetime(2026,1,2,tzinfo=timezone.utc)+timedelta(minutes=15,seconds=2)
                                            current[0]=market(clock[0]-timedelta(seconds=2),'m1');discover();candles()
                                            self.assertEqual((await measured_get('/health')).json()['status'],'degraded')
                                        else:clock[0]+=timedelta(seconds=1)
                                        feed_on.set();before_count=len(acknowledgements)
                                        archive=asyncio.create_task(lifecycle_run(True))
                                        while not archive.done():await probe();await asyncio.sleep(.02)
                                        result=await archive
                                        if producer.done():producer.result()
                                        self.assertEqual(result['status'],'ok',result)
                                        self.assertEqual(result['generation_retirement']['status'],'held',result)
                                        self.assertTrue(raw.exists());self.assertGreater(len(acknowledgements),before_count)
                                        hold.close();store.rotation_tick(clock[0])
                                        result=await lifecycle_run()
                                        self.assertEqual(result['generation_retirement']['status'],'ok',result)
                                        self.assertFalse(raw.exists());metrics['retirement_readbacks_and_reader_hold']+=1
                                        feature_wake.set();await until(lambda:len(published)>=phase+1)
                                        gid=store.protocol.active()['id'];await until(lambda:gid in metrics['sse_generations'])
                                        observed=next(t for t,value in events if (value.get('active_buffer') or {}).get('generation_id')==gid)
                                        maximum('sse_max_seconds',observed-publication_times[gid])
                                        metrics.setdefault('scheduler_request_to_sse_max_seconds',0.)
                                        maximum('scheduler_request_to_sse_max_seconds',observed-change)
                                        await probe()
                                        health=(await measured_get('/health')).json();self.assertEqual(health['status'],'ok',health)
                                        metrics['phases'].append({'slot':store.protocol.active()['slot'],'id':gid,'market':current[0]['id']})
                                    self.assertEqual([p['slot'] for p in metrics['phases']],['B','A','B','A'])
                                    self.assertEqual(len({p['id'] for p in metrics['phases']}),4)
                                    self.assertGreater(max(prices),min(prices),'HTTP values did not advance')
                                    metrics['http_price_values_advanced']=True
                                    self.assertEqual(main_db.execute('PRAGMA foreign_key_check').fetchall(),[])
                                    self.assertEqual(main_db.execute("SELECT count(*) FROM ab_events WHERE status='pending'").fetchone()[0],0)
                                    for key in acknowledgements:
                                        self.assertEqual(main_db.execute("SELECT count(*) FROM ab_events WHERE event_key=? AND status='committed'",('coinbase:'+key,)).fetchone()[0],1)
                                    feed_on.clear()
                                    clock[0]+=timedelta(seconds=31)
                                    self.assertEqual((await measured_get('/health')).json()['status'],'degraded')
                                    if event_task.done():event_task.result()
                                    metrics['http_timeouts']=metrics.get('http_timeouts',0)
                                    metrics['acknowledged_ticks']=len(acknowledgements)
                                finally:
                                    event_task.cancel();await asyncio.gather(event_task,return_exceptions=True)
                                    stop.set();feed_on.set();feature_wake.set()
                                    for task in (producer,rotation,feature,beat):task.cancel()
                                    await asyncio.gather(producer,rotation,feature,beat,return_exceptions=True)
                        self.assertEqual(metrics['maximum_feature_workers'],1)
                        self.assertLess(metrics['save_max_seconds'],1);self.assertLess(metrics['heartbeat_max_seconds'],1)
                        self.assertLess(metrics['api_max_seconds'],2);self.assertLess(metrics['sse_max_seconds'],2)
                        self.assertLess(metrics['history_max_seconds'],1);self.assertLess(metrics['feature_max_seconds'],30)
                    asyncio.run(scenario())
                    metrics['allocation']=store.protocol.allocation();self.assertLess(metrics['allocation']['total_bytes'],2*1024**3)
            finally:
                if history_hold[0]:history_hold[0].close()
                if main_db:main_db.close()
                if server:server.should_exit=True
                if thread:thread.join(3);self.assertFalse(thread.is_alive(),'local API did not drain')
                if worker:
                    if worker.is_alive():lifecycle_pipe.send('close')
                    worker.join(3)
                    if worker.is_alive():worker.kill();worker.join();self.fail('lifecycle process did not drain')
                    lifecycle_pipe.close()
                store.close()
        metrics['status']='PASS_GENERATED_JOINT'
        metrics['elapsed_seconds']=time.monotonic()-started
        self.assertLess(metrics['elapsed_seconds'],180)
        if os.environ.get('AB_JOINT_REPORT_PATH'):
            with open(os.environ['AB_JOINT_REPORT_PATH'],'x') as report:json.dump(metrics,report,sort_keys=True)
        print(json.dumps({'joint_application_handoff':metrics},sort_keys=True),flush=True)

    def test_process_crashes_at_reused_slot_preserve_acknowledged_and_archived_rows(self):
        import subprocess
        import gzip
        from raw_generations import FileArchive
        from test_ab_application import T
        for phase in ('rotation_planned','rotation_file_created','rotation_published'):
            with self.subTest(phase=phase),guarded_fixture() as folder:
                root=Path(folder);path=root/'generated-legacy.db';legacy(path)
                owner=ApplicationStore(root,path,routing=True,fresh_b=True)
                with closing(owner.connection()) as db:
                    first=db.save_observation('m',iso(T),'book',{'B0':'exact'},iso(T))
                b0=owner.protocol.active()['id'];owner.rotation_tick(T+timedelta(hours=72))
                with closing(owner.connection()) as db:
                    second=db.save_observation('m',iso(T+timedelta(hours=72,seconds=1)),'book',{'A1':'exact'},iso(T))
                archive=FileArchive(root/'archive');owner.protocol.archive_hour(archive,T+timedelta(hours=145))
                owner.protocol.retire(b0,archive,T+timedelta(hours=145));owner.close()
                code="""
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from test_ab_application import ApplicationStore,T,timedelta
root=Path(sys.argv[2]);phase=sys.argv[3]
def crash(at):
    if at==phase:os._exit(43)
store=ApplicationStore(root,root/'generated-legacy.db',routing=True,fresh_b=True,fault=crash)
store.rotation_tick(T+timedelta(hours=144))
raise AssertionError('fault did not fire')
"""
                result=subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parent),str(root),phase],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,43,result.stderr)
                owner=ApplicationStore(root,path,routing=True,fresh_b=True)
                try:
                    self.assertEqual(owner.protocol.active()['slot'],'B');self.assertNotEqual(owner.protocol.active()['id'],b0)
                    self.assertEqual(owner.protocol.active()['started'],iso(T+timedelta(hours=144)))
                    with closing(owner.connection()) as db:
                        self.assertEqual(db.execute('SELECT id FROM observations WHERE id=?',(second,)).fetchone(),(second,))
                        self.assertEqual(db.execute('SELECT count(*) FROM ab_events WHERE status=\'committed\'').fetchone()[0],2)
                        self.assertEqual(db.execute('SELECT count(*) FROM ab_raw_receipts').fetchone()[0],2)
                        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                    manifests=owner.protocol.core.execute('SELECT metadata FROM manifests WHERE gen=?',(b0,)).fetchall()
                    bodies=[json.loads(line)['row'] for (text,) in manifests for line in gzip.decompress(archive.download_bytes('market-raw',json.loads(text)['object_path'])).splitlines()]
                    self.assertEqual([row['id'] for row in bodies if row.get('id')==first],[first])
                finally:owner.close()
