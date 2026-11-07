"""Isolated read-only replay request; private config via stdin, never arguments."""
import json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from types import SimpleNamespace
from contextlib import closing
from application_store import ApplicationWorker
from cloud_memory import SupabaseHTTP
from compatible_cloud import CompatibleCloud

def run():
    request=json.loads(sys.stdin.buffer.read(65537))
    if time.monotonic()>=request['deadline']:raise RuntimeError('expired')
    if sys.platform=='linux':
        import resource
        soft,hard=resource.getrlimit(resource.RLIMIT_AS)
        cap=min(x for x in (soft,hard,512*1024**2) if x!=resource.RLIM_INFINITY)
        resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
    worker=ApplicationWorker(request['root'],request['legacy'],routing=True,role='history')
    try:
        with closing(worker.connection()) as db,closing(CompatibleCloud(SupabaseHTTP(SimpleNamespace(url=request['url'],secret_key=request['key'])),request['deadline'])) as cloud:
            result=db.archived_history(cloud,request['generation'],request['dataset'],request['identities'],request['deadline'])
            body=json.dumps(result,allow_nan=False,separators=(',',':')).encode()
            if len(body)>1024**2:raise RuntimeError('response bound')
            sys.stdout.buffer.write(body)
    finally:worker.close()

if __name__=='__main__':
    try:run()
    except Exception:
        sys.stdout.write('{"status":"unavailable","reason":"archive_history_unverified_or_unavailable","records":[]}')
