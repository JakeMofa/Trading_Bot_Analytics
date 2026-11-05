"""Generated-only A/B/core qualification prototype. NOT imported by production.

One serial caller; SQLite FULL. Independent file commits are recovered through
core intents, never treated as an atomic attached-database WAL transaction.
"""
from contextlib import contextmanager,closing
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
def connect(path,ro=False,sealed_legacy=False):
    path=Path(path)
    sealed=False
    if sealed_legacy and ro and not path.is_symlink() and path.is_file():
        main=path.stat();parent=path.parent.stat()
        sealed=main.st_uid==0 and not main.st_mode&0o222 and parent.st_uid==0 and bool(parent.st_mode&0o1000)
    for component in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm')):
        if component.is_symlink():raise Stop('SQLite component symlink forbidden')
        if component.exists() and component.stat().st_uid!=os.getuid():
            owned=component.stat()
            if not (sealed and owned.st_uid==0 and not owned.st_mode&0o022):raise Stop('unexpected SQLite component owner')
    if any(p.name not in (path.name+'-wal',path.name+'-shm') for p in path.parent.glob(path.name+'-*')):
        raise Stop('unknown SQLite sidecar: verification required')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1) if ro else sqlite3.connect(path,timeout=5)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
    if ro:db.execute('PRAGMA query_only=ON')
    else:db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    return db

class MemoryArchive:
    """Generated private-object fixture, not a Supabase client or upload."""
    def __init__(self):self.objects={};self.manifests={};self.available=True;self.reads=0
    def upload_bytes(self,bucket,path,data,content_type="application/gzip"):
        if not self.available:raise Stop('archive unavailable')
        if path in self.objects and self.objects[path]!=data:raise Stop('immutable object collision')
        self.objects[path]=data
    def upsert(self,table,rows,on_conflict):
        if not self.available:raise Stop('archive metadata unavailable')
        if table!='raw_archives' or on_conflict!='bucket,object_path':raise Stop('fixture raw manifests only')
        for row in rows:self.manifests[(row['bucket'],row['object_path'])]=row
    def download_bytes(self,bucket,path):
        if not self.available:raise Stop('archive unavailable')
        self.reads+=1;return self.objects[path]

