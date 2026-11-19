"""Disposable native/CI proof of a full generated queue; no cloud or real feeds."""
import json
import os
import unittest
from unittest.mock import patch

from postgres.config import Settings
from postgres.connection import connect,connect_migrator
from postgres.lifecycle import LifecycleRepository
from postgres.archive_codec import ArchiveIntegrityError,ArchiveLimit,ArchiveUnavailable,encoded,sha256
from postgres import generated_storage as target
from postgres.ingestion import generated_events
from postgres.store import Store,StorageHold
from postgres.worker import CalculationWorker


ENABLED=all(os.getenv(name) for name in ('TRADEBOT_TEST_LIFECYCLE_DSN','TRADEBOT_TEST_APP_DSN',
    'TRADEBOT_TEST_READER_DSN','TRADEBOT_TEST_MIGRATOR_DSN'))


@unittest.skipUnless(ENABLED,'isolated generated PostgreSQL role DSNs required')
class GeneratedStorageIntegration(unittest.TestCase):
    def test_exact_full_backlog_durable_retry_guards_and_repeated_acceptance(self):
        import psycopg
        lifecycle=lambda:connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'])
        app=lambda:connect(os.environ['TRADEBOT_TEST_APP_DSN'])
        reader=lambda:connect(os.environ['TRADEBOT_TEST_READER_DSN'],readonly=True)
        owner=lambda:connect_migrator(os.environ['TRADEBOT_TEST_MIGRATOR_DSN'])
        repo=LifecycleRepository(lifecycle)
        generated=repo.bootstrap('generated-pp')['generation_id']
        live=repo.bootstrap('pp-live-pp')['generation_id']
        # Existing source evidence is retained. Fill only the remaining pending
        # slots; no reset, fake ACK, truncate or delete is used in this test.
        with owner() as db:
            count=db.execute("SELECT count(*) n FROM ops.outbox WHERE origin_id='generated-pp' AND acknowledged_at IS NULL").fetchone()['n']
            self.assertLessEqual(count,10000)
            for origin,generation,amount,ack in [('generated-pp',generated,10000-count,False),
                                               ('pp-live-pp',live,42133,True)]:
                db.execute('''INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,
                    payload,created_at,acknowledged_at)
                    SELECT %s,%s,'core.candles','["'||%s||'","coinbase","BTC-USD",60,'||(1000000+i*60)||']',
                        encode(sha256(convert_to(i::text||%s,'UTF8')),'hex'),
                        jsonb_build_object('origin_id',%s::text,'source','coinbase','symbol','BTC-USD',
                            'granularity',60,'time',1000000+i*60,'low','99.0000','high','101.0000',
                            'open','100.0000','close','100.1000','volume','1.00000000',
                            'first_seen','2026-11-19T00:00:00+00:00','payload',jsonb_build_object('generated',true),
                            'content_hash',encode(sha256(convert_to(i::text||%s,'UTF8')),'hex')),
                        clock_timestamp(),CASE WHEN %s THEN clock_timestamp() ELSE NULL END
                    FROM generate_series(1,%s) i ON CONFLICT DO NOTHING''',
                    (origin,generation,origin,origin,origin,origin,ack,amount))
        def state(origin,*,include_ack,through_id=None):
            with reader() as db:
                return db.execute('''SELECT count(*) n,count(*) FILTER(WHERE acknowledged_at IS NULL) pending,
                    encode(sha256(convert_to(coalesce(string_agg(
                        (CASE WHEN %s THEN to_jsonb(o) ELSE to_jsonb(o)-'acknowledged_at' END)::text,
                        '' ORDER BY id),''),'UTF8')),'hex') digest FROM ops.outbox o WHERE origin_id=%s AND (%s::bigint IS NULL OR id<=%s)''',
                    (include_ack,origin,through_id,through_id)).fetchone()
        with reader() as db:
            initial_through=db.execute("SELECT max(id) n FROM ops.outbox WHERE origin_id='generated-pp'").fetchone()['n']
        before=state('generated-pp',include_ack=False)
        self.assertEqual(before['pending'],10000)
        live_before=state('pp-live-pp',include_ack=True)
        store=Store(Settings(dsn=os.environ['TRADEBOT_TEST_APP_DSN']))
        with self.assertRaises(StorageHold):store.require_generated_headroom()
        # Crash after independent durable storage readback, before local ACK.
        # The source queue stays full, but committed bytes survive restart.
        with patch.object(repo,'acknowledge',side_effect=ArchiveUnavailable('injected before ACK')):
            with self.assertRaises(ArchiveUnavailable):target.drain(repo)
        self.assertEqual(state('generated-pp',include_ack=False)['pending'],10000)
        with reader() as db:
            stored=db.execute('''SELECT outbox_id,envelope,envelope_hash FROM archive.generated_outbox_storage
                ORDER BY outbox_id LIMIT 250''').fetchall()
        self.assertTrue(stored)
        for row in stored:self.assertEqual(sha256(bytes(row['envelope'])),row['envelope_hash'])
        # A torn independent read result cannot produce an ACK. Record the two
        # real authenticated backend identities to exclude read-your-write proof.
        from types import SimpleNamespace
        backends=[]
        class TornRead:
            def __init__(self,inner):self.inner=inner
            def __enter__(self):self.inner.__enter__();return self
            def __exit__(self,*args):return self.inner.__exit__(*args)
            def __getattr__(self,name):return getattr(self.inner,name)
            def execute(self,query,*args):
                result=self.inner.execute(query,*args)
                if 'FROM archive.generated_outbox_storage' in query and 'generation_id=%s' in query:
                    return SimpleNamespace(fetchall=lambda:[])
                return result
        def torn_factory():
            db=lifecycle();backends.append(db.info.backend_pid)
            return TornRead(db) if len(backends)==2 else db
        with (patch.object(repo,'connection_factory',side_effect=torn_factory),
              patch.object(repo,'acknowledge') as acknowledge):
            with self.assertRaises(ArchiveIntegrityError):target.drain(repo)
            acknowledge.assert_not_called()
        self.assertEqual(len(set(backends)),2)
        self.assertEqual(state('generated-pp',include_ack=False)['pending'],10000)
        # An owner-only fixture corruption cannot be hidden by a matching new
        # stored hash. Exact source bytes, not hash alone, must authenticate it.
        first=stored[0];broken=json.loads(bytes(first['envelope']))
        broken['payload']['close']='8.0000';body=encoded(broken)
        with owner() as db:
            db.execute('UPDATE archive.generated_outbox_storage SET envelope=%s,envelope_hash=%s WHERE outbox_id=%s',
                (body,sha256(body),first['outbox_id']))
        with self.assertRaises(ArchiveIntegrityError):target.drain(repo)
        self.assertEqual(state('generated-pp',include_ack=False)['pending'],10000)
        with owner() as db:
            db.execute('UPDATE archive.generated_outbox_storage SET envelope=%s,envelope_hash=%s WHERE outbox_id=%s',
                (bytes(first['envelope']),first['envelope_hash'],first['outbox_id']))
        with patch.object(target,'MAX_STORED_BYTES',1):
            with self.assertRaises(ArchiveLimit):target.drain(repo)
        self.assertEqual(state('generated-pp',include_ack=False)['pending'],10000)
        # A new repository/session resumes exact existing target bytes, then
        # acknowledges only rows that were independently read back.
        repo=LifecycleRepository(lifecycle)
        result=target.drain(repo)
        self.assertEqual(result['scope'],'durable_generated_local_storage')
        self.assertGreaterEqual(result['headroom'],128)
        self.assertFalse(result['raw_retirement_authorized']);self.assertFalse(result['cloud_receipts'])
        after=state('generated-pp',include_ack=False)
        self.assertEqual((after['n'],after['digest']),(before['n'],before['digest']))
        self.assertLess(after['pending'],10000)
        self.assertEqual(state('pp-live-pp',include_ack=True),live_before)
        # A genuinely new process runs the exact bootstrap CLI used by CD,
        # reading a private lifecycle DSN and returning scoped proof only.
        import subprocess,sys,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            secret=Path(folder)/'dsn';secret.write_text(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']);secret.chmod(0o400)
            env={**os.environ,**dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='generated',
                TRADEBOT_ORIGIN_ID='generated-pp',TRADEBOT_DATABASE_DSN_FILE=str(secret),
                TRADEBOT_DATABASE_DSN='',TRADEBOT_COLLECTOR_ENABLED='false',
                TRADEBOT_CLOUD_ENABLED='false',TRADEBOT_RETIREMENT_ENABLED='false',
                TRADEBOT_GENERATED_LOCAL_STORAGE='true',TRADEBOT_OUTBOX_MAX_PENDING='10000')}
            child=subprocess.run([sys.executable,'-m','postgres.lifecycle_worker','--once','--bootstrap'],
                env=env,capture_output=True,text=True,timeout=30,check=True)
            proof=json.loads(child.stdout)
            self.assertGreaterEqual(proof['generated_storage']['headroom'],128)
            self.assertEqual(proof['retirement'],'off')
            self.assertEqual(proof['archive'],'held_no_qualified_transport')
        # Repeated seed/calculate/admission cycles retain the same generated
        # origin, source rows and 10k cap. No fresh-origin escape is needed.
        for _ in range(8):
            target.drain(repo)
            store.require_generated_headroom()
            for event in generated_events():store.ingest(event)
            worker=CalculationWorker(store);worker.discover_once()
            self.assertIsNotNone(worker.calculate_once())
            self.assertLessEqual(state('generated-pp',include_ack=False)['pending'],10000)
        self.assertEqual(state('pp-live-pp',include_ack=True),live_before)
        # Exercise real HTTP/SSE acceptance across independent API/acceptance
        # processes after recovery, using only this generated fixture database.
        import socket,time,urllib.request
        with tempfile.TemporaryDirectory() as folder:
            secret=Path(folder)/'app-dsn';secret.write_text(os.environ['TRADEBOT_TEST_APP_DSN']);secret.chmod(0o400)
            env={**os.environ,**dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='generated',
                TRADEBOT_ORIGIN_ID='generated-pp',TRADEBOT_DATABASE_DSN_FILE=str(secret),
                TRADEBOT_DATABASE_DSN='',TRADEBOT_COLLECTOR_ENABLED='false',
                TRADEBOT_GENERATED_LOCAL_STORAGE='false',ENABLE_SUPABASE_SYNC='false',
                ENABLE_OPENAI_ANALYST='false',ENABLE_LOCAL_RETENTION='false')}
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            server=subprocess.Popen([sys.executable,'-m','uvicorn','postgres.api:app',
                '--host','127.0.0.1','--port',str(port),'--log-level','warning'],env=env,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+10
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1):break
                    except OSError:
                        if server.poll() is not None or time.monotonic()>=deadline:
                            self.fail('isolated generated API did not become healthy')
                        time.sleep(.1)
                accepted=subprocess.run([sys.executable,'-m','postgres.acceptance',
                    '--base-url',f'http://127.0.0.1:{port}'],env=env,capture_output=True,text=True,
                    timeout=30,check=True)
                result=json.loads(accepted.stdout)
                self.assertEqual(result['status'],'pass')
                self.assertTrue(result['generated_headroom_verified'])
                self.assertEqual(result['sse_connections'],2)
            finally:
                server.terminate()
                try:server.wait(timeout=5)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
        retained=state('generated-pp',include_ack=False,through_id=initial_through)
        self.assertEqual((retained['n'],retained['digest']),(before['n'],before['digest']))
        # Runtime app/lifecycle credentials cannot rewrite/delete target bytes.
        for factory in (app,lifecycle):
            for statement in ('UPDATE archive.generated_outbox_storage SET stored_at=clock_timestamp()',
                              'DELETE FROM archive.generated_outbox_storage'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with factory() as db:db.execute(statement)
        with owner() as db:
            # SQL origin constraint independently excludes PP live envelopes.
            bad=json.loads(bytes(stored[0]['envelope']));bad['origin_id']='pp-live-pp';bad['generation_id']=live
            value=encoded(bad)
            with self.assertRaises(psycopg.errors.CheckViolation):
                with db.transaction():
                    db.execute('''INSERT INTO archive.generated_outbox_storage
                        (origin_id,outbox_id,generation_id,envelope,envelope_hash) VALUES(%s,%s,%s,%s,%s)''',
                        ('pp-live-pp',99999999,live,value,sha256(value)))
        self.assertEqual(state('pp-live-pp',include_ack=True),live_before)
