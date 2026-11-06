"""Read-only sampled allocation of named files and all owned regular descriptors.

Counts max(length,allocated blocks),deduplicates inodes,includes unlinked TEMP.
Linux walks children of every thread;other platforms can measure only self FDs.
No payload/path logging,no database open/checkpoint/copy or allocation credit.
"""
import errno,os,stat,sys
from pathlib import Path

def measure(root,inputs=(),require_family=False):
    root=Path(root)
    if root.is_symlink():raise ValueError('measurement root symlink')
    items={};categories={};incomplete=[]
    def account(s,category):
        if not stat.S_ISREG(s.st_mode):return
        key=(s.st_dev,s.st_ino);items[key]=max(items.get(key,0),s.st_size,s.st_blocks*512)
        categories.setdefault(key,category)
    for p in [*map(Path,inputs),*root.rglob('*')]:
        if p.is_symlink():raise ValueError('measurement input symlink')
        try:account(p.stat(),'named')
        except FileNotFoundError:continue
    pids={os.getpid()}
    if sys.platform=='linux':
        pending=list(pids)
        while pending:
            pid=pending.pop()
            try:
                threads=list(Path('/proc',str(pid),'task').iterdir())
                if len(threads)>128:raise ValueError('measurement thread bound')
                for tid in threads:
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
    totals={key:sum(v for inode,v in items.items() if categories[inode]==key) for key in ('named','unlinked','other_regular')}
    return {'sampled_total_bytes':sum(items.values()),'named_bytes':totals['named'],
            'unlinked_regular_bytes':totals['unlinked'],'other_regular_bytes':totals['other_regular'],
            'regular_inode_count':len(items),'observed_processes':len(pids),
            'owner_scope':'owned Linux process family' if sys.platform=='linux' else 'self only',
            'kernel_hard_quota':False}
