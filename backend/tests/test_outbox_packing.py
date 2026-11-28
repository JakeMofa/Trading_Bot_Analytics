"""Exact page admission on PostgreSQL 17, including legacy JSONB and retry boundaries."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'),str(Path(__file__).parent)]
from postgres.archive_codec import ArchiveLimit, encoded
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

    def test_sql_json_spelling_expansion_does_not_charge_transport(self):
        first=self.put(1,{'before':'Ω'})
        second=self.put(2,{'tiny':[1e-300]*250,'quote':'x'*8100+'🐍\\ " ,: \t'})
        suffix=self.put(3,{'suffix':True})
        fits=len(encoded([envelope(first),envelope(second)]))
        self.assertEqual(self.repo.outbox(self.generation,50,fits),[first,second])
        self.assertEqual(self.repo.outbox(self.generation,50,fits-1),[first])
        self.repo.acknowledge(self.generation,[envelope(first)])
        self.assertEqual(self.repo.outbox(self.generation,50,fits),[second,suffix])
