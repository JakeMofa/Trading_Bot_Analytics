"""One bounded read-only source verification + isolated selected-core qualification.

No production path/activation route. Whole operation <=180s,work170s,2GiB including
existing source/dependencies/export and stage,512MiB Linux address space. Retains
review artifacts; does not delete or transfer data. No WAL/checkpoint commands.
"""
import argparse,hashlib,json,os,resource,sys,time
from pathlib import Path
from selected_recovery import verify,stage,RecoveryHold
from run_application_qualification import supervise

def qualify(args):
    start=float(os.environ['AB_PROFILE_STARTED']);deadline=start+170;root=Path(args.root)
    result={'status':'FAIL','production_authorized':False,'platform':sys.platform}
    if not root.is_dir() or root.is_symlink() or not root.name.startswith('generated-ab-recovery-') or root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077:raise RecoveryHold('isolated private root required')
    if any(root.iterdir()) or Path(args.report).name!='qualification-report.json' or Path(args.report).is_symlink() or Path(args.report).resolve().parent!=root.resolve() or Path(args.report).exists():raise RecoveryHold('empty staging root and fresh qualification-report.json required')
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    external=[Path(args.source),Path(str(args.source)+'-wal'),Path(str(args.source)+'-shm'),Path(args.dependencies)]
    export=Path(__file__).resolve().parents[2];manifest=export/'AB_CANDIDATE_MANIFEST.json'
    code_bytes=0
    if manifest.exists():
        from build_ab_candidate import verify_export
        m=verify_export(export,args.sha,repo=args.repo)
        result['source_sha']=m['source_sha'];code_bytes=sum(max((export/f).stat().st_size,(export/f).stat().st_blocks*512) for f in m['files'])+manifest.stat().st_size
    else:raise RecoveryHold('exact exported candidate required')
    peak=0;last=0
    def guard(force=False):
        nonlocal peak,last
        now=time.monotonic()
        if not force and now-last<.025:return
        last=now;seen=set();used=code_bytes
        for p in external+list(root.rglob('*')):
            try:
                if p.is_symlink():raise RecoveryHold('accounted path symlink')
                st=p.stat()
                if p.is_file() and (st.st_dev,st.st_ino) not in seen:
                    seen.add((st.st_dev,st.st_ino));used+=max(st.st_size,st.st_blocks*512)
            except FileNotFoundError:continue
        peak=max(peak,used)
        if used>2*1024**3:raise RecoveryHold('2GiB aggregate verification/staging resource cap')
        if now>=deadline:raise TimeoutError('complete recovery work deadline')
    try:
        guard(True);begin=time.monotonic()
        verified=verify(args.source,args.dependencies,args.source_hash,args.dependency_hash,deadline,guard)
        result['verification_seconds']=time.monotonic()-begin
        report_manifest=verified[0];(root/'recovery-manifest.json').write_text(json.dumps(report_manifest,sort_keys=True,indent=2)+'\n')
        begin=time.monotonic();result['first_stage']=stage(root,verified,deadline,guard=guard)
        result['stage_seconds']=time.monotonic()-begin;guard(True)
        begin=time.monotonic();result['retry_stage']=stage(root,verified,deadline,guard=guard)
        result['retry_seconds']=time.monotonic()-begin
        if result['retry_stage']['changed_rows']!=0:raise RecoveryHold('idempotent retry changed rows')
        guard(True)
        result.update(status='PASS_ISOLATED_SELECTED_RECOVERY',manifest_sha256=report_manifest['manifest_sha256'],selection_sha256=report_manifest['selection_sha256'],
                      observations=report_manifest['observations'],stream_events=report_manifest['stream_events'],
                      source_integrity='ok',source_fk_violations=0,conflicts=0,unverifiable_rows=0,
                      manifest_file_sha256=hashlib.sha256((root/'recovery-manifest.json').read_bytes()).hexdigest(),
                      independent_verification_limit='expected source hash pinned; no cryptographic proof of historical origin beyond retained source and dependency provenance')
    except Exception as error:result.update(error_type=type(error).__name__,reason=str(error))
    finally:
        result.update(elapsed_seconds=time.monotonic()-start,aggregate_peak_bytes=peak,existing_source_included=True,
                      rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                      linux_memory_limit_applied=sys.platform=='linux',full_application_bootstrap='NOT_PERFORMED',production_repair='NOT_PERFORMED')
        Path(args.report).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','dependencies','source-hash','dependency-hash','root','report','sha'):p.add_argument('--'+key,required=True)
    p.add_argument('--repo');p.add_argument('--child',action='store_true');a=p.parse_args()
    if not a.child:
        os.environ['AB_PROFILE_STARTED']=str(time.monotonic())
        raise SystemExit(supervise([sys.executable,__file__,*sys.argv[1:],'--child'],a.report,180))
    r=qualify(a);print(json.dumps(r,sort_keys=True));raise SystemExit(0 if r['status']=='PASS_ISOLATED_SELECTED_RECOVERY' else 1)
