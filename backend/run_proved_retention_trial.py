"""Explicit one-scope operator; default is plan-only. Never enables a service flag."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--candidate-app',type=Path)
    parser.add_argument('--proof',type=Path);parser.add_argument('--proof-sha256')
    parser.add_argument('--database',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'plan_only','maximum_rows':1000,'automatic_retention_enablement':False}));return
    stage='validate_operator'
    try:
        if (sys.platform!='linux' or not all((args.candidate_app,args.proof,args.proof_sha256,args.database,args.report))
            or args.database.resolve()!=Path('/opt/tradebot/data/btc_intelligence.db')):
            raise ValueError('explicit bounded Linux operator inputs required')
        if args.proof.is_symlink() or args.proof.stat().st_mode&0o777!=0o600 or args.proof.stat().st_size>64*1024**2:
            raise ValueError('private bounded proof required')
        data=args.proof.read_bytes()
        if hashlib.sha256(data).hexdigest()!=args.proof_sha256:raise ValueError('reviewed proof changed')
        proof=json.loads(data);del data
        resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
        sys.path.insert(0,str(Path('/opt/tradebot/backend/app')));sys.path.insert(0,str(args.candidate_app))
        from run_api import load_local_env
        os.environ.clear();load_local_env()
        if (os.environ.get('ENABLE_LOCAL_RETENTION')!='false' or os.environ.get('ENABLE_OPENAI_ANALYST')!='false'
            or any(os.environ.get(key) for key in ('OPENAI_API_KEY','OPENAPIKEY','OPENAI_KEY'))):
            raise ValueError('safe flags required')
        from retention_trial import apply_proved_scope
        from prepare_retention_recovery import private_save,health
        stage='health_preflight';health()
        stage='proved_scope_apply'
        with closing(sqlite3.connect(args.database,timeout=5)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            before={key:db.execute('PRAGMA '+key).fetchone()[0] for key in ('page_size','page_count','freelist_count')}
            result=apply_proved_scope(db,proof)
            result['storage_before']=before
            result['storage_after']={key:db.execute('PRAGMA '+key).fetchone()[0] for key in ('page_size','page_count','freelist_count')}
        stage='save_report';sha=private_save(args.report,result)
        # Report committed data BEFORE a post-operation health failure. Never
        # imply that rollback restored rows already committed by the core.
        summary={key:result.get(key) for key in ('status','dataset','approved_rows','committed_rows','skipped_rows',
                 'error_type','reason','failed_phase','failed_write_seconds','phase_seconds','deleted_identities_sha256',
                 'affected_fk_tables_checked','attempted_identity_count','storage_before','storage_after') if key in result}
        summary.update(report_sha256=sha,proof_sha256=args.proof_sha256)
        print(json.dumps(summary),flush=True)
        stage='post_commit_health';health()
        raise SystemExit(0 if result['status']=='PASS' else 1)
    except SystemExit:raise
    except BaseException as error:
        print(json.dumps({'status':'STOP','stage':stage,'error_type':type(error).__name__,
                          'committed_result_previously_reported':stage=='post_commit_health'}),flush=True)
        raise SystemExit(1) from None


if __name__=='__main__':main()
