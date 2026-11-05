"""One serial normal/outage sample. Generated data and local archive only."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen

from raw_generations import Store, FileArchive, Stop, iso

MIB = 1024**2
CAP = 64*MIB
FREE_FLOOR = 10*1024**3
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
RATE = 20480
TRIGGER = 2*MIB


def production_health():
    services = {}
    for unit in ('tradebot-api','tradebot-ensemble','tradebot-lifecycle'):
        services[unit] = subprocess.check_output(
            ['systemctl','show',unit,'-pActiveState','-pMainPID','-pNRestarts'],
            text=True, timeout=2).strip()
        if 'ActiveState=active' not in services[unit]:
            raise Stop('production service inactive')
    with urlopen('http://127.0.0.1:8000/health', timeout=2) as response:
        health = json.load(response)
    if health.get('collector',{}).get('running') is not False:
        raise Stop('production collector state changed')
    if health.get('feeds',{}).get('storage_guard',{}).get('status') != 'limit_reached':
        raise Stop('production storage hold changed')
    return services


def available_ram():
    return int(next(line for line in Path('/proc/meminfo').read_text().splitlines()
                    if line.startswith('MemAvailable:')).split()[1])*1024


class MeteredArchive(FileArchive):
    def __init__(self, root, guard):
        super().__init__(root)
        self.guard = guard
        self.upload_bytes_total = self.read_bytes_total = 0
        self.upload_seconds = self.read_seconds = 0.0

    def upload_bytes(self, bucket, key, data, content_type='application/gzip'):
        began = time.monotonic()
        super().upload_bytes(bucket, key, data, content_type)
        self.upload_seconds += time.monotonic()-began
        self.upload_bytes_total += len(data)
        self.guard()

    def download_bytes(self, bucket, key):
        began = time.monotonic()
        data = super().download_bytes(bucket, key)
        self.read_seconds += time.monotonic()-began
        self.read_bytes_total += len(data)
        self.guard()
        return data


def sample(root, outage, check, report):
    store = Store(root, ceiling=CAP, generation_bytes=TRIGGER)
    cloud = MeteredArchive(root/'archive', check)
    count = payload_bytes = 0
    began = time.monotonic()
    peak_at = {}
    def save():
        nonlocal count, payload_bytes, peak_at
        at = START+timedelta(seconds=payload_bytes/RATE)
        observation = count%18 == 0
        size = (732,7408,7411,7475,7830)[count%5] if observation else (435,436,437)[count%3]
        data = '{"p":"'+hashlib.shake_256(str(count).encode()).hexdigest(size)[:size-8]+'"}'
        if observation:
            dataset, key = 'observations', str(count)
            row = dict(market_id='m',received_at=iso(at),source_time=iso(at),kind='book',payload=data)
        else:
            dataset, key = 'stream_events', 'coinbase:'+str(count)
            row = dict(source='coinbase',event_id=str(count),received_at=iso(at),source_time=iso(at),
                       price='12345.0000000001',size='0.01',side='buy',payload=data)
        eid = store.save(dataset,key,row)
        assert store.core.execute('SELECT status FROM events WHERE id=?',(eid,)).fetchone()[0]=='committed'
        count += 1
        payload_bytes += len(data)
        allocation = store.allocation()
        if allocation['total_bytes'] >= sum(peak_at.values()):
            peak_at = allocation['files']
        check()

    try:
        save()
        a = store.active()['id']
        while store.active()['id'] == a:
            save()
        b = store.active()['id']
        sealed = time.monotonic()
        a_rows = count-1
        seal = datetime.fromisoformat(store.core.execute('SELECT sealed_at FROM generations WHERE id=?',(a,)).fetchone()[0])
        before = hashlib.sha256(store.path(a).read_bytes()).hexdigest()
        metrics = dict(a_rows=a_rows, a_main_bytes=store.path(a).stat().st_size,
                       active_a_seconds=(seal-START).total_seconds())
        if outage:
            cloud.available = False
            try:
                store.finish_sealed(a,cloud,START+timedelta(seconds=payload_bytes/RATE))
            except Stop as error:
                assert str(error)=='archive unavailable'
            else:
                raise Stop('outage did not hold archive')
            while True:
                try:
                    save()
                except Stop as error:
                    if str(error) != 'both slots retained: bounded ingestion STOP, no backlog':
                        raise
                    metrics['stop_reason'] = str(error)
                    break
            assert hashlib.sha256(store.path(a).read_bytes()).hexdigest()==before
            assert store.core.execute("SELECT count(*) FROM events WHERE status='pending'").fetchone()[0]==0
            metrics.update(sealed_a_intact=True, outage_runway_simulated_seconds=payload_bytes/RATE-metrics['active_a_seconds'])
        else:
            archive_done, release_reader = threading.Event(), threading.Event()
            def retire():
                with store.worker_session():
                    while store.archive_hour(cloud,START+timedelta(hours=1),sealed_generation=a):
                        check()
                    archive_done.set()
                    if not release_reader.wait(5):
                        raise Stop('sample reader drain deadline')
                    store.retire(a,cloud,START+timedelta(hours=1))
            with ThreadPoolExecutor(max_workers=1) as pool:
                with store.reader(a):
                    future = pool.submit(retire)
                    try:
                        while not archive_done.is_set():
                            if future.done():
                                future.result()
                            save()
                        assert store.path(a).exists()
                        drain_started = time.monotonic()
                    except BaseException:
                        release_reader.set()
                        raise
                release_reader.set()
                future.result(timeout=5)
            metrics.update(reader_drain_seconds=time.monotonic()-drain_started,
                           seal_to_retirement_seconds=time.monotonic()-sealed)
            assert not store.path(a).exists() and store.active()['id']==b
        metrics.update(case='outage' if outage else 'normal', b_acknowledged=count-a_rows,
                       payload_bytes=payload_bytes,wall_seconds=time.monotonic()-began,
                       peak_files=peak_at, sampled_peak_bytes=store.peak,
                       upload_bytes=cloud.upload_bytes_total,upload_seconds=cloud.upload_seconds,
                       readback_bytes=cloud.read_bytes_total,readback_seconds=cloud.read_seconds)
        report['cases'].append(metrics)
    finally:
        store.close()


def run():
    began = time.monotonic()
    report = {'result':'FAIL','cases':[]}
    root = Path(tempfile.mkdtemp(prefix='generated-ab-'))
    peak_disk = 0
    next_health = 0
    baseline = None
    def check():
        nonlocal peak_disk, next_health
        size = 0
        for path in root.rglob('*'):
            try:
                if path.is_file():
                    size += path.stat().st_size
            except FileNotFoundError:
                pass
        peak_disk = max(peak_disk,size)
        if size > CAP or time.monotonic()-began >= 170:
            raise Stop('sample workspace or work deadline')
        fs = os.statvfs(root)
        if fs.f_bavail*fs.f_frsize < FREE_FLOOR:
            raise Stop('filesystem free floor')
        if time.monotonic() >= next_health:
            next_health = time.monotonic()+2
            if production_health() != baseline:
                raise Stop('production service identity changed')
    def interrupted(*_):
        raise Stop('sample absolute deadline')
    signal.signal(signal.SIGALRM,interrupted)
    signal.alarm(177)
    try:
        baseline = production_health()
        if available_ram() < 1152*MIB:
            raise Stop('sample RAM preflight')
        if shutil.disk_usage(root).free < FREE_FLOOR+CAP:
            raise Stop('sample disk preflight')
        resource.setrlimit(resource.RLIMIT_AS,(256*MIB,256*MIB))
        for outage in (False,True):
            case = root/('generated-ab-outage' if outage else 'generated-ab-normal')
            case.mkdir(mode=0o700)
            sample(case,outage,check,report)
            shutil.rmtree(case)
            check()
        report['result']='PASS'
    except Exception as error:
        report.update(error_type=type(error).__name__,reason=str(error) if isinstance(error,Stop) else 'sample failed')
    finally:
        shutil.rmtree(root)
        report.update(peak_workspace_bytes=peak_disk,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                      total_seconds=time.monotonic()-began)
        signal.alarm(0)
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    run()
