"""Exact page admission on PostgreSQL 17, including legacy JSONB and retry boundaries."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'),str(Path(__file__).parent)]
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded
from postgres.connection import connect
from postgres.lifecycle import LifecycleRepository
from postgres.outbox_packing import envelope
import test_pp_initial_trial_drain as fixture


class ExactOutboxPage(unittest.TestCase):
    setUpClass = classmethod(fixture.InitialSealNative.setUpClass.__func__)
    tearDownClass = classmethod(fixture.InitialSealNative.tearDownClass.__func__)
    admin = classmethod(fixture.InitialSealNative.admin.__func__)

    def setUp(self):
        self.repo=LifecycleRepository(lambda:connect(self.lifecycle_dsn))
        self.origin='packing-'+self._testMethodName
        self.generation=self.repo.bootstrap(self.origin)['generation_id']

    def put(self, key, payload):
        from psycopg.types.json import Jsonb
        with self.admin() as db:
            return db.execute("""INSERT INTO ops.outbox
                (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                VALUES(%s,%s,'core.predictions',%s,%s,%s,now()) RETURNING *""",
                (self.origin,self.generation,str(key),'a'*64,Jsonb(payload))).fetchone()

    def test_exact_bytes_ids_full_rows_and_retry_through_ack(self):
        rows=[self.put(i,{'raw':'x'*4000,'unicode':'𝄞, " : 中文 ☀'}) for i in range(57)]
        fits=len(encoded([envelope(r) for r in rows[:30]]))
        self.assertEqual(self.repo.outbox(self.generation,50,fits),rows[:30])
        self.assertEqual(self.repo.outbox(self.generation,50,fits-1),rows[:29])
        self.assertEqual(self.repo.outbox(self.generation,50,262144),rows[:50])
        self.assertEqual(self.repo.outbox(self.generation,50,fits),rows[:30])
        self.repo.acknowledge(self.generation,[envelope(r) for r in rows[:30]])
        self.assertEqual(self.repo.outbox(self.generation,50,fits),rows[30:])

    def test_cumulative_verified_ack_counter_ignores_retries_and_rolls_back(self):
        from unittest.mock import patch
        from postgres import quote_ack_counter
        self.origin += '-tracked'
        tracked = patch.object(quote_ack_counter, 'WATCH_ORIGIN', self.origin)
        tracked.start()
        self.addCleanup(tracked.stop)
        self.generation=self.repo.bootstrap(self.origin)['generation_id']
        def count():
            with self.admin() as db:
                return db.execute("""SELECT cursor->>'rows' AS n FROM archive.checkpoints
                    WHERE origin_id=%s AND generation_id=%s AND consumer='structured:verified-acks-v1'""",
                    (self.origin,self.generation)).fetchone()['n']
        rows=[envelope(self.put(key,{'value':key})) for key in ('one','two','three')]
        self.assertEqual(count(),'0')
        self.repo.acknowledge(self.generation,rows[:1])
        self.repo.acknowledge(self.generation,rows[:2])
        self.assertEqual(count(),'2')
        with self.assertRaises(ArchiveIntegrityError):
            self.repo.acknowledge(self.generation,[rows[2],dict(rows[0],content_hash='f'*64)])
        self.assertEqual(count(),'2')
        self.assertEqual(self.repo.outbox(self.generation,50,262144)[0]['id'],rows[2]['id'])
        self.repo.acknowledge(self.generation,rows)
        self.assertEqual(count(),'3')

    def test_watch_quote_counter_scope_restart_retry_and_other_generation(self):
        from types import SimpleNamespace
        from postgres.quote_ack_counter import WATCH_ORIGIN, register
        from postgres.store import Store
        self.origin=WATCH_ORIGIN
        self.generation=self.repo.bootstrap(self.origin)['generation_id']
        session=str(uuid.uuid4())
        store=Store(SimpleNamespace(environment='preprod',origin_id=self.origin,dsn=self.app_dsn),producer_session_id=session)
        with self.admin() as db:
            db.execute("""UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,
                   collector_lease_expires_at=now()+interval '10 minutes' WHERE origin_id=%s""",(session,self.origin))
        def quote(key):
            row=self.put(key,{'kind':'quote','payload':{'provenance':{'feed':'polymarket_us_websocket'}}})
            with self.admin() as db:
                return envelope(db.execute("""UPDATE ops.outbox SET entity_type='core.protected_evidence'
                    WHERE id=%s RETURNING *""",(row['id'],)).fetchone())
        old=quote('old')
        first=register(store)
        received=quote('current')
        unrelated=envelope(self.put('wrong-kind',{'kind':'quote'}))
        self.assertEqual(store.archived_quote_count(first),0)
        self.repo.acknowledge(self.generation,[old,received,unrelated])
        self.repo.acknowledge(self.generation,[received])
        self.assertEqual(store.archived_quote_count(first),1)
        pending_before_restart=quote('previous-pending')
        restarted=register(store)
        self.assertIsNone(store.archived_quote_count(first))
        self.assertEqual(store.archived_quote_count(restarted),0)
        self.repo.acknowledge(self.generation,[pending_before_restart])
        self.assertEqual(store.archived_quote_count(restarted),0)
        with self.repo.transaction() as db:
            self.generation=self.repo._create(db,self.origin,'B',datetime.now(timezone.utc))['generation_id']
        another=quote('B-after-restart')
        self.repo.acknowledge(self.generation,[another])
        self.assertEqual(store.archived_quote_count(restarted),1)

    def test_exact_single_boundary_and_oversized_head_preservation(self):
        row=self.put('large',{'pad':'x'*160_000,'escapes':'"\\\t\n [] , :é','tiny':1e-307})
        later=self.put('tail',{'small':True})
        single=len(encoded([envelope(row)]))
        self.assertEqual(self.repo.outbox(self.generation,50,single),[row])
        with self.assertRaisesRegex(ArchiveLimit,'single structured envelope'):
            self.repo.outbox(self.generation,50,single-1)
        with self.admin() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM ops.outbox WHERE generation_id=%s AND "
                "acknowledged_at IS NULL",(self.generation,)).fetchone()['n'],2)
        self.assertEqual(self.repo.outbox(self.generation,50,262144),[row,later])

    def test_production_ceiling_counts_array_bytes(self):
        limit=256*1024
        row=self.put('exact-256k',{'pad':''})
        fit=limit-len(encoded([envelope(row)]))
        from psycopg.types.json import Jsonb
        with self.admin() as db:
            db.execute('UPDATE ops.outbox SET payload=%s WHERE id=%s',(Jsonb({'pad':'x'*fit}),row['id']))
        self.assertEqual(len(encoded([envelope(r) for r in self.repo.outbox(self.generation,50,limit)])),limit)
        with self.admin() as db:
            db.execute('UPDATE ops.outbox SET payload=%s WHERE id=%s',(Jsonb({'pad':'x'*(fit+1)}),row['id']))
        with self.assertRaisesRegex(ArchiveLimit,'single structured envelope'):
            self.repo.outbox(self.generation,50,limit)
        with self.admin() as db:
            self.assertIsNone(db.execute('SELECT acknowledged_at FROM ops.outbox WHERE id=%s',
                                         (row['id'],)).fetchone()['acknowledged_at'])

    def test_sql_json_spelling_expansion_does_not_charge_transport(self):
        first=self.put(1,{'before':'Ω'})
        second=self.put(2,{'tiny':[1e-300]*250,'quote':'x'*8100+'🐍\\ " ,: \t'})
        suffix=self.put(3,{'suffix':True})
        fits=len(encoded([envelope(first),envelope(second)]))
        self.assertEqual(self.repo.outbox(self.generation,50,fits),[first,second])
        self.assertEqual(self.repo.outbox(self.generation,50,fits-1),[first])
        self.repo.acknowledge(self.generation,[envelope(first)])
        self.assertEqual(self.repo.outbox(self.generation,50,fits),[second,suffix])
