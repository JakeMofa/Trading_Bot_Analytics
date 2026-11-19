"""Disposable native PP switch protocol, with simulated completed retirement.

This tests actual lease, row locks, quote qualification and slot reuse. Fixture
owner retirement below is NOT the PP permit proof (covered by retirement tests).
No source network, cloud, host deployment or real collection occurs.
"""
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.connection import connect,connect_migrator
from postgres.lifecycle import LifecycleRepository,LifecycleHold
from postgres.live_contract import polymarket_market,polymarket_bbo,coinbase_ticker
from postgres.store import Store,StorageHold

ENABLED=all(os.getenv(k) for k in ('TRADEBOT_TEST_MIGRATOR_DSN','TRADEBOT_TEST_LIFECYCLE_DSN','TRADEBOT_TEST_APP_DSN'))

@unittest.skipUnless(ENABLED,'disposable native PostgreSQL DSNs required')
class NativeCycleTests(unittest.TestCase):
    def test_exact_finite_cycle_retained_rejection_and_successor_writes(self):
        self._exercise_cycle()

    def test_occupied_a_stops_cycle_without_recycling_old_retained_rows(self):
        self._exercise_cycle(occupied=True)

    def _exercise_cycle(self, occupied=False):
        from psycopg import sql
        origin='pp-live-pp'
        owner=lambda:connect_migrator(os.environ['TRADEBOT_TEST_MIGRATOR_DSN'])
        factory=lambda:connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'])
        repo=LifecycleRepository(factory)
        # The generated harness owns a previously absent scope; never adopt
        # existing retained partitions from another run.
        with owner() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s',(origin,)).fetchone())
        generations=[]
        def cleanup():
            repo.disable_collector(origin)
            with owner() as db:
                for gen in generations:
                    db.execute(sql.SQL('DROP TABLE IF EXISTS raw.{}').format(sql.Identifier('events_g_'+gen.replace('-',''))))
                for table in ('core.snapshot_evidence','core.predictions','core.outcomes','core.feature_snapshots',
                    'core.protected_evidence','core.current_prices','core.markets','ops.dedup','ops.outbox',
                    'ops.feed_health','ops.worker_checkpoints','archive.reader_leases','archive.checkpoints',
                    'archive.manifests','ops.writer_state','archive.generations'):
                    db.execute(sql.SQL('DELETE FROM {} WHERE origin_id=%s').format(sql.Identifier(*table.split('.'))),(origin,))
        self.addCleanup(cleanup)
        stamp=datetime.now(timezone.utc)
        start=stamp.replace(minute=stamp.minute//15*15,second=0,microsecond=0)
        a=repo.bootstrap(origin,now=start)
        anchor=str(a['generation_id']);generations.append(anchor)
        store=Store(SimpleNamespace(origin_id=origin,environment='preprod',data_mode='pp_live',
            dsn=os.environ['TRADEBOT_TEST_APP_DSN'],outbox_max_pending=10000))
        session=str(uuid.uuid4())
        space={'space_hold':None,'filesystem_free_bytes':20*1024**3,'filesystem_floor_bytes':10*1024**3}
        # Market clock is generated; production alignment uses actual returned DB time.
        with patch('postgres.pp_space.sample',return_value=space), \
             patch('postgres.lifecycle.require_cycle_alignment',return_value=30):
            with patch('postgres.lifecycle.require_cycle_alignment',side_effect=ValueError('outside alignment')):
                with self.assertRaisesRegex(LifecycleHold,'outside alignment'):
                    repo.enable_collector(origin,session_id=session,expected_generation_id=anchor,
                                          max_seconds=6600,rehearsal_anchor=anchor)
            rolled_back=repo.collector_state(origin)
            self.assertFalse(rolled_back['stored_enabled'])
            self.assertIsNone(rolled_back['collector_lease_expires_at'])
            enabled=repo.enable_collector(origin,session_id=session,expected_generation_id=anchor,
                                          max_seconds=6600,rehearsal_anchor=anchor)
            expires=enabled['lease_expires_at']
            with owner() as db:
                db.execute('UPDATE ops.writer_state SET updated_at=%s WHERE origin_id=%s',(start,origin))
            def quote(minute):
                left=start+timedelta(minutes=minute);ts=(left+timedelta(seconds=1)).isoformat()
                market=polymarket_market({'id':f'fixture-{minute}','slug':f'fixture-{minute}',
                    'status':'MARKET_STATUS_OPEN','updatedAt':ts,'assetPriceTerms':{
                    'asset':{'symbol':'btc'},'horizon':'15m','marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                    'windowStart':left.isoformat(),'windowEnd':(left+timedelta(minutes=15)).isoformat()}},ts)
                store.ingest(market)
                return store.ingest(polymarket_bbo({'marketData':{'marketSlug':market['payload']['slug'],
                    'lastPriceSample':{'ts':ts},'bestBid':{'value':'0.4900000000000000001'}}},market,ts))
            def switch(minute):
                return repo.switch_if_due(origin,now=start+timedelta(minutes=minute),
                    require_live_lease=True,market_pair_trial=True,rehearsal_anchor=anchor)
            quote(0)
            # A changed/missing recorded session cannot borrow the cycle
            # profile, and the failed attempt never seals or allocates.
            with owner() as db:
                saved=db.execute("SELECT cursor FROM archive.checkpoints WHERE origin_id=%s "
                    "AND generation_id=%s AND consumer='rehearsal:two-leg-session'",(origin,anchor)).fetchone()['cursor']
                db.execute("UPDATE archive.checkpoints SET cursor=cursor||'{\"lease_seconds\":4560}'::jsonb "
                    "WHERE origin_id=%s AND generation_id=%s AND consumer='rehearsal:two-leg-session'",(origin,anchor))
            with self.assertRaisesRegex(LifecycleHold,'admission changed'):
                switch(30)
            from psycopg.types.json import Jsonb
            with owner() as db:
                db.execute("UPDATE archive.checkpoints SET cursor=%s WHERE origin_id=%s "
                    "AND generation_id=%s AND consumer='rehearsal:two-leg-session'",(Jsonb(saved),origin,anchor))
            self.assertEqual(switch(30)['status'],'collecting') # delayed second market metadata
            self.assertTrue(repo.owns_collector(origin,session))
            quote(15)
            first=switch(30);b=str(first['generation_id']);generations.append(b)
            self.assertEqual((first['status'],first['slot']),('switched','B'))
            self.assertEqual(str(quote(30)['generation_id']),b)
            self.assertEqual(switch(60)['status'],'collecting') # B waits too
            self.assertTrue(repo.owns_collector(origin,session))
            # PP21-style retained A+B must never be admitted as a new trial.
            with self.assertRaises(LifecycleHold):
                repo.enable_collector(origin,session_id=str(uuid.uuid4()),expected_generation_id=b,
                                      max_seconds=6600,rehearsal_anchor=b)
            if occupied:
                quote(45)
                held=switch(60)
                self.assertEqual((held['status'],held['reason'],held['collector_enabled']),
                                 ('held','other_slot_not_retired',False))
                self.assertFalse(repo.owns_collector(origin,session))
                self.assertEqual(repo.generation(anchor)['state'],'sealed')
                with factory() as db:
                    self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child',
                        ('raw.'+a['partition_name'],)).fetchone()['child'])
                return
            # Simulate an independently completed A retirement in this owner-only
            # fixture. The production operator has neither this DDL nor UPDATE.
            with owner() as db:
                db.execute(sql.SQL('DROP TABLE raw.{}').format(sql.Identifier(a['partition_name'])))
                db.execute("UPDATE archive.generations SET state='retired',verified_at=now(),retired_at=now(),"
                           "seal_hash=%s WHERE generation_id=%s",('a'*64,anchor))
            quote(45)
            second=switch(60);fresh=str(second['generation_id']);generations.append(fresh)
            self.assertEqual((second['status'],second['slot']),('switched','A'))
            self.assertEqual(len(set(generations)),3)
            self.assertEqual(str(quote(60)['generation_id']),fresh)
            quote(75)
            self.assertEqual(switch(90)['reason'],'two_leg_rehearsal_complete')
            self.assertTrue(repo.owns_collector(origin,session))
            with factory() as db:
                writer=db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(origin,)).fetchone()
            self.assertEqual(str(writer['collector_session_id']),session)
            self.assertEqual(writer['collector_lease_expires_at'],expires)
            # Explicit OFF/expiry still fences every source after both switches.
            with owner() as db:
                db.execute("UPDATE ops.writer_state SET collector_lease_expires_at=clock_timestamp() WHERE origin_id=%s",(origin,))
            self.assertFalse(repo.owns_collector(origin,session))
            with self.assertRaises(StorageHold):quote(90)
