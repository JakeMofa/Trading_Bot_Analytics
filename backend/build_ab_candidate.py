"""Export an exact tracked source tree for generated qualification, never deploy.

No git checkout/worktree/branch, database copy or local untracked content. The
manifest binds source SHA and every exported byte. This is not an operator bundle.
"""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path,PurePosixPath
PREFIXES=('backend/','deploy/','supabase/schema/','docs/','.github/')
EXACT={'AGENTS.md','README.md','pyproject.toml'}
MANIFEST='AB_CANDIDATE_MANIFEST.json'
def selected(name):return name in EXACT or name.startswith(PREFIXES)
def validate_path(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe export path')
    if any(x in ('.git','.venv','__pycache__','node_modules','data') for x in p.parts):raise ValueError('local data/build content not exportable')
    low=p.name.lower()
    if (p.suffix.lower() in ('.db','.sqlite','.sqlite3','.pyc','.pem','.key','.p12','.pfx','.log')
        or low.startswith('.env') or low in ('credentials','credentials.json','credentials.ini','secrets.json','secrets.yaml','secrets.toml','id_rsa','id_ed25519')
        or any(x in ('.aws','.ssh') for x in p.parts) or re.search(r'\.(?:db|sqlite3?)-(?:wal|shm|journal)$',low)):
        raise ValueError('database/environment/credential content not exportable')
def verify_export(output,expected_sha=None,repo=None):
    output=Path(output)
    if output.is_symlink():raise ValueError('export root symlink')
    output=output.resolve()
    if (output/MANIFEST).is_symlink():raise ValueError('manifest symlink')
    manifest=json.loads((output/MANIFEST).read_text())
    if not re.fullmatch('[0-9a-f]{40}',manifest['source_sha']):raise ValueError('exact SHA required')
    if expected_sha and manifest['source_sha']!=expected_sha:raise ValueError('source SHA mismatch')
    actual={str(p.relative_to(output)) for p in output.rglob('*') if p.is_file() or p.is_symlink()}
    if actual!=set(manifest['files'])|{MANIFEST}:raise ValueError('export file set mismatch')
    git_files=None
    if repo is not None:
        git_files={name:(mode,oid) for name,mode,oid in tracked_entries(repo,manifest['source_sha'])}
        if set(git_files)!=set(manifest['files']):raise ValueError('export differs from exact Git tree')
    for name,info in manifest['files'].items():
        validate_path(name);p=output/name
        if info['mode'] not in ('100644','100755'):raise ValueError('invalid export mode')
        if p.is_symlink() or any((output/parent).is_symlink() for parent in PurePosixPath(name).parents):raise ValueError('export symlink')
        if (p.stat().st_mode&0o777)!=(0o755 if info['mode']=='100755' else 0o644):raise ValueError('export mode mismatch')
        data=p.read_bytes()
        if git_files is not None:
            mode,oid=git_files[name]
            if mode!=info['mode'] or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=oid:raise ValueError('export blob differs from exact Git commit')
        if len(data)!=info['bytes'] or hashlib.sha256(data).hexdigest()!=info['sha256']:raise ValueError('export content mismatch')
    return manifest

def tracked_entries(repo,sha):
    def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(Path(repo).resolve()),'-C',str(repo),*args])
    if git('rev-parse',sha+'^{commit}').decode().strip()!=sha:raise ValueError('commit identity mismatch')
    entries=[]
    for entry in git('ls-tree','-r','-z',sha).split(b'\0'):
        if not entry:continue
        meta,name=entry.split(b'\t',1);mode,kind,oid=meta.decode().split();name=name.decode()
        if not selected(name):continue
        validate_path(name)
        if mode not in ('100644','100755') or kind!='blob':raise ValueError('only regular tracked source files allowed')
        entries.append((name,mode,oid))
    return entries

def export(repo,sha,output):
    repo=Path(repo).resolve();output=Path(output)
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('exact SHA required')
    if output.is_symlink() or output.exists():raise ValueError('fresh export path required')
    entries=tracked_entries(repo,sha)
    def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args])
    output.mkdir(mode=0o700,parents=True)
    files={};total=0
    for name,mode,oid in entries:
        data=git('cat-file','blob',oid);total+=len(data)
        if total>128*1024**2:raise ValueError('source export resource limit')
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as file:file.write(data)
        target.chmod(0o755 if mode=='100755' else 0o644)
        files[name]={'mode':mode,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    manifest={'source_sha':sha,'files':files,'source_bytes':total,'purpose':'generated qualification only; not production migration authority'}
    (output/MANIFEST).write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    verify_export(output,sha,repo=repo);return manifest
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',default='.');parser.add_argument('--sha',required=True);parser.add_argument('--output',required=True);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();m=verify_export(args.output,args.sha,repo=args.repo) if args.verify else export(args.repo,args.sha,args.output)
    print(json.dumps({'source_sha':m['source_sha'],'source_files':len(m['files']),'source_bytes':m['source_bytes']}))
