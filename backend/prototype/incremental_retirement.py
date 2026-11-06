"""Opt-in bounded second readback across cycles; generated-only existing actors.

Receipt validity binds exact sealed file/ledger epoch/catalog/validator bytes.
Cached checks never authorize unlink: final fresh readback remains mandatory.
No source-time, SQLite or cloud deadline change. Expired/changed proof restarts.
"""
import hashlib,json,time,math
from pathlib import Path
from raw_generations import Stop,COLUMNS,canonical,digest,identity,verify_archive,build_manifest,iso,stamp
from retention import _manifest_interval
from retention_recovery import RecoveryError


def initialize(actor):
    core=actor.core;prefix='ab_' if hasattr(core,'native') else ''
    if core.in_transaction:raise Stop('verification cannot commit a caller transaction')
    core.executescript('''CREATE TABLE IF NOT EXISTS ab_retire_epoch(gen TEXT PRIMARY KEY,epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ab_retire_checks(gen TEXT,path TEXT,token TEXT,manifest_sha TEXT,verified_at TEXT,PRIMARY KEY(gen,path));''')
    for table in ('events','raw_receipts','manifests'):
        actual=prefix+table
        for op in ('INSERT','UPDATE','DELETE'):
            refs=[]
            for kind in (('NEW',) if op=='INSERT' else ('OLD',) if op=='DELETE' else ('OLD','NEW')):
                target=kind+'.gen' if table!='raw_receipts' else '(SELECT gen FROM '+prefix+'events WHERE id='+kind+'.id)'
                refs.append('UPDATE ab_retire_epoch SET epoch=epoch+1 WHERE gen='+target+';')
            core.execute('CREATE TRIGGER IF NOT EXISTS ab_verify_'+actual+'_'+op+' AFTER '+op+' ON '+actual+' BEGIN '+''.join(refs)+' END')
    core.commit()


def catalog(actor,gid):
    gen=actor.core.execute('SELECT id,slot,started,sealed_at,state FROM generations WHERE id=?',(gid,)).fetchone()
    if not gen or gen['state'] not in ('sealed','draining','retiring'):raise Stop('incremental verification requires sealed generation')
    records=actor.core.execute('SELECT dataset,path,metadata FROM manifests WHERE gen=? ORDER BY dataset,path LIMIT 20001',(gid,)).fetchall()
    if len(records)>20000:raise Stop('incremental manifest bound')
    entries=[(r[0],r[1],json.loads(r[2])) for r in records]
    if any(d not in COLUMNS or p!=m.get('object_path') for d,p,m in entries):raise Stop('unknown or conflicting manifest identity')
    physical=[]
    for suffix in ('','-wal'):
        path=Path(str(actor.path(gid))+suffix)
        if path.is_symlink():raise Stop('sealed proof symlink')
        if path.exists():
            st=path.stat()
            if suffix=='-wal' and st.st_size==0:continue # no data frames; normal reader cleanup can remove it
            physical.append((suffix,st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns))
    if not physical:raise Stop('sealed file missing')
    epoch=actor.core.execute('SELECT epoch FROM ab_retire_epoch WHERE gen=?',(gid,)).fetchone()[0]
    validators=[hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('incremental_retirement.py','raw_generations.py','application_validation.py')]
    token=digest({'format':1,'gen':tuple(gen)[:4],'physical':physical,'epoch':epoch,'catalog':[tuple(r) for r in records],'validators':validators})
    return token,entries


class VerifiedSession:
    def __init__(self,actor,gid,token,now,max_age):self.actor,self.gid,self.token,self.now,self.max_age=actor,gid,token,now,max_age
    def validate(self,actor,gid):
        if actor is not self.actor or gid!=self.gid or catalog(actor,gid)[0]!=self.token:raise Stop('sealed verification binding changed')
    def contains(self,m):
        row=self.actor.core.execute('SELECT token,manifest_sha,verified_at FROM ab_retire_checks WHERE gen=? AND path=?',(self.gid,m['object_path'])).fetchone()
        return bool(row and row[0]==self.token and row[1]==digest(m) and 0<=(stamp(self.now)-stamp(row[2])).total_seconds()<=self.max_age)


