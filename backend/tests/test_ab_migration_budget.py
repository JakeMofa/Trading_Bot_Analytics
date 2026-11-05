import sys
import time
from pathlib import Path
import unittest
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from migration_budget import MigrationBudget


class BudgetTests(unittest.TestCase):
    def test_default_scope_and_explicit_rows_do_not_raise_byte_or_time_limits(self):
        b=MigrationBudget(deadline=time.monotonic()+10)
        self.assertEqual(b.row_limit,10000)
        self.assertEqual(MigrationBudget(row_limit=60000,deadline=time.monotonic()+10).byte_limit,128*1024**2)
        for args in ({'row_limit':100001},{'byte_limit':128*1024**2+1},{'row_limit':True}):
            with self.subTest(args=args),self.assertRaises(ValueError):MigrationBudget(deadline=time.monotonic()+10,**args)
        with self.assertRaises(ValueError):MigrationBudget(deadline=time.monotonic()+171)
        with self.assertRaises(ValueError):MigrationBudget(deadline=time.monotonic()-1)

    def test_expired_original_deadline_is_not_reset(self):
        from unittest.mock import patch
        b=MigrationBudget(deadline=time.monotonic()+10)
        with patch('migration_budget.time.monotonic',return_value=b.deadline):
            with self.assertRaises(TimeoutError):b.check()

    def test_deadline_before_import_commit_rolls_back_and_can_recover(self):
        import tempfile
        import sqlite3
        from unittest.mock import patch
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from test_ab_application import legacy,ApplicationStore
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            path=Path(folder)/'generated-legacy.db';legacy(path)
            budget=MigrationBudget(deadline=time.monotonic()+10)
            original=budget.check
            expired=[False]
            def check():
                if expired[0]:raise TimeoutError('injected original deadline')
                original()
            def fault(phase):
                if phase=='migration_before_commit':expired[0]=True
            with patch.object(MigrationBudget,'check',side_effect=check):
                with self.assertRaisesRegex(TimeoutError,'original deadline'):
                    ApplicationStore(folder,path,routing=True,migration_budget=budget,fault=fault)
            with closing(sqlite3.connect(Path(folder)/'core.db')) as db:
                self.assertFalse(db.execute("SELECT 1 FROM ab_migration_state WHERE status='complete'").fetchone())
            store=ApplicationStore(folder,path,routing=True)
            try:self.assertEqual(store.protocol.core.native.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:store.close()

    def test_concurrent_unfenced_legacy_change_blocks_import_commit(self):
        import tempfile
        import sqlite3
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from test_ab_application import legacy,ApplicationStore,Stop
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            path=Path(folder)/'generated-legacy.db';legacy(path)
            def fault(phase):
                if phase=='migration_before_commit':
                    with closing(sqlite3.connect(path)) as writer, writer:
                        writer.execute("UPDATE observations SET payload='{}' WHERE id=41")
            with self.assertRaisesRegex(Stop,'legacy changed during migration'):
                ApplicationStore(folder,path,routing=True,fault=fault)
            with closing(sqlite3.connect(Path(folder)/'core.db')) as db:
                self.assertFalse(db.execute("SELECT 1 FROM ab_migration_state WHERE status='complete'").fetchone())
