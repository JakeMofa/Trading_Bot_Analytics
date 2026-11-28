import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Budget, DeploymentHold
from outbox_inventory import CLEANUP_SECONDS, outbox_digests, work_time


class ScriptedSnapshot:
    def __init__(self, manifest, descriptors, hashes):
        self.manifest = manifest
        self.descriptors = list(descriptors)
        self.hashes = iter(hashes)
        self.statements = []

    def __call__(self, sql):
        self.statements.append(sql)
        if sql.startswith('FETCH FORWARD 1 '):
            return [self.manifest]
        if sql.startswith('FETCH FORWARD 4 '):
            batch, self.descriptors = self.descriptors[:4], self.descriptors[4:]
            combined=[]
            for row in batch:
                if not isinstance(row,list):
                    combined.append(row)
                    continue
                result=next(self.hashes,None)
                combined.append(row+result if isinstance(result,list) else row)
            return combined
        if sql.startswith(('BEGIN ', 'DECLARE ', 'CLOSE ')):
            return []
        raise AssertionError(sql)


class CursorProtocolTests(unittest.TestCase):
    origins = {'generated-pp', 'pp-live-pp'}

    def fold(self, manifest, descriptors=(), hashes=()):
        return outbox_digests(ScriptedSnapshot(manifest, descriptors, hashes), self.origins)

    def test_counts_and_order_match_complete_signed_id_groups(self):
        a, b = sorted(self.origins)
        manifest = [[a,2,3],[b,1,1]]
        descriptors = [[a,-1,-1024,-1024,1],[a,0,-1,1,2],[b,0,4,4,1]]
        channel = ScriptedSnapshot(manifest, descriptors, [[1,1,'a'*64],[2,0,'b'*64],[1,1,'c'*64]])
        self.assertEqual(outbox_digests(channel, self.origins), {
            a:dict(count=3,pending=1,digest=hashlib.sha256(('a'*64+'b'*64).encode()).hexdigest()),
            b:dict(count=1,pending=1,digest=hashlib.sha256(('c'*64).encode()).hexdigest())})
        self.assertEqual(sum(s.startswith('BEGIN ') for s in channel.statements),1)
        self.assertEqual(sum(s.startswith('DECLARE ') for s in channel.statements),1)
        self.assertTrue(all(s.startswith(('BEGIN ','DECLARE ','FETCH ','CLOSE ')) for s in channel.statements))
        self.assertEqual(channel.statements[-1],'CLOSE outbox_pages; COMMIT;')

    def test_empty_or_unapproved_catalog(self):
        self.assertEqual(self.fold([]),{})
        for manifest in ([['third-origin',1,1]], [[None,1,1]], [['generated-pp',1,1]]*2,
                         [['generated-pp',1,1],['third-origin',1,1]]):
            channel = ScriptedSnapshot(manifest, (), ())
            with self.subTest(manifest=manifest), self.assertRaisesRegex(DeploymentHold,'unexpected_outbox_origin'):
                outbox_digests(channel,self.origins)
            self.assertFalse(any(s.startswith('WITH hashes ') for s in channel.statements))

    def test_missing_reordered_or_corrupt_descriptors_are_rejected(self):
        a,b = sorted(self.origins)
        header = [[a,2,2],[b,1,1]]
        pages = [[a,1,1024,1024,1],[a,2,2048,2048,1],[b,3,3072,3072,1]]
        values = [[1,0,'a'*64]]*4
        for altered in (pages[:1], pages[:2], list(reversed(pages)), [pages[0],pages[0],pages[2]],
                        [[a,1,1023,1024,1],*pages[1:]], [*pages,pages[-1]], [*pages,None]):
            with self.subTest(altered=altered),self.assertRaises(DeploymentHold):
                self.fold(header,altered,values)
        for broken in ([[a,2,3],[b,1,1]], [[a,0,0]], [[a,True,1]]):
            with self.subTest(header=broken),self.assertRaises(DeploymentHold):
                self.fold(broken,pages,values)
        for bad_row in ([1,2,'0'*64],[True,0,'0'*64],[1,0,'0'*63],['1',0,'0'*64],[1,0,'A'*64]):
            with self.subTest(row=bad_row),self.assertRaises(DeploymentHold):
                self.fold(header,pages,[bad_row])
        with self.assertRaises(DeploymentHold):
            self.fold([], [None])

    def test_pending_cap_applies_to_each_origin(self):
        a,b=sorted(self.origins)
        pages=[[x,i,i*1024,i*1024+1023,1000] for x in (a,b) for i in range(10)]
        self.assertEqual(self.fold([[a,10,10000],[b,10,10000]],pages,[[1000,1000,'0'*64]]*20)[b]['pending'],10000)
        with self.assertRaisesRegex(DeploymentHold,'outbox_inventory_invalid'):
            self.fold([[a,11,11000]],[*pages[:10],[a,10,10240,11263,1000]],[[1000,1000,'0'*64]]*11)

    def test_per_exchange_and_cleanup_headroom_share_the_original_global_deadline(self):
        elapsed = 0
        b=Budget(600,lambda: elapsed)
        self.assertEqual(work_time(b),20)
        elapsed=600-CLEANUP_SECONDS-3
        self.assertEqual(work_time(b),3)
        elapsed+=3
        with self.assertRaisesRegex(DeploymentHold,'deadline_exceeded'):
            work_time(b)
