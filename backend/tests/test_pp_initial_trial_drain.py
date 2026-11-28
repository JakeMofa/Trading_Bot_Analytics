"""Initial-trial maintenance seal; all native data belongs to an owned temp PG17."""
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from postgres.archive_codec import ArchiveUnavailable, ArchiveIntegrityError, encoded
from postgres.lifecycle import LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.pp_initial_trial_drain import CONSUMER, MAX_RAW_ROWS, SealTarget, main, seal_initial_a
from postgres.rehearsal_profile import TRIAL_ORIGIN
from postgres_lifecycle_fixtures import ImmutableMemoryTransport


class InitialSealControls(unittest.TestCase):
    def test_exact_target_and_default_off(self):
        anchor=str(uuid.uuid4())
        target=SealTarget(anchor,anchor,3,5241,5651,str(uuid.uuid4()),'a'*40)
        target.validate()
        for change in ({'generation':str(uuid.uuid4())},{'initial_a':'A'},{'outbox_count':0},
                       {'outbox_count':10001},{'outbox_count':True},{'raw_count':MAX_RAW_ROWS+1},
                       {'writer_epoch':True},{'source':'main'},{'operation':'now'}):
            with self.subTest(change=change), self.assertRaises((ValueError,LifecycleHold)):
                replace(target,**change).validate()
        class Repo: environment='production'
        for execute in (False,True):
            with self.assertRaises(LifecycleHold):seal_initial_a(Repo(),target,execute=execute)
        with patch('postgres.pp_initial_trial_drain.private_dsn') as secret:
            self.assertEqual(main(['--generation',anchor,'--initial-a',anchor,'--writer-epoch','3',
                '--raw-count','5241','--outbox-count','5651','--operation',target.operation,'--source',target.source]),1)
            secret.assert_not_called()

    def test_actual_machine_file_transport_reader_binding_is_admitted_without_network(self):
        import httpx
        from types import SimpleNamespace
        from postgres.cloud_origin_binding import LEGACY_ORIGIN, TRIAL_READER
        from postgres.pp_initial_trial_drain import audit_initial_a
        from postgres.pp_retirement_verify import RetirementTransport
        from postgres.supabase_storage import SupabaseStorageTransport
        anchor=str(uuid.uuid4())
        target=SealTarget(anchor,anchor,3,5241,5651,str(uuid.uuid4()),'a'*40)
        requests=[]
        def no_network(request):
            requests.append(request)
            raise AssertionError('transport construction and scope validation must not use network')
        with tempfile.TemporaryDirectory(prefix='initial-trial-fake-auth-') as folder, \
                httpx.Client(transport=httpx.MockTransport(no_network)) as client:
            paths=[]
            for name,value in (('key','sb_publishable_generated_only_12345'),
                               ('email','generated@example.invalid'),
                               ('password','generated-password-for-tests-only'),
                               ('uid',str(uuid.uuid4()))):
                path=Path(folder)/name;path.write_text(value);path.chmod(0o400);paths.append(path)
            structured=SimpleNamespace(expected_role=TRIAL_READER,origin_id=TRIAL_ORIGIN,generation_id=anchor)
            for origin,reader,admitted in ((TRIAL_ORIGIN,True,True),(LEGACY_ORIGIN,True,False),
                                            (TRIAL_ORIGIN,False,False)):
                with self.subTest(origin=origin,reader=reader):
                    raw=SupabaseStorageTransport.from_machine_files(*paths,client=client,
                                                                  origin_id=origin,reader=reader)
                    self.assertFalse(hasattr(raw,'_binding'))
                    self.assertEqual(raw._origin_binding.origin_id,origin)
                    transport=RetirementTransport(raw,structured,origin_id=TRIAL_ORIGIN,generation_id=anchor)
                    with patch('postgres.pp_retained_archive_audit.local_snapshot',
                               side_effect=RuntimeError('reader snapshot reached')) as snapshot:
                        if admitted:
                            with self.assertRaisesRegex(RuntimeError,'reader snapshot reached'):
                                audit_initial_a(None,transport,target,seal_hash='a'*64,
                                                raw_objects=11,structured_pages=12)
                            snapshot.assert_called_once()
                        else:
                            with self.assertRaisesRegex(LifecycleHold,'independent initial trial reader'):
                                audit_initial_a(None,transport,target,seal_hash='a'*64,
                                                raw_objects=11,structured_pages=12)
                            snapshot.assert_not_called()
                    raw.close()
        self.assertEqual(requests,[])


class InitialSealNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        choices=[os.getenv('TRADEBOT_TEST_PG17_BIN'),'/opt/homebrew/opt/postgresql@17/bin',
                 str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin=next((Path(p) for p in choices if p and all((Path(p)/n).is_file()
                     for n in ('initdb','pg_ctl','psql'))),None)
        if cls.bin is None:raise unittest.SkipTest('native PG17 binaries unavailable')
        if ' 17.' not in subprocess.run([str(cls.bin/'psql'),'--version'],capture_output=True,text=True,check=True).stdout:
            raise unittest.SkipTest('native PG17 required')
        cls.temp=tempfile.TemporaryDirectory(prefix='initial-trial-seal-',dir='/tmp')
        cls.root=Path(cls.temp.name);cls.socket=cls.root/'socket';cls.socket.mkdir()
        cls.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        subprocess.run([str(cls.bin/'initdb'),'-D',str(cls.root/'data'),'-U','postgres',
            '--auth-local=trust','--auth-host=reject','--no-locale','-E','UTF8'],env=cls.env,capture_output=True,check=True)
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-l',str(cls.root/'log'),
            '-o',shlex.join(['-k',str(cls.socket),'-h','','-p','5432']),'-w','start'],env=cls.env,capture_output=True,check=True)
        try:
            with cls.admin('postgres') as db:db.execute('CREATE DATABASE tradebot_pp')
            # Use the actual local foundation and migrations, without mounted passwords.
            foundation=(ROOT/'deploy/preprod/init.sh').read_text().split("<<'SQL'\n",1)[1].split('\nSQL',1)[0]
            foundation=re.sub(r'DO \$body\$.*?\$body\$;', '',foundation,flags=re.S)
            foundation=foundation.replace('SET ROLE tradebot_owner;',
                'CREATE ROLE tradebot_lifecycle LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE; '
                'GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle; SET ROLE tradebot_owner;')
            with cls.admin() as db:
                db.execute(foundation)
                db.execute('SET ROLE tradebot_owner')
                for migration in sorted((ROOT/'backend/postgres/migrations').glob('*.sql')):
                    db.execute(migration.read_text())
            cls.lifecycle_dsn=f'host={cls.socket} user=tradebot_lifecycle dbname=tradebot_pp'
            cls.app_dsn=f'host={cls.socket} user=tradebot_app dbname=tradebot_pp'
        except BaseException:cls.tearDownClass();raise

    @classmethod
    def admin(cls,database='tradebot_pp'):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(host=str(cls.socket),user='postgres',dbname=database,row_factory=dict_row,autocommit=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-m','immediate','-w','stop'],env=cls.env,capture_output=True,check=True)
        cls.temp.cleanup()

    def setUp(self):
        from postgres.connection import connect
        from postgres.config import Settings
        from postgres.store import Store
        from postgres.pp_trial_prepare import prepare
        from postgres.live_contract import coinbase_ticker
        self.factory=lambda:connect(self.lifecycle_dsn,environment='preprod')
        self.repo=LifecycleRepository(self.factory)
        self.raw=ImmutableMemoryTransport()
        self.anchor=str(uuid.uuid4());self.origins=['pp-live-pp',TRIAL_ORIGIN]
        self.children=[]
        self.addCleanup(self.cleanup)
        old_a=self.repo.bootstrap('pp-live-pp');self.children.append(old_a['generation_id'])
        old_b=self.repo.switch_if_due('pp-live-pp',RotationPolicy(1))['generation_id'];self.children.append(old_b)
        prepare(self.repo,self.anchor,'b'*40,execute=True);self.children.append(self.anchor)
        self.store=Store(Settings(environment='preprod',data_mode='pp_live',origin_id=TRIAL_ORIGIN,dsn=self.app_dsn))
        def event(index):
            at=datetime.now(timezone.utc).isoformat()
            return coinbase_ticker(dict(type='ticker',product_id='BTC-USD',trade_id=index,time=at,
                price='100001.00000000000000001',last_size='0.0001'),at)
        self.event=event
        self.fixture_on()
        self.store.ingest(event(1));self.repo.disable_collector(TRIAL_ORIGIN)
        from postgres.active_structured import ActiveStructuredWorker
        ActiveStructuredWorker(self.repo,self.raw,origin_id=TRIAL_ORIGIN).cycle(self.anchor)
        self.target=SealTarget(self.anchor,self.anchor,self.repo.collector_state(TRIAL_ORIGIN)['epoch'],
                               1,1,str(uuid.uuid4()),'a'*40)

    def fixture_on(self):
        with self.admin() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '2 minutes' WHERE origin_id=%s",
                       (str(uuid.uuid4()),TRIAL_ORIGIN))

    def cleanup(self):
        from psycopg import sql
        with self.admin() as db:
            for table in ('ops.dedup','ops.outbox','core.protected_evidence','core.current_prices','archive.reader_leases',
                          'archive.manifests','archive.checkpoints','ops.writer_state'):
                db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=ANY(%s)').format(
                    sql.Identifier(*table.split('.'))),(self.origins,))
            for generation in self.children:
                db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(
                    sql.Identifier('events_g_'+generation.replace('-',''))))
            db.execute('DELETE FROM core.markets WHERE origin_id=ANY(%s)', (self.origins,))
            db.execute('DELETE FROM archive.generations WHERE origin_id=ANY(%s)',(self.origins,))

    def evidence(self):
        with self.admin() as db:
            return [db.execute(query).fetchall() for query in (
                "SELECT * FROM archive.generations WHERE origin_id='pp-live-pp' ORDER BY generation_id",
                'SELECT * FROM raw.events ORDER BY generation_id,event_id',
                'SELECT * FROM core.current_prices ORDER BY origin_id,source,symbol',
                'SELECT * FROM ops.outbox ORDER BY id',
                'SELECT * FROM ops.dedup ORDER BY origin_id,source,event_id')]

    def test_display_before_commit_and_verified_quote_ack(self):
        import asyncio
        import json
        from datetime import timedelta
        from postgres.active_structured import ActiveStructuredWorker
        from postgres.api import event_stream
        from postgres.live_contract import polymarket_market
        from postgres.live_state import LiveState
        from postgres.quote_display import DisplaySender, receive
        from postgres.quote_session import QuotePipeline

        self.fixture_on()
        state = LiveState(self.store.settings)
        at = datetime.now(timezone.utc)
        start = at - timedelta(minutes=1)
        raw = {'id': 'display-market', 'slug': 'quote-market', 'status': 'open',
               'assetPriceTerms': {'asset': {'symbol': 'btc'}, 'horizon': '15m',
                   'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                   'windowStart': start.isoformat(), 'windowEnd': (start+timedelta(minutes=15)).isoformat()}}
        market = polymarket_market(raw, at.isoformat())
        data = {'marketData': {'marketSlug': raw['slug'], 'transactTime': at.isoformat(),
                'bids': [{'px': {'value': '0.6100'}}], 'offers': [{'px': {'value': '0.6300'}}]}}
        release = threading.Event()
        blocked = threading.Event()
        ingest = self.store.ingest

        def slow_write(event):
            if event['kind'] == 'quote':
                blocked.set()
                if not release.wait(5):
                    raise AssertionError('fixture writer release timed out')
            return ingest(event)

        async def exercise():
            path = str(self.root/'display.sock')
            listener = asyncio.create_task(receive(state, path))
            await asyncio.sleep(0)
            sender = DisplaySender(self.store.origin, path)
            pipe = QuotePipeline(self.store, sender)
            writer = asyncio.create_task(pipe.write())
            try:
                with patch.object(self.store, 'ingest', slow_write):
                    await pipe.market(market)
                    await pipe.book(data)
                    self.assertTrue(await asyncio.to_thread(blocked.wait, 3))
                    stream = event_stream(state)
                    frame = await anext(stream)
                    await stream.aclose()
                    displayed = json.loads(frame.split('data: ', 1)[1])
                    quote = displayed['polymarket']
                    self.assertEqual(quote['best_bid'], '0.6100')
                    self.assertIsNone(displayed['market']['target_usd'])
                    self.assertEqual(displayed['quote_counts']['saved'], 0)
                    await pipe.book(data)
                    self.assertEqual(pipe.received, 1)
                    release.set()
                    await asyncio.wait_for(pipe.queue.join(), 4)
                    self.assertEqual(pipe.saved, 1)
                    self.assertEqual(pipe.last_commit['event_id'], quote['event_id'])
                return quote, pipe.started
            finally:
                release.set()
                listener.cancel()
                writer.cancel()
                await asyncio.gather(listener, writer, return_exceptions=True)
                sender.socket.close()
        quote, started = asyncio.run(exercise())
        self.assertEqual(self.store.archived_quote_count(started), 0)
        self.repo.disable_collector(TRIAL_ORIGIN)
        result = ActiveStructuredWorker(self.repo, self.raw, origin_id=TRIAL_ORIGIN).cycle(self.anchor)
        self.assertGreater(result['acknowledged'], 0)
        self.assertEqual(self.store.archived_quote_count(started), 1)
        with self.admin() as db:
            row = db.execute("""SELECT r.content_hash AS local_hash, o.content_hash AS archive_hash,
                       o.payload->'payload'->'data'->>'best_bid' AS bid
                FROM raw.events r JOIN ops.outbox o ON o.origin_id=r.origin_id
                AND o.payload->>'event_id'=r.event_id
                WHERE r.event_id=%s AND o.acknowledged_at IS NOT NULL""", (quote['event_id'],)).fetchone()
        self.assertEqual(row['local_hash'], row['archive_hash'])
        self.assertEqual(row['bid'], quote['best_bid'])

    def test_seal_replay_and_existing_raw_worker_preserve_all_sources(self):
        from postgres.pp_sealed_archive import cycle
        before=self.evidence()
        result=seal_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(result['status'],'sealed_for_initial_trial_archive')
        self.assertFalse(result['original_trial_satisfied']);self.assertFalse(result['retirement_authorized'])
        self.assertEqual(self.evidence(),before)
        state=self.repo.collector_state(TRIAL_ORIGIN)
        self.assertEqual(state['generation_id'],self.anchor)
        self.assertEqual(state['epoch'],self.target.writer_epoch+1)
        self.assertFalse(state['stored_enabled'])
        self.assertEqual(seal_initial_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        self.raw.fail_get=True
        with self.assertRaises(ArchiveUnavailable):cycle(self.repo,self.raw,origin=TRIAL_ORIGIN)
        self.raw.fail_get=False
        self.assertEqual(cycle(self.repo,self.raw,origin=TRIAL_ORIGIN)['status'],'archived')
        self.assertEqual(self.repo.generation(self.anchor)['state'],'verified')
        self.assertEqual(seal_initial_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        self.assertEqual(self.evidence(),before)
        with self.factory() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.generations WHERE origin_id=%s',
                                       (TRIAL_ORIGIN,)).fetchone()['n'],1)
        with self.assertRaises(LifecycleHold):
            self.repo.enable_collector(TRIAL_ORIGIN,session_id=str(uuid.uuid4()),expected_generation_id=self.anchor,max_seconds=60)
        with self.assertRaises(ValueError):self.store.ingest(self.event(2))
        for change in ({'operation':str(uuid.uuid4())},{'source':'c'*40},{'outbox_count':2}):
            with self.subTest(change=change),self.assertRaises(LifecycleHold):
                seal_initial_a(self.repo,replace(self.target,**change),execute=True)

    def test_independent_readonly_maintenance_audit_and_corruption_hold(self):
        from postgres.connection import connect
        from postgres.pp_initial_trial_drain import audit_initial_a
        from postgres.pp_retirement_verify import RetirementTransport
        from postgres.cloud_origin_binding import cloud_binding, TRIAL_READER
        from postgres.pp_sealed_archive import cycle
        seal_initial_a(self.repo,self.target,execute=True)
        cycle(self.repo,self.raw,origin=TRIAL_ORIGIN)
        self.raw._reader=True;self.raw._origin_binding=cloud_binding(TRIAL_ORIGIN)
        raw=self.raw
        class StructuredReader:
            expected_role=TRIAL_READER
            origin_id=TRIAL_ORIGIN
            generation_id=self.anchor
            def read_retirement_revisions(inner,records,*,max_bytes,timeout_seconds):
                result=raw.read_structured_authenticated(records,max_bytes=max_bytes,timeout_seconds=timeout_seconds)
                return result,max(len(encoded(records)),len(encoded(result)))
        transport=RetirementTransport(raw,StructuredReader(),origin_id=TRIAL_ORIGIN,generation_id=self.anchor)
        reader=lambda:connect(f'host={self.socket} user=tradebot_reader dbname=tradebot_pp',readonly=True)
        digest=self.repo.generation(self.anchor)['seal_hash']
        before=self.evidence()
        with patch('postgres.pp_retained_archive_audit.remote_preflight') as remote:
            result=audit_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
            remote.assert_called_once()
            self.assertEqual(result['status'],'initial_trial_archive_audit_verified')
            self.assertFalse(result['original_trial_satisfied'])
            raw.corrupt_structured=True
            with self.assertRaises(ArchiveIntegrityError):
                audit_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
            raw.corrupt_structured=False;raw.fail_get=True
            with self.assertRaises(ArchiveUnavailable):
                audit_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
            raw.fail_get=False
            with self.assertRaises(LifecycleHold):
                audit_initial_a(reader,transport,self.target,seal_hash='0'*64,raw_objects=1,structured_pages=1)
            transport.structured.expected_role='tradebot_pp_history'
            with self.assertRaises(LifecycleHold):
                audit_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
        self.assertEqual(self.evidence(),before)

    def test_second_generation_is_not_initial_a_maintenance(self):
        with self.repo.transaction() as db:
            other=self.repo._create(db,TRIAL_ORIGIN,'B',datetime.now(timezone.utc))
        self.children.append(other['generation_id'])
        with self.assertRaisesRegex(LifecycleHold,'prepared single'):
            seal_initial_a(self.repo,self.target,execute=True)

    def test_exact_counts_epoch_anchor_and_pending_are_required(self):
        before=self.evidence()
        for change in ({'writer_epoch':99},{'raw_count':2},{'outbox_count':2},
                       {'generation':str(uuid.uuid4()),'initial_a':str(uuid.uuid4())}):
            with self.subTest(change=change),self.assertRaises((ValueError,LifecycleHold)):
                seal_initial_a(self.repo,replace(self.target,**change),execute=True)
        self.assertEqual(self.evidence(),before)
        with self.admin() as db:db.execute('UPDATE ops.outbox SET acknowledged_at=NULL WHERE origin_id=%s',(TRIAL_ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'fully acknowledged'):seal_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.anchor)['state'],'collecting')

    def test_every_pp_writer_requires_null_session_and_lease_even_if_expired(self):
        for origin in ('pp-live-pp',TRIAL_ORIGIN):
            with self.subTest(origin=origin):
                with self.admin() as db:
                    db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                        "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",(str(uuid.uuid4()),origin))
                with self.assertRaisesRegex(LifecycleHold,'durably OFF'):seal_initial_a(self.repo,self.target,execute=True)
                self.repo.disable_collector(origin)
                # The schema independently requires OFF to clear session and lease.
                with self.admin() as db:
                    state=db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(origin,)).fetchone()
                    self.assertIsNone(state['collector_session_id'])
                    self.assertIsNone(state['collector_lease_expires_at'])

    def test_checkpoint_failure_rolls_back_seal_and_epoch(self):
        before=self.evidence()
        with patch.object(self.repo,'_checkpoint',side_effect=RuntimeError('journal failure')):
            with self.assertRaises(RuntimeError):seal_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.evidence(),before)
        self.assertEqual(self.repo.generation(self.anchor)['state'],'collecting')
        self.assertEqual(self.repo.collector_state(TRIAL_ORIGIN)['epoch'],self.target.writer_epoch)
        with self.factory() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.checkpoints WHERE generation_id=%s AND consumer=%s',
                                        (self.anchor,CONSUMER)).fetchone())

    def test_missing_prepare_wrong_slot_and_extra_generation_rejected(self):
        with self.admin() as db:
            db.execute("UPDATE archive.generations SET slot='B' WHERE generation_id=%s",(self.anchor,))
        with self.assertRaises(LifecycleHold):seal_initial_a(self.repo,self.target,execute=True)
        with self.admin() as db:
            db.execute("UPDATE archive.generations SET slot='A' WHERE generation_id=%s",(self.anchor,))
            db.execute("UPDATE archive.checkpoints SET cursor='{}'::jsonb WHERE generation_id=%s",(self.anchor,))
        with self.assertRaisesRegex(LifecycleHold,'prepared single'):seal_initial_a(self.repo,self.target,execute=True)

    def test_detached_partition_rejected(self):
        from psycopg import sql
        child='events_g_'+self.anchor.replace('-','')
        with self.admin() as db:
            db.execute(sql.SQL('ALTER TABLE raw.events DETACH PARTITION raw.{}').format(sql.Identifier(child)))
        # Detached raw rows cannot satisfy the reviewed count, nor be sealed.
        with self.assertRaises(LifecycleHold):seal_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.anchor)['state'],'collecting')

    def test_inflight_store_write_is_drained_then_changed_counts_hold(self):
        locked,release=threading.Event(),threading.Event();errors=[]
        original=self.store._locked_writer
        def wait(db):
            writer=original(db);locked.set()
            if not release.wait(3):raise RuntimeError('fixture wait expired')
            return writer
        self.fixture_on()
        def ingest():
            try:self.store.ingest(self.event(2))
            except Exception as error:errors.append(error)
        def stop_and_seal():
            try:
                self.repo.disable_collector(TRIAL_ORIGIN)
                seal_initial_a(self.repo,replace(self.target,writer_epoch=self.target.writer_epoch+1),execute=True)
            except Exception as error:errors.append(error)
        with patch.object(self.store,'_locked_writer',side_effect=wait):
            writer=threading.Thread(target=ingest);writer.start();self.assertTrue(locked.wait(2))
            seal=threading.Thread(target=stop_and_seal);seal.start()
            try:time.sleep(.05);self.assertTrue(seal.is_alive())
            finally:release.set();writer.join(4);seal.join(4)
        self.assertFalse(writer.is_alive());self.assertFalse(seal.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],LifecycleHold)
        self.assertFalse(self.store.collector_enabled())
        self.assertEqual(self.repo.generation(self.anchor)['state'],'collecting')
