"""Generated-only actual application adapter. No production enablement route.

Legacy raw remains read-only. Structured tables keep original schemas/IDs in
core; protocol bookkeeping lives in ab_* tables. TEMP raw views span pinned
legacy/A/B plus protected core observations. Every caller owns its connection.
"""
from contextlib import ExitStack,contextmanager
from pathlib import Path
import hashlib,json,re,sqlite3,threading,gzip
from decimal import Decimal
from raw_generations import Store,Stop,connect,canonical,COLUMNS,iso,digest
import collector,streaming,features,forecasts,cloud_memory,cloud_lifecycle

RAW={'observations','stream_events'}
MAX_ROWS=10000
class ApplicationStore:
    def __init__(self,root,legacy,routing=False,retirement=False,fault=None,generation_bytes=None):
        if retirement and not routing:raise Stop('inconsistent AB enablement')
        if not routing:raise Stop('AB application routing disabled by default')
        self.connections=set();self.connection_lock=threading.RLock();self.external_workers=set();self.worker_opening=0;self.closed=False
        self.protocol=Store(root,fault=fault,application_namespace=True,generation_bytes=generation_bytes)
        self.root=self.protocol.root;self.legacy=Path(legacy)
        self.retirement_enabled=retirement;self.hold=None;self.collector_authority=True
        try:
            if self.legacy.is_symlink() or self.legacy.resolve().parent not in self._legacy_parents() or not self.legacy.name.startswith('generated-legacy'):
                raise Stop('generated legacy allowlist required')
            self.legacy=self.legacy.resolve()
            self._bind_external_legacy()
            self.protocol.guard()
            if any(Path(str(self.legacy)+suffix).is_symlink() for suffix in ('-wal','-shm')):raise Stop('legacy sidecar symlink forbidden')
            if not self.legacy.is_file():raise Stop('legacy missing')
            self._initialize()
            self.legacy_identity=self._legacy_allocation()
            core=self.protocol.core.native
            core.execute('CREATE TABLE IF NOT EXISTS ab_worker_binding(id INTEGER PRIMARY KEY CHECK(id=1),legacy TEXT NOT NULL,allocation TEXT NOT NULL)')
            with core:core.execute('INSERT OR REPLACE INTO ab_worker_binding VALUES(1,?,?)',(str(self.legacy),canonical(self.legacy_identity)))
        except BaseException:self.protocol.close();raise
    def _legacy_parents(self):
        parents = {self.root}
        if self.root.parent.name.startswith('generated-ab-'):
            parents.add(self.root.parent)
        return parents

    def _bind_external_legacy(self):
        self.protocol.external_files = ()
        if self.legacy.parent != self.root:
            self.protocol.external_files = tuple(
                Path(str(self.legacy)+suffix) for suffix in ('','-wal','-shm'))

    def _legacy_allocation(self):
        return tuple((p.name,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns) for p in
                     (self.legacy,Path(str(self.legacy)+'-wal')) if p.exists())
    def _initialize(self):
        core=self.protocol.core.native
        core.create_function('ab72_writer_enabled',0,lambda:1)
        core.executescript('''CREATE TABLE IF NOT EXISTS ab_migration_state(id INTEGER PRIMARY KEY CHECK(id=1),identity TEXT NOT NULL,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ab_legacy_audit(dataset TEXT,key TEXT,fingerprint TEXT,PRIMARY KEY(dataset,key));
CREATE TABLE IF NOT EXISTS ab_legacy_stream_ids(source TEXT,event_id TEXT,id INTEGER UNIQUE,PRIMARY KEY(source,event_id));
CREATE TABLE IF NOT EXISTS ab_legacy_stream_pins(source TEXT,event_id TEXT,record TEXT NOT NULL,PRIMARY KEY(source,event_id));
CREATE TABLE IF NOT EXISTS ab_legacy_pins(id INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ab_application_marker(id INTEGER PRIMARY KEY CHECK(id=1),layout TEXT NOT NULL);
INSERT OR IGNORE INTO ab_application_marker VALUES(1,'AB72_FORWARD_ONLY');''')
        legacy=connect(self.legacy,True)
        try:
            # Identity binds content metadata at quiescent migration; raw rows are
            # audited by exact fingerprint below. No byte copy or backup.
            schema=legacy.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for row in schema:
                if row['sql'] is None:raise Stop('unsupported legacy schema')
                if 'VIRTUAL TABLE' in row['sql'].upper() and not (row['name']=='news_events_fts' and 'USING fts5' in row['sql']):raise Stop('unsupported legacy virtual schema')
            shadows={r[1] for r in legacy.execute('PRAGMA table_list') if r[2]=='shadow'}
            if any(r['name'].startswith('news_events_fts') and r['name']!='news_events_fts' and r['name'] not in shadows for r in schema):raise Stop('unexpected FTS-prefixed table')
            schema=[r for r in schema if r['name']!='news_events_fts' and r['name'] not in shadows]

            # Reject over-bound legacy input after at most MAX_ROWS+1 row
            # visits, rather than COUNT(*) scanning an arbitrary raw history.
            # This does not raise the generated migration allowance.
            count=0
            for table in schema:
                quoted=table['name'].replace('"','""')
                for _ in legacy.execute('SELECT 1 FROM "'+quoted+'" LIMIT ?', (MAX_ROWS-count+1,)):
                    count+=1
                    if count>MAX_ROWS:raise Stop('generated migration qualification bound exceeded')
            audit=hashlib.sha256(canonical({'path':str(self.legacy),'schema':[tuple(r) for r in schema]}).encode());audited_bytes=0
            for table in schema:
                audit.update(table['name'].encode()+b'\0')
                for row in legacy.execute('SELECT * FROM "'+table['name']+'" ORDER BY rowid'):
                    encoded=canonical(tuple(row)).encode();audited_bytes+=len(encoded)
                    if len(encoded)>1024**2 or audited_bytes>128*1024**2:raise Stop('generated migration audit byte bound exceeded')
                    audit.update(len(encoded).to_bytes(8,'big'));audit.update(encoded)
            identity=audit.hexdigest()
            prior=core.execute('SELECT identity,status FROM ab_migration_state WHERE id=1').fetchone()
            if prior and prior[0]!=identity:raise Stop('legacy identity changed')
            if prior and prior[1]=='complete':
                streaming.initialize(core);features.initialize(core);forecasts.initialize(core)
                self._news(core)
                cloud_memory.initialize_local_sync(core);cloud_lifecycle.initialize_lifecycle_state(core)
                self._write_guards(core);core.commit()
                return
            # One core transaction: incomplete imports never become routed state.
            core.execute('BEGIN IMMEDIATE')
            core.execute('PRAGMA defer_foreign_keys=ON')
            try:
                for row in schema:
                    if row['name']=='stream_events':continue
                    if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',row['name']) or row['name'].startswith('ab_'):raise Stop('unsupported legacy table')
                    core.execute(row['sql'].replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
                # Preserve every structured row and only explicitly protected raw
                # observations in core. Legacy keeps the complete raw history.
                protected=set();protected_stream=set()
                for table in schema:
                    for fk in legacy.execute('PRAGMA foreign_key_list("'+table['name']+'")'):
                        if fk['table']=='observations':
                            if fk['to']!='id' or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',fk['from']):raise Stop('unsupported observation FK')
                            protected.update(r[0] for r in legacy.execute('SELECT "'+fk['from']+'" FROM "'+table['name']+'" WHERE "'+fk['from']+'" IS NOT NULL'))

                if any(r['name']=='prediction_context_links' for r in schema):
                    protected.update(r[0] for r in legacy.execute('SELECT outcome_observation_id FROM prediction_context_links WHERE outcome_observation_id IS NOT NULL'))
                if any(r['name']=='feature_snapshots' for r in schema):
                    for row in legacy.execute('SELECT evidence_json FROM feature_snapshots'):
                        evidence=json.loads(row[0]);key=evidence.get('metadata_observation_id')
                        if not isinstance(key,int) or isinstance(key,bool) or key<=0:raise Stop('unknown embedded metadata reference')
                        protected.add(key)
                        if set(evidence)-{'metadata_observation_id','metadata_received_at','price','latest_completed_candle_time','candle_inputs'}:raise Stop('unsupported embedded evidence schema')
                        price=evidence.get('price') or {};source=price.get('source');input_id=price.get('input_id')
                        if source=='coinbase_stream':protected_stream.add(('coinbase',str(input_id)))
                        elif source=='coinbase_rest':
                            if not legacy.execute('SELECT 1 FROM reference_prices WHERE id=?',(input_id,)).fetchone():raise Stop('missing embedded REST price reference')
                        elif source is not None or input_id is not None:raise Stop('unknown embedded price reference')
                for row in schema:
                    name=row['name']
                    if name in RAW:continue
                    for row in legacy.execute('SELECT * FROM "'+name+'"'):
                        self.protocol.guard()
                        core.execute('INSERT INTO "'+name+'" VALUES('+','.join('?' for _ in row)+')',tuple(row))
                    self.protocol.trip('migration_structured:'+name)
                for name in RAW:
                    exists=any(r['name']==name for r in schema)
                    if not exists:raise Stop('legacy raw schema missing')
                    for row in legacy.execute('SELECT '+','.join(COLUMNS[name])+' FROM '+name):
                        raw=dict(row);key=str(raw['id']) if name=='observations' else canonical([raw['source'],raw['event_id']])
                        core.execute('INSERT INTO ab_legacy_audit VALUES(?,?,?)',(name,key,digest(raw)))
                        if name=='stream_events' and (raw['source'],raw['event_id']) in protected_stream:
                            core.execute('INSERT INTO ab_legacy_stream_pins VALUES(?,?,?)',(raw['source'],raw['event_id'],canonical(raw)))
                        if name=='observations' and raw['id'] in protected:
                            core.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',tuple(raw[k] for k in COLUMNS[name]))
                            core.execute('INSERT INTO ab_legacy_pins VALUES(?,?)',(raw['id'],digest(raw)))
                if protected_stream-{tuple(r) for r in core.execute('SELECT source,event_id FROM ab_legacy_stream_pins')}:raise Stop('missing legacy protected stream')
                for obj in legacy.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('index','trigger') AND sql IS NOT NULL"):
                    if obj['name'].startswith('news_events_fts'):continue
                    # Raw indexes stay in retained legacy; new raw generations own theirs.
                    if re.search(r'\bON\s+(observations|stream_events)\b',obj['sql'],re.I):continue
                    core.execute(obj['sql'])
                missing=protected-{r[0] for r in core.execute('SELECT id FROM observations')}
                if missing:raise Stop('missing legacy protected observation')
                # Reserve above ALL legacy observation IDs, not only copied pins.
                maximum=legacy.execute('SELECT COALESCE(MAX(id),0) FROM observations').fetchone()[0]
                for row in legacy.execute('SELECT source,event_id FROM stream_events ORDER BY rowid'):
                    maximum+=1;core.execute('INSERT INTO ab_legacy_stream_ids VALUES(?,?,?)',(row['source'],row['event_id'],maximum))
                core.execute("INSERT OR REPLACE INTO sqlite_sequence(name,seq) VALUES('ab_events',?)",(maximum,))
                if core.execute('PRAGMA foreign_key_check').fetchall():raise Stop('legacy foreign key audit failed')
                self._write_guards(core)
                core.execute('INSERT OR REPLACE INTO ab_migration_state VALUES(1,?,?)',(identity,'complete'))
                self.protocol.trip('migration_before_commit');core.commit();self.protocol.trip('migration_committed')
            except BaseException:core.rollback();raise
        finally:legacy.close()
        # Only the production's real schema initializers, no synthetic tables.
        streaming.initialize(core);features.initialize(core);forecasts.initialize(core)
        self._news(core)
        cloud_memory.initialize_local_sync(core);cloud_lifecycle.initialize_lifecycle_state(core)
        self._write_guards(core);core.commit()
    def _write_guards(self,core):
        for row in core.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT GLOB 'ab_*'").fetchall():
            name=row[0]
            if name.startswith('news_events_fts'):continue
            if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',name):raise Stop('unsupported guarded table')
            for operation in ('INSERT','UPDATE','DELETE'):
                core.execute(f"""CREATE TRIGGER IF NOT EXISTS ab_guard_{name}_{operation} BEFORE {operation} ON "{name}" WHEN ab72_writer_enabled()!=1 BEGIN SELECT RAISE(ABORT,'AB72 forward adapter required'); END""")
    def _news(self,core):
        if core.execute("SELECT 1 FROM sqlite_master WHERE name='news_events'").fetchone():
            import news
            news.initialize(core)
            with core:core.execute("INSERT INTO news_events_fts(news_events_fts) VALUES('rebuild')")
    @contextmanager
    def collector_write(self):
        # Existing Store lock, no writer thread/service/queue. REST and WS calls
        # remain synchronous durable saves on their own connections. A contending
        # caller waits at most 0.5s; never retries or accumulates queued records.
        if self.hold:raise Stop(self.hold)
        if not self.protocol.readerlock.acquire(timeout=.5):
            self.hold='collector_contention_hold';raise Stop(self.hold)
        previous=getattr(self.protocol._application_writer,'authorized',False)
        self.protocol._application_writer.authorized=True
        try:yield
        except BaseException:
            self.hold='durable_raw_save_failed';raise
        finally:
            self.protocol._application_writer.authorized=previous
            if threading.get_ident()!=self.protocol.owner_thread and hasattr(self.protocol._connections,'db'):
                self.protocol._connections.db.close();del self.protocol._connections.db
            self.protocol.readerlock.release()
    def connection(self):
        if self.closed:raise Stop('storage owner closed')
        return ApplicationConnection(self)
    def reader_connection(self):
        if self.closed:raise Stop('storage owner closed')
        return ApplicationConnection(self,readonly=True)
    def worker_connection(self,role):
        with self.connection_lock:
            if self.closed:raise Stop('storage owner closed')
            self.worker_opening+=1
        worker=None
        try:
            worker=ApplicationWorker(self.root,self.legacy,routing=True,role=role)
            db=worker.connection();db.owned_worker=worker;db.owning_store=self
            with self.connection_lock:self.external_workers.add(worker)
            return db
        except BaseException:
            if worker:worker.close()
            raise
        finally:
            with self.connection_lock:self.worker_opening-=1
    def close(self):
        with self.connection_lock:
            if self.closed:return
            if self.connections or self.external_workers or self.worker_opening:raise Stop('drain application connections before owner release')
            self.protocol.close();self.closed=True
    def rotation_tick(self, now):
        """Collector-loop timer. Recovery completes before this is called."""
        if not self.collector_authority:
            raise Stop('worker cannot schedule rotation')
        if self.hold:
            raise Stop(self.hold)
        with self.collector_write():
            generation = self.protocol.rotate(now)
        # Only the owning thread may detach a connection. An active transaction
        # retains its snapshot and lease until its caller commits or closes it.
        with self.connection_lock:
            connections = tuple(self.connections)
        for connection in connections:
            if connection.owner == threading.get_ident() and not connection.db.in_transaction:
                try:
                    connection._refresh()
                except sqlite3.OperationalError:
                    # A live cursor may still pin an attachment. Keep its lease.
                    continue
        return generation

    def retire(self,*args):
        if not self.retirement_enabled:raise Stop('AB retirement disabled by default')
        return self.protocol.retire(*args)

class ApplicationConnection:
    def __init__(self,store,readonly=False):
        self.readonly=readonly;self.closed=False
        self.store=store;self.protocol=store.protocol;self.owner=threading.get_ident()
        self.db=connect(store.root/'core.db',ro=readonly);self.db.row_factory=None
        self.db.create_function('ab72_writer_enabled',0,lambda:0 if readonly else 1)
        def valid_evidence(record,sha):
            if hashlib.sha256(record.encode()).hexdigest()!=sha:raise ValueError('core evidence checksum mismatch')
            return 1
        self.db.create_function('ab72_verified_evidence',2,valid_evidence)
        self.db.execute('PRAGMA query_only=OFF')
        self.stack=ExitStack();self.signature=None
        self.raw_attached=[];self.legacy_attached=False;self.views_ready=False
        try:
            self._refresh()
            if readonly:self.db.execute('PRAGMA query_only=ON')
            with store.connection_lock:store.connections.add(self)
        except BaseException:
            self.db.close();self.stack.close();raise
    def _check(self):
        if self.closed:raise Stop('application connection closed')
        if self.owner!=threading.get_ident():raise Stop('connection belongs to worker')
    def _refresh(self):
        self._check()
        if self.store._legacy_allocation()!=self.store.legacy_identity:
            self.store.hold='legacy_identity_changed';raise Stop(self.store.hold)
        signature=tuple(r[0] for r in self.db.execute("SELECT id FROM ab_generations WHERE state IN ('active','sealed') ORDER BY started"))
        if signature==self.signature and self.views_ready:return
        if self.db.in_transaction:return # Keep pinned bindings until commit; refresh next operation.
        self.db.execute('PRAGMA query_only=OFF')
        try:
            self._bind_generations(signature)
        finally:
            if self.readonly:
                self.db.execute('PRAGMA query_only=ON')

    def _bind_generations(self,signature):
        self.views_ready=False
        for name in RAW:self.db.execute('DROP VIEW IF EXISTS temp.'+name)
        for alias in tuple(self.raw_attached):
            self.db.execute('DETACH DATABASE '+alias)
            self.raw_attached.remove(alias)
        if self.legacy_attached:
            self.db.execute('DETACH DATABASE legacy')
            self.legacy_attached=False
        self.stack.close();self.stack=ExitStack()
        self.db.execute('ATTACH DATABASE ? AS legacy',(store_uri(self.store.legacy),))
        self.legacy_attached=True
        for i,gid in enumerate(signature):
            self.stack.enter_context(self.protocol.reader(gid))
            self.db.execute('ATTACH DATABASE ? AS raw'+str(i),(store_uri(self.protocol.path(gid)),))
            self.raw_attached.append('raw'+str(i))
        obs=['SELECT * FROM main.observations','SELECT * FROM legacy.observations WHERE id NOT IN (SELECT id FROM main.observations)']
        ticks=['SELECT '+','.join(COLUMNS['stream_events'])+' FROM legacy.stream_events']
        # After retirement, copied protected records remain real historical inputs.
        # Active/sealed records come from raw views, so identities never duplicate.
        for dataset,target in (('observations',obs),('stream_events',ticks)):
            fields=','.join("json_extract(p.record,'$.row."+column+"') AS "+column for column in COLUMNS[dataset])
            clause=" AND e.id NOT IN (SELECT id FROM main.observations)" if dataset=='observations' else ''
            target.append("SELECT "+fields+" FROM main.ab_evidence p JOIN main.ab_events e ON e.id=p.id JOIN main.ab_generations g ON g.id=e.gen WHERE g.state IN ('draining','retiring','retired') AND e.status='committed' AND e.dataset='"+dataset+"' AND ab72_verified_evidence(p.record,p.sha256)=1"+clause)
        for i in range(len(signature)):
            gid=signature[i] # validated Store.path UUID, never an SQL parameter/input fragment
            obs.append('SELECT r.* FROM raw'+str(i)+".observations r JOIN main.ab_events e ON e.id=r.id AND e.dataset='observations' AND e.status='committed' AND e.gen='"+gid+"' WHERE r.id NOT IN (SELECT id FROM main.observations)")
            ticks.append('SELECT '+','.join('r.'+k for k in COLUMNS['stream_events'])+' FROM raw'+str(i)+".stream_events r JOIN main.ab_events e ON e.event_key=r.source||':'||r.event_id AND e.dataset='stream_events' AND e.status='committed' AND e.gen='"+gid+"'")
        self.db.execute('CREATE TEMP VIEW observations AS '+' UNION ALL '.join(obs))
        self.db.execute('CREATE TEMP VIEW stream_events AS '+' UNION ALL '.join(ticks))
        self.signature=signature
        self.views_ready=True
    def execute(self,sql,args=()):
        self._refresh()
        if re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE)\b',sql,re.I):
            if self.store.hold and not re.search(r'\b(runs|feed_health|cloud_lifecycle_state)\b',sql,re.I):raise Stop(self.store.hold)
            self.protocol.guard()
        if re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE)\b',sql,re.I) and re.search(r'\b(observations|stream_events)\b',sql,re.I):
            raise Stop('raw SQL writes require durable routing hook')
        return self.db.execute(sql,args)
    def executescript(self,sql):
        # Application initializers contain no raw DML; raw index creation is
        # handled by raw_archive_rows below rather than indexes on UNION views.
        if re.search(r'\b(CREATE TABLE IF NOT EXISTS (observations|stream_events))\b',sql,re.I):raise Stop('raw schema initialization belongs to adapter')
        return self.db.executescript(sql)
    def active_buffer(self):
        row = self.execute("SELECT slot,id,started FROM ab_generations WHERE state='active'").fetchone()
        return dict(zip(('slot','generation_id','started_at'),row)) if row else None

    def chart_ticks(self,limit):
        if not 1<=limit<=12000:raise Stop('unsupported chart request bound')
        rows=self.execute("""SELECT t.received_at,t.source_time,t.price FROM stream_events t
LEFT JOIN ab_legacy_stream_ids l ON l.source=t.source AND l.event_id=t.event_id
LEFT JOIN ab_events e ON e.dataset='stream_events' AND e.event_key=t.source||':'||t.event_id
WHERE t.source='coinbase' ORDER BY COALESCE(e.id,l.id) DESC LIMIT ?""",(min(limit,10001),)).fetchall()
        if len(rows)>10000:raise Stop('chart exceeds unchanged10000-row resource bound')
        return rows
    def latest_tick_event(self):
        row=self.execute("""SELECT COALESCE(e.id,l.id),t.price,t.source_time,t.received_at FROM stream_events t
LEFT JOIN ab_legacy_stream_ids l ON l.source=t.source AND l.event_id=t.event_id
LEFT JOIN ab_events e ON e.dataset='stream_events' AND e.event_key=t.source||':'||t.event_id
WHERE t.source='coinbase' ORDER BY COALESCE(e.id,l.id) DESC LIMIT 1""").fetchone()
        if row and row[0] is None:raise Stop('stream identity unknown')
        return dict(zip(('sequence','price_usd','source_time','received_at'),row)) if row else None
    def set_progress_handler(self,*args):return self.db.set_progress_handler(*args)
    def commit(self):self.db.commit()
    def rollback(self):self.db.rollback()
    def __enter__(self):self._refresh();return self
    def __exit__(self,kind,value,tb):
        if kind:self.db.rollback()
        else:self.db.commit()
    def close(self):
        if self.closed:return
        self._check()
        try:self.db.close()
        finally:
            self.stack.close();self.closed=True
            with self.store.connection_lock:self.store.connections.discard(self)
            worker=getattr(self,'owned_worker',None)
            if worker:
                worker.close()
                with self.owning_store.connection_lock:self.owning_store.external_workers.discard(worker)
    def ab_stop_requested(self):return self.store.hold
    def save_market(self,m,received):
        if not self.store.collector_authority:raise Stop('worker has no collector authority')
        if self.store.hold:raise Stop(self.store.hold)
        # Durable metadata first; a raw failure leaves missing evidence, never a
        # successful publication. The caller cannot roll back a committed raw save.
        try:
            with self.db:collector.save_market_record(self.db,m,received)
        except BaseException:
            self.store.hold='structured_metadata_save_failed';raise
        return self.save_observation(m['id'],received,'metadata',m['raw'],m['raw'].get('updatedAt'))
    def save_observation(self,market_id,received,kind,payload,source_time=None):
        self._check()
        if not self.store.collector_authority:raise Stop('worker has no collector authority')
        if self.store.hold:raise Stop(self.store.hold)
        if self.db.in_transaction:raise Stop('raw handoff requires clean application transaction')
        raw=dict(market_id=market_id,received_at=received,kind=kind,payload=json.dumps(payload),source_time=source_time)
        identity={k:v for k,v in raw.items() if k!='payload'};identity['received_at']=iso(received)
        old=self.db.execute('SELECT id,payload FROM legacy.observations WHERE market_id=? AND kind=? AND received_at IN (?,?) AND source_time IS ? ORDER BY id LIMIT 2',(market_id,kind,received,iso(received),source_time)).fetchall()
        if old:
            if any(r[1]!=raw['payload'] for r in old):raise Stop('legacy observation identity conflict')
            return old[0][0]
        key='observation:'+digest(identity)
        with self.store.collector_write():eid=self.protocol.save('observations',key,raw)
        self._refresh();return eid
    def save_stream_event(self,row):
        self._check()
        if not self.store.collector_authority:raise Stop('worker has no collector authority')
        if self.store.hold:raise Stop(self.store.hold)
        if self.db.in_transaction:raise Stop('raw handoff requires clean application transaction')
        key=row['source']+':'+row['event_id']
        legacy=self.db.execute('SELECT '+','.join(COLUMNS['stream_events'])+' FROM legacy.stream_events WHERE source=? AND event_id=?',(row['source'],row['event_id'])).fetchone()
        if legacy:
            old=dict(zip(COLUMNS['stream_events'],legacy))
            if any(old[k]!=row[k] for k in row if k!='received_at'):raise Stop('legacy duplicate conflict')
            return False
        with self.store.collector_write():
            prior=self.protocol.core.execute('SELECT id FROM events WHERE dataset=? AND event_key=?',('stream_events',key)).fetchone()
            self.protocol.save('stream_events',key,row)
        self._refresh();return prior is None
    def protect_observation(self,event_id):
        row=self.db.execute('SELECT * FROM observations WHERE id=?',(event_id,)).fetchone()
        if not row:raise Stop('protected observation missing')
        raw=dict(zip(COLUMNS['observations'],row))
        prior=self.db.execute('SELECT * FROM main.observations WHERE id=?',(event_id,)).fetchone()
        if prior and tuple(prior)!=tuple(row):raise Stop('protected identity conflict')
        self.db.execute('INSERT OR IGNORE INTO main.observations VALUES(?,?,?,?,?,?)',row)
        event=self.db.execute('SELECT gen FROM ab_events WHERE id=? AND dataset=? AND status=?',(event_id,'observations','committed')).fetchone()
        if event:
            record=canonical({'generation_id':event[0],'dataset':'observations','row':raw})
            self.db.execute('INSERT OR IGNORE INTO ab_evidence VALUES(?,?,?)',(event_id,record,hashlib.sha256(record.encode()).hexdigest()))
            self.db.execute('INSERT OR IGNORE INTO ab_required_evidence VALUES(?)',(event_id,))
    def protect_feature_inputs(self,evidence):
        self.protocol.guard()
        self.protect_observation(evidence['metadata_observation_id'])
        price=evidence.get('price') or {}
        if price.get('source')=='coinbase_stream':
            key='coinbase:'+str(price['input_id'])
            event=self.db.execute("SELECT id,gen FROM ab_events WHERE dataset='stream_events' AND event_key=? AND status='committed'",(key,)).fetchone()
            if event:
                row=self.db.execute('SELECT * FROM stream_events WHERE source=? AND event_id=?',('coinbase',str(price['input_id']))).fetchone()
                record=canonical({'generation_id':event[1],'dataset':'stream_events','row':dict(zip(COLUMNS['stream_events'],row))})
                self.db.execute('INSERT OR IGNORE INTO ab_evidence VALUES(?,?,?)',(event[0],record,hashlib.sha256(record.encode()).hexdigest()))
                self.db.execute('INSERT OR IGNORE INTO ab_required_evidence VALUES(?)',(event[0],))
        self.protocol.trip('feature_evidence_ready')
    def archive_handoff_token(self):
        return tuple(self.db.execute(
            "SELECT id,state FROM ab_generations WHERE state IN ('sealed','draining','retiring') ORDER BY started"
        ).fetchall())

    def raw_archive_caught_up(self,dataset):
        return not self.raw_archive_rows(dataset,1)
    def feature_cycle_ready(self):self.protocol.trip('feature_cycle_committed')
    def map_cloud_row(self,table,row,mapped):
        result=dict(mapped)
        fields={'markets':('target','final'),'official_outcomes':('final',),
                'candles':('low','high','open','close','volume')}.get(table,())
        for field in fields:
            value=row.get(field)
            result[field]=Decimal(str(value)) if value not in (None,'') else None
            if result[field] is not None and not result[field].is_finite():raise Stop('invalid exact cloud numeric')
        for field in ('raw_json','values_json','quality_json','evidence_json','categories_json','assumptions_json'):
            if field in result and field in row:result[field]=json.loads(row[field],parse_float=Decimal)
        if table=='official_outcomes':result['source_json']=json.loads(row['raw_json'],parse_float=Decimal)
        if table=='predictions':
            result['extra_json']={**result['extra_json'],'source_exact':{k:row.get(k) for k in ('probability_up','probability_down','seconds_remaining')}}
        return result
    def ab_retention_hold(self):return 'AB row cleanup prohibited; generation retirement requires drained operator phase'
    def _row_generation(self,dataset,row):
        if dataset=='observations':
            event=self.db.execute("SELECT gen FROM ab_events WHERE dataset='observations' AND id=? AND status='committed'",(row['id'],)).fetchone()
        else:
            event=self.db.execute("SELECT gen FROM ab_events WHERE dataset='stream_events' AND event_key=? AND status='committed'",(row['source']+':'+row['event_id'],)).fetchone()
        return event[0] if event else 'legacy'
    def archive_batch_object_path(self,dataset,rows):
        source,path=cloud_memory.archive_batch_object_path(dataset,rows)
        gid=self._row_generation(dataset,rows[0])
        return source, (gid+'/'+path if gid!='legacy' else path)
    def archive_manifest_metadata(self,dataset,rows):
        ids={self._row_generation(dataset,r) for r in rows}
        if len(ids)!=1:raise Stop('archive must not span generations')
        return {'generation_id':ids.pop(),'dataset':dataset}
    def commit_verified_archive(self,cloud,dataset,rows,manifest):
        if self.db.in_transaction:raise Stop('archive cannot run in writer transaction')
        self.protocol.trip('archive_remote_verified')
        name='archive:'+dataset;last=rows[-1]
        key=None if dataset=='observations' else cloud_memory._stream_cursor_key(last)
        source_id=last.get('source_id')
        cloud_memory._cloud_checkpoint(cloud,name,source_id=source_id,source_time=last['received_at'],source_key=key,
            rows_synced=cloud_memory._checkpoint(self,name)[3]+len(rows),status='verified',detail=manifest['object_path'])
        with self:
            self.record_archive_manifest(dataset,rows,manifest)
            self.protocol.trip('archive_before_local_commit')
            cloud_memory._save_checkpoint(self,name,source_id=source_id,source_time=last['received_at'],source_key=key,
                rows_added=len(rows),status='verified',detail=manifest['object_path'])
        self.protocol.trip('archive_checkpoint_committed')
    def record_archive_manifest(self,dataset,rows,manifest):
        gid=self.archive_manifest_metadata(dataset,rows)['generation_id']
        if gid!='legacy':
            self.db.execute('INSERT OR IGNORE INTO ab_manifests VALUES(?,?,?,?)',(gid,dataset,manifest['object_path'],canonical(manifest)))
    def build_archive(self,dataset,rows):
        lines=[]
        for row in rows:
            value=dict(row);payload=value.pop('payload')
            json.loads(payload,parse_float=Decimal)
            text=canonical(value)
            lines.append('{"dataset":'+json.dumps(dataset)+',"row":'+text[:-1]+',"payload":'+payload+'}}')
        raw=('\n'.join(lines)+'\n').encode();compressed=gzip.compress(raw,mtime=0)
        return raw,compressed,hashlib.sha256(compressed).hexdigest()
    def raw_archive_rows(self,dataset,limit):
        # Reuse exact existing cursor semantics; avoid CREATE INDEX on temp view.
        if dataset=='observations':
            last=cloud_memory._checkpoint(self,'archive:observations')[0] or 0
            cursor=self.execute('SELECT id AS source_id,id,market_id,received_at,source_time,kind,payload FROM observations WHERE id>? ORDER BY id LIMIT ?',(last,limit))
        elif dataset=='stream_events':
            _,at,key,_=cloud_memory._checkpoint(self,'archive:stream_events')
            if at and key:
                source,event=json.loads(key)
                cursor=self.execute('SELECT * FROM stream_events WHERE (received_at,source,event_id)>(?,?,?) ORDER BY received_at,source,event_id LIMIT ?',(at,source,event,limit))
            else:cursor=self.execute('SELECT * FROM stream_events ORDER BY received_at,source,event_id LIMIT ?',(limit,))
        else:raise Stop('unknown raw archive dataset')
        rows=cloud_memory._dict_rows(cursor)
        if not rows:return rows
        first=self._row_generation(dataset,rows[0]);end=0
        for row in rows:
            if self._row_generation(dataset,row)!=first:break
            end+=1
        return rows[:end]

