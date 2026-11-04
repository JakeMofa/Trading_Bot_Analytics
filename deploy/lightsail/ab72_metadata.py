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


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path');args=parser.parse_args()
    print(json.dumps(inspect(args.path)))
