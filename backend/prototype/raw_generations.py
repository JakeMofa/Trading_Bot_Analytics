"""Generated-only A/B/core qualification prototype. NOT imported by production.

One serial caller; SQLite FULL. Independent file commits are recovered through
core intents, never treated as an atomic attached-database WAL transaction.
"""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import fcntl,gzip,hashlib,io,json,os
from pathlib import Path
import sqlite3,sys,time,uuid,threading,re

APP=Path(__file__).resolve().parents[1]/'app'
if str(APP) not in sys.path:sys.path.insert(0,str(APP))
from retention_recovery import verify_archive,build_manifest,identity,COLUMNS
from retention import _manifest_interval

HOURS=72
class Stop(RuntimeError):pass
class Unproven(Stop):pass

def stamp(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if d.tzinfo is None:raise Stop('receipt/source time must be aware')
    return d.astimezone(timezone.utc)
def iso(value):return stamp(value).isoformat(timespec='microseconds')
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def connect(path,ro=False):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1) if ro else sqlite3.connect(path,timeout=5)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
    if ro:db.execute('PRAGMA query_only=ON')
    else:db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    return db

class MemoryArchive:
    """Generated private-object fixture, not a Supabase client or upload."""
    def __init__(self):self.objects={};self.available=True;self.reads=0
    def upload_bytes(self,bucket,path,data):
        if not self.available:raise Stop('archive unavailable')
        if path in self.objects and self.objects[path]!=data:raise Stop('immutable object collision')
        self.objects[path]=data
    def download_bytes(self,bucket,path):
        if not self.available:raise Stop('archive unavailable')
        self.reads+=1;return self.objects[path]

