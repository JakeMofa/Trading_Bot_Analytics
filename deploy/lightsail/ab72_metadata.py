"""Bounded read-only readiness metadata. No payloads, row scans, copies or authority.

Counts from sqlite_stat1 are optimizer estimates, never certified cardinalities.
Indexed extrema are identities, never COUNT(*). Timeout is an explicit missing fact.
"""
import json,os,sqlite3,time
from pathlib import Path


def inspect(path,seconds=3):
    if not 0<seconds<=5:raise ValueError('metadata budget must be <=5 seconds')
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('existing nonsymlink database required')
    end=time.monotonic()+seconds
    files={}
    for suffix in ('','-wal','-shm'):
        p=Path(str(path)+suffix)
        if p.is_symlink():raise ValueError('sidecar symlink')
        if p.exists():
            st=p.stat();files[suffix or 'main']={'bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns}
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
    try:
        db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>=end),100)
        schema=db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 257").fetchall()
        if len(schema)>256:raise ValueError('schema metadata bound exceeded')
        estimates=[]
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'").fetchone():
            estimates=db.execute('SELECT tbl,idx,stat FROM sqlite_stat1 LIMIT 257').fetchall()
            if len(estimates)>256:raise ValueError('optimizer estimate bound exceeded')
        geometry={k:db.execute('PRAGMA '+k).fetchone()[0] for k in ('page_size','page_count','freelist_count','schema_version')}
        if time.monotonic()>=end:raise TimeoutError('metadata deadline')
        return {'status':'PASS_METADATA_ONLY','files':files,'geometry':geometry,'schema':schema,
            'optimizer_estimates_not_counts':estimates,'exact_cardinalities':'NOT_PROVEN',
            'filesystem_free_bytes':os.statvfs(path.parent).f_bavail*os.statvfs(path.parent).f_frsize}
    finally:db.close()

def verification_binding(path):
    """Quiescent identity, not a substitute for full checks or FD visibility.

    Bind main/WAL inode, length, allocation and mtime as well as schema identity.
    SHM lock-byte changes from readers are not data changes. Capture after closing
    the identity reader; no immutable mode, checkpoint or payload scan.
    """
    from release_verification import _identity
    path=Path(path);identity=_identity(path);files={}
    for suffix in ('','-wal'):
        p=Path(str(path)+suffix)
        if p.is_symlink():raise ValueError('binding sidecar symlink')
        if p.exists():
            st=p.stat();files[suffix or 'main']=(st.st_dev,st.st_ino,st.st_size,st.st_blocks*512,st.st_mtime_ns)
    return {'schema_identity':identity,'files':files}


def recovery_capacity(preflight):
    """Finite recovery-envelope arithmetic only; never authorizes a guard change.

    Actual retained files and bound service FDs count in full. Quota arithmetic
    is not proof of transaction overrun, a peak, verification or live runway.
    """
    gib=1024**3
    if preflight.get('status')!='PASS_READ_ONLY_METADATA' or preflight.get('sqlite_opened') is not False:raise ValueError('bounded read-only preflight required')
    allocation=preflight['allocation']
    if allocation.get('owner_scope')!='bound Linux service roots and descendants' or set(allocation.get('bound_service_roles',[]))!={'tradebot-api','tradebot-ensemble','tradebot-lifecycle'}:raise ValueError('all independent service owners required')
    fields=(allocation['sampled_total_bytes'],preflight['filesystem_available_bytes'],preflight['mem_available_bytes'])
    if any(type(x) is not int or x<0 for x in fields):raise ValueError('nonnegative measured bytes required')
    retained,free,ram=fields;new=2*gib;reserve=gib//2;proposal=8*gib
    subtotal=retained+new+reserve
    return {'status':'REVIEW_ONLY_NOT_AUTHORITY','production_authorized':False,
            'measured_at_utc':preflight['at_utc'],'measured_retained_and_open_fd_bytes':retained,
            'new_layout_quota_bytes':new,'recovery_reserve_bytes':reserve,
            'required_sum_bytes':subtotal,'proposed_aggregate_bytes':proposal,
            'quota_margin_bytes':proposal-subtotal,'quota_arithmetic_fits':subtotal<=proposal,
            'filesystem_floor_bytes':10*gib,'filesystem_after_full_new_and_recovery_bytes':free-new-reserve,
            'filesystem_floor_fits':free-new-reserve>=10*gib,
            'available_ram_bytes':ram,'qualification_ram_prerequisite_bytes':1152*1024**2,
            'ram_precondition_fits':ram>=1152*1024**2,
            'normal_5120mib_remaining_bytes':5*gib-retained,
            'continuous_runway':'NOT_PROVEN','peak_and_write_overrun':'NOT_PROVEN',
            'required_before_dispatch':['complete legacy verification within reviewed absolute budget',
                'post-quiescent source/dependency binding and exact capsule revalidation',
                'aggregate guard covering all service owners with qualified write-overrun margin',
                'reviewed production path/UID/permission/manual scope and fresh absolute expiry',
                'separate explicit source-use/cutover/storage-policy approval']}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path',nargs='?');parser.add_argument('--recovery-preflight',type=Path);args=parser.parse_args()
    if bool(args.path)==bool(args.recovery_preflight):parser.error('one metadata path or recovery preflight required')
    if args.recovery_preflight:
        p=args.recovery_preflight
        if p.is_symlink() or not p.is_file() or p.stat().st_size>65536:raise ValueError('bounded preflight JSON required')
        print(json.dumps(recovery_capacity(json.loads(p.read_text()))))
    else:print(json.dumps(inspect(args.path)))