def store_uri(path):return Path(path).resolve().as_uri()+'?mode=ro'


class WorkerProtocol:
    """Existing lifecycle/feature/history process handle: no raw-owner methods."""
    path=Store.path
    reader=Store.reader
    generation_lease=Store.generation_lease
    allocation=Store.allocation
    guard=Store.guard
    def __init__(self,root):
        self.root=Path(root).resolve();self.ceiling=2*1024**3;self.core_ceiling=self.ceiling
        self.leases={};self.readerlock=threading.RLock();self.wal_peaks={};self.peak=0
        from protocol_namespace import ProtocolConnection
        self.core=ProtocolConnection(connect(self.root/'core.db',ro=True))
    def trip(self,phase):pass # Worker has no transition/fault operator capability.
    def close(self):self.core.close()

class ApplicationWorker(ApplicationStore):
    """Explicit generated worker role, never obtains/releases collector authority."""
    def __init__(self,root,legacy,routing=False,role=None):
        if not routing:raise Stop('AB worker routing disabled by default')
        if role not in ('lifecycle','feature','history'):raise Stop('explicit worker role required')
        path=Path(root)
        if path.is_symlink():raise Stop('worker root symlink')
        path=path.resolve()
        if (not path.name.startswith('generated-ab-') or path.stat().st_uid!=__import__('os').getuid()
            or path.stat().st_mode&0o077 or Path('/opt/tradebot') in path.parents):raise Stop('private generated worker required')
        self.root=path;self.legacy=Path(legacy);self.role=role;self.hold=None;self.retirement_enabled=False;self.collector_authority=False
        self.connections=set();self.connection_lock=threading.RLock();self.external_workers=set();self.worker_opening=0;self.closed=False
        if self.legacy.is_symlink() or self.legacy.resolve().parent not in self._legacy_parents():raise Stop('worker legacy allowlist mismatch')
        self.legacy=self.legacy.resolve()
        self.protocol=WorkerProtocol(path)
        self._bind_external_legacy()
        try:
            core=self.protocol.core.native
            if not core.execute("SELECT 1 FROM ab_migration_state WHERE id=1 AND status='complete'").fetchone():raise Stop('worker migration incomplete')
            binding=core.execute('SELECT legacy,allocation FROM ab_worker_binding WHERE id=1').fetchone()
            if not binding or binding[0]!=str(self.legacy):raise Stop('worker legacy identity mismatch')
            self.legacy_identity=self._legacy_allocation()
            if canonical(self.legacy_identity)!=binding[1]:raise Stop('worker legacy allocation changed')
        except BaseException:self.protocol.close();raise
    def connection(self):
        if self.closed:raise Stop('worker closed')
        return ApplicationConnection(self,readonly=self.role=='history')
    @contextmanager
    def collector_write(self):
        raise Stop('worker cannot acquire raw collector authority')
        yield
    def retire(self,*args):raise Stop('worker retirement disabled; drained operator phase required')


class RetirementProtocol(WorkerProtocol):
    """Verified lifecycle retirement only. No raw-save or rotation methods."""
    retire=Store.retire
    _remove=Store._remove
    _owners=Store._owners
    pin_record=Store.pin_record
    verify_protected=Store.verify_protected

    def __init__(self,root,legacy=None):
        # Reuse the worker's root, ownership and migration validation.
        worker=ApplicationWorker(root,legacy or Path(root)/'generated-legacy.db',routing=True,role='lifecycle')
        try:
            self.__dict__.update(worker.protocol.__dict__)
        finally:
            worker.close()
        from protocol_namespace import ProtocolConnection
        self.core=ProtocolConnection(connect(self.root/'core.db'))
        for row in self.core.execute("SELECT id FROM generations WHERE state='retiring'").fetchall():
            if not self.path(row[0]).exists():
                if any(Path(str(self.path(row[0]))+suffix).exists() for suffix in ('-wal','-shm')):
                    self.close()
                    raise Stop('orphan retirement sidecars')
                with self.core:
                    self.core.execute("UPDATE generations SET state='retired' WHERE id=?",(row[0],))
