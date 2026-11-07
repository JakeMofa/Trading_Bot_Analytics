"""Explicit verified selected-row input for generated fresh-B bootstrap.

No source DB transfer, legacy write, inferred IDs or automatic capsule discovery.
All three input hashes are supplied out of band; files/bindings fail closed.
"""
from contextlib import closing
import hashlib,json,os,sqlite3,time
from pathlib import Path
from types import MappingProxyType
from application_validation import row_check
from raw_generations import COLUMNS,canonical,digest,Stop
from selected_recovery import file_binding

class RecoveryCapsule:
    def __init__(self,manifest,dependencies,stream,*,manifest_sha256,dependency_sha256,stream_sha256,deadline):
        self._rows={};self._catalog={};self._proof={}
        for path,expected,limit in ((manifest,manifest_sha256,8*1024**2),(dependencies,dependency_sha256,8*1024**2)):
            if time.monotonic()>=deadline:raise TimeoutError('complete bootstrap deadline')
            p=Path(path)
            if p.is_symlink() or not p.is_file() or p.stat().st_size>limit:raise Stop('capsule input path/size hold')
            if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise Stop('capsule proof file hash mismatch')
        m=json.loads(Path(manifest).read_text());deps=json.loads(Path(dependencies).read_text())
        if time.monotonic()>=deadline:raise TimeoutError('complete bootstrap deadline')
        if m.get('format')!='AB72_SELECTED_RECOVERY_V1' or deps.get('format')!='AB72_SELECTED_DEPENDENCIES_V1':raise Stop('unsupported recovery format')
        if digest({k:v for k,v in m.items() if k!='manifest_sha256'})!=m['manifest_sha256'] or digest(m['records'])!=m['selection_sha256']:raise Stop('capsule manifest checksum hold')
        if m['dependency_sha256']!=dependency_sha256 or m['production_authorized'] is not False:raise Stop('capsule dependency/scope mismatch')
        if len(m['records'])>20000:raise Stop('selected capsule row bound')
        for item in m['records']:
            key=(item['dataset'],item['key'])
            if key in self._catalog:raise Stop('duplicate capsule manifest identity')
            self._catalog[key]=item['sha256']
        expected_keys={('observations',str(i)) for i in deps['missing_observations']}|{('stream_events',i) for i in deps['missing_stream_events']}
        if set(self._catalog)!=expected_keys:raise Stop('capsule identity/dependency mismatch')
        p=Path(stream)
        if p.is_symlink() or not p.is_file() or p.stat().st_size>64*1024**2:raise Stop('capsule stream path/size hold')
        h=hashlib.sha256();size=0
        with p.open('rb') as f:
            while True:
                if time.monotonic()>=deadline:raise TimeoutError('complete bootstrap deadline')
                line=f.readline(1024*1024+1)
                if not line:break
                if len(line)>1024*1024 or not line.endswith(b'\n'):raise Stop('capsule record framing/size hold')
                h.update(line);size+=len(line);item=json.loads(line);key=(item['dataset'],item['key']);row=item['row']
                if key in self._rows:raise Stop('duplicate capsule stream identity')
                if key not in self._catalog or item['sha256']!=self._catalog[key] or digest(row)!=item['sha256']:raise Stop('capsule body/identity checksum hold')
                if key[0] not in COLUMNS or set(row)!=set(COLUMNS[key[0]]):raise Stop('capsule row schema hold')
                if (key[0]=='observations' and str(row['id'])!=key[1]) or (key[0]=='stream_events' and (row['source']!='coinbase' or row['event_id']!=key[1])):raise Stop('capsule row identity hold')
                row_check(key[0],row);self._rows[key]=MappingProxyType(row)
        if h.hexdigest()!=stream_sha256 or set(self._rows)!=set(self._catalog):raise Stop('incomplete/corrupt capsule stream')
        self._legacy_binding=deps['legacy_binding']
        self._proof={'manifest_file_sha256':manifest_sha256,'manifest_sha256':m['manifest_sha256'],
                     'dependency_sha256':dependency_sha256,'stream_sha256':stream_sha256,'stream_bytes':size,
                     'source_sha256':m['source_sha256'],'selected_rows':len(self._rows),
                     'legacy_binding_sha256':digest(self._legacy_binding)}
    @property
    def proof(self):return dict(self._proof)
    def assert_legacy(self,path):
        if file_binding(path)!=self._legacy_binding:raise Stop('capsule legacy binding changed')
    def lookup(self,dataset,key,current=None):
        saved=self._rows.get((dataset,str(key)))
        if current is not None:
            if saved is not None and digest(dict(current))!=digest(dict(saved)):raise Stop('legacy/capsule conflicting identity')
            return current
        return dict(saved) if saved is not None else None


def export_stream(staged_core,manifest,expected_manifest_sha,output,expected_stream_sha,deadline):
    """Only selected TEXT rows; never copies a SQLite file or replaces a conflict."""
    manifest=Path(manifest)
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=expected_manifest_sha:raise Stop('export manifest hash hold')
    m=json.loads(manifest.read_text());catalog={(x['dataset'],x['key']):x['sha256'] for x in m['records']}
    output=Path(output)
    if output.suffix!='.jsonl' or output.is_symlink() or output.parent.is_symlink() or output.parent.stat().st_uid!=os.getuid() or output.parent.stat().st_mode&0o077:raise Stop('private capsule output required')
    if output.exists():
        if hashlib.sha256(output.read_bytes()).hexdigest()!=expected_stream_sha:raise Stop('capsule output conflict')
        return {'changed':False,'sha256':expected_stream_sha,'bytes':output.stat().st_size}
    source=Path(staged_core)
    if source.is_symlink():raise Stop('stage source symlink')
    h=hashlib.sha256();size=0;seen=set()
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
        db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as dest:
            for dataset,key,record,sha in db.execute('SELECT dataset,key,record,sha256 FROM recovery_records ORDER BY dataset,key'):
                if time.monotonic()>=deadline:raise TimeoutError('capsule export deadline')
                row=json.loads(record)
                if (dataset,key) in seen or catalog.get((dataset,key))!=sha or digest(row)!=sha:raise Stop('staged recovery body/membership changed')
                seen.add((dataset,key));line=(canonical(dict(dataset=dataset,key=key,row=row,sha256=sha))+'\n').encode();h.update(line);size+=len(line);dest.write(line)
            if seen!=set(catalog) or h.hexdigest()!=expected_stream_sha:raise Stop('capsule export checksum/membership hold')
            dest.flush();os.fsync(dest.fileno())
    parent=os.open(output.parent,os.O_RDONLY)
    try:os.fsync(parent)
    finally:os.close(parent)
    return {'changed':True,'sha256':h.hexdigest(),'bytes':size}
