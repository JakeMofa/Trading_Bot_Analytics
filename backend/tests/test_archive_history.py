"""Application history readback, isolated subprocess HTTP, synthetic objects only."""
from contextlib import closing, contextmanager
import json, os, sys, tempfile, threading, time, unittest, sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import unquote
from test_ab_application import ApplicationStore, legacy, T, timedelta, iso, features, forecasts
from raw_generations import MemoryArchive
from cloud_memory import SupabaseHTTP
from compatible_cloud import CompatibleCloud

@contextmanager
def endpoint(remote):
    state={'mode':'normal','gets':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['gets']+=1
            prefix='/storage/v1/object/authenticated/market-raw/'
            if self.headers.get('Authorization')!='Bearer generated-only' or not self.path.startswith(prefix):
                self.send_error(403);return
            key=unquote(self.path[len(prefix):]);body=remote.objects.get(key)
            if state['mode']=='missing' or body is None:self.send_error(404);return
            if state['mode']=='hang':time.sleep(2)
            if state['mode']=='corrupt':body=b'corrupt'
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except BrokenPipeError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def factory(deadline):return CompatibleCloud(SupabaseHTTP(SimpleNamespace(url='http://127.0.0.1:'+str(server.server_port),secret_key='generated-only')),deadline)
    try:yield factory,state
    finally:server.shutdown();server.server_close();thread.join(2)

class Tests(unittest.TestCase):
    def test_changed_committed_receipt_blocks_archived_history(self):
        from fastapi.testclient import TestClient
        from api import create_app
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,now,remote,oid,event,before=self.fixture(root)
            try:
                with store.protocol.core:
                    store.protocol.core.execute("UPDATE raw_receipts SET sha256='bad' WHERE id=(SELECT id FROM events WHERE gen=? AND event_key=?)",(gid,'coinbase:history-8'))
                with endpoint(remote) as (factory,state):
                    app=create_app(db_path=str(Path(root)/'core.db'),start_collectors=False,read_connection_factory=lambda:store.worker_connection('history'),archive_read_factory=factory)
                    with TestClient(app) as client:
                        result=client.get('/history/archive',params=dict(generation=gid,dataset='stream_events',identities=json.dumps([[event['source'],event['event_id'],event['received_at']]]))).json()
                        self.assertEqual(result['status'],'unavailable');self.assertEqual(result['records'],[])
                self.assertTrue(store.protocol.path(gid).exists())
            finally:store.close()

    def test_active_metadata_does_not_acquire_retiring_raw_handles(self):
        from api import create_app
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,now,remote,oid,event,before=self.fixture(root)
            try:
                def unavailable():raise RuntimeError('generated raw lease unavailable')
                app=create_app(db_path=str(Path(root)/'core.db'),start_collectors=False,read_connection_factory=unavailable)
                with TestClient(app) as client:
                    result=client.get('/system/status').json()
                    self.assertEqual(result['active_buffer']['generation_id'],store.protocol.active()['id'])
                    self.assertEqual(client.get('/history/archive',params={'generation':gid,'dataset':'observations','identities':json.dumps([[oid]])}).json()['reason'],'archive_history_not_configured')
                    bad=Path(root)/'generated-unsupported-core.db'
                    with closing(sqlite3.connect(bad)) as db,db:
                        db.execute('CREATE TABLE ab_layout_version(id INTEGER,version INTEGER)')
                        db.execute('INSERT INTO ab_layout_version VALUES(1,999)')
                    with TestClient(create_app(db_path=str(bad),start_collectors=False,read_connection_factory=unavailable)) as bad_client:
                        result=bad_client.get('/system/status').json()
                        self.assertIsNone(result['active_buffer'])
                        self.assertEqual(result['active_buffer_diagnostic']['type'],'RuntimeError')
            finally:store.close()

    def fixture(self,root):
        path=Path(root)/'generated-legacy.db';legacy(path)
        store=ApplicationStore(root,path,routing=True,fresh_b=True,retirement=True)
        at=T+timedelta(seconds=2)
        with closing(store.connection()) as db:
            oid=db.save_observation('m',iso(at),'book',{'exact':'0.00000000001'},iso(at))
            event=dict(source='coinbase',event_id='history-8',received_at=iso(at),source_time=iso(at),price='12345.1234567890123456789',size='0.00000001',side='buy',payload=' { "exact":0.1234567890123456789 } ')
            db.save_stream_event(event)
            features.capture(db,at+timedelta(seconds=1))
            before=features.calculate(db,'m',at+timedelta(seconds=1))
            sid=db.execute('SELECT MAX(id) FROM feature_snapshots').fetchone()[0]
            forecasts.forecast_snapshot(db,sid,at+timedelta(seconds=1))
        gid=store.protocol.active()['id'];now=T+timedelta(hours=73)
        store.rotation_tick(now);remote=MemoryArchive()
        store.protocol.archive_hour(remote,now,limit=100,sealed_generation=gid)
        return store,path,gid,now,remote,oid,event,before

    def check_api(self,store,path,gid,oid,event,before,factory,state):
        from fastapi.testclient import TestClient
        from api import create_app
        app=create_app(db_path=str(Path(path).parent/'core.db'),start_collectors=False,
            read_connection_factory=lambda:store.worker_connection('history'),archive_read_factory=factory)
        with TestClient(app) as client:
            params=dict(generation=gid,dataset='stream_events',identities=json.dumps([[event['source'],event['event_id'],event['received_at']]]))
            result=client.get('/history/archive',params=params);self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()['status'],'ok',result.text)
            self.assertEqual(result.json()['records'],[event])
            self.assertTrue(result.json()['archives'])
            self.assertEqual(result.json()['provenance'],'authenticated_archive_and_committed_core_receipt')
            params.update(dataset='observations',identities=json.dumps([[oid]]))
            result=client.get('/history/archive',params=params).json()
            self.assertEqual(result['status'],'ok',result)
            self.assertEqual(result['records'][0]['payload'],'{"exact": "0.00000000001"}')
            self.assertNotEqual(client.get('/history/context').json().get('status'),'unavailable')
            self.assertTrue(client.get('/history/predictions').json()['items'])
            self.assertEqual(client.get('/dashboard').status_code,200)
            for mode in ('missing','corrupt','hang'):
                state['mode']=mode;started=time.monotonic();result=client.get('/history/archive',params=params).json()
                self.assertEqual(result['status'],'unavailable');self.assertEqual(result['records'],[])
                self.assertLess(time.monotonic()-started,2)
            state['mode']='normal'
        with closing(store.worker_connection('history')) as reader:
            self.assertEqual(features.calculate(reader,'m',T+timedelta(seconds=3)),before)
            self.assertEqual(reader.execute('SELECT outcome_observation_id FROM prediction_context_links WHERE prediction_id=1').fetchone()[0],90)
            self.assertEqual(reader.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_explicit_history_api_preserves_exact_archived_rows_and_unavailable_states(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,now,remote,oid,event,before=self.fixture(root)
            try:
                with endpoint(remote) as (factory,state):self.check_api(store,path,gid,oid,event,before,factory,state)
            finally:store.close()

    @unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'actual retirement needs Linux root descriptor proof')
    def test_actual_retirement_then_archive_history_calculations_and_dashboard(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            store,path,gid,now,remote,oid,event,before=self.fixture(root)
            try:
                store.retire(gid,remote,now)
                self.assertFalse(store.protocol.path(gid).exists())
                with endpoint(remote) as (factory,state):self.check_api(store,path,gid,oid,event,before,factory,state)
            finally:store.close()
