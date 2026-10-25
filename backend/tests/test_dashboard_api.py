"""Phase 1.5 integration contracts; local fixtures only, collectors never started."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from fastapi.testclient import TestClient
from api import create_app
from live_state import LiveState
from system_monitoring import read_history


class DashboardAPITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / 'test.db'
        self.telemetry = Path(self.folder.name) / 'cloud-soak.jsonl'
        self.state = LiveState()
        self.env = patch.dict(os.environ, {'ENABLE_OPENAI_ANALYST':'false', 'ENABLE_LOCAL_RETENTION':'false', 'ENABLE_SUPABASE_SYNC':'false'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app(self.state, str(self.db), False, str(self.telemetry))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def sample(self, i=0):
        return {'captured_at':f'2026-10-25T01:{i % 60:02d}:00+00:00',
                'cpu_busy_percent_1s':2.5, 'memory_bytes':{'MemTotal':1000,'MemAvailable':400},
                'disk_bytes':{'total':5000,'used':1000,'free':4000}, 'sqlite_bytes':123,'wal_bytes':45,
                'services':{'tradebot-api.service':{'ActiveState':'active','NRestarts':'2','secret':'NEVER_EXPOSE'}},
                'endpoints':{'/health':{'feeds':{'coinbase_stream':{'last_data_at':f'2026-10-25T01:{i % 60:02d}:00Z','reconnects':12}}},
                             '/cloud/status':{'datasets':[{'dataset':'archive:observations','rows_synced':10,'last_source_id':9,'detail':'NEVER_EXPOSE'}]}},
                'environment':{'KEY':'NEVER_EXPOSE'}}

    def test_dashboard_and_plan_are_fastapi_assets(self):
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        for value in ('Market','Models','History','System', "new EventSource('/events')"):
            self.assertIn(value,response.text)
        for old in ('/api/status','/api/ticks','/api/market-live','8765','sqlite3'):
            self.assertNotIn(old,response.text)
        self.assertEqual(self.client.get('/dashboard/plan').status_code,200)
        self.assertEqual(self.client.get('/').json()['service'],'btc-intelligence-api')

    def test_missing_telemetry_is_safe(self):
        result = self.client.get('/system/history').json()
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['items'],[])
        result = self.client.get('/system/status').json()
        self.assertEqual(result['host']['status'],'unavailable')
        self.assertTrue(result['services_stale'])
        self.assertFalse(self.db.exists())

    def test_status_schema_flags_and_current_db_wal_sizes(self):
        self.db.write_bytes(b'x'*123)
        Path(str(self.db)+'-wal').write_bytes(b'x'*45)
        result = self.client.get('/system/status').json()
        self.assertEqual(result['sqlite'],{'size_bytes':123,'wal_size_bytes':45})
        self.assertFalse(result['openai_enabled'])
        self.assertFalse(result['retention_enabled'])
        self.assertFalse(result['collector']['enabled'])
        self.assertEqual(result['api'],'responding')
        self.assertIn('coinbase',result['feeds'])
        self.assertEqual(result['cloud']['status'],'unavailable')

    def test_history_limits_and_no_file_mutation(self):
        content='\n'.join(json.dumps(self.sample(i)) for i in range(310))+'\n'
        self.telemetry.write_text(content)
        response=self.client.get('/system/history?limit=2').json()
        self.assertEqual(len(response['items']),2)
        self.assertEqual(len(self.client.get('/system/history').json()['items']),288)
        for limit in (0,289):
            self.assertEqual(self.client.get(f'/system/history?limit={limit}').status_code,422)
        self.assertEqual(self.telemetry.read_text(),content)

    def test_malformed_lines_and_shapes_are_ignored(self):
        content='bad json\nnull\n[]\n'+json.dumps({'captured_at':'bad'})+'\n'
        content+=json.dumps({**self.sample(), 'endpoints':[],'memory_bytes':[]})+'\n'
        content+=json.dumps(self.sample(1))+'\n'+ '{"captured_at":'
        self.telemetry.write_text(content)
        response=self.client.get('/system/history').json()
        self.assertEqual(len(response['items']),2)
        self.assertEqual(response['items'][0]['ram_used_bytes'],None)
        self.assertEqual(response['items'][1]['ram_used_bytes'],600)
        self.assertNotIn('NEVER_EXPOSE',json.dumps(response))

    def test_nonfinite_values_are_not_forwarded(self):
        self.telemetry.write_text(json.dumps({**self.sample(),'cpu_busy_percent_1s':float('nan')})+'\n')
        response=self.client.get('/system/history')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json()['items'][0]['cpu_percent'])

    def test_telemetry_projection_and_staleness(self):
        self.telemetry.write_text(json.dumps(self.sample())+'\n')
        result=self.client.get('/system/status').json()
        self.assertEqual(result['host']['status'],'stale')
        self.assertEqual(result['services']['tradebot-api.service'],{'state':'active','restarts':2})
        sample=self.client.get('/system/history').json()['items'][0]
        self.assertEqual(sample['coinbase_reconnects_cumulative'],12)
        self.assertEqual(sample['coinbase_age_seconds'],0)
        self.assertEqual(sample['observations_archive_checkpoint'],9)
        self.assertNotIn('NEVER_EXPOSE',json.dumps(result))

    def test_absent_wal_is_zero_for_existing_database(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE example(id INTEGER)')
        result=self.client.get('/system/status').json()
        self.assertGreater(result['sqlite']['size_bytes'],0)
        self.assertEqual(result['sqlite']['wal_size_bytes'],0)

    def test_oversized_and_non_utf8_lines_do_not_break_history(self):
        self.telemetry.write_bytes(b'x'*300000+b'\n\xff\xfe\n'+json.dumps(self.sample()).encode()+b'\n')
        result=self.client.get('/system/history')
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(result.json()['items']),1)

    def test_missing_cloud_counter_is_unavailable(self):
        row=self.sample()
        row['endpoints']['/cloud/status']['datasets'][0]['rows_synced']='invalid'
        self.telemetry.write_text(json.dumps(row)+'\n')
        self.assertIsNone(self.client.get('/system/history').json()['items'][0]['cloud_rows_synced'])

    def test_feed_freshness_comes_from_live_state(self):
        now=datetime.now(timezone.utc).isoformat()
        self.state.update_feed_health('polymarket_stream','live',last_data_at=now,reconnects=17)
        feed=self.client.get('/system/status').json()['feeds']['polymarket']
        self.assertEqual(feed['reconnects_cumulative'],17)
        self.assertLess(feed['age_seconds'],5)
        self.state.update_feed_health('polymarket_stream','live',last_data_at='2020-01-01T00:00:00Z')
        stale=self.client.get('/system/status').json()['feeds']['polymarket']
        self.assertEqual(stale['status'],'stale')
        self.assertEqual(stale['reported_status'],'live')

    def test_ensemble_latest_valid_and_baseline_remain_separate(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE predictions(id INTEGER PRIMARY KEY, market_id TEXT, model_version TEXT, as_of TEXT, probability_up TEXT, component_scores TEXT, decision_summary TEXT)')
            for i,p in enumerate(('0.61','NaN','invalid')):
                db.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?,?)',(i,'old-market','ensemble_v1',f'2026-10-25T01:0{i}:00Z',p,'{"baseline":0.62}','HOLD'))
        self.state.set_forecast('gaussian_distance_v1',0.7)
        result=self.client.get('/models/current').json()
        self.assertEqual(result['models']['ensemble_v1']['probability_up'],0.61)
        self.assertFalse(result['models']['ensemble_v1']['current_market'])
        self.assertTrue(result['models']['ensemble_v1']['experimental'])
        self.assertEqual(result['models']['gaussian_distance_v1']['probability_up'],0.7)
        self.assertEqual(self.client.get('/forecast/current').json()['forecast']['model_version'],'gaussian_distance_v1')
        self.assertNotIn('ensemble_v1',self.state.snapshot()['models'])

    def test_ensemble_unavailable_is_additive_only(self):
        self.state.set_forecast('baseline',0.5)
        self.assertEqual(set(self.client.get('/models/current').json()['models']),{'baseline'})
        self.assertFalse(self.db.exists())

    def test_database_failure_does_not_break_live_health_or_state(self):
        self.db.write_text('corrupt')
        for path in ('/state/current','/forecast/current','/models/current','/health','/cloud/status','/system/status'):
            self.assertEqual(self.client.get(path).status_code,200,path)
        with patch('api._read_cloud_datasets',side_effect=sqlite3.OperationalError('secret error')):
            health=self.client.get('/health').json()
            self.assertEqual(health['cloud']['status'],'unavailable')
            self.assertNotIn('secret error',json.dumps(health))

    def test_context_and_chart_handle_missing_database(self):
        self.assertEqual(self.client.get('/history/context').json()['status'],'unavailable')
        self.assertEqual(self.client.get('/history/coinbase-chart').json()['points'],[])
        self.assertFalse(self.db.exists())

    def test_sse_emits_same_live_contract_and_cancels(self):
        route=next(route for route in self.app.routes if route.path=='/events')
        async def first_event():
            response=await route.endpoint()
            event=await anext(response.body_iterator)
            self.assertEqual(response.media_type,'text/event-stream')
            payload=json.loads(event.removeprefix('data: ').strip())
            self.assertEqual(payload['models'],self.client.get('/state/current').json()['models'])
            self.assertIn('live_estimate',payload)
            await response.body_iterator.aclose()
        asyncio.run(first_event())

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for the dashboard script contract test')
    def test_shipped_dashboard_consumes_actual_fastapi_contract(self):
        now=datetime.now(timezone.utc).isoformat()
        from datetime import timedelta
        self.state.set_market({'id':'m','slug':'btc-test','start':now,
            'end':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),
            'target_usd':'100','status':'MARKET_STATUS_OPEN'})
        self.state.update_coinbase_ticker({'type':'ticker','product_id':'BTC-USD',
            'trade_id':1,'price':'101','last_size':'0.1','side':'buy','time':now},now)
        self.state.update_polymarket({'marketData':{'marketSlug':'btc-test',
            'longQuote':{'value':'0.55'},'shortQuote':{'value':'0.45'}}},now)
        self.state.set_feature_snapshot('m',now,{'target_usd':'100','realized_volatility_15m':'0.002'},
            {'price':{'status':'fresh'},'candle_status':'fresh'})
        self.telemetry.write_text(json.dumps(self.sample())+'\n')
        paths=('/state/current','/models/current','/history/predictions?limit=100',
               '/history/context','/history/coinbase-chart','/system/status','/system/history')
        payload={path:self.client.get(path).json() for path in paths}
        result=subprocess.run(['node',str(Path(__file__).with_name('dashboard_contract.cjs')),
            str(Path(__file__).resolve().parents[1]/'app/dashboard.html')],
            input=json.dumps(payload),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_cloud_freeform_details_are_excluded(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE cloud_sync_state(dataset TEXT,last_source_id INTEGER,last_source_time TEXT,last_source_key TEXT,rows_synced INTEGER,status TEXT,detail TEXT,updated_at TEXT)')
            db.execute("INSERT INTO cloud_sync_state VALUES('archive:observations',1,NULL,'NEVER_EXPOSE',10,'verified','NEVER_EXPOSE','2026-10-25')")
        for endpoint in ('/health','/cloud/status','/system/status'):
            self.assertNotIn('NEVER_EXPOSE', self.client.get(endpoint).text)


if __name__=='__main__':
    unittest.main()