def step(actor,gid,cloud,now,*,max_objects=1,max_age=300,finalize=True,deadline=None):
    supplied=[value for value in (getattr(cloud,'deadline',None),deadline) if value is not None]
    if any(type(value) not in (int,float) or not math.isfinite(value) for value in supplied):raise Stop('invalid verification operation deadline')
    end=min([time.monotonic()+30,*supplied])
    if not math.isfinite(end) or time.monotonic()>=end:raise Stop('original verification operation deadline')
    def guard():
        if time.monotonic()>=end:raise Stop('original verification operation deadline')
    previous=getattr(actor,'retirement_guard',None)
    actor.retirement_guard=guard
    actor.core.set_progress_handler(lambda:int(time.monotonic()>=end),1000)
    try:
        guard()
        return _step(actor,gid,cloud,now,max_objects=max_objects,max_age=max_age,finalize=finalize)
    finally:
        actor.core.set_progress_handler(None,0);actor.retirement_guard=previous


def _step(actor,gid,cloud,now,*,max_objects,max_age,finalize):
    if type(max_objects) is not int or not 1<=max_objects<=8 or type(max_age) is not int or not 1<=max_age<=21600:raise Stop('explicit bounded retirement verification policy required')
    initialize(actor)
    with actor.core:actor.core.execute('INSERT OR IGNORE INTO ab_retire_epoch VALUES(?,0)',(gid,))
    token,entries=catalog(actor,gid);session=VerifiedSession(actor,gid,token,now,max_age)
    checked=0;covered={};ordered=[]
    for dataset in COLUMNS:
        actor.retirement_guard()
        group=[m for d,p,m in entries if d==dataset]
        if len(group)>10000:raise Stop('bounded manifest budget')
        group.sort(key=lambda m:_manifest_interval(dataset,m,'market-raw')[0]);previous=None;count=0
        for m in group:
            if m['metadata'].get('generation_id')!=gid or not m['object_path'].startswith(gid+'/'):raise Stop('generation archive identity mismatch')
            lo,hi=_manifest_interval(dataset,m,'market-raw')
            if previous is not None and lo<=previous:raise Stop('overlapping archive identities')
            previous=hi;count+=m['event_count'];ordered.append((dataset,m,lo,hi))
        with actor.reader(gid,allow_draining=True) as db:raw_count=db.execute('SELECT count(*) FROM '+dataset).fetchone()[0]
        ledger=actor.core.execute("SELECT count(*) FROM events WHERE gen=? AND dataset=? AND status='committed'",(gid,dataset)).fetchone()[0]
        if count!=raw_count or ledger!=raw_count:raise Stop('archive coverage incomplete')
        covered[dataset]=raw_count
    for dataset,m,lo,hi in ordered:
        actor.retirement_guard()
        if session.contains(m):continue
        if checked==max_objects:break
        with actor.reader(gid,allow_draining=True) as db:
            key='id' if dataset=='observations' else '(received_at,source,event_id)';marker='?' if dataset=='observations' else '(?,?,?)'
            rows=[dict(r) for r in db.execute('SELECT * FROM '+dataset+' WHERE '+key+'>='+marker+' AND '+key+'<='+marker+' ORDER BY '+('id' if dataset=='observations' else 'received_at,source,event_id')+' LIMIT 1001',(*lo,*hi))]
        if len(rows)>1000 or len(rows)!=m['event_count']:raise Stop('archive/local scope count mismatch')
        for row in rows:actor.verify_ack_row(gid,dataset,row)
        proof,found=verify_archive(m,cloud.download_bytes('market-raw',m['object_path']),{identity(dataset,r) for r in rows})
        if rows:build_manifest(dataset,rows,[(proof,found)])
        session.validate(actor,gid)
        actor.retirement_guard()
        with actor.core:actor.core.execute('INSERT OR REPLACE INTO ab_retire_checks VALUES(?,?,?,?,?)',(gid,m['object_path'],token,digest(m),iso(now)))
        checked+=1
    session.validate(actor,gid)
    actor.retirement_guard()
    ready=all(session.contains(m) for d,m,lo,hi in ordered)
    retired=False;reason=None
    if ready and finalize:
        # Supabase create-only client behavior is not immutable remote storage.
        # Preserve the original fresh final readback and its complete checks.
        # Budget that work as well; never reuse a cached receipt to delete data.
        if len(ordered)>max_objects:
            reason='fresh final readback exceeds object budget'
        elif len(ordered)>max_objects-checked:
            reason='fresh final readback reserved for next cycle'
        else:
            try:actor.retire(gid,cloud,now)
            except RecoveryError:
                with actor.core:actor.core.execute('DELETE FROM ab_retire_checks WHERE gen=?',(gid,))
                raise
            retired=True;checked+=len(ordered)
    return {'status':'retired' if retired else 'ready' if ready and not finalize else 'verifying',
            'objects_checked':checked,'objects_total':len(ordered),'covered_rows':covered,'reason':reason}
