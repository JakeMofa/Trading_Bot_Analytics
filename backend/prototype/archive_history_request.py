"""Explicit API history subprocess, with no fork of the threaded API process."""
import json, os, signal, subprocess, sys, time
from pathlib import Path

def request_history(connection,cloud,generation,dataset,identities,deadline):
    unavailable={'status':'unavailable','reason':'archive_history_unverified_or_unavailable','records':[]}
    if time.monotonic()>=deadline:return unavailable
    body=json.dumps(dict(root=str(connection.store.root),legacy=str(connection.store.legacy),
        url=cloud.cloud.config.url,key=cloud.cloud.config.secret_key,
        generation=generation,dataset=dataset,identities=identities,deadline=deadline)).encode()
    if len(body)>65536:return unavailable
    child=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).with_name('archive_history_worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        try:output,_=child.communicate(body,timeout=max(.001,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:return unavailable
        if child.returncode or time.monotonic()>=deadline or len(output)>1024**2:return unavailable
        result=json.loads(output)
        return result if time.monotonic()<deadline else unavailable
    finally:
        # The isolated worker may own a GET child; cancel its entire owned group.
        if child.returncode is None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        child.communicate()
