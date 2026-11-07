"""Synthetic authenticated HTTP readback, no live cloud or deletion gate change."""
import json, multiprocessing, tempfile, time, unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote
import httpx
from test_ab_application import ApplicationStore, legacy, T, timedelta, iso
from application_store import RetirementProtocol
from cloud_memory import SupabaseHTTP
from compatible_cloud import CompatibleCloud
from archive_reads import ArchiveHold
from raw_generations import MemoryArchive
from background_verification import verify_phase


class Tests(unittest.TestCase):
    def fixture(self,root):
        path=Path(root)/'generated-legacy.db';legacy(path)
        store=ApplicationStore(root,path,routing=True,fresh_b=True)
        with closing(store.connection()) as db:
            for i in range(12):
                at=T+timedelta(seconds=i+1)
                db.save_stream_event(dict(source='coinbase',event_id='phase-'+str(i),received_at=iso(at),source_time=iso(at),price='123.00000000001',size='1',side='buy',payload='{}'))
        gid=store.protocol.active()['id'];now=T+timedelta(hours=73)
        store.rotation_tick(now);remote=MemoryArchive()
        for _ in range(12):store.protocol.archive_hour(remote,now,limit=1,sealed_generation=gid)
        store.close()
        return path,gid,now,remote

    def factory(self,remote,mode='normal'):
        def create(deadline):
            def handle(request):
                self.assertEqual(request.method,'GET')
                self.assertIn('/object/authenticated/market-raw/',request.url.path)
                self.assertEqual(request.headers['Authorization'],'Bearer generated-only')
                if mode=='hang':time.sleep(2)
                else:time.sleep(.015)
                path=unquote(request.url.path.split('/market-raw/',1)[1])
                body=remote.objects[path]
                if mode=='corrupt':body=b'corrupt'
                return httpx.Response(200,content=body)
            client=SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated-only'),client=httpx.Client(transport=httpx.MockTransport(handle)))
            return CompatibleCloud(client,deadline)
        return create

    def test_full_phase_more_than_cycle_budget_while_other_slot_acknowledges(self):
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            path,gid,now,remote=self.fixture(root)
            ctx=multiprocessing.get_context('fork');ready=ctx.Event();stop=ctx.Event()
            count=ctx.Value('i',0);delay=ctx.Value('d',0);heartbeat=ctx.Value('d',0);peak=ctx.Value('q',0)
            def collect():
                store=ApplicationStore(root,path,routing=True,fresh_b=True)
                try:
                    with closing(store.connection()) as db:
                        last=time.monotonic();ready.set()
                        for i in range(80):
                            if stop.is_set():break
                            before=time.monotonic();at=now+timedelta(seconds=i+1)
                            db.save_observation('m',iso(at),'book',{'new':i},iso(at))
                            delay.value=max(delay.value,time.monotonic()-before)
                            heartbeat.value=max(heartbeat.value,time.monotonic()-last)
                            count.value+=1
                            peak.value=max(peak.value,sum(p.stat().st_size for p in Path(root).iterdir() if p.is_file()))
                            time.sleep(.01);last=before
                finally:store.close()
            writer=ctx.Process(target=collect);writer.start()
            try:
                self.assertTrue(ready.wait(5));before=count.value
                report=verify_phase(root,path,gid,self.factory(remote),now,deadline=time.monotonic()+10)
                self.assertGreater(count.value,before)
            finally:
                stop.set();writer.join(5)
                if writer.is_alive():writer.kill();writer.join()
            self.assertEqual(writer.exitcode,0)
            self.assertEqual(report['objects'],12);self.assertEqual(report['cycles'],12)
            self.assertEqual(report['transfer_bytes'],sum(map(len,remote.objects.values())))
            self.assertEqual(report['covered_rows']['stream_events'],12)
            self.assertFalse(report['retirement_authorized'])
            self.assertLess(delay.value,1);self.assertLess(heartbeat.value,1)
            report.update(collector_acks=count.value,save_max_seconds=delay.value,heartbeat_max_seconds=heartbeat.value,sampled_workspace_peak_bytes=peak.value)
            print(json.dumps({'background_verification':report},sort_keys=True))
            self.assertTrue(any(Path(root).glob('raw-*.db')))
        self.assertLess(time.monotonic()-started,180)

    def test_corruption_and_hard_cancellation_preserve_raw_and_allow_fresh_recovery(self):
        for mode in ('corrupt','hang'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                path,gid,now,remote=self.fixture(root)
                before=set(Path(root).glob('raw-*.db'));started=time.monotonic()
                with self.assertRaises(ArchiveHold):
                    verify_phase(root,path,gid,self.factory(remote,mode),now,deadline=time.monotonic()+.15)
                self.assertLess(time.monotonic()-started,1)
                self.assertEqual(set(Path(root).glob('raw-*.db')),before)
                report=verify_phase(root,path,gid,self.factory(remote),now,deadline=time.monotonic()+10)
                self.assertEqual(report['objects'],12);self.assertFalse(report['retirement_authorized'])
