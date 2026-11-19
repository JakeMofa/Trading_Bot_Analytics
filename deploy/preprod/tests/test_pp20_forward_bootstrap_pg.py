"""Execute forward-preservation SQL with an actual authenticated PG reader."""
import json
import os
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pp20_forward_bootstrap as f


@unittest.skipUnless(os.environ.get('TRADEBOT_TEST_READER_DSN'),'isolated PostgreSQL reader required')
class ForwardPreservationSQL(unittest.TestCase):
    def test_actual_reader_fingerprints_cover_original_rows_without_ddl(self):
        import psycopg
        dsn=os.environ['TRADEBOT_TEST_READER_DSN']
        with psycopg.connect(dsn,connect_timeout=5,options='-c default_transaction_read_only=on') as db:
            self.assertEqual(db.execute("SELECT current_user,current_setting('transaction_read_only')").fetchone(),
                             ('tradebot_reader','on'))
            through,cutoff=db.execute("SELECT coalesce((SELECT max(id) FROM ops.outbox WHERE origin_id='generated-pp'),1),clock_timestamp()::text").fetchone()
            expected_raw=db.execute('SELECT count(*) FROM raw.events WHERE received_at<=%s',(cutoff,)).fetchone()[0]
            expected_generated=db.execute("SELECT count(*) FROM ops.outbox WHERE origin_id='generated-pp' AND id<=%s",(through,)).fetchone()[0]
            class ReaderActions:
                _json=staticmethod(json.loads)
                def _reader_sql(self,budget,query):return json.dumps(db.execute(query).fetchone()[0])
            state=f.database_state(ReaderActions(),None)
            self.assertEqual(state['versions'],[1,2,3,4])
            self.assertIn('raw_cutoff',state)
            before=f.preserved_state(ReaderActions(),None,through,cutoff)
            self.assertEqual(before,f.preserved_state(ReaderActions(),None,through,cutoff))
            self.assertEqual(before['original_raw']['count'],expected_raw)
            self.assertEqual(before['original_generated_outbox']['count'],expected_generated)
            self.assertIn('archive.generations',before)
            self.assertIn('core.outcomes',before)
            for value in before.values():
                self.assertIs(type(value['count']),int)
                self.assertTrue(re.fullmatch('[0-9a-f]{64}',value['digest']))


if __name__=='__main__':unittest.main()
