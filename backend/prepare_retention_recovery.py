"""Operator-only private archive readback and bounded raw recovery proof.

Default is plan-only. Explicit read-only execution never deletes, enables
retention, uploads, creates indexes, restarts services or restores a database.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys
import urllib.request
import uuid


def private_save(path,value):
    path=Path(path);parent=path.parent;st=parent.stat()
    if parent.is_symlink() or st.st_uid!=os.geteuid() or st.st_mode&0o077:
        raise ValueError('private operator output directory required')
    temporary=parent/(path.name+'.pending-'+uuid.uuid4().hex)
    data=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        # Publish without replacing an earlier immutable recovery proof.
        os.link(temporary,path,follow_symlinks=False)
        return hashlib.sha256(data).hexdigest()
    finally:
        if temporary.exists():temporary.unlink()


def health():
    with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as response:value=json.load(response)
    now=datetime.now(timezone.utc)
    if not value.get('collector',{}).get('running'):raise RuntimeError('collector not running')
    for key in ('coinbase_stream','polymarket_stream'):
        feed=value.get('feeds',{}).get(key,{})
        age=(now-datetime.fromisoformat(feed['last_data_at'])).total_seconds()
        if feed.get('status')!='live' or not 0<=age<30:raise RuntimeError('feed not fresh live')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-read-only',action='store_true')
    parser.add_argument('--candidate-app',type=Path)
    parser.add_argument('--deployed-app',type=Path,default=Path('/opt/tradebot/backend/app'))
    parser.add_argument('--database',type=Path)
    parser.add_argument('--dataset',choices=('observations','stream_events'),default='observations')
    parser.add_argument('--limit',type=int,default=1000)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.execute_read_only:
        print(json.dumps({'mode':'plan_only','max_rows':1000,'cloud_operations':'authenticated_reads_only'}));return
    stage='validate_operator'
    try:
        if sys.platform!='linux' or not 1<=args.limit<=1000:raise ValueError('bounded Linux operator required')
        if (args.deployed_app.resolve()!=Path('/opt/tradebot/backend/app') or args.candidate_app is None
            or args.database is None or args.database.resolve()!=Path('/opt/tradebot/data/btc_intelligence.db') or args.output is None):
            raise ValueError('pinned runtime paths and private output required')
        resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
        sys.path.insert(0,str(args.deployed_app));sys.path.insert(0,str(args.candidate_app))
        stage="load_runtime"
        from run_api import load_local_env
        os.environ.clear();load_local_env()
        if (os.environ.get('ENABLE_LOCAL_RETENTION')!='false' or os.environ.get('ENABLE_OPENAI_ANALYST')!='false'
            or any(os.environ.get(key) for key in ('OPENAI_API_KEY','OPENAPIKEY','OPENAI_KEY'))):
            raise ValueError('safe flags required')
        from cloud_memory import CloudConfig,SupabaseHTTP
        from retention import fetch_verified_manifests
        from retention_recovery import prepare_scope,RecoveryError
        cloud=SupabaseHTTP(CloudConfig.from_env(),timeout=15)
        class Readback:
            def download_bytes(self,bucket,path):
                nonlocal stage
                stage="archive_readback"
                health();data=cloud.download_bytes(bucket,path);health()
                stage="compare_raw_scope"
                return data
        try:
            stage="load_manifests"
            health();manifests=fetch_verified_manifests(cloud,cloud.config.raw_bucket)
            cutoff=(datetime.now(timezone.utc)-timedelta(hours=48)).isoformat(timespec='microseconds')
            stage="select_bounded_scope"
            with closing(sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
                db.execute('PRAGMA query_only=ON')
                proof=prepare_scope(db,Readback(),manifests,args.dataset,cutoff,cloud.config.raw_bucket,args.limit)
            stage="save_private_proof"
            health();sha=private_save(args.output,proof)
            print(json.dumps({'status':'PREPARED_NOT_APPLIED','dataset':args.dataset,
                              'rows':len(proof['recovery']['records']),'archives':len(proof['recovery']['archives']),
                              'sha256':sha,'reconstruction':proof['reconstruction'],'cutoff':cutoff}),flush=True)
        finally:cloud.close()
    except BaseException as error:
        # HTTP errors can include request details. Report only typed failures.
        result={'status':'STOP','stage':stage,'error_type':type(error).__name__}
        if type(error).__module__=='retention_recovery':result['reason']=str(error)
        response=getattr(error,'response',None)
        if response is not None:result['HTTP_status']=int(response.status_code)
        if type(error) is RuntimeError and str(error) in ('collector not running','feed not fresh live'):
            result['reason']=str(error)
        print(json.dumps(result),flush=True)
        raise SystemExit(1) from None


if __name__=='__main__':main()
