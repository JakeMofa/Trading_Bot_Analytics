"""Final trial A tail: source controls and disposable PostgreSQL qualification."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, ArchiveUnavailable, encoded
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.pp_final_trial_drain import CONSUMER, TailTarget, main, seal_final_a
from postgres.rehearsal_profile import TRIAL_ORIGIN, lease_cap
from postgres_lifecycle_fixtures import ImmutableMemoryTransport


class TailControls(unittest.TestCase):
    def test_exact_target_and_default_off(self):
        target=TailTarget(TRIAL_ORIGIN,*[str(uuid.uuid4()) for _ in range(3)],3,1,
                          str(uuid.uuid4()),'a'*40,'b'*40)
        target.validate()
        for change in ({'origin':'pp-live-pp'},{'origin':TRIAL_ORIGIN+'-other'},
                       {'anchor':target.generation},{'raw_count':64001},{'trial_source':'main'}):
            with self.subTest(change=change),self.assertRaises((ValueError,LifecycleHold)):
                replace(target,**change).validate()
        with self.assertRaises(LifecycleHold):
            seal_final_a(SimpleNamespace(environment='preprod'),target)
        args=['--origin',target.origin,'--anchor',target.anchor,'--retired-b',target.retired_b,
              '--trial-source',target.trial_source,'--generation',target.generation,
              '--writer-epoch','3','--raw-count','1','--operation',target.operation,'--source',target.source]
        with patch('postgres.pp_final_trial_drain.private_dsn') as secret:
            self.assertEqual(main(args),1)
            secret.assert_not_called()


NATIVE=all(os.getenv('TRADEBOT_TEST_'+r+'_DSN') for r in ('LIFECYCLE','APP','MIGRATOR'))


@unittest.skipUnless(NATIVE,'requires disposable PostgreSQL role DSNs')
class TailNative(unittest.TestCase):
    def setUp(self):
        if (os.getenv('TRADEBOT_DATA_MODE'),os.getenv('TRADEBOT_ORIGIN_ID')) != ('generated','generated-pp'):
            self.skipTest('dedicated generated fixture required')
        from postgres.connection import connect,connect_migrator
        from postgres.config import Settings
        from postgres.store import Store
        from postgres.live_contract import coinbase_ticker
        from postgres.pp_retirement_verify import Permit,RetirementTransport,Target,TwoMarketReadbackLimits,verify
        self.origin=TRIAL_ORIGIN
        self.factory=lambda:connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'])
        self.owner=lambda:connect_migrator(os.environ['TRADEBOT_TEST_MIGRATOR_DSN'])
        self.repo=LifecycleRepository(self.factory)
        self.raw=ImmutableMemoryTransport()
        self.worker=ArchiveWorker(self.repo,self.raw,ArchiveLimits())
        self.ids=[];self.tickets=[];self.extra_origins=[]
        with self.owner() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s',
                                         (self.origin,)).fetchone())
        a=self.repo.bootstrap(self.origin,datetime.now(timezone.utc)-timedelta(hours=2))
        self.ids.append(a['generation_id'])
        self.addCleanup(self.cleanup)
        now=datetime.now(timezone.utc)
        boundary=datetime.fromtimestamp(int(now.timestamp())//900*900,timezone.utc)
        admitted=boundary-timedelta(seconds=30)
        expiry=admitted+timedelta(seconds=lease_cap(self.ids[0]))
        session=str(uuid.uuid4())
        self.admission=dict(session_id=session,initial_a=self.ids[0],lease_seconds=lease_cap(self.ids[0]),
                            admitted_at=admitted.isoformat(),lease_expires_at=expiry.isoformat())
        with self.owner() as db:
            self.repo._checkpoint(db,a,'rehearsal:two-leg-session',self.admission)
            db.execute('UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,'
                       'collector_lease_expires_at=%s WHERE origin_id=%s',(session,expiry,self.origin))
        self.store=Store(Settings(data_mode='pp_live',origin_id=self.origin,
                                  dsn=os.environ['TRADEBOT_TEST_APP_DSN']))
        def event(index):
            at=datetime.now(timezone.utc).isoformat()
            return coinbase_ticker(dict(type='ticker',product_id='BTC-USD',trade_id=index,time=at,
                                        price='100001.00000000000000001',last_size='0.0001'),at)
        self.event=event
        self.store.ingest(event(1))
        for leg in range(2):
            sealed=self.ids[-1]
            active=self.repo.switch_if_due(self.origin,RotationPolicy(1))['generation_id']
            self.ids.append(active)
            self.worker.archive_cycle(sealed)
            generation=self.repo.generation(sealed)
            ticket=str(uuid.uuid4());self.tickets.append(ticket)
            permit=Permit(ticket,'b'*40,'c'*64,'d'*64)
            with self.owner() as db:
                db.execute("""INSERT INTO archive.pp_retirement_permits(ticket,sealed_id,collecting_id,
                    seal_hash,seal_count,release_sha,policy_epoch_hash,history_reader_proof,authority_scope,expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pp-admin-change-freeze-v1',clock_timestamp()+interval '1 minute')""",
                    (ticket,sealed,active,generation['seal_hash'],generation['seal_count'],
                     permit.release,permit.policy_epoch,permit.history_reader_proof))
            def revisions(records,**kw):
                rows=self.raw.read_structured_authenticated(records,**kw)
                return rows,len(encoded(rows))
            scoped=RetirementTransport(self.raw,SimpleNamespace(read_retirement_revisions=revisions),
                                       origin_id=self.origin,generation_id=sealed)
            raw_read=self.raw.read_authenticated
            def progress(*args,**kw):
                self.store.ingest(event(2+leg))
                return raw_read(*args,**kw)
            self.raw.read_authenticated=progress
            try:
                result=verify(self.repo,scoped,Target(sealed,active,generation['seal_hash'],1),
                              limits=TwoMarketReadbackLimits(),origin=self.origin,permit=permit)
            finally:
                self.raw.read_authenticated=raw_read
            self.assertEqual(result['status'],'retired_pp')
        self.repo.disable_collector(self.origin)
        self.target=TailTarget(self.origin,self.ids[0],self.ids[1],self.ids[2],
            self.repo.collector_state(self.origin)['epoch'],1,str(uuid.uuid4()),'a'*40,'b'*40)

    def cleanup(self):
        from psycopg import sql
        with self.owner() as db:
            for table in ('ops.dedup','ops.outbox','core.current_prices','archive.reader_leases',
                          'archive.manifests','archive.checkpoints','ops.writer_state'):
                for origin in [self.origin,*self.extra_origins]:
                    db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=%s').format(
                        sql.Identifier(*table.split('.'))),(origin,))
            for gen in self.ids:
                db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(
                    sql.Identifier('events_g_'+gen.replace('-',''))))
            for origin in [self.origin,*self.extra_origins]:
                db.execute('DELETE FROM archive.generations WHERE origin_id=%s',(origin,))
            for ticket in self.tickets:
                db.execute('DELETE FROM archive.pp_retirement_permits WHERE ticket=%s',(ticket,))

    def snapshot(self):
        with self.owner() as db:
            return (
                db.execute('SELECT * FROM archive.generations WHERE generation_id=ANY(%s::text[]) '
                           'ORDER BY generation_id',(self.ids[:2],)).fetchall(),
                db.execute('SELECT * FROM raw.events WHERE origin_id=%s ORDER BY event_id',(self.origin,)).fetchall(),
                db.execute('SELECT * FROM core.current_prices WHERE origin_id=%s',(self.origin,)).fetchall(),
                db.execute('SELECT id,origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at '
                           'FROM ops.outbox WHERE origin_id=%s ORDER BY id',(self.origin,)).fetchall(),
                db.execute("SELECT * FROM archive.checkpoints WHERE origin_id=%s AND consumer IN "
                           "('rehearsal:two-leg-session','retirement:pp-fresh-readback') ORDER BY generation_id,consumer",
                           (self.origin,)).fetchall())

    def test_off_tail_seal_then_scoped_existing_archive_retains_final_partition(self):
        from postgres.active_structured import SealedStructuredWorker
        from postgres.pp_sealed_archive import cycle
        before=self.snapshot()
        result=seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(result['status'],'sealed_final_a_for_archive')
        self.assertFalse(result['retirement_authorized'])
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(seal_final_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        self.assertEqual(self.repo.collector_state(self.origin)['generation_id'],self.target.generation)
        self.assertEqual(self.repo.collector_state(self.origin)['epoch'],self.target.writer_epoch+1)
        with self.assertRaises(LifecycleHold):
            self.repo.enable_collector(self.origin,session_id=str(uuid.uuid4()),
                expected_generation_id=self.target.generation,max_seconds=60)
        with self.assertRaises(LifecycleHold):
            cycle(self.repo,self.raw,origin=self.origin)
        drain=SealedStructuredWorker(self.repo,self.raw,origin_id=self.origin)
        self.raw.corrupt_structured=True
        with self.assertRaises(ArchiveIntegrityError):drain.cycle(self.target.generation)
        self.raw.corrupt_structured=False
        self.assertEqual(drain.cycle(self.target.generation)['acknowledged'],1)
        self.raw.fail_get=True
        with self.assertRaises(ArchiveUnavailable):cycle(self.repo,self.raw,origin=self.origin)
        self.raw.fail_get=False
        self.assertEqual(cycle(self.repo,self.raw,origin=self.origin)['status'],'archived')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'verified')
        self.assertEqual(seal_final_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        with self.factory() as db:
            self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child',
                ('raw.events_g_'+self.target.generation.replace('-',''),)).fetchone()['child'])
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.generations WHERE origin_id=%s',
                                       (self.origin,)).fetchone()['n'],3)

    def test_drifted_binding_rejects_before_seal_and_checkpoint_failure_rolls_back(self):
        before=self.snapshot()
        for change in ({'anchor':str(uuid.uuid4())},{'retired_b':str(uuid.uuid4())},
                       {'generation':self.target.anchor},{'writer_epoch':self.target.writer_epoch+1},
                       {'raw_count':2},{'trial_source':'e'*40}):
            with self.subTest(change=change),self.assertRaises(LifecycleHold):
                seal_final_a(self.repo,replace(self.target,**change),execute=True)
        with patch.object(self.repo,'_checkpoint',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')
        self.assertEqual(self.repo.collector_state(self.origin)['epoch'],self.target.writer_epoch)

    def test_missing_retirement_boundary_or_changed_admission_fails_closed(self):
        for mutation in ('admission','active','boundary','retired_at','state'):
            with self.subTest(mutation=mutation),self.owner() as db:
                # Fixture changes roll back after the independently connected check.
                if mutation=='admission':
                    table='archive.checkpoints';column='cursor';where="generation_id=%s AND consumer='rehearsal:two-leg-session'"
                    gen=self.target.anchor
                elif mutation=='active':
                    table='archive.checkpoints';column='cursor';where="generation_id=%s AND consumer='retirement:pp-fresh-readback'"
                    gen=self.target.retired_b
                else:
                    table='archive.generations';column='started_at' if mutation=='boundary' else ('state' if mutation=='state' else 'retired_at');where='generation_id=%s'
                    gen=self.target.generation if mutation=='boundary' else self.target.retired_b
                old=db.execute(f'SELECT {column} AS value FROM {table} WHERE {where}',(gen,)).fetchone()['value']
                if mutation in ('admission','active'):
                    changed={**old,('initial_a' if mutation=='admission' else 'active'):str(uuid.uuid4())}
                    db.execute(f'UPDATE {table} SET {column}=%s::jsonb WHERE {where}',(encoded(changed).decode(),gen))
                elif mutation=='state':
                    db.execute(f"UPDATE {table} SET state='verified' WHERE {where}",(gen,))
                else:
                    db.execute(f"UPDATE {table} SET {column}={column}+interval '1 hour' WHERE {where}",(gen,))
                db.commit()
                try:
                    with self.assertRaises(LifecycleHold):seal_final_a(self.repo,self.target,execute=True)
                finally:
                    if mutation in ('admission','active'):
                        db.execute(f'UPDATE {table} SET {column}=%s::jsonb WHERE {where}',(encoded(old).decode(),gen))
                    else:db.execute(f'UPDATE {table} SET {column}=%s WHERE {where}',(old,gen))
                    db.commit()
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')

    def test_any_enabled_writer_and_original_b_command_do_not_admit_tail(self):
        from postgres.pp_historical_drain import SealTarget,seal_offline_b
        with self.assertRaises(LifecycleHold):
            seal_offline_b(self.repo,SealTarget(self.target.generation,self.target.writer_epoch,1,
                                              self.target.operation,self.target.source),execute=True)
        other='pp-live-tail-control-'+uuid.uuid4().hex
        g=self.repo.bootstrap(other);self.extra_origins.append(other);self.ids.append(g['generation_id'])
        with self.owner() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",
                       (str(uuid.uuid4()),other))
        with self.assertRaises(LifecycleHold):seal_final_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(self.target.generation)['state'],'collecting')
