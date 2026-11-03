"""Actual SupabaseHTTP wire contract via generated private object fixtures."""
import sys,tempfile,json,time,hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest,httpx
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from cloud_memory import SupabaseHTTP
from compatible_cloud import CompatibleCloud
from archive_reads import ArchiveHold
class Remote:
    def __init__(self,root):self.root=Path(root);self.mode='normal'
    def handle(self,r):
        with (self.root/'calls').open('a') as log:log.write(r.method+' '+r.url.path+'\n')
        obj=self.root/'object';manifest=self.root/'manifest'
        if '/storage/v1/' in r.url.path:
            if r.method=='GET':
                if self.mode in ('401','403','429','503'):return httpx.Response(int(self.mode))
                if self.mode=='timeout':raise httpx.ReadTimeout('fixture')
                if not obj.exists():return httpx.Response(404)
                return httpx.Response(200,content=obj.read_bytes() if self.mode!='truncated' else b'x')
            if r.method=='POST':
                if r.headers.get('x-upsert')!='false':return httpx.Response(400)
                if obj.exists():return httpx.Response(409)
                obj.write_bytes(r.content)
                if self.mode=='ambiguous_upload':raise httpx.ReadTimeout('fixture committed upload')
                return httpx.Response(200)
        if r.url.path.endswith('/raw_archives'):
            if r.method=='GET':return httpx.Response(200,json=[json.loads(manifest.read_text())] if manifest.exists() else [])
            if r.method=='POST':
                if 'ignore-duplicates' not in r.headers.get('Prefer',''):return httpx.Response(400)
                if not manifest.exists():manifest.write_text(json.dumps(json.loads(r.content)[0]))
                if self.mode=='ambiguous_manifest':raise httpx.ReadTimeout('fixture committed manifest')
                return httpx.Response(201)
        from compatible_cloud import KEYS,exact_json
        table=r.url.path.rsplit('/',1)[-1]
        if table in KEYS:
            file=self.root/(table+'.json');rows=json.loads(file.read_text(),parse_float=Decimal) if file.exists() else []
            if r.method=='GET':
                def matches(row):
                    for key in KEYS[table]:
                        expected=json.loads(r.url.params[key][3:])
                        if row.get(key)!=expected:return False
                    return True
                return httpx.Response(200,content=exact_json([row for row in rows if matches(row)]).encode())
            if r.method=='POST':
                incoming=json.loads(r.content,parse_float=Decimal)
                for row in incoming:
                    found=any(all(old[k]==row[k] for k in KEYS[table]) for old in rows)
                    if found and 'ignore-duplicates' in r.headers.get('Prefer',''):continue
                    rows=[old for old in rows if any(old[k]!=row[k] for k in KEYS[table])]+[row]
                file.write_text(exact_json(rows))
                if self.mode=='ambiguous_structured':raise httpx.ReadTimeout('generated committed structured write')
                return httpx.Response(201)
        return httpx.Response(404)