class Store:
    def __init__(self,root,ceiling=2*1024**3,core_ceiling=None,fault=None,application_namespace=False, generation_bytes=None, initial_slot="A", recovery_deadline=None):
        if generation_bytes is not None and (type(generation_bytes) is not int or not 0 < generation_bytes < ceiling):
            raise Stop('generation size threshold must be positive and below aggregate ceiling')
        if initial_slot not in ("A","B"):raise Stop("invalid initial slot")
        self.recovery_deadline=recovery_deadline or time.monotonic()+170
        self.initial_slot=initial_slot
        self.generation_bytes = generation_bytes
        if Path(root).is_symlink():raise Stop('generated root symlink forbidden')
        self.application_namespace=application_namespace;self._application_writer=threading.local()
        self.root=Path(root).resolve();self.ceiling=ceiling;self.core_ceiling=core_ceiling or ceiling
        if (not self.root.name.startswith('generated-ab-') or self.root.stat().st_uid!=os.getuid()
            or self.root.stat().st_mode&0o077 or Path('/opt/tradebot') in self.root.parents):raise Stop('private generated fixture required')
        self.fault=fault or (lambda phase:None);self._connections=threading.local();self.owner_thread=threading.get_ident();self.worker_count=0;self.wal_peaks={};self.peak=0;self.leases={};self.readerlock=threading.RLock();self.last_rotation_seconds=0
        if (self.root/'owner.lock').is_symlink():raise Stop('owner lock symlink forbidden')
        self.lock=(self.root/'owner.lock').open('a+')
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise
        if (self.root/'core.db').is_symlink():raise Stop('symlink forbidden')
        self.core=connect(self.root/'core.db')
        self.core.executescript('''
CREATE TABLE IF NOT EXISTS generations(id TEXT PRIMARY KEY,slot TEXT,state TEXT,started TEXT,sealed_at TEXT,newest TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON generations(state) WHERE state='active';
CREATE UNIQUE INDEX IF NOT EXISTS one_live_slot ON generations(slot) WHERE state!='retired';
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,dataset TEXT,event_key TEXT,gen TEXT REFERENCES generations(id),fingerprint TEXT,status TEXT,intent TEXT,UNIQUE(dataset,event_key));
CREATE TABLE IF NOT EXISTS raw_receipts(id INTEGER PRIMARY KEY REFERENCES events(id),sha256 TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_intent ON events(status) WHERE status='pending';
CREATE INDEX IF NOT EXISTS events_generation ON events(gen,dataset,status,id);
CREATE TABLE IF NOT EXISTS markets(id TEXT PRIMARY KEY,metadata TEXT);
CREATE TABLE IF NOT EXISTS outcomes(market_id TEXT PRIMARY KEY REFERENCES markets(id),known_at TEXT,detail TEXT);
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY REFERENCES events(id),record TEXT NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,market_id TEXT REFERENCES markets(id),as_of TEXT,value TEXT,evidence_id INTEGER REFERENCES evidence(id));
CREATE TABLE IF NOT EXISTS feature_snapshots(id INTEGER PRIMARY KEY,market_id TEXT REFERENCES markets(id),as_of TEXT,version INTEGER,values_json TEXT,quality_json TEXT,evidence_json TEXT,UNIQUE(market_id,as_of,version));
CREATE TABLE IF NOT EXISTS prediction_details(id TEXT PRIMARY KEY REFERENCES predictions(id),snapshot_id INTEGER REFERENCES feature_snapshots(id),model_version TEXT,abstain_reason TEXT);
CREATE TABLE IF NOT EXISTS candles(source TEXT,symbol TEXT,granularity INTEGER,time INTEGER,low TEXT,high TEXT,open TEXT,close TEXT,volume TEXT,first_seen TEXT,PRIMARY KEY(source,symbol,granularity,time));
CREATE TABLE IF NOT EXISTS reference_prices(id INTEGER PRIMARY KEY,received_at TEXT,source_time TEXT,source TEXT,price TEXT,payload TEXT);
CREATE INDEX IF NOT EXISTS reference_features_price ON reference_prices(source,julianday(source_time) DESC,id);
CREATE TABLE IF NOT EXISTS metadata_pins(event_id INTEGER PRIMARY KEY REFERENCES evidence(id),market_id TEXT,received_at TEXT);
CREATE INDEX IF NOT EXISTS metadata_pins_market ON metadata_pins(market_id,julianday(received_at) DESC,event_id DESC);
CREATE TABLE IF NOT EXISTS required_evidence(event_id INTEGER PRIMARY KEY REFERENCES events(id));
CREATE TRIGGER IF NOT EXISTS protect_retired_reference BEFORE INSERT ON required_evidence
WHEN (SELECT state FROM generations WHERE id=(SELECT gen FROM events WHERE id=NEW.event_id)) IN ('retiring','retired')
 AND NOT EXISTS(SELECT 1 FROM evidence WHERE id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'protected evidence required'); END;
CREATE TABLE IF NOT EXISTS manifests(gen TEXT REFERENCES generations(id),dataset TEXT,path TEXT PRIMARY KEY,metadata TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS manifests_generation ON manifests(gen,dataset);
''')
        self.core.executescript("""CREATE TRIGGER IF NOT EXISTS protect_draining_reference
BEFORE INSERT ON required_evidence
WHEN (SELECT state FROM generations WHERE id=(SELECT gen FROM events WHERE id=NEW.event_id))='draining'
 AND NOT EXISTS(SELECT 1 FROM evidence WHERE id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'protected evidence required while draining'); END;""")
        self.core.commit()
        try:self.recover();self.guard()
        except BaseException:self.core.close();self.lock.close();raise
    @property
    def core(self):
        if not hasattr(self._connections,'db'):self.core=connect(self.root/'core.db')
        return self._connections.db
    @core.setter
    def core(self,value):
        if self.application_namespace:
            from protocol_namespace import ProtocolConnection
            value=ProtocolConnection(value)
        self._connections.db=value
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
        def accounted(st):
            return max(st.st_size,st.st_blocks*512) if getattr(self,'physical_accounting',False) else st.st_size
        for p in self.root.rglob('*'):
            try:
                if p.is_file() and p.name!='owner.lock':values[str(p.relative_to(self.root))]=accounted(p.stat())
            except FileNotFoundError:pass
        for path in getattr(self,'external_files',()):
            if path.is_symlink():
                raise Stop('external legacy component symlink')
            try:
                values['legacy-external/'+path.name]=accounted(path.stat())
            except FileNotFoundError:
                pass
        for name,size in values.items():
            if name.endswith('-wal'):self.wal_peaks[name]=max(size,self.wal_peaks.get(name,0))
        if Path('/proc/self/fd').exists():
            for fd in Path('/proc/self/fd').iterdir():
                try:
                    target=os.readlink(fd)
                    if target.startswith(str(self.root)) and target.endswith(' (deleted)'):
                        st=fd.stat();values['unlinked:'+str(st.st_dev)+':'+str(st.st_ino)]=accounted(st)
                except FileNotFoundError:pass
        total=sum(values.values());self.peak=max(self.peak,total)
        return {'files':values,'total_bytes':total,'peak_bytes':self.peak}
    def guard(self):
        a=self.allocation();c=sum(v for n,v in a['files'].items() if n.startswith('core.db'))
        if a['total_bytes']>=self.ceiling or c>=self.core_ceiling:raise Stop('aggregate/core physical guard STOP')
        if getattr(self,'fresh_layout_limit',None):
            for (gid,) in self.core.execute("SELECT id FROM generations WHERE state!='retired'"):
                used=sum(v for n,v in a['files'].items() if n.startswith('raw-'+gid+'.db'))
                if used>=getattr(self,'fresh_slot_limit',64*1024**2):raise Stop('fresh per-slot allocation STOP')
            retained=sum(v for n,v in a['files'].items() if n.startswith('legacy-external/') or n in self.retained_legacy_names)
            if a['total_bytes']-retained>=self.fresh_layout_limit:raise Stop('fresh layout quota STOP')
            if self.ceiling-a['total_bytes']<512*1024**2:raise Stop('fresh-B recovery headroom STOP')
            fs=os.statvfs(self.root)
            if fs.f_bavail*fs.f_frsize<10*1024**3:raise Stop('fresh-B filesystem floor STOP')
    def path(self,gid):
        if not re.fullmatch('[0-9a-f]{32}',gid):raise Stop('invalid generation identity')
        p=self.root/('raw-'+gid+'.db')
        if p.is_symlink():raise Stop('raw symlink')
        return p
    def _create(self,gid):
        p=self.path(gid)
        if p.is_symlink():raise Stop('raw symlink')
        with closing(connect(p)) as db:
            db.executescript('''
    CREATE TABLE IF NOT EXISTS generation(id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,market_id TEXT NOT NULL,received_at TEXT NOT NULL,source_time TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS stream_events(source TEXT NOT NULL,event_id TEXT NOT NULL,received_at TEXT NOT NULL,source_time TEXT NOT NULL,price TEXT NOT NULL,size TEXT,side TEXT,payload TEXT NOT NULL,source_key TEXT NOT NULL,PRIMARY KEY(source,event_id));
    CREATE INDEX IF NOT EXISTS obs_receipt ON observations(received_at,id);
    CREATE INDEX IF NOT EXISTS obs_market ON observations(market_id,received_at,id);
    CREATE INDEX IF NOT EXISTS stream_receipt ON stream_events(received_at,source,event_id);
    CREATE INDEX IF NOT EXISTS stream_source ON stream_events(source_key,received_at);
    CREATE INDEX IF NOT EXISTS stream_features_price ON stream_events(source,julianday(source_time) DESC,event_id);
    CREATE INDEX IF NOT EXISTS obs_features_metadata ON observations(market_id,kind,julianday(received_at) DESC,id DESC);
    ''')
            from application_validation import header
            header(db,{'observations':COLUMNS['observations'],'stream_events':COLUMNS['stream_events']+('source_key',),'generation':('id',)},exact=True)
            identities=db.execute('SELECT id FROM generation LIMIT 2').fetchall()
            if len(identities)>1:raise Stop('ambiguous generation identity')
            value=identities[0] if identities else None
            if value is None:db.execute('INSERT INTO generation VALUES(?)',(gid,));db.commit()
            elif value[0]!=gid:raise Stop('wrong generation identity')
    def _publish(self,row):
        with self.core:
            self.core.execute("UPDATE generations SET state='sealed',sealed_at=? WHERE state='active'",(row['started'],))
            self.core.execute("UPDATE generations SET state='active' WHERE id=?",(row['id'],))
    def recover(self):
        states=self.core.execute("SELECT slot,state,count(*) FROM generations GROUP BY slot,state").fetchall()
        live=[(slot,state,n) for slot,state,n in states if state!='retired']
        if any(slot not in ('A','B') or state not in ('preparing','active','sealed','draining','retiring','retired') for slot,state,n in states):raise Stop('invalid generation registry state')
        if sum(n for slot,state,n in live)>2 or any(sum(n for s,state,n in live if s==slot)>1 for slot in ('A','B')):raise Stop('ambiguous live generation slots')
        if sum(n for slot,state,n in live if state=='active')>1 or sum(n for slot,state,n in live if state=='preparing')>1:raise Stop('ambiguous generation activation')
        for row in self.core.execute("SELECT * FROM generations WHERE state='preparing'").fetchall():
            self._create(row['id']);self._publish(row)
        for row in self.core.execute("SELECT * FROM events WHERE status='pending' ORDER BY id").fetchall():self._finish(row)
        for row in self.core.execute("SELECT * FROM generations WHERE state='retiring'").fetchall():
            if not self.path(row['id']).exists():
                if any(Path(str(self.path(row['id']))+x).exists() for x in ('-wal','-shm')):raise Stop('orphan sidecars')
                with self.core:self.core.execute("UPDATE generations SET state='retired' WHERE id=?",(row['id'],))
            # A surviving file requires fresh archive/drain verification. No unlink on startup.
        # Verify every acknowledged row in the two owned raw files before
        # accepting more writes. Legacy is deliberately outside this audit.
        from application_validation import header,row_check
        end=self.recovery_deadline
        checked=0
        for generation in self.core.execute("SELECT id FROM generations WHERE state!='retired'").fetchall():
            raw=connect(self.path(generation[0]),True)
            try:
                raw.set_progress_handler(lambda:int(time.monotonic()>=end),1000)
                header(raw,{'observations':COLUMNS['observations'],'stream_events':COLUMNS['stream_events']+('source_key',),'generation':('id',)},exact=True)
                ids=raw.execute('SELECT id FROM generation LIMIT 2').fetchall()
                if len(ids)!=1 or ids[0][0]!=generation[0]:raise Stop('wrong raw identity')
                if [tuple(r) for r in raw.execute('PRAGMA quick_check')]!=[('ok',)]:raise Stop('raw quick_check failed')
                for dataset in COLUMNS:
                    expected=0
                    for event in self.core.execute("SELECT e.id,e.event_key,h.sha256 FROM events e LEFT JOIN raw_receipts h ON h.id=e.id WHERE e.gen=? AND e.dataset=? AND e.status='committed'",(generation[0],dataset)):
                        checked+=1;expected+=1
                        if time.monotonic()>=end:raise Stop('bounded acknowledged recovery audit')
                        where='id=?' if dataset=='observations' else 'source=? AND event_id=?'
                        key=(event[0],) if dataset=='observations' else tuple(event[1].split(':',1))
                        fields=COLUMNS[dataset]+(('source_key',) if dataset=='stream_events' else ())
                        row=raw.execute('SELECT '+','.join(fields)+' FROM '+dataset+' WHERE '+where,key).fetchone()
                        if row is None or digest({c:row[c] for c in COLUMNS[dataset]})!=event[2]:raise Stop('acknowledged raw missing/corrupted')
                        row_check(dataset,dict(row))
                    if raw.execute('SELECT count(*) FROM '+dataset).fetchone()[0]!=expected:raise Stop('raw/acknowledgement count mismatch')
            finally:raw.close()

    def _owns_writer(self):
        return threading.get_ident()==self.owner_thread or (self.application_namespace and getattr(self._application_writer,'authorized',False))
    def active(self):return self.core.execute("SELECT * FROM generations WHERE state='active'").fetchone()
    def rotate(self,receipt):
        if not self._owns_writer():raise Stop('collector owns handoff')
        at=iso(receipt);old=self.active()
        if old and stamp(at)<stamp(old['started'])+timedelta(hours=HOURS):
            if self.generation_bytes is None:
                return old['id']
            raw_path = self.path(old['id'])
            wal_path = Path(str(raw_path)+'-wal')
            size = raw_path.stat().st_size
            try:
                size += wal_path.stat().st_size
            except FileNotFoundError:
                pass
            if size < self.generation_bytes:
                return old['id']
        begun=time.monotonic();self.guard()
        occupied={r[0] for r in self.core.execute("SELECT slot FROM generations WHERE state!='retired'")}
        order=(getattr(self,'initial_slot','A'), 'B' if getattr(self,'initial_slot','A')=='A' else 'A')
        slot=next((x for x in order if x not in occupied),None)
        if slot is None:raise Stop('both slots retained: bounded ingestion STOP, no backlog')
        gid=uuid.uuid4().hex
        with self.core:self.core.execute('INSERT INTO generations VALUES(?,?,?,?,?,?)',(gid,slot,'preparing',at,None,None))
        self.trip('rotation_planned');self._create(gid);self.trip('rotation_file_created')
        row=self.core.execute('SELECT * FROM generations WHERE id=?',(gid,)).fetchone();self._publish(row)
        self.trip('rotation_published');self.last_rotation_seconds=time.monotonic()-begun
        return gid
    def save(self,dataset,key,row):
        if not self._owns_writer():raise Stop('exactly one raw writer')
        if dataset not in COLUMNS:raise Stop('unsupported raw dataset')
        if not isinstance(key,str) or not 1<=len(key)<=512:raise Stop('event identity required')
        self.guard();r=dict(row);r['received_at']=iso(r['received_at'])
        if dataset=='stream_events' and key!=r['source']+':'+r['event_id']:raise Stop('source identity mismatch')
        if set(r)-set(COLUMNS[dataset]):raise Stop('unsupported raw fields')
        if dataset=='stream_events' and (not isinstance(r['price'],str) or not Decimal(r['price']).is_finite()):raise Stop('exact decimal text required')
        if r.get('source_time') is not None:stamp(r['source_time'])
        if not isinstance(r['payload'],str) or len(r['payload'].encode())>1024**2:
            raise Stop('raw payload exceeds qualified 1MiB input bound')
        json.loads(r['payload'],parse_float=Decimal) # original text is retained
        fp=digest({k:v for k,v in r.items() if k not in ('received_at','id')})
        prior=self.core.execute('SELECT * FROM events WHERE dataset=? AND event_key=?',(dataset,key)).fetchone()
        if prior:
            if prior['fingerprint']!=fp:raise Stop('conflicting duplicate')
            if prior['status']=='pending':self._finish(prior)
            return prior['id']
        if getattr(self,'fresh_event_limit',None):
            span=self.core.execute('SELECT COALESCE(MAX(id)-MIN(id)+1,0) FROM events').fetchone()[0]
            if span>=self.fresh_event_limit:raise Stop('fresh persistent event ledger limit STOP')
        if self.core.execute("SELECT 1 FROM events WHERE status='pending'").fetchone():raise Stop('pending intent must recover before another event')
        active=self.active()
        if active and r['received_at']<active['started']:raise Stop('receipt regression; source lateness is allowed')
        gid=self.rotate(r['received_at'])
        intent=canonical(r)
        if len(intent.encode()) > 1024**2:
            raise Stop('raw record exceeds qualified 1MiB input bound')
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
            self.core.execute('INSERT OR REPLACE INTO raw_receipts VALUES(?,?)',(event['id'],digest({c:r[c] for c in cols})))
            self.core.execute("UPDATE events SET status='committed',intent=NULL WHERE id=?",(event['id'],))
            if dataset=='observations' and r['kind']=='metadata':
                self.pin_record(event['id'],{'generation_id':event['gen'],'dataset':dataset,'row':r})
                self.core.execute('INSERT OR IGNORE INTO metadata_pins VALUES(?,?,?)',(event['id'],r['market_id'],r['received_at']))
            self.core.execute('UPDATE generations SET newest=MAX(COALESCE(newest,?),?) WHERE id=?',(r['received_at'],r['received_at'],event['gen']))
        self.trip('intent_acknowledged')
    @contextmanager
    def generation_lease(self, gid, exclusive=False):
        # This file is independent of SQLite. Readers hold a shared lease for
        # their entire attachment lifetime, including across process boundaries.
        lock = self.root / ('lease-'+self.path(gid).stem+'.lock')
        fd = os.open(lock, os.O_CREAT | os.O_RDONLY | os.O_NOFOLLOW, 0o600)
        try:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop('raw reader leases open or retirement in progress') from None
            yield
        finally:
            os.close(fd)

    @contextmanager
    def reader(self, gid, allow_draining=False):
        with self.generation_lease(gid):
            with self.readerlock:
                state = self.core.execute('SELECT state FROM generations WHERE id=?',(gid,)).fetchone()
                allowed = ('active','sealed','draining','retiring') if allow_draining else ('active','sealed')
                if not state or state[0] not in allowed:
                    raise Stop('generation unavailable for new readers')
                db=connect(self.path(gid),True)
                try:
                    from application_validation import header
                    header(db,{'observations':COLUMNS['observations'],'stream_events':COLUMNS['stream_events']+('source_key',),'generation':('id',)},exact=True)
                    identities=db.execute('SELECT id FROM generation LIMIT 2').fetchall()
                    if len(identities)!=1 or identities[0][0]!=gid:raise Stop('wrong raw identity')
                except BaseException:
                    db.close();raise
                self.leases[gid]=self.leases.get(gid,0)+1
            try:
                yield db
            finally:
                with self.readerlock:
                    db.close()
                    self.leases[gid]-=1

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
    def set_market(self,market):
        if market.get('duration')!=900:raise Stop('15-minute market required')
        for field in ('start','end','first_seen'):stamp(market[field])
        with self.core:self.core.execute('INSERT INTO markets VALUES(?,?) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata',(market['id'],canonical(market)))
    def pin_record(self,event_id,record):
        """Called inside caller core transaction; copied evidence and refs atomic."""
        event=self.core.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event or event['status']!='committed' or event['gen']!=record['generation_id'] or event['dataset']!=record['dataset']:raise Stop('wrong evidence identity')
        row={k:record['row'][k] for k in COLUMNS[event['dataset']]}
        if digest({k:v for k,v in row.items() if k not in ('id','received_at')})!=event['fingerprint']:raise Stop('evidence fingerprint changed')
        record={'generation_id':event['gen'],'dataset':event['dataset'],'row':row};text=canonical(record);sha=hashlib.sha256(text.encode()).hexdigest()
        previous=self.core.execute('SELECT sha256 FROM evidence WHERE id=?',(event_id,)).fetchone()
        if previous and previous[0]!=sha:raise Stop('protected evidence is immutable')
        self.core.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(event_id,text,sha))
        self.core.execute('INSERT OR IGNORE INTO required_evidence VALUES(?)',(event_id,))
    def protect(self,event_id,prediction,market,asof):
        event=self.core.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event or event['status']!='committed':raise Stop('unknown evidence identity')
        with self.reader(event['gen'],allow_draining=True) as db:
            if event['dataset']=='observations':raw=db.execute('SELECT * FROM observations WHERE id=?',(event_id,)).fetchone()
            else:raw=db.execute('SELECT * FROM stream_events WHERE source=? AND event_id=?',tuple(event['event_key'].split(':',1))).fetchone()
        if raw is None:raise Stop('evidence unavailable')
        if stamp(raw['received_at'])>stamp(asof) or (raw['source_time'] and stamp(raw['source_time'])>stamp(asof)):raise Stop('future evidence')
        with self.core:
            self.core.execute('INSERT OR IGNORE INTO markets VALUES(?,?)',(market,'{}'))
            self.pin_record(event_id,{'generation_id':event['gen'],'dataset':event['dataset'],'row':dict(raw)})
            self.core.execute('INSERT INTO predictions VALUES(?,?,?,?,?)',(prediction,market,iso(asof),'0.5',event_id))
    def archive_hour(self,cloud,now,limit=1000,*,sealed_generation=None):
        if not 1<=limit<=1000:raise Stop('archive batch limit')
        boundary=stamp(now).replace(minute=0,second=0,microsecond=0);done=0
        for gen in self.core.execute("SELECT * FROM generations WHERE state IN ('active','sealed')").fetchall():
            if sealed_generation is not None and (gen['id'] != sealed_generation or gen['state'] != 'sealed'):
                continue
            cutoff = iso(boundary)
            if gen['state'] == 'sealed' and gen['newest']:
                cutoff = iso(stamp(gen['newest']) + timedelta(microseconds=1))
            for dataset in COLUMNS:
                manifests=[json.loads(r[0]) for r in self.core.execute('SELECT metadata FROM manifests WHERE gen=? AND dataset=?',(gen['id'],dataset))]
                with self.reader(gen['id']) as db:
                    if dataset=='observations':
                        lo=max((m['last_source_id'] for m in manifests),default=0)
                        rows=[dict(r) for r in db.execute('SELECT * FROM observations WHERE id>? AND received_at<? ORDER BY id LIMIT ?',(lo,cutoff,limit))]
                    else:
                        last=max(((m['ended_at'],*json.loads(m['metadata']['last_source_key'])) for m in manifests),default=('', '', ''))
                        rows=[dict(r) for r in db.execute('SELECT * FROM stream_events WHERE (received_at,source,event_id)>(?,?,?) AND received_at<? ORDER BY received_at,source,event_id LIMIT ?',(*last,cutoff,limit))]
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
                m={'source':'polymarket' if dataset=='observations' else 'coinbase','bucket':'market-raw','object_path':path,'sha256':sha,'event_count':len(rows),'compressed_bytes':len(compressed),'first_source_id':first.get('id'),'last_source_id':last.get('id'),'started_at':first['received_at'],'ended_at':last['received_at'],'verified_at':iso(now),'metadata':meta,'compression':'gzip','content_type':'application/jsonl','uncompressed_bytes':len(raw),'market_id':None}
                cloud.upload_bytes('market-raw',path,compressed,'application/gzip')
                readback=cloud.download_bytes('market-raw',path)
                proof,found=verify_archive(m,readback,{identity(dataset,r) for r in rows});build_manifest(dataset,rows,[(proof,found)])
                cloud.upsert('raw_archives',[m],'bucket,object_path')
                self.trip('archive_readback_verified')
                with self.core:self.core.execute('INSERT OR IGNORE INTO manifests VALUES(?,?,?,?)',(gen['id'],dataset,path,canonical(m)))
                done+=len(rows)
        self.guard();return done
    def finish_sealed(self,gid,cloud,now,limit=1000):
        """Background step. A partial batch or failed proof keeps the file."""
        self.archive_hour(cloud,now,limit,sealed_generation=gid)
        self.retire(gid,cloud,now)

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
    def verify_ack_row(self,gid,dataset,row):
        fields={c:row[c] for c in COLUMNS[dataset]}
        if dataset=='observations':
            proof=self.core.execute("SELECT h.sha256 FROM events e LEFT JOIN raw_receipts h ON h.id=e.id WHERE e.id=? AND e.gen=? AND e.dataset='observations' AND e.status='committed'",(row['id'],gid)).fetchone()
        else:
            proof=self.core.execute("SELECT h.sha256 FROM events e LEFT JOIN raw_receipts h ON h.id=e.id WHERE e.event_key=? AND e.gen=? AND e.dataset='stream_events' AND e.status='committed'",(row['source']+':'+row['event_id'],gid)).fetchone()
        if not proof or proof[0]!=digest(fields):raise Stop('acknowledged row proof differs')
        from application_validation import row_check
        row_check(dataset,dict(row))

    def verify_protected(self,gid):
        references=self.core.execute("""
SELECT e.id,e.dataset,e.event_key,p.record,p.sha256
FROM required_evidence r JOIN events e ON e.id=r.event_id
LEFT JOIN evidence p ON p.id=e.id WHERE e.gen=? LIMIT 10001
""",(gid,)).fetchall()
        if len(references)>10000:
            raise Stop('protected reference verification bound')
        raw=connect(self.path(gid),True)
        try:
            for event_id,dataset,key,text,checksum in references:
                if not text or hashlib.sha256(text.encode()).hexdigest()!=checksum:
                    raise Stop('protected evidence unavailable')
                fields=','.join(COLUMNS[dataset])
                if dataset=='observations':
                    row=raw.execute('SELECT '+fields+' FROM observations WHERE id=?',(event_id,)).fetchone()
                else:
                    row=raw.execute('SELECT '+fields+' FROM stream_events WHERE source=? AND event_id=?',
                                    tuple(key.split(':',1))).fetchone()
                expected={'generation_id':gid,'dataset':dataset,'row':dict(row) if row else None}
                if json.loads(text)!=expected:
                    raise Stop('protected evidence differs from sealed raw')
        finally:
            raw.close()

    def retire(self,gid,cloud,now):
        gen=self.core.execute('SELECT * FROM generations WHERE id=?',(gid,)).fetchone()
        if not gen or gen['state'] not in ('sealed','draining','retiring'):raise Stop('not a sealed generation')
        if stamp(now)<stamp(gen['sealed_at']):raise Stop('retirement time precedes seal')
        if self.leases.get(gid):raise Stop('reader lease open')
        # Stream <=1000 local rows/object. Do not materialize a full generation.
        for dataset in COLUMNS:
            with self.reader(gid,allow_draining=True) as db:expected_count=db.execute('SELECT COUNT(*) FROM '+dataset).fetchone()[0]
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
                with self.reader(gid,allow_draining=True) as db:
                    key='id' if dataset=='observations' else '(received_at,source,event_id)'
                    marker='?' if dataset=='observations' else '(?,?,?)'
                    rows=[dict(r) for r in db.execute('SELECT * FROM '+dataset+' WHERE '+key+'>='+marker+' AND '+key+'<='+marker+' ORDER BY '+('id' if dataset=='observations' else 'received_at,source,event_id')+' LIMIT 1001',(*lo,*hi))]
                if len(rows)>1000 or len(rows)!=m['event_count']:raise Stop('archive/local scope count mismatch')
                for row in rows:self.verify_ack_row(gid,dataset,row)
                requested={identity(dataset,r) for r in rows}
                proof,found=verify_archive(m,cloud.download_bytes('market-raw',m['object_path']),requested)
                if rows:build_manifest(dataset,rows,[(proof,found)])
                covered+=len(rows)
            if covered!=expected_count:raise Stop('archive coverage incomplete')
        from features import price_query
        cutoff=iso(now)
        with self.reader(gid,allow_draining=True) as db:
            price=db.execute(price_query('stream_events','event_id'),(cutoff,cutoff)).fetchone()
            live_price=None if price is None else db.execute(
                'SELECT '+','.join(COLUMNS['stream_events'])+' FROM stream_events WHERE source=? AND event_id=?',
                ('coinbase',price[0])).fetchone()
        with self.readerlock:
            self.core.execute('BEGIN IMMEDIATE')
            try:
                current=self.core.execute('SELECT state FROM generations WHERE id=?',(gid,)).fetchone()
                if current[0] not in ('sealed','draining','retiring'):raise Stop('generation changed')
                if live_price is not None:
                    event=self.core.execute("SELECT id FROM events WHERE gen=? AND dataset='stream_events' AND event_key=?",
                                            (gid,'coinbase:'+live_price['event_id'])).fetchone()
                    if event is None:raise Stop('live price identity unavailable')
                    self.pin_record(event[0],{'generation_id':gid,'dataset':'stream_events','row':dict(live_price)})
                self.verify_protected(gid)
                self.core.execute("UPDATE generations SET state='draining' WHERE id=?",(gid,))
                self.core.commit()
            except BaseException:self.core.rollback();raise
            self.trip('retirement_draining')
            if self.leases.get(gid):
                raise Stop('reader lease open')
            with self.generation_lease(gid,exclusive=True):
                self.core.execute('BEGIN IMMEDIATE')
                try:
                    self.verify_protected(gid)
                    if self._owners(gid):
                        raise Stop('raw database handles open')
                    self.core.execute("UPDATE generations SET state='retiring' WHERE id=?",(gid,))
                    self.core.commit()
                except BaseException:
                    self.core.rollback()
                    raise
                self.trip('retirement_authorized')
                self._remove(gid)
    def _remove(self,gid):
        if self.leases.get(gid) or self._owners(gid):raise Stop('retirement drain not proven')
        # Read-only readers can leave empty sidecars. An ordinary metadata
        # connection/close lets SQLite perform its normal last-close cleanup.
        # No checkpoint pragma, truncation or sidecar unlink is issued.
        if self.path(gid).exists():
            db=connect(self.path(gid))
            try:
                identities=db.execute('SELECT id FROM generation LIMIT 2').fetchall()
                if len(identities)!=1 or identities[0][0]!=gid:raise Stop('wrong close identity')
            finally:db.close()
            self.trip('retirement_normal_close')
        if self._owners(gid):raise Stop('handle opened before unlink')
        if any(Path(str(self.path(gid))+suffix).exists() for suffix in ('-wal','-shm')):raise Stop('sidecars remain; no manual WAL deletion')
        self.allocation()
        if self.path(gid).exists():self.path(gid).unlink()
        self.trip('retirement_file_removed')
        with self.core:self.core.execute("UPDATE generations SET state='retired' WHERE id=?",(gid,))

class FileArchive(MemoryArchive):
    """Generated objects on disk so archive working space is actually measured."""
    def __init__(self,root):
        super().__init__();self.root=Path(root)
        if self.root.is_symlink() or not self.root.resolve().parent.name.startswith('generated-ab-'):raise Stop('private generated archive root required')
        self.root.mkdir(mode=0o700,exist_ok=True)
        if self.root.stat().st_uid!=os.getuid() or self.root.stat().st_mode&0o077:raise Stop('private archive owner/mode required')
    def upload_bytes(self,bucket,path,data,content_type="application/gzip"):
        if '..' in Path(path).parts or Path(path).is_absolute():raise Stop('bad fixture object path')
        super().upload_bytes(bucket,path,data)
        p=self.root/path;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not p.exists():
            with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    def download_bytes(self,bucket,path):
        if not self.available:raise Stop('archive unavailable')
        self.reads+=1;return (self.root/path).read_bytes()
