"""Owned Unix-socket PG17 trial proof; no hosted or externally supplied DSN."""
from contextlib import contextmanager,nullcontext
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import getpass,json,os,shlex,shutil,subprocess,sys,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from postgres.archive_codec import ArchiveIntegrityError,ArchiveLimit,ArchiveLimits,encoded,sha256
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.history_v2_envelope import TABLE_KEYS
from postgres.cloud_origin_binding import TRIAL_ORIGIN,TRIAL_WRITER
from postgres.active_structured import ActiveStructuredWorker


def page(generation):
    start=datetime(2026,11,19,12,tzinfo=timezone.utc);records=[]
    def add(table,payload):
        identity=encoded([payload[k] for k in TABLE_KEYS[table]]).decode()
        record=dict(id=len(records)+1,origin_id=TRIAL_ORIGIN,generation_id=generation,
            entity_type=table,entity_id=identity,content_hash=payload['content_hash'],payload=payload)
        records.append(record)
    for i in range(14):
        at=start+timedelta(seconds=i)
        add('core.candles',dict(origin_id=TRIAL_ORIGIN,source='coinbase',symbol='BTC-USD',granularity=60,
            time=int(start.timestamp())+i*60,low='99.0000',high='101.0000',open='100.0000',close='100.1000',volume='1E-8',
            first_seen=at.isoformat(),payload={'generated':True,'padding':'c'*500},content_hash=f'{i+1:064x}'))
        add('core.current_prices',dict(origin_id=TRIAL_ORIGIN,source='coinbase',symbol='BTC-USD',event_id=f'tick-{i}',generation_id=generation,
            source_time=at.isoformat(),source_epoch=str(int(at.timestamp())),received_at=at.isoformat(),available_at=at.isoformat(),
            price=f'100.{i:04d}',size=None,payload={'generated':True,'padding':'p'*700},content_hash=f'{i+100:064x}'))
    add('core.markets',dict(origin_id=TRIAL_ORIGIN,market_id='market',source='polymarket_us',slug='market',duration=900,
        start_time=start.isoformat(),end_time=(start+timedelta(minutes=15)).isoformat(),start_epoch=str(int(start.timestamp())),
        end_epoch=str(int(start.timestamp())+900),target='100.0000',final=None,result=None,status='open',index_symbol='BTC-USD',rules=None,
        first_seen=start.isoformat(),last_seen=start.isoformat(),payload={'generated':True,'padding':'m'*2000},content_hash='f'*64))
    for i in range(7):
        add('core.protected_evidence',dict(origin_id=TRIAL_ORIGIN,evidence_id=f'evidence-{i}',generation_id=generation,source='polymarket_us',
            event_id=f'quote-{i}',kind='quote',market_id='market',source_time=start.isoformat(),source_epoch=str(int(start.timestamp())),
            received_at=start.isoformat(),available_at=start.isoformat(),payload={'generated':True,'padding':'e'*700},raw_payload=None,content_hash=f'{i+200:064x}'))
    for i in range(5):
        at=start+timedelta(seconds=i)
        add('core.feature_snapshots',dict(origin_id=TRIAL_ORIGIN,snapshot_id=f'snapshot-{i}',market_id='market',as_of=at.isoformat(),version=1,
            values_json={'price':'100.0000','padding':'v'*900},quality_json={'generated':True,'missing':None},
            evidence_json={'inputs':[f'evidence-{i}']},content_hash=f'{i+300:064x}'))
        add('core.predictions',dict(origin_id=TRIAL_ORIGIN,prediction_id=f'prediction-{i}',snapshot_id=f'snapshot-{i}',market_id='market',
            model_version='generated-v1',as_of=at.isoformat(),created_at=at.isoformat(),seconds_remaining='890.000',probability_up='0.5000',
            probability_down='0.5000',abstain_reason=None,assumptions_json={'generated':True},payload={'padding':'r'*700},content_hash=f'{i+400:064x}'))
    for i in range(4):
        edge=dict(origin_id=TRIAL_ORIGIN,snapshot_id=f'snapshot-{i}',evidence_id=f'evidence-{i}')
        add('core.snapshot_evidence',{**edge,'content_hash':sha256(encoded(edge))})
    assert len(records)==50
    return records


class Counted:
    def __init__(self,inner,delay=0):self.inner,self.delay,self.depth,self.waits,self.sql=inner,delay,0,0,0
    def __getattr__(self,name):return getattr(self.inner,name)
    def wait(self):
        self.waits+=1
        if self.delay:time.sleep(self.delay)
    def execute(self,*args,**kwargs):
        self.sql+=1
        if not self.depth:self.wait()
        return self.inner.execute(*args,**kwargs)
    @contextmanager
    def transaction(self):
        self.wait()
        try:
            with self.inner.transaction():yield
        finally:self.wait()
    @contextmanager
    def pipeline(self):
        self.depth+=1
        try:
            with self.inner.pipeline():yield
        finally:
            self.depth-=1
            if not self.depth:self.wait()


class SyncBarriersPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        choices=[os.getenv('TRADEBOT_TEST_PG17_BIN'),'/opt/homebrew/opt/postgresql@17/bin',str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin=next((Path(p) for p in choices if p and all((Path(p)/x).is_file() for x in ('initdb','pg_ctl','psql'))),None)
        if cls.bin is None:raise unittest.SkipTest('native PG17 binaries unavailable')
        if ' 17.' not in subprocess.run([str(cls.bin/'psql'),'--version'],capture_output=True,text=True,check=True).stdout:
            raise unittest.SkipTest('native PG17 required')
        cls.temp=tempfile.TemporaryDirectory(prefix='sync-barriers-',dir='/tmp');cls.root=Path(cls.temp.name);cls.socket=cls.root/'socket';cls.socket.mkdir()
        cls.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        subprocess.run([str(cls.bin/'initdb'),'-D',str(cls.root/'data'),'-U','postgres','--auth-local=trust','--auth-host=reject','--no-locale','-E','UTF8'],env=cls.env,capture_output=True,check=True)
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-l',str(cls.root/'log'),'-o',shlex.join(['-k',str(cls.socket),'-h','','-p','5432']),'-w','start'],env=cls.env,capture_output=True,check=True)
        try:
            with cls.admin() as db:
                db.execute('CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN')
                for name in ('20261116050000_history_v2_private.sql','20261118012340_structured_receipts_v2.sql','20261118020000_pp_history_v2_role.sql',
                             '20261118031407_pp_structured_receipt_grants.sql','20261119020000_pp_structured_revision_payloads.sql'):
                    db.execute((ROOT/'supabase/migrations'/name).read_text())
                db.execute((ROOT/'supabase/review/pp_trial_20261119_01_structured.sql').read_text())
        except BaseException:cls.tearDownClass();raise
    @classmethod
    def admin(cls):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(host=str(cls.socket),user='postgres',dbname='postgres',row_factory=dict_row,autocommit=True)
    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-m','immediate','-w','stop'],env=cls.env,capture_output=True,check=True)
        cls.temp.cleanup()
    def setUp(self):self.reset()
    def reset(self):
        with self.admin() as db:
            names=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='history_v2'").fetchall()
            from psycopg import sql
            db.execute(sql.SQL('TRUNCATE {} CASCADE').format(sql.SQL(',').join(sql.Identifier('history_v2',row['tablename']) for row in names)))
    @contextmanager
    def connected(self,delay=0):
        from psycopg import sql
        with self.admin() as db:
            db.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(TRIAL_WRITER)))
            yield Counted(db,delay)
    def transport(self,connection,generation,*,fast=True,fail_after_commit=False):
        @contextmanager
        def factory(**_):
            yield connection
            if fail_after_commit:raise ArchiveLimit('generated ambiguous completed import')
        return HistoryV2PostgresTransport(factory,origin_id=TRIAL_ORIGIN,generation_id=generation,
            expected_database='postgres',expected_role=TRIAL_WRITER,retain_revisions=True,sync_barriers=fast)
    def test_paired_import_readback_replay_and_barrier_counts(self):
        generation=str(uuid.uuid4());records=page(generation);results=[]
        for fast in (False,True):
            self.reset()
            with self.connected() as db:
                transport=self.transport(db,generation,fast=fast)
                transport.put_structured(records,timeout_seconds=4);write=db.waits
                self.assertEqual(transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=4),records)
                read=db.waits-write
                transport.put_structured(records,timeout_seconds=4)
                results.append((write,read))
                with self.admin() as admin:
                    self.assertEqual(admin.execute('SELECT count(*) AS n FROM history_v2.structured_receipts').fetchone()['n'],50)
                    self.assertEqual(admin.execute('SELECT count(*) AS n FROM history_v2.structured_revision_payloads').fetchone()['n'],50)
        self.assertLess(sum(results[1]),sum(results[0]))
        print('generated_sync_barriers waits baseline/candidate='+repr(results),flush=True)
    def test_committed_ambiguous_import_never_acks_then_exact_replay_does(self):
        generation=str(uuid.uuid4());records=page(generation)
        class Repo:
            acknowledged=[]
            def structured_sync_lock(self,_):return nullcontext()
            def generation(self,_):return dict(origin_id=TRIAL_ORIGIN,state='collecting')
            def has_other_pending(self,*_):return False
            def outbox(self,*_):return records
            def acknowledge(self,_,rows):self.acknowledged.extend(rows)
        repo=Repo();limits=ArchiveLimits(max_rows=50,max_object_bytes=256*1024,max_decoded_bytes=256*1024,max_cycle_bytes=512*1024,max_requests=2,max_seconds=20)
        with self.connected() as db:
            transport=self.transport(db,generation,fail_after_commit=True)
            with self.assertRaises(ArchiveLimit):ActiveStructuredWorker(repo,transport,origin_id=TRIAL_ORIGIN,limits=limits).cycle(generation)
            self.assertEqual(repo.acknowledged,[])
            transport=self.transport(db,generation)
            # Exact full page replay works; first-half projection shortcut is rejected.
            with self.assertRaises(ArchiveIntegrityError):transport.read_structured_authenticated(records[:25],max_bytes=256*1024,timeout_seconds=4)
            self.assertEqual(ActiveStructuredWorker(repo,transport,origin_id=TRIAL_ORIGIN,limits=limits).cycle(generation)['acknowledged'],50)
            self.assertEqual(repo.acknowledged,records)
    def test_post_sync_validation_failure_rolls_back_all_writes_and_checkpoint(self):
        generation=str(uuid.uuid4());records=page(generation)
        with self.connected() as db:
            transport=self.transport(db,generation)
            with patch.object(transport,'_decode_revisions',side_effect=ArchiveIntegrityError('generated decode conflict')):
                with self.assertRaises(ArchiveIntegrityError):transport.put_structured(records,timeout_seconds=4)
        with self.admin() as db:
            for table in ('structured_receipts','structured_revision_payloads','generation_checkpoints','current_prices','markets'):
                self.assertEqual(db.execute('SELECT count(*) AS n FROM history_v2.'+table).fetchone()['n'],0)
    def test_exact_projection_corruption_and_wrong_role_fail(self):
        generation=str(uuid.uuid4());records=page(generation)
        with self.connected() as db:
            transport=self.transport(db,generation);transport.put_structured(records,timeout_seconds=4)
            with self.admin() as admin:admin.execute("UPDATE history_v2.current_prices SET price=123.0000")
            with self.assertRaises(ArchiveIntegrityError):transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=4)
        with self.admin() as admin:
            transport=self.transport(Counted(admin),generation)
            with self.assertRaises(ArchiveIntegrityError):transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=4)
    def test_checkpoint_receipt_envelope_and_oversize_corruption_never_return_success(self):
        mutations=[("UPDATE history_v2.generation_checkpoints SET content_hash=repeat('b',64)",ArchiveIntegrityError),
            ("UPDATE history_v2.structured_receipts SET payload_hash=repeat('b',64) WHERE outbox_id=1",ArchiveIntegrityError),
            ("DELETE FROM history_v2.structured_revision_payloads WHERE outbox_id=1; DELETE FROM history_v2.structured_receipts WHERE outbox_id=1",ArchiveIntegrityError),
            ("UPDATE history_v2.structured_revision_payloads SET envelope=envelope||convert_to(' ','UTF8') WHERE outbox_id=1",ArchiveIntegrityError),
            ("UPDATE history_v2.structured_revision_payloads SET envelope=convert_to(repeat('x',300000),'UTF8') WHERE outbox_id=1",ArchiveLimit)]
        for statement,error in mutations:
            with self.subTest(statement=statement):
                self.reset();generation=str(uuid.uuid4());records=page(generation)
                with self.connected() as db:
                    transport=self.transport(db,generation);transport.put_structured(records,timeout_seconds=4)
                    with self.admin() as admin:admin.execute(statement)
                    with self.assertRaises(error):transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=4)

    def test_cold_retained_original_revisions_still_verify_newer_projection(self):
        generation=str(uuid.uuid4());records=page(generation)
        with self.connected() as db:
            a=self.transport(db,generation);a.put_structured(records,timeout_seconds=4)
            newer=deepcopy(records[27]);other=str(uuid.uuid4());newer['id']=51;newer['generation_id']=other
            payload=newer['payload'];payload.update(generation_id=other,event_id='newer',source_time='2026-11-19T12:00:14+00:00',
                source_epoch='1795089614',received_at='2026-11-19T12:00:14+00:00',available_at='2026-11-19T12:00:14+00:00',price='100.0014',content_hash='e'*64)
            newer['content_hash']='e'*64
            b=self.transport(db,other);b.put_structured([newer],timeout_seconds=4)
            self.assertEqual(a.read_retirement_revisions(records,max_bytes=256*1024,timeout_seconds=4)[0],records)
    def test_opt_in_scope_and_four_second_deadline_remain_explicit(self):
        with self.assertRaises(ArchiveIntegrityError):HistoryV2PostgresTransport(lambda **_:None,origin_id='pp-live-pp',generation_id=str(uuid.uuid4()),expected_database='postgres',expected_role='tradebot_pp_history',sync_barriers=True)
        generation=str(uuid.uuid4());records=page(generation)
        with self.connected() as db:
            transport=self.transport(db,generation)
            with self.assertRaises(ArchiveLimit):transport.put_structured(records+[records[-1]],timeout_seconds=4)
            @contextmanager
            def slow(**_):time.sleep(.01);yield db
            transport.connection_factory=slow
            with self.assertRaises(ArchiveLimit):transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=.001)
