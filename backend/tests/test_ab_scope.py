import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy
from fresh_b_scope import inventory
class ScopeTests(unittest.TestCase):
    def test_exact_scope_and_no_authority(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            p=Path(root)/'generated-legacy.db';legacy(p);result=inventory(p)
            self.assertEqual(result['status'],'PASS_BOUNDED_INPUT_CENSUS')
            self.assertGreater(result['structured_counts']['candles'],0)
            self.assertGreater(result['selected_observations'],0)
            self.assertFalse(result['production_authority'])
    def test_bound_and_missing_protected_input_fail(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            p=Path(root)/'generated-legacy.db';legacy(p)
            with self.assertRaisesRegex(ValueError,'row scope'):inventory(p,row_limit=1)
            with closing(sqlite3.connect(p)) as db,db:db.execute('DELETE FROM observations WHERE id=41')
            with self.assertRaisesRegex(ValueError,'missing selected'):inventory(p)

    def test_persistent_ledger_cap_stops_new_writes_but_keeps_commits_readable(self):
        from test_ab_application import ApplicationStore,T,iso,Stop,timedelta
        from contextlib import closing
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path=Path(root)/'generated-legacy.db';legacy(path)
            store=ApplicationStore(root,path,routing=True,fresh_b=True)
            try:
                self.assertEqual(store.protocol.fresh_event_limit,100000)
                store.protocol.fresh_event_limit=2
                with closing(store.connection()) as db:
                    for i in range(2):db.save_observation('m',iso(T+timedelta(seconds=i+2)),'book',{'i':i},iso(T))
                    with self.assertRaisesRegex(Stop,'ledger limit'):db.save_observation('m',iso(T+timedelta(seconds=4)),'book',{},iso(T))
                self.assertEqual(store.protocol.core.execute("SELECT count(*) FROM events WHERE status='committed'").fetchone()[0],2)
                self.assertEqual(store.protocol.core.execute("SELECT count(*) FROM events WHERE status='pending'").fetchone()[0],0)
            finally:store.close()
