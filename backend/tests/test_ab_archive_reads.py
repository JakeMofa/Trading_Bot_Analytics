import sys, unittest
from pathlib import Path
from types import SimpleNamespace
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from archive_reads import BoundedArchiveReads, ArchiveHold
from cloud_memory import SupabaseHTTP

class Tests(unittest.TestCase):
    def adapter(self, statuses, deadline=20):
        self.now=0.; self.calls=[]; self.sleeps=[]
        def handler(request):
            self.calls.append(request)
            result=statuses[len(self.calls)-1]
            if isinstance(result, Exception): raise result
            code, headers = result if isinstance(result, tuple) else (result,{})
            return httpx.Response(code,headers=headers,content=b'original evidence')
        def sleep(delay): self.sleeps.append(delay); self.now+=delay
        cloud=SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated-only'),client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(cloud.close)
        return BoundedArchiveReads(cloud,deadline,clock=lambda:self.now,sleep=sleep,jitter=lambda:0)
    def test_transient_gets_same_identity_and_original_deadline(self):
        a=self.adapter([429,503,200]);self.assertEqual(a.download_bytes('private','a/b'),b'original evidence')
        self.assertEqual(self.sleeps,[1,2]);self.assertEqual(len({str(r.url) for r in self.calls}),1)
        self.assertTrue(all(r.method=='GET' and r.headers['Cache-Control']=='no-store' for r in self.calls))
        self.assertEqual([r.extensions['timeout']['read'] for r in self.calls],[20,19,17])
    def test_network_error_safe_retry(self):
        a=self.adapter([httpx.ConnectError('generated'),200]);a.download_bytes('b','p');self.assertEqual(len(self.calls),2)
    def test_permanent_auth_missing_malformed_no_retry(self):
        for code in [400,401,403,404]:
            a=self.adapter([code])
            with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
            self.assertEqual(len(self.calls),1);self.assertEqual(self.sleeps,[])
    def test_three_attempt_bound(self):
        a=self.adapter([500,500,500])
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
        self.assertEqual(len(self.calls),3)
    def test_retry_after_and_insufficient_budget(self):
        a=self.adapter([(429,{'Retry-After':'10'}),200],deadline=5)
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
        self.assertEqual(len(self.calls),1);self.assertEqual(self.sleeps,[])
    def test_expired_or_late_response_cannot_succeed(self):
        a=self.adapter([200],deadline=0)
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
        self.assertEqual(self.calls,[])
        a=self.adapter([200]);a.cloud.client.event_hooks={'response':[lambda response:setattr(self,'now',21)]}
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
    def test_no_upload_or_manifest_retry_interface(self):
        a=self.adapter([200]);self.assertFalse(hasattr(a,'upload_bytes'));self.assertFalse(hasattr(a,'upsert'))