class Store:
    def __init__(self,root,ceiling=2*1024**3,core_ceiling=None,fault=None):
        if Path(root).is_symlink():raise Stop('generated root symlink forbidden')
        self.root=Path(root).resolve();self.ceiling=ceiling;self.core_ceiling=core_ceiling or ceiling
        if (not self.root.name.startswith('generated-ab-') or self.root.stat().st_uid!=os.getuid()
            or self.root.stat().st_mode&0o077 or Path('/opt/tradebot') in self.root.parents):raise Stop('private generated fixture required')
        self.fault=fault or (lambda phase:None);self._connections=threading.local();self.owner_thread=threading.get_ident();self.worker_count=0;self.wal_peaks={};self.peak=0;self.leases={};self.readerlock=threading.RLock();self.last_rotation_seconds=0
        self.lock=(self.root/'owner.lock').open('a+');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (self.root/'core.db').is_symlink():raise Stop('symlink forbidden')
        self.core=connect(self.root/'core.db')
        self.core.executescript('''
CREATE TABLE IF NOT EXISTS generations(id TEXT PRIMARY KEY,slot TEXT,state TEXT,started TEXT,sealed_at TEXT,newest TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON generations(state) WHERE state='active';
CREATE UNIQUE INDEX IF NOT EXISTS one_live_slot ON generations(slot) WHERE state!='retired';
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,dataset TEXT,event_key TEXT,gen TEXT REFERENCES generations(id),fingerprint TEXT,status TEXT,intent TEXT,UNIQUE(dataset,event_key));
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_intent ON events(status) WHERE status='pending';
CREATE INDEX IF NOT EXISTS events_generation ON events(gen,dataset,status,id);
CREATE TABLE IF NOT EXISTS markets(id TEXT PRIMARY KEY,metadata TEXT);
CREATE TABLE IF NOT EXISTS outcomes(market_id TEXT PRIMARY KEY REFERENCES markets(id),known_at TEXT,detail TEXT);
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY REFERENCES events(id),record TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,market_id TEXT REFERENCES markets(id),as_of TEXT,value TEXT,evidence_id INTEGER REFERENCES evidence(id));
CREATE TABLE IF NOT EXISTS required_evidence(event_id INTEGER PRIMARY KEY REFERENCES events(id));
CREATE TRIGGER IF NOT EXISTS protect_retired_reference BEFORE INSERT ON required_evidence
WHEN (SELECT state FROM generations WHERE id=(SELECT gen FROM events WHERE id=NEW.event_id)) IN ('retiring','retired')
 AND NOT EXISTS(SELECT 1 FROM evidence WHERE id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'protected evidence required'); END;
CREATE TABLE IF NOT EXISTS manifests(gen TEXT REFERENCES generations(id),dataset TEXT,path TEXT PRIMARY KEY,metadata TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS manifests_generation ON manifests(gen,dataset);
''')
        self.core.commit()
        try:self.recover();self.guard()
        except BaseException:self.core.close();self.lock.close();raise
    @property
    def core(self):
        if not hasattr(self._connections,'db'):self._connections.db=connect(self.root/'core.db')
        return self._connections.db
    @core.setter
    def core(self,value):self._connections.db=value
    @contextmanager
    def worker_session(self):
        if threading.get_ident()==self.owner_thread:raise Stop('worker must own its connection')
        with self.readerlock:self.worker_count+=1
        try:yield self
        finally:
            if hasattr(self._connections,'db'):self._connections.db.close();del self._connections.db
            with self.readerlock:self.worker_count-=1
    def close(self):
        if self.worker_count:raise Stop('drain workers before closing')
        self.core.close();self.lock.close()
    def trip(self,name):self.fault(name)
    def allocation(self):
        values={}
        for p in self.root.rglob('*'):
            try:
                if p.is_file() and p.name!='owner.lock':values[str(p.relative_to(self.root))]=p.stat().st_size
            except FileNotFoundError:pass
        for name,size in values.items():
            if name.endswith('-wal'):self.wal_peaks[name]=max(size,self.wal_peaks.get(name,0))
        total=sum(values.values());self.peak=max(self.peak,total)
        return {'files':values,'total_bytes':total,'peak_bytes':self.peak}
    def guard(self):
        a=self.allocation();c=sum(v for n,v in a['files'].items() if n.startswith('core.db'))
        if a['total_bytes']>=self.ceiling or c>=self.core_ceiling:raise Stop('aggregate/core physical guard STOP')
    def path(self,gid):
        if not re.fullmatch('[0-9a-f]{32}',gid):raise Stop('invalid generation identity')
        p=self.root/('raw-'+gid+'.db')
        if p.is_symlink():raise Stop('raw symlink')
        return p
    def _create(self,gid):
        p=self.path(gid)
        if p.is_symlink():raise Stop('raw symlink')
        db=connect(p)
        db.executescript('''
CREATE TABLE IF NOT EXISTS generation(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,market_id TEXT NOT NULL,received_at TEXT NOT NULL,source_time TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stream_events(source TEXT NOT NULL,event_id TEXT NOT NULL,received_at TEXT NOT NULL,source_time TEXT NOT NULL,price TEXT NOT NULL,size TEXT,side TEXT,payload TEXT NOT NULL,source_key TEXT NOT NULL,PRIMARY KEY(source,event_id));
CREATE INDEX IF NOT EXISTS obs_receipt ON observations(received_at,id);
CREATE INDEX IF NOT EXISTS obs_market ON observations(market_id,received_at,id);
CREATE INDEX IF NOT EXISTS stream_receipt ON stream_events(received_at,source,event_id);
CREATE INDEX IF NOT EXISTS stream_source ON stream_events(source_key,received_at);
''')
        value=db.execute('SELECT id FROM generation').fetchone()
        if value is None:db.execute('INSERT INTO generation VALUES(?)',(gid,));db.commit()
        elif value[0]!=gid:raise Stop('wrong generation identity')
        db.close()
    def _publish(self,row):
        with self.core:
            self.core.execute("UPDATE generations SET state='sealed',sealed_at=? WHERE state='active'",(row['started'],))
            self.core.execute("UPDATE generations SET state='active' WHERE id=?",(row['id'],))
    def recover(self):
        for row in self.core.execute("SELECT * FROM generations WHERE state='preparing'").fetchall():
            self._create(row['id']);self._publish(row)
        for row in self.core.execute("SELECT * FROM events WHERE status='pending' ORDER BY id").fetchall():self._finish(row)
        for row in self.core.execute("SELECT * FROM generations WHERE state='retiring'").fetchall():
            if not self.path(row['id']).exists():
                if any(Path(str(self.path(row['id']))+x).exists() for x in ('-wal','-shm')):raise Stop('orphan sidecars')
                with self.core:self.core.execute("UPDATE generations SET state='retired' WHERE id=?",(row['id'],))
            # A surviving file requires fresh archive/drain verification. No unlink on startup.
    def active(self):return self.core.execute("SELECT * FROM generations WHERE state='active'").fetchone()
    def rotate(self,receipt):
        if threading.get_ident()!=self.owner_thread:raise Stop('collector owns handoff')
        at=iso(receipt);old=self.active()
        if old and stamp(at)<stamp(old['started'])+timedelta(hours=HOURS):return old['id']
        begun=time.monotonic();self.guard()
        occupied={r[0] for r in self.core.execute("SELECT slot FROM generations WHERE state!='retired'")}
        slot=next((x for x in ('A','B') if x not in occupied),None)
        if slot is None:raise Stop('both slots retained: bounded ingestion STOP, no backlog')
        gid=uuid.uuid4().hex
        with self.core:self.core.execute('INSERT INTO generations VALUES(?,?,?,?,?,?)',(gid,slot,'preparing',at,None,None))
        self.trip('rotation_planned');self._create(gid);self.trip('rotation_file_created')
        row=self.core.execute('SELECT * FROM generations WHERE id=?',(gid,)).fetchone();self._publish(row)
        self.trip('rotation_published');self.last_rotation_seconds=time.monotonic()-begun
        return gid
    def save(self,dataset,key,row):
        if threading.get_ident()!=self.owner_thread:raise Stop('exactly one raw writer')
        if dataset not in COLUMNS:raise Stop('unsupported raw dataset')
        if not isinstance(key,str) or not 1<=len(key)<=512:raise Stop('event identity required')
        self.guard();r=dict(row);r['received_at']=iso(r['received_at'])
        if dataset=='stream_events' and key!=r['source']+':'+r['event_id']:raise Stop('source identity mismatch')
        if set(r)-set(COLUMNS[dataset]):raise Stop('unsupported raw fields')
        if dataset=='stream_events' and (not isinstance(r['price'],str) or not Decimal(r['price']).is_finite()):raise Stop('exact decimal text required')
        if r.get('source_time') is not None:stamp(r['source_time'])
        json.loads(r['payload'],parse_float=Decimal) # original text is retained
        fp=digest({k:v for k,v in r.items() if k not in ('received_at','id')})
        prior=self.core.execute('SELECT * FROM events WHERE dataset=? AND event_key=?',(dataset,key)).fetchone()
        if prior:
            if prior['fingerprint']!=fp:raise Stop('conflicting duplicate')
            if prior['status']=='pending':self._finish(prior)
            return prior['id']
        if self.core.execute("SELECT 1 FROM events WHERE status='pending'").fetchone():raise Stop('pending intent must recover before another event')
        active=self.active()
        if active and r['received_at']<active['started']:raise Stop('receipt regression; source lateness is allowed')
        gid=self.rotate(r['received_at'])
        intent=canonical(r)
        with self.core:
            if dataset=='observations':self.core.execute('INSERT OR IGNORE INTO markets VALUES(?,?)',(r['market_id'],'{}'))
            cur=self.core.execute('INSERT INTO events(dataset,event_key,gen,fingerprint,status,intent) VALUES(?,?,?,?,?,?)',(dataset,key,gid,fp,'pending',intent));eid=cur.lastrowid
        self.trip('intent_committed');record=self.core.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone();self._finish(record)
        try:self.guard()
        except Stop as error:error.committed_id=eid;raise
        return eid
    def _finish(self,event):
        r=json.loads(event['intent']);dataset=event['dataset']
        if dataset=='observations':r['id']=event['id']
        cols=COLUMNS[dataset];db=connect(self.path(event['gen']))
        try:
            if db.execute('SELECT id FROM generation').fetchone()[0]!=event['gen']:raise Stop('wrong raw identity')
            where='id=?' if dataset=='observations' else 'source=? AND event_id=?'
            key=(event['id'],) if dataset=='observations' else (r['source'],r['event_id'])
            prior=db.execute('SELECT '+','.join(cols)+' FROM '+dataset+' WHERE '+where,key).fetchone()
            if prior is not None:
                if dict(prior)!={c:r[c] for c in cols}:raise Stop('intent/raw mismatch')
            else:
                fields=cols+('source_key',) if dataset=='stream_events' else cols
                values=tuple(r[c] for c in cols)+((iso(r['source_time']),) if dataset=='stream_events' else ())
                with db:db.execute('INSERT INTO '+dataset+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',values)
            self.allocation();self.trip('raw_committed')
        finally:db.close()
        with self.core:
            self.core.execute("UPDATE events SET status='committed',intent=NULL WHERE id=?",(event['id'],))
            self.core.execute('UPDATE generations SET newest=MAX(COALESCE(newest,?),?) WHERE id=?',(r['received_at'],r['received_at'],event['gen']))
        self.trip('intent_acknowledged')
    @contextmanager
    def reader(self,gid):
        with self.readerlock:
            db=connect(self.path(gid),True)
            if db.execute('SELECT id FROM generation').fetchone()[0]!=gid:db.close();raise Stop('wrong raw identity')
            self.leases[gid]=self.leases.get(gid,0)+1
        try:yield db
        finally:
            with self.readerlock:db.close();self.leases[gid]-=1
    def history(self,dataset,start,end,market=None,source_cutoff=None,limit=10000):
        if not 1<=limit<=10000:raise Stop('bounded history required')
        result=[]
        registry=connect(self.root/'core.db',True)
        try:generations=registry.execute("SELECT * FROM generations WHERE state IN ('active','sealed','retiring') ORDER BY started").fetchall()
        finally:registry.close()
        for g in generations:
            with self.reader(g['id']) as db:
                q='SELECT * FROM '+dataset+' WHERE received_at>=? AND received_at<=?';args=[iso(start),iso(end)]
                if market is not None and dataset=='observations':q+=' AND market_id=?';args.append(market)
                if source_cutoff is not None:q+=' AND source_key<=?';args.append(iso(source_cutoff))
                q+=' ORDER BY received_at LIMIT ?';args.append(limit+1)
                for r in db.execute(q,args):result.append({'generation_id':g['id'],**dict(r)})
        result.sort(key=lambda r:(r['received_at'],canonical(identity(dataset,r))))
        if len(result)>limit:raise Stop('history bound exceeded; no silent truncation')
        return result
    def inputs(self,start,asof):
        rows=self.history('stream_events',start,asof,source_cutoff=asof)
        prices=[Decimal(r['price']) for r in rows]
        return {'count':len(prices),'mean':str(sum(prices)/len(prices)) if prices else None,'latest_source':max((r['source_time'] for r in rows),default=None,key=stamp)}
    def protect(self,event_id,prediction,market,asof):
        event=self.core.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event or event['status']!='committed':raise Stop('unknown evidence identity')
        with self.reader(event['gen']) as db:
            if event['dataset']=='observations':raw=db.execute('SELECT * FROM observations WHERE id=?',(event_id,)).fetchone()
            else:raw=db.execute('SELECT * FROM stream_events WHERE source=? AND event_id=?',tuple(event['event_key'].split(':',1))).fetchone()
        if raw is None:raise Stop('evidence unavailable')
        if stamp(raw['received_at'])>stamp(asof) or (raw['source_time'] and stamp(raw['source_time'])>stamp(asof)):raise Stop('future evidence')
        record={'generation_id':event['gen'],'dataset':event['dataset'],'row':dict(raw)};text=canonical(record)
        with self.core:
            self.core.execute('INSERT OR IGNORE INTO markets VALUES(?,?)',(market,'{}'))
            self.core.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(event_id,text,hashlib.sha256(text.encode()).hexdigest()))
            self.core.execute('INSERT INTO predictions VALUES(?,?,?,?,?)',(prediction,market,iso(asof),'0.5',event_id))
            self.core.execute('INSERT OR IGNORE INTO required_evidence VALUES(?)',(event_id,))
    def archive_hour(self,cloud,now,limit=1000):
        if not 1<=limit<=1000:raise Stop('archive batch limit')
        boundary=stamp(now).replace(minute=0,second=0,microsecond=0);done=0
        for gen in self.core.execute("SELECT * FROM generations WHERE state IN ('active','sealed')").fetchall():
            for dataset in COLUMNS:
                manifests=[json.loads(r[0]) for r in self.core.execute('SELECT metadata FROM manifests WHERE gen=? AND dataset=?',(gen['id'],dataset))]
                with self.reader(gen['id']) as db:
                    if dataset=='observations':
                        lo=max((m['last_source_id'] for m in manifests),default=0)
                        rows=[dict(r) for r in db.execute('SELECT * FROM observations WHERE id>? AND received_at<? ORDER BY id LIMIT ?',(lo,iso(boundary),limit))]
                    else:
                        last=max(((m['ended_at'],*json.loads(m['metadata']['last_source_key'])) for m in manifests),default=('', '', ''))
                        rows=[dict(r) for r in db.execute('SELECT * FROM stream_events WHERE (received_at,source,event_id)>(?,?,?) AND received_at<? ORDER BY received_at,source,event_id LIMIT ?',(*last,iso(boundary),limit))]
                if not rows:continue
                # Embed validated original JSON text without float conversion.
                lines=[]
                for r in rows:
                    payload=r['payload'];json.loads(payload,parse_float=Decimal)
                    base=canonical({k:v for k,v in r.items() if k!='payload'})
                    lines.append('{"dataset":'+json.dumps(dataset)+',"row":'+base[:-1]+',"payload":'+payload+'}}')
                raw=('\n'.join(lines)+'\n').encode();compressed=gzip.compress(raw,mtime=0)
                if len(raw)>256*1024**2 or len(compressed)>64*1024**2:raise Stop('archive resource STOP')
                first,last=rows[0],rows[-1];sha=hashlib.sha256(compressed).hexdigest();path=gen['id']+'/'+dataset+'/'+sha+'.jsonl.gz'
                meta={'dataset':dataset,'generation_id':gen['id'],'verification':'authenticated_readback_sha256','first_source_key':canonical([first['source'],first['event_id']]) if dataset=='stream_events' else None,'last_source_key':canonical([last['source'],last['event_id']]) if dataset=='stream_events' else None}
                m={'source':'polymarket' if dataset=='observations' else 'coinbase','bucket':'market-raw','object_path':path,'sha256':sha,'event_count':len(rows),'compressed_bytes':len(compressed),'first_source_id':first.get('id'),'last_source_id':last.get('id'),'started_at':first['received_at'],'ended_at':last['received_at'],'verified_at':iso(now),'metadata':meta}
                cloud.upload_bytes('market-raw',path,compressed)
                readback=cloud.download_bytes('market-raw',path)
                proof,found=verify_archive(m,readback,{identity(dataset,r) for r in rows});build_manifest(dataset,rows,[(proof,found)])
                self.trip('archive_readback_verified')
                with self.core:self.core.execute('INSERT OR IGNORE INTO manifests VALUES(?,?,?,?)',(gen['id'],dataset,path,canonical(m)))
                done+=len(rows)
        self.guard();return done
    def _owners(self,gid):
        identities=set()
        for suffix in ('','-wal','-shm'):
            p=Path(str(self.path(gid))+suffix)
            if p.exists():s=p.stat();identities.add((s.st_dev,s.st_ino))
        if sys.platform!='linux':raise Unproven('complete OS descriptor drain requires Linux; no local unlink')
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                for fd in (p/'fd').iterdir():
                    try:s=fd.stat()
                    except FileNotFoundError:continue
                    if (s.st_dev,s.st_ino) in identities:return True
            except FileNotFoundError:continue
            except PermissionError:raise Unproven('descriptor visibility incomplete')
        return False
    def retire(self,gid,cloud,now):
        gen=self.core.execute('SELECT * FROM generations WHERE id=?',(gid,)).fetchone()
        if not gen or gen['state'] not in ('sealed','retiring'):raise Stop('not a sealed generation')
        if gen['newest'] and stamp(now)-stamp(gen['newest'])<=timedelta(hours=72):raise Stop('strict72h retention not passed')
        if self.leases.get(gid):raise Stop('reader lease open')
        # Stream <=1000 local rows/object. Do not materialize a full generation.
        for dataset in COLUMNS:
            with self.reader(gid) as db:expected_count=db.execute('SELECT COUNT(*) FROM '+dataset).fetchone()[0]
            ledger_count=self.core.execute("SELECT COUNT(*) FROM events WHERE gen=? AND dataset=? AND status='committed'",(gid,dataset)).fetchone()[0]
            if ledger_count!=expected_count:raise Stop('registry/raw row count mismatch')
            entries=self.core.execute('SELECT metadata FROM manifests WHERE gen=? AND dataset=? LIMIT 10001',(gid,dataset)).fetchall()
            if len(entries)>10000:raise Stop('bounded manifest budget')
            manifests=[json.loads(row[0]) for row in entries]
            manifests.sort(key=lambda m:_manifest_interval(dataset,m,'market-raw')[0])
            previous=None;covered=0
            for m in manifests:
                if m['metadata'].get('generation_id')!=gid or not m['object_path'].startswith(gid+'/'):raise Stop('generation archive identity mismatch')
                lo,hi=_manifest_interval(dataset,m,'market-raw')
                if previous is not None and lo<=previous:raise Stop('overlapping archive identities')
                previous=hi
                with self.reader(gid) as db:
                    key='id' if dataset=='observations' else '(received_at,source,event_id)'
                    marker='?' if dataset=='observations' else '(?,?,?)'
                    rows=[dict(r) for r in db.execute('SELECT * FROM '+dataset+' WHERE '+key+'>='+marker+' AND '+key+'<='+marker+' ORDER BY '+('id' if dataset=='observations' else 'received_at,source,event_id')+' LIMIT 1001',(*lo,*hi))]
                if len(rows)>1000 or len(rows)!=m['event_count']:raise Stop('archive/local scope count mismatch')
                requested={identity(dataset,r) for r in rows}
                proof,found=verify_archive(m,cloud.download_bytes('market-raw',m['object_path']),requested)
                if rows:build_manifest(dataset,rows,[(proof,found)])
                covered+=len(rows)
            if covered!=expected_count:raise Stop('archive coverage incomplete')
        with self.readerlock:
            self.core.execute('BEGIN IMMEDIATE')
            try:
                current=self.core.execute('SELECT state FROM generations WHERE id=?',(gid,)).fetchone()
                if current[0] not in ('sealed','retiring'):raise Stop('generation changed')
                for row in self.core.execute('SELECT e.id FROM events e JOIN required_evidence r ON e.id=r.event_id WHERE e.gen=?',(gid,)):
                    evidence=self.core.execute('SELECT record,sha256 FROM evidence WHERE id=?',tuple(row)).fetchone()
                    if not evidence or hashlib.sha256(evidence[0].encode()).hexdigest()!=evidence[1]:raise Stop('protected evidence unavailable')
                    if json.loads(evidence[0])['generation_id']!=gid:raise Stop('protected generation mismatch')
                if self.leases.get(gid) or self._owners(gid):raise Stop('raw database handles open')
                self.core.execute("UPDATE generations SET state='retiring' WHERE id=?",(gid,));self.core.commit()
            except BaseException:self.core.rollback();raise
            self.trip('retirement_authorized');self._remove(gid)
    def _remove(self,gid):
        if self.leases.get(gid) or self._owners(gid):raise Stop('retirement drain not proven')
        # Read-only readers can leave empty sidecars. An ordinary metadata
        # connection/close lets SQLite perform its normal last-close cleanup.
        # No checkpoint pragma, truncation or sidecar unlink is issued.
        if self.path(gid).exists():
            db=connect(self.path(gid))
            try:
                if db.execute('SELECT id FROM generation').fetchone()[0]!=gid:raise Stop('wrong close identity')
            finally:db.close()
            self.trip('retirement_normal_close')
        if self._owners(gid):raise Stop('handle opened before unlink')
        if any(Path(str(self.path(gid))+suffix).exists() for suffix in ('-wal','-shm')):raise Stop('sidecars remain; no manual WAL deletion')
        if self.path(gid).exists():self.path(gid).unlink()
        self.trip('retirement_file_removed')
        with self.core:self.core.execute("UPDATE generations SET state='retired' WHERE id=?",(gid,))

class FileArchive(MemoryArchive):
    """Generated objects on disk so archive working space is actually measured."""
    def __init__(self,root):super().__init__();self.root=Path(root);self.root.mkdir(mode=0o700)
    def upload_bytes(self,bucket,path,data):
        if '..' in Path(path).parts or Path(path).is_absolute():raise Stop('bad fixture object path')
        super().upload_bytes(bucket,path,data)
        p=self.root/path;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not p.exists():
            with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    def download_bytes(self,bucket,path):
        if not self.available:raise Stop('archive unavailable')
        self.reads+=1;return (self.root/path).read_bytes()
