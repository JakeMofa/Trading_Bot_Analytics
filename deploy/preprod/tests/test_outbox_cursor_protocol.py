import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Budget, DeploymentHold
from outbox_inventory import CLEANUP_SECONDS, origin_digest, work_time


class CursorProtocolTests(unittest.TestCase):
    def fold(self, descriptors, results):
        batches = iter(descriptors)
        hashes = iter(results)
        def exchange(sql):
            if sql.startswith('FETCH '):
                return next(batches)
            if sql.startswith('WITH hashes '):
                return next(hashes)
            return []
        return origin_digest(exchange,'generated-pp')

    def test_counts_and_order_match_complete_signed_id_groups(self):
        pages=[[-1,-1024,-1024,1,2,3],[0,-1,1,2,2,3]]
        rows=[[[1,1,'a'*64]],[[2,0,'b'*64]]]
        self.assertEqual(self.fold([pages,[]],rows),{
            'count':3,'pending':1,'digest':hashlib.sha256(('a'*64+'b'*64).encode()).hexdigest()
        })

    def test_missing_reordered_or_corrupt_descriptors_are_rejected(self):
        pages=[[1,1024,1024,1,2,2],[2,2048,2048,1,2,2]]
        rows=[[[1,0,'a'*64]],[[1,0,'b'*64]]]
        for altered in ([pages[0]],list(reversed(pages)),[pages[0],pages[0]],
                        [[1,1023,1024,1,2,2],pages[1]], [pages[0],[2,2048,2048,1,3,4]]):
            with self.subTest(altered=altered),self.assertRaises(DeploymentHold):
                self.fold([altered,[]],rows)
        for bad_row in ([1,2,'0'*64],[True,0,'0'*64],[1,0,'0'*63],['1',0,'0'*64],[1,0,'A'*64]):
            with self.subTest(row=bad_row),self.assertRaises(DeploymentHold):
                self.fold([pages,[]],[[bad_row]])

    def test_per_exchange_and_cleanup_headroom_share_the_original_global_deadline(self):
        elapsed = 0
        b=Budget(600,lambda: elapsed)
        self.assertEqual(work_time(b),20)
        elapsed=600-CLEANUP_SECONDS-3
        self.assertEqual(work_time(b),3)
        elapsed+=3
        with self.assertRaisesRegex(DeploymentHold,'deadline_exceeded'):
            work_time(b)
