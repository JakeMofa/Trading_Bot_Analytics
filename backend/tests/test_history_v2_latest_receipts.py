"""Exact opt-in never silently enables an unindexed latest lookup."""
import unittest
from unittest.mock import Mock
from contextlib import nullcontext
from postgres.archive_codec import ArchiveIntegrityError
from postgres.history_v2_latest_receipts import indexed_latest_requested,latest_receipts,RANK_SQL,checked_index


class LatestReceiptTests(unittest.TestCase):
    def test_default_off_and_exact_pp_selection(self):
        self.assertFalse(indexed_latest_requested({}))
        self.assertTrue(indexed_latest_requested({'TRADEBOT_PP_INDEXED_LATEST_RECEIPTS':'true'}))
        for value in ('TRUE','1','',True):
            with self.assertRaises(ArchiveIntegrityError):
                indexed_latest_requested({'TRADEBOT_PP_INDEXED_LATEST_RECEIPTS':value})

    def test_rank_default_has_no_index_probe(self):
        db=Mock()
        db.execute.return_value.fetchall.return_value=[]
        self.assertEqual(latest_receipts(db,'pp-live-pp',[('core.markets','key')]),[])
        self.assertEqual(db.execute.call_count,1)
        self.assertEqual(db.execute.call_args.args[0],RANK_SQL)

    def test_missing_invalid_or_unready_abi_never_queues_data_query(self):
        for row in (None,{'valid':False},{'valid':None}):
            db=Mock()
            db.pipeline.return_value=nullcontext()
            db.execute.return_value.fetchone.return_value=row
            with self.assertRaises(ArchiveIntegrityError):
                latest_receipts(db,'pp-live-pp',[('core.markets','key')],indexed=True)
            self.assertEqual(db.execute.call_count,2) # SET LOCAL + catalog, no lateral

    def test_scoped_index_token_cannot_cross_connections(self):
        db,other=Mock(),Mock()
        token=checked_index(db,True)
        with self.assertRaises(ArchiveIntegrityError):
            latest_receipts(other,'pp-live-pp',[('core.markets','key')],indexed=True,_checked=token)
        other.execute.assert_not_called()
