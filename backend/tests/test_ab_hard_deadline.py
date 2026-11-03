import os,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from archive_reads import HardArchiveReads,ArchiveHold
from cloud_memory import SupabaseHTTP
class SlowBody(httpx.SyncByteStream):
    def __iter__(self):
        while True:
            time.sleep(.02);yield b'x'
class Tests(unittest.TestCase):
    def cloud(self,handler):
        c=SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated'),client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(c.close);return c
    def check_reaped(self,a):
        with self.assertRaises(ChildProcessError):os.waitpid(a.last_child_pid,os.WNOHANG)
    def test_trickled_body_is_killed_and_reaped(self):
        a=HardArchiveReads(self.cloud(lambda req:httpx.Response(200,stream=SlowBody())),time.monotonic()+.15)
        before=time.monotonic()
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
        self.assertLess(time.monotonic()-before,.8);self.check_reaped(a)
    def test_backoff_and_all_retries_share_hard_deadline(self):
        a=HardArchiveReads(self.cloud(lambda req:httpx.Response(503)),time.monotonic()+.1)
        with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
        self.check_reaped(a)
    def test_success_and_max_response_bound(self):
        for cap,success in [(10,True),(2,False)]:
            a=HardArchiveReads(self.cloud(lambda req:httpx.Response(200,content=b'123')),time.monotonic()+1,cap)
            if success:self.assertEqual(a.download_bytes('b','p'),b'123')
            else:
                with self.assertRaises(ArchiveHold):a.download_bytes('b','p')
            self.check_reaped(a)
    def test_checksum_response_processing_is_inside_killable_deadline(self):
        from compatible_cloud import CompatibleCloud
        from unittest.mock import patch
        cloud=self.cloud(lambda req:httpx.Response(200,content=b'123'))
        adapter=CompatibleCloud(cloud,time.monotonic()+.15)
        def stalled_hash(*args,**kwargs):
            time.sleep(2);raise AssertionError('processing escaped deadline')
        before=time.monotonic()
        with patch('compatible_cloud.hashlib.sha256',side_effect=stalled_hash):
            with self.assertRaises(ArchiveHold):adapter.verify_object('b','p','irrelevant',3)
        self.assertLess(time.monotonic()-before,.8)
