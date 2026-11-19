"""Historical seal-only controls; native tests use an owned disposable PP DB."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, ArchiveUnavailable
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.pp_historical_drain import CONSUMER, MAX_RAW_ROWS, SealTarget, main, seal_offline_b
from postgres_lifecycle_fixtures import ImmutableMemoryTransport


class HistoricalSealControls(unittest.TestCase):
    def test_target_and_execution_are_exact_and_bounded(self):
        target=SealTarget(str(uuid.uuid4()),2,9784,str(uuid.uuid4()),'a'*40)
        target.validate()
        for values in ({'raw_count':0},{'raw_count':MAX_RAW_ROWS+1},{'writer_epoch':True},
                       {'source':'main'},{'generation':'B'}):
            with self.subTest(values=values),self.assertRaises((ValueError,LifecycleHold)):
                replace(target,**values).validate()
        class Repo:
            environment='production'
        with self.assertRaises(LifecycleHold):
            seal_offline_b(Repo(),target,execute=True)
        with self.assertRaises(LifecycleHold):
            seal_offline_b(Repo(),target)

    def test_default_off_cli_never_reads_secret(self):
        args=['--generation',str(uuid.uuid4()),'--writer-epoch','2','--raw-count','1',
              '--operation',str(uuid.uuid4()),'--source','a'*40]
        with patch('postgres.pp_historical_drain.private_dsn') as secret:
            self.assertEqual(main(args),1)
            secret.assert_not_called()


NATIVE=all(os.getenv('TRADEBOT_TEST_'+role+'_DSN') for role in ('LIFECYCLE','APP','MIGRATOR'))


@unittest.skipUnless(NATIVE,'requires isolated generated PostgreSQL role DSNs')
class HistoricalSealNative(unittest.TestCase):
    def setUp(self):
        if (os.getenv('TRADEBOT_DATA_MODE'),os.getenv('TRADEBOT_ORIGIN_ID')) != ('generated','generated-pp'):
            self.skipTest('dedicated generated harness required')
        from postgres.connection import connect, connect_migrator
        from postgres.config import Settings
        from postgres.store import Store
        from postgres.live_contract import coinbase_ticker
        self.origin='pp-live-pp'
        self.origins=[self.origin]
        self.factory=lambda:connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'],environment='preprod')
        self.owner=lambda:connect_migrator(os.environ['TRADEBOT_TEST_MIGRATOR_DSN'])
        self.repo=LifecycleRepository(self.factory)
        self.raw=ImmutableMemoryTransport()
        self.store=Store(Settings(environment='preprod',data_mode='pp_live',origin_id=self.origin,
                                  dsn=os.environ['TRADEBOT_TEST_APP_DSN']))
        with self.owner() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s',
                                         (self.origin,)).fetchone())
        self.a=self.repo.bootstrap(self.origin,datetime.now(timezone.utc)-timedelta(hours=73))
        self.children=[self.a['generation_id']]
        self.addCleanup(self.cleanup)
        with self.owner() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '2 minutes' WHERE origin_id=%s",
                       (str(uuid.uuid4()),self.origin))
        def event(index):
            at=datetime.now(timezone.utc).isoformat()
            return coinbase_ticker(dict(type='ticker',product_id='BTC-USD',trade_id=index,time=at,
                                        price='100001.00000000000000001',last_size='0.0001'),at)
        self.event=event
        self.store.ingest(event(1))
        self.b=self.repo.switch_if_due(self.origin,RotationPolicy(1))['generation_id']
        self.children.append(self.b)
        self.store.ingest(event(2))
        self.repo.disable_collector(self.origin)
        worker=ArchiveWorker(self.repo,self.raw,ArchiveLimits())
        self.assertEqual(worker.archive_cycle(self.a['generation_id'])['status'],'archived')
        with self.owner() as db:
            # Expired original A trial remains expired throughout maintenance.
            db.execute("UPDATE archive.generations SET sealed_at=clock_timestamp()-interval '31 minutes' "
                       'WHERE generation_id=%s',(self.a['generation_id'],))
        self.target=SealTarget(self.b,self.repo.collector_state(self.origin)['epoch'],1,
                               str(uuid.uuid4()),'a'*40)

    def cleanup(self):
        from psycopg import sql
        with self.owner() as db:
            for table in ('ops.dedup','ops.outbox','core.current_prices','archive.reader_leases',
                          'archive.manifests','archive.checkpoints','ops.writer_state'):
                for origin in self.origins:
                    db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=%s').format(
                        sql.Identifier(*table.split('.'))),(origin,))
            for generation in self.children:
                db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(
                    sql.Identifier('events_g_'+generation.replace('-',''))))
            for origin in self.origins:
                db.execute('DELETE FROM archive.generations WHERE origin_id=%s',(origin,))

    def snapshot(self):
        with self.owner() as db:
            return (
                db.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                           (self.a['generation_id'],)).fetchone(),
                db.execute('SELECT * FROM raw.events WHERE origin_id=%s ORDER BY generation_id,event_id',
                           (self.origin,)).fetchall(),
                db.execute('SELECT * FROM core.current_prices WHERE origin_id=%s ORDER BY source,symbol',
                           (self.origin,)).fetchall(),
                db.execute('SELECT id,origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at '
                           'FROM ops.outbox WHERE origin_id=%s ORDER BY id',(self.origin,)).fetchall(),
                db.execute('SELECT * FROM archive.manifests WHERE generation_id=%s ORDER BY manifest_id',
                           (self.a['generation_id'],)).fetchall(),
                db.execute('SELECT * FROM ops.dedup WHERE origin_id=%s ORDER BY source,event_id',
                           (self.origin,)).fetchall())

    def test_seal_retry_then_existing_bounded_workers_archive_without_removal(self):
        from postgres.active_structured import SealedStructuredWorker
        from postgres.pp_sealed_archive import cycle
        before=self.snapshot()
        result=seal_offline_b(self.repo,self.target,execute=True)
        self.assertEqual(result['status'],'sealed_for_historical_archive')
        self.assertFalse(result['retirement_authorized'])
        self.assertFalse(result['original_trial_satisfied'])
        self.assertEqual(self.snapshot(),before)
        state=self.repo.collector_state(self.origin)
        self.assertEqual(state['generation_id'],self.b)
        self.assertEqual(state['epoch'],self.target.writer_epoch+1)
        self.assertFalse(state['stored_enabled'])
        receipt=seal_offline_b(self.repo,self.target,execute=True)
        self.assertEqual(receipt['status'],'already_sealed')
        self.assertEqual(receipt['sealed_at'],result['sealed_at'])
        with self.assertRaises(LifecycleHold):
            seal_offline_b(self.repo,replace(self.target,operation=str(uuid.uuid4())),execute=True)
        with self.assertRaises(LifecycleHold):
            self.repo.enable_collector(self.origin,session_id=str(uuid.uuid4()),
                expected_generation_id=self.b,max_seconds=60)
        with self.assertRaisesRegex(ValueError, 'bootstrap required'):
            self.store.ingest(self.event(3))
        # No raw transfer before the genuine structured ACK; failure retains B.
        calls=len(self.raw.calls)
        with self.assertRaises(LifecycleHold):
            cycle(self.repo,self.raw)
        self.assertEqual(len(self.raw.calls),calls)
        drain=SealedStructuredWorker(self.repo,self.raw,origin_id=self.origin)
        self.raw.corrupt_structured=True
        with self.assertRaises(ArchiveIntegrityError):
            drain.cycle(self.b)
        self.assertTrue(self.repo.outbox(self.b,1))
        self.raw.corrupt_structured=False
        self.assertEqual(drain.cycle(self.b)['acknowledged'],1)
        self.raw.fail_get=True
        with self.assertRaises(ArchiveUnavailable):
            cycle(self.repo,self.raw)
        self.raw.fail_get=False
        archived=cycle(self.repo,self.raw)
        self.assertEqual(archived['status'],'archived')
        self.assertEqual(archived['retirement'],'off')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.repo.generation(self.b)['state'],'verified')
        with self.factory() as db:
            checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE generation_id=%s '
                                  'AND consumer=%s',(self.b,CONSUMER)).fetchone()['cursor']
            self.assertEqual(checkpoint['operation'],self.target.operation)
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.generations WHERE origin_id=%s',
                                        (self.origin,)).fetchone()['n'],2)
        self.assertEqual(seal_offline_b(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])

    def test_identity_count_epoch_and_durable_off_failures_preserve_generations(self):
        before=self.snapshot()
        for change in ({'generation':self.a['generation_id']},{'raw_count':2},
                       {'writer_epoch':self.target.writer_epoch+1}):
            with self.subTest(change=change),self.assertRaises(LifecycleHold):
                seal_offline_b(self.repo,replace(self.target,**change),execute=True)
        with self.owner() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",
                       (str(uuid.uuid4()),self.origin))
        with self.assertRaises(LifecycleHold):
            seal_offline_b(self.repo,self.target,execute=True)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.repo.generation(self.b)['state'],'collecting')

    def test_other_collector_and_atomic_checkpoint_failure_preserve_b(self):
        before=self.snapshot()
        other='pp-live-drain-control-'+uuid.uuid4().hex
        g=self.repo.bootstrap(other)
        self.origins.append(other)
        self.children.append(g['generation_id'])
        with self.owner() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '1 minute' WHERE origin_id=%s",
                       (str(uuid.uuid4()),other))
        with self.assertRaisesRegex(LifecycleHold,'all PP collectors OFF'):
            seal_offline_b(self.repo,self.target,execute=True)
        self.repo.disable_collector(other)
        with patch.object(self.repo,'_checkpoint',side_effect=RuntimeError('fixture journal failure')):
            with self.assertRaises(RuntimeError):
                seal_offline_b(self.repo,self.target,execute=True)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.repo.generation(self.b)['state'],'collecting')
        self.assertEqual(self.repo.collector_state(self.origin)['epoch'],self.target.writer_epoch)
        with self.factory() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.checkpoints WHERE generation_id=%s '
                                        'AND consumer=%s',(self.b,CONSUMER)).fetchone())

    def test_inflight_store_write_finishes_before_exact_count_is_checked(self):
        locked,release=threading.Event(),threading.Event()
        errors=[]
        original=self.store._locked_writer
        def wait(db):
            writer=original(db)
            locked.set()
            if not release.wait(3):
                raise RuntimeError('fixture write wait expired')
            return writer
        # Explicit fixture-only re-enable, then start one acknowledged Store write.
        with self.owner() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '2 minutes' WHERE origin_id=%s",
                       (str(uuid.uuid4()),self.origin))
        with patch.object(self.store,'_locked_writer',side_effect=wait):
            writer=threading.Thread(target=lambda:self.store.ingest(self.event(4)))
            writer.start()
            self.assertTrue(locked.wait(2))
            def stop_and_seal():
                try:
                    self.repo.disable_collector(self.origin)
                    seal_offline_b(self.repo,replace(self.target,writer_epoch=self.target.writer_epoch+1),execute=True)
                except Exception as error:
                    errors.append(error)
            seal=threading.Thread(target=stop_and_seal)
            seal.start()
            try:
                time.sleep(.05)
                self.assertTrue(seal.is_alive())
            finally:
                release.set()
                writer.join(4)
                seal.join(4)
        self.assertFalse(writer.is_alive())
        self.assertFalse(seal.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],LifecycleHold)
        self.assertEqual(self.repo.generation(self.b)['state'],'collecting')
        self.assertEqual(self.store.collector_enabled(),False)
        with self.factory() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM raw.events WHERE generation_id=%s',
                                        (self.b,)).fetchone()['n'],2)
