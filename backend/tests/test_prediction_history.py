"""Saved decision history through local PostgreSQL and a separate restricted archive login."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'),str(Path(__file__).parent)]
from postgres.archive_codec import ArchiveIntegrityError, encoded, sha256, wire
from postgres.cloud_origin_binding import DISPLAY_ORIGIN, DISPLAY_READER
from postgres.config import Settings
from postgres.connection import connect
from postgres.domain import digest
from postgres.history import HistoryError
from postgres.ingestion import generated_events
from postgres.lifecycle import LifecycleRepository, RotationPolicy
from postgres.market_history import Window
from postgres.prediction_history import HostedPredictions, PredictionHistory, configured_archive
from postgres.store import Store
import test_pp_initial_trial_drain as fixture


class NativeSavedForecasts(unittest.TestCase):
    setUpClass = classmethod(fixture.InitialSealNative.setUpClass.__func__)
    tearDownClass = classmethod(fixture.InitialSealNative.tearDownClass.__func__)
    admin = classmethod(fixture.InitialSealNative.admin.__func__)

    def test_two_generations_overlap_then_archive_only_with_exact_readonly_login(self):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        migrations = ROOT/'supabase/migrations'
        with self.admin('postgres') as db:
            for role in ('anon','authenticated','service_role','tradebot_pp_history',DISPLAY_READER):
                db.execute('CREATE ROLE '+role+' LOGIN')
            for name in ('20261116050000_history_v2_private.sql','20261118012340_structured_receipts_v2.sql',
                         '20261119020000_pp_structured_revision_payloads.sql'):
                db.execute((migrations/name).read_text())
            db.execute('GRANT USAGE ON SCHEMA history_v2 TO '+DISPLAY_READER)
            for table in ('predictions','structured_receipts','structured_revision_payloads'):
                db.execute('GRANT SELECT ON history_v2.'+table+' TO '+DISPLAY_READER)
                db.execute('CREATE POLICY test_reader ON history_v2.'+table+' FOR SELECT TO '+DISPLAY_READER+
                           " USING(origin_id="+psycopg.sql.Literal(DISPLAY_ORIGIN).as_string(db)+")")
        settings = Settings(data_mode="pp_live",origin_id=DISPLAY_ORIGIN,dsn=self.app_dsn)
        store = Store(settings)
        def login(*, timeout_seconds):
            return psycopg.connect(host=str(self.socket),dbname='postgres',user=DISPLAY_READER,row_factory=dict_row)
        archive = HostedPredictions(DISPLAY_ORIGIN,login)
        history = PredictionHistory(store,archive)
        now = datetime(2026,11,12,12,tzinfo=timezone.utc)
        window = Window('market-test',now-timedelta(seconds=5),now+timedelta(seconds=10),now+timedelta(seconds=6))
        repo = LifecycleRepository(lambda:connect(self.lifecycle_dsn))
        generation_a = repo.bootstrap(DISPLAY_ORIGIN, now=now-timedelta(minutes=5))['generation_id']
        other_market = 'unrelated-market'
        for market in (window.market_id, other_market):
            seed=dict(generated_events(now)[0],event_id=market,market_id=market)
            seed['payload']=dict(seed['payload'],id=market,slug=market)
            with self.admin() as local, self.admin('postgres') as hosted:
                store._market(local,seed,{'data':seed['payload']},now,generation_a)
                row=local.execute('SELECT * FROM core.markets WHERE origin_id=%s AND market_id=%s',
                                  (DISPLAY_ORIGIN,market)).fetchone()
                hosted.execute('INSERT INTO history_v2.markets SELECT * FROM jsonb_populate_record(NULL::history_v2.markets,%s)',
                               (Jsonb(wire(row)),))
        def add(number, market, instant, created_at, gid):
            pred_id='prediction-'+str(number)
            snapshot='snapshot-'+str(number)
            feature=dict(origin_id=DISPLAY_ORIGIN,market_id=market,snapshot_id=snapshot,as_of=instant,
                         version=number,values_json={},quality_json={},evidence_json={},content_hash='a'*64)
            forecast=dict(origin_id=DISPLAY_ORIGIN,market_id=market,prediction_id=pred_id,snapshot_id=snapshot,
                       model_version='model-'+str(number),as_of=instant,created_at=created_at,seconds_remaining='10.0',
                       probability_up='0.500000000000000001',probability_down='0.499999999999999999',
                       abstain_reason=None,assumptions_json={},payload={},content_hash=digest([number]))
            with self.admin() as local, self.admin('postgres') as hosted:
                for db,schema in ((local,'core'),(hosted,'history_v2')):
                    for table,row in (('feature_snapshots',feature),('predictions',forecast)):
                        identifier=schema+'.'+table
                        db.execute('INSERT INTO '+identifier+' SELECT * FROM jsonb_populate_record(NULL::'+identifier+',%s)',
                                   (Jsonb(wire(row)),))
                record=dict(id=number,origin_id=DISPLAY_ORIGIN,generation_id=gid,entity_type='core.predictions',
                            entity_id=encoded([DISPLAY_ORIGIN,pred_id]).decode(),content_hash=forecast['content_hash'],
                            payload=wire(forecast))
                local.execute('''INSERT INTO ops.outbox
                    (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at,acknowledged_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', (DISPLAY_ORIGIN,gid,record['entity_type'],
                    record['entity_id'],record['content_hash'],Jsonb(wire(forecast)),created_at,created_at))
                hosted.execute('''INSERT INTO history_v2.structured_receipts(origin_id,generation_id,outbox_id,entity_type,
                             entity_id,content_hash,payload_hash,envelope_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                             (DISPLAY_ORIGIN,gid,number,record['entity_type'],record['entity_id'],record['content_hash'],
                              sha256(encoded(record['payload'])),sha256(encoded(record))))
                hosted.execute('INSERT INTO history_v2.structured_revision_payloads VALUES (%s,%s,%s,%s)',
                               (DISPLAY_ORIGIN,gid,number,encoded(record)))
        add(1,window.market_id,now,now,generation_a)
        generation_b = repo.switch_if_due(DISPLAY_ORIGIN,RotationPolicy(1),now=now+timedelta(seconds=1))['generation_id']
        add(2,window.market_id,now+timedelta(seconds=2),now+timedelta(seconds=2),generation_b)
        add(3,window.market_id,now+timedelta(seconds=2),now+timedelta(seconds=3),generation_b)
        add(4,window.market_id,now+timedelta(seconds=4),now+timedelta(seconds=8),generation_b) # saved too late
        add(5,other_market,now+timedelta(seconds=2),now+timedelta(seconds=2),generation_b)
        add(6,window.market_id,now+timedelta(seconds=8),now+timedelta(seconds=8),generation_b)
        local=history.read(window,None,2)
        self.assertEqual([r['id'] for r in local['items']],['prediction-3','prediction-2'])
        self.assertEqual(local['coverage']['tiers'],['local_postgres'])
        with self.assertRaises(HistoryError):
            history.read(window,local['next_cursor'],2,True)
        joined=history.read(window,None,2,True)
        self.assertEqual(joined['items'],local['items'])
        self.assertEqual(joined['coverage']['tiers'],['local_postgres','authenticated_archive'])
        self.assertCountEqual(joined['coverage']['generation_ids'],[generation_a,generation_b])
        self.assertEqual(joined['items'][0]['probability_up'],'0.500000000000000001')
        self.assertTrue(joined['coverage']['complete'])
        self.assertEqual([r['id'] for r in history.read(window,joined['next_cursor'],2,True)['items']],['prediction-1'])
        with self.assertRaises(HistoryError):
            history.read(Window(other_market,window.start,window.end,window.as_of),joined['next_cursor'],2,True)
        # Raw retirement leaves immutable predictions available locally. A historical
        # interval subsequently merges that projection with authenticated cold rows.
        with self.admin() as db:
            db.execute("UPDATE archive.generations SET state='retired',verified_at=sealed_at,"
                       "retired_at=sealed_at,seal_count=0,seal_hash=%s WHERE generation_id=%s",
                       ('0'*64,generation_a))
        self.assertEqual(history.read(window,None,2)['coverage']['tiers'],
                         ['local_postgres','authenticated_archive'])
        with self.admin() as db: # Isolated fixture only: simulate local projection eviction.
            db.execute('DELETE FROM core.predictions WHERE origin_id=%s',(DISPLAY_ORIGIN,))
        cold=history.read(window,None,500,True)
        self.assertEqual([r['id'] for r in cold['items']],['prediction-3','prediction-2','prediction-1'])
        self.assertTrue(all(r['tier']=='authenticated_archive' for r in cold['items']))
        self.assertIsNone(cold['next_cursor'])
        from postgres.api import create_app
        import httpx
        async def exercise_api():
            with patch('postgres.prediction_history.configured_archive',return_value=archive):
                app=create_app(settings,store=store,refresh=False)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
                params=dict(market_id=window.market_id,start=window.start.isoformat(),end=window.end.isoformat(),
                            as_of=window.as_of.isoformat(),limit=2)
                response=await client.get('/history/market-predictions',params=params)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['items'],cold['items'][:2])
                params['cursor']=response.json()['next_cursor']
                params['market_id']=other_market
                self.assertEqual((await client.get('/history/market-predictions',params=params)).status_code,422)
        asyncio.run(exercise_api())
        unavailable=PredictionHistory(store).read(window,None,500,True)
        self.assertFalse(unavailable['coverage']['complete'])
        self.assertIn('archive_unavailable',unavailable['coverage']['reasons'])
        with self.admin('postgres') as db:
            db.execute("DELETE FROM history_v2.predictions WHERE prediction_id='prediction-2'")
        gaps=history.read(window,None,500)
        self.assertIn('saved_prediction_missing',gaps['coverage']['reasons'])
        self.assertIn(generation_b,gaps['coverage']['missing_generations'])
        with self.admin('postgres') as db:
            db.execute("UPDATE history_v2.predictions SET probability_up=.01 WHERE prediction_id='prediction-3'")
        with self.assertRaises(ArchiveIntegrityError):
            history.read(window,None,500,True)

    def test_runtime_never_uses_a_writer_credential(self):
        settings=Settings(environment='preprod',data_mode='pp_live',origin_id=DISPLAY_ORIGIN)
        self.assertIsNone(configured_archive(settings,{}))
        with patch('postgres.prediction_history.PPHistoryConnectionFactory') as factory:
            result=configured_archive(settings,{'TRADEBOT_PP_PREDICTION_HISTORY':'true'})
            self.assertEqual(result.role,DISPLAY_READER)
            self.assertTrue(factory.call_args.kwargs['reader'])
        with self.assertRaises(ValueError):
            HostedPredictions('pp-live-pp',lambda **kwargs: self.fail('legacy role contacted'))
        with self.assertRaises(ValueError):
            configured_archive(Settings(),{'TRADEBOT_PP_PREDICTION_HISTORY':'true'})