class Tests(unittest.TestCase):
    def setup_cloud(self,f,seconds=5):
        remote=Remote(f);cloud=SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated-only'),client=httpx.Client(transport=httpx.MockTransport(remote.handle)))
        self.addCleanup(cloud.close);return remote,CompatibleCloud(cloud,time.monotonic()+seconds)
    def test_immutable_upload_duplicate_conflict_and_ambiguous_commit_reconciliation(self):
        for mode in ['normal','ambiguous_upload']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                remote,cloud=self.setup_cloud(f);remote.mode=mode
                cloud.upload_bytes('private','same',b'exact')
                cloud.upload_bytes('private','same',b'exact')
                self.assertEqual(Path(f,'object').read_bytes(),b'exact')
                self.assertEqual(sum(x.startswith('POST') for x in Path(f,'calls').read_text().splitlines()),1)
                with self.assertRaises(ArchiveHold):cloud.upload_bytes('private','same',b'conflict')
                self.assertEqual(Path(f,'object').read_bytes(),b'exact')
    def test_manifest_duplicate_conflict_and_ambiguous_response(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            remote,cloud=self.setup_cloud(f);remote.mode='ambiguous_manifest'
            row={'source':'polymarket','bucket':'private','object_path':'same','sha256':'exact','event_count':1,'metadata':{'dataset':'observations'}}
            cloud.upsert('raw_archives',[row],'bucket,object_path');cloud.upsert('raw_archives',[row],'bucket,object_path')
            with self.assertRaises(ArchiveHold):cloud.upsert('raw_archives',[{**row,'sha256':'wrong'}],'bucket,object_path')
            self.assertEqual(sum(x.startswith('POST') for x in Path(f,'calls').read_text().splitlines()),1)
    def test_auth_transient_timeout_truncated_wrong_object_all_hold(self):
        for mode in ['401','403','429','503','timeout','truncated','normal']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
                remote,cloud=self.setup_cloud(f,seconds=.12);remote.mode=mode;Path(f,'object').write_bytes(b'wrong object')
                before=time.monotonic()
                with self.assertRaises(ArchiveHold):cloud.verify_object('private','same',hashlib.sha256(b'expected').hexdigest(),8)
                self.assertLess(time.monotonic()-before,.8)
                calls=Path(f,'calls').read_text().splitlines()
                self.assertLessEqual(len(calls),3);self.assertTrue(all(x.startswith('GET') for x in calls))
    def test_existing_archive_checkpoint_code_through_actual_wire_adapter(self):
        from test_ab_application import legacy,ApplicationStore
        import cloud_memory
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            path=Path(f)/'generated-legacy.db';legacy(path);s=ApplicationStore(f,path,routing=True);db=s.connection()
            remote,cloud=self.setup_cloud(f)
            try:
                m=cloud_memory.archive_raw_batch(db,cloud,'observations',limit=1)
                self.assertEqual(m['first_source_id'],90);self.assertEqual(m['last_source_id'],90)
                self.assertEqual(cloud_memory._checkpoint(db,'archive:observations')[0],90)
                self.assertEqual(json.loads(Path(f,'manifest').read_text())['sha256'],m['sha256'])
                self.assertIsNone(cloud_memory.archive_raw_batch(db,cloud,'observations',limit=1))
            finally:db.close();s.close()
    def test_structured_ambiguity_reconciles_and_conflicts_do_not_replay(self):
        from decimal import Decimal
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            remote,cloud=self.setup_cloud(f);remote.mode='ambiguous_structured'
            row={'source_id':123,'market_id':'m','as_of':'2026-01-01T00:00:00+00:00','version':2,'values_json':{'exact':Decimal('12345.1234567890123456789')}}
            cloud.upsert('feature_snapshots',[row],'source_id')
            cloud.upsert('feature_snapshots',[row],'source_id')
            with self.assertRaises(ArchiveHold):cloud.upsert('feature_snapshots',[{**row,'version':3}],'source_id')
            calls=Path(f,'calls').read_text().splitlines()
            self.assertEqual(sum(x=='POST /rest/v1/feature_snapshots' for x in calls),1)
            self.assertIn('12345.1234567890123456789',Path(f,'feature_snapshots.json').read_text())
    def test_exact_structured_prices_use_original_numeric_text(self):
        from test_ab_application import legacy,ApplicationStore
        import cloud_memory
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            path=Path(f)/'generated-legacy.db';legacy(path);s=ApplicationStore(f,path,routing=True);db=s.connection()
            remote,cloud=self.setup_cloud(f)
            try:
                with db:db.execute('UPDATE markets SET target=?',('12345.1234567890123456789',))
                cloud_memory.sync_structured_once(db,cloud,100)
                self.assertIn('12345.1234567890123456789',Path(f,'markets.json').read_text())
            finally:db.close();s.close()
    def test_equal_timestamp_checkpoint_keeps_binary_source_key_order(self):
        from compatible_cloud import allowed_update
        at='2026-01-01T00:00:00+00:00'
        old={'dataset':'markets','rows_synced':1,'last_source_time':at,'last_source_key':'2'}
        self.assertFalse(allowed_update('sync_checkpoints',old,{**old,'rows_synced':2,'last_source_key':'10'}))
        self.assertTrue(allowed_update('sync_checkpoints',old,{**old,'rows_synced':2,'last_source_key':'3'}))
        old={**old,'dataset':'archive:stream_events','last_source_key':'["coinbase","2"]'}
        self.assertFalse(allowed_update('sync_checkpoints',old,{**old,'rows_synced':2,'last_source_key':'["coinbase","10"]'}))

    def test_concurrent_immutable_insert_is_not_overwritten(self):
        from compatible_cloud import exact_json
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            remote,cloud=self.setup_cloud(f);original=remote.handle
            wanted={'source_id':1,'market_id':'m','version':2};conflict={**wanted,'version':99}
            def race(request):
                if request.method=='POST' and request.url.path.endswith('/feature_snapshots'):
                    Path(f,'feature_snapshots.json').write_text(exact_json([conflict]))
                return original(request)
            cloud.cloud.client.close();cloud.cloud.client=httpx.Client(transport=httpx.MockTransport(race));self.addCleanup(cloud.cloud.client.close)
            with self.assertRaises(ArchiveHold):cloud.upsert('feature_snapshots',[wanted],'source_id')
            self.assertEqual(json.loads(Path(f,'feature_snapshots.json').read_text())[0]['version'],99)
