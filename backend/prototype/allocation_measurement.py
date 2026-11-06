"""Read-only sampled allocation of named files and all owned regular descriptors.

Counts max(length,allocated blocks),deduplicates inodes,includes unlinked TEMP.
Linux walks children of every thread;other platforms can measure only self FDs.
No payload/path logging,no database open/checkpoint/copy or allocation credit.
"""
import errno,os,stat,sys,time
from itertools import chain
from pathlib import Path

def process_binding(pid):
    """Read-only Linux identity; never reads command lines or environment/secrets."""
    if sys.platform!='linux' or type(pid) is not int or pid<=0:raise ValueError('Linux positive PID required')
    p=Path('/proc',str(pid));fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    if fields[0]=='Z':raise RuntimeError('service owner exited')
    return {'pid':pid,'start_ticks':int(fields[19]),'uid':p.stat().st_uid}

def measure(root,inputs=(),require_family=False,owners=None):
    root=Path(root)
    if root.is_symlink():raise ValueError('measurement root symlink')
    items={};categories={};incomplete=[];end=time.monotonic()+2;objects=0
    owners={} if owners is None else owners
    if not isinstance(owners,dict) or set(owners)-{'tradebot-api','tradebot-ensemble','tradebot-lifecycle'}:raise ValueError('explicit service role binding required')
    if owners and sys.platform!='linux':raise RuntimeError('service descriptor visibility requires Linux')
    def check_owners():
        for binding in owners.values():
            if not isinstance(binding,dict) or set(binding)!={'pid','start_ticks','uid'} or any(type(x) is not int for x in binding.values()):raise ValueError('complete PID/start/UID binding required')
            if process_binding(binding['pid'])!=binding:raise RuntimeError('service owner identity changed')
    check_owners()
    def bound():
        nonlocal objects
        objects+=1
        if objects>8192 or time.monotonic()>=end:raise RuntimeError('allocation inspection bound')
    def account(s,category):
        if not stat.S_ISREG(s.st_mode):return
        key=(s.st_dev,s.st_ino);items[key]=max(items.get(key,0),s.st_size,s.st_blocks*512)
        categories.setdefault(key,category)
    for p in chain(map(Path,inputs),root.rglob('*')):
        bound()
        if p.is_symlink():raise ValueError('measurement input symlink')
        try:account(p.stat(),'named')
        except FileNotFoundError:continue
    pids={os.getpid(),*(binding['pid'] for binding in owners.values())}
    if sys.platform=='linux':
        pending=list(pids)
        while pending:
            pid=pending.pop()
            try:
                threads=list(Path('/proc',str(pid),'task').iterdir())
                if len(threads)>128:raise ValueError('measurement thread bound')
                for tid in threads:
                    bound()
                    try:children=(tid/'children').read_text().split()
                    except (FileNotFoundError,ProcessLookupError):continue
                    for value in children:
                        child=int(value)
                        if child not in pids:
                            pids.add(child);pending.append(child)
                            if len(pids)>32:raise ValueError('measurement process-family bound')
            except (FileNotFoundError,ProcessLookupError):continue
            except PermissionError:incomplete.append('child visibility')
        for pid in pids:
            try:
                for fd in Path('/proc',str(pid),'fd').iterdir():
                    bound()
                    try:
                        s=fd.stat();account(s,'unlinked' if s.st_nlink==0 else 'other_regular')
                    except (FileNotFoundError,ProcessLookupError):continue
            except (FileNotFoundError,ProcessLookupError):continue
            except PermissionError:incomplete.append('descriptor visibility')
    else:
        if require_family:incomplete.append('process-family visibility unavailable')
        try:
            for fd in Path('/dev/fd').iterdir():
                if not fd.name.isdigit():continue
                try:
                    s=os.fstat(int(fd.name));account(s,'unlinked' if s.st_nlink==0 else 'other_regular')
                except OSError as error:
                    if error.errno!=errno.EBADF:raise
        except OSError:incomplete.append('self descriptor visibility')
    if incomplete:raise RuntimeError('allocation visibility incomplete: '+','.join(sorted(set(incomplete))))
    check_owners()
    totals={key:sum(v for inode,v in items.items() if categories[inode]==key) for key in ('named','unlinked','other_regular')}
    return {'sampled_total_bytes':sum(items.values()),'named_bytes':totals['named'],
            'unlinked_regular_bytes':totals['unlinked'],'other_regular_bytes':totals['other_regular'],
            'regular_inode_count':len(items),'observed_processes':len(pids),
            'owner_scope':('bound Linux service roots and descendants' if owners else 'owned Linux process family') if sys.platform=='linux' else 'self only',
            'bound_service_roles':sorted(owners),
            'kernel_hard_quota':False}
