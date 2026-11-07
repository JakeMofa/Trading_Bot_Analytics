"""Default-off selected-evidence verification/staging. Never modifies legacy/source.

Staging roots must be isolated generated-ab-recovery-* directories. This is not
an application activation, production repair, archive approval or deployment tool.
"""
from contextlib import closing
from datetime import timedelta
import hashlib,json,os,re,sqlite3,time
from pathlib import Path
from decimal import Decimal,InvalidOperation
from application_validation import header,row_check,timestamp
from raw_generations import COLUMNS,canonical,digest

class RecoveryHold(ValueError):pass

def file_binding(path):
    path=Path(path);out={}
    for suffix in ('','-wal'):
        f=Path(str(path)+suffix)
        if f.is_symlink():raise RecoveryHold('source/sidecar symlink')
        if f.exists():
            s=f.stat()
            if not suffix or s.st_size:out[suffix or 'main']=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]
    return out

def sha_file(path,check):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):check();h.update(chunk)
    return h.hexdigest()

def verify(source,dependencies,expected_source_sha,expected_dependency_sha,deadline,guard=lambda:None):
    source=Path(source);dependencies=Path(dependencies)
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('complete recovery deadline')
        guard()
    if source.is_symlink() or dependencies.is_symlink() or dependencies.stat().st_size>8*1024**2:raise RecoveryHold('unsafe verification inputs')
    before=file_binding(source)
    if sha_file(source,check)!=expected_source_sha:raise RecoveryHold('candidate source hash mismatch')
    if sha_file(dependencies,check)!=expected_dependency_sha:raise RecoveryHold('dependency manifest hash mismatch')
    deps=json.loads(dependencies.read_text())
    if deps.get('format')!='AB72_SELECTED_DEPENDENCIES_V1':raise RecoveryHold('unsupported dependency manifest')
    obs=deps['missing_observations'];ticks=deps['missing_stream_events']
    if len(obs)+len(ticks)>20000 or len(obs)!=len(set(obs)) or len(ticks)!=len(set(ticks)):raise RecoveryHold('duplicate/overbound selected identities')
    if any(type(x) is not int or x<=0 for x in obs) or any(not isinstance(x,str) or not x for x in ticks):raise RecoveryHold('malformed selected identity')
    if len(deps['snapshots'])>20000 or len(deps['predictions'])>30000:raise RecoveryHold('dependency scope exceeded')
    if '-wal' in before:raise RecoveryHold('nonempty candidate WAL needs explicit hash verification')
    records={};markets={};conflicts=[];refs={};uses_m=set();uses_p=set();obs_set=set(obs);ticks_set=set(ticks)
    def same_decimal(a,b):
        try:return Decimal(str(a)).is_finite() and Decimal(str(b)).is_finite() and Decimal(str(a))==Decimal(str(b))
        except InvalidOperation:return False
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN');db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        header(db,{'observations':COLUMNS['observations'],'stream_events':COLUMNS['stream_events']})
        market_columns=db.execute('PRAGMA table_info(markets)').fetchall()
        if {r[1]:r[5] for r in market_columns if r[5]}!={'id':1} or any(not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',r[1]) for r in market_columns):raise RecoveryHold('supporting market schema identity')
        for table in ('observations','stream_events'):
            cols=db.execute('PRAGMA table_info('+table+')').fetchall()
            primary={r[1]:r[5] for r in cols if r[5]}
            expected={'id':1} if table=='observations' else {'source':1,'event_id':2}
            if primary!=expected or tuple(r[1] for r in cols)!=COLUMNS[table]:raise RecoveryHold('source raw schema/identity mismatch')
        integrity=[tuple(x) for x in db.execute('PRAGMA integrity_check(10)')]
        if integrity!=[('ok',)]:raise RecoveryHold('source integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchone():raise RecoveryHold('source foreign key check failed')
        schema=[tuple(x) for x in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        for table,keys,sql in (('observations',obs,'SELECT * FROM observations WHERE id=?'),('stream_events',ticks,"SELECT * FROM stream_events WHERE source='coinbase' AND event_id=?")):
            for key in keys:
                check();found=db.execute(sql,(key,)).fetchone()
                if found is None:conflicts.append([table,str(key),'missing candidate row']);continue
                row=dict(found)
                try:row_check(table,row)
                except (ValueError,KeyError,TypeError):conflicts.append([table,str(key),'malformed body/provenance']);continue
                records[(table,str(key))]=row
                if table=='observations':
                    market=db.execute('SELECT * FROM markets WHERE id=?',(row['market_id'],)).fetchone()
                    if market is None:conflicts.append([table,str(key),'missing supporting market'])
                    else:row_check('markets',dict(market));markets[row['market_id']]=dict(market)
        for ref in deps['snapshots']:
            check()
            if len(ref)!=10:raise RecoveryHold('snapshot reference format')
            sid,version,market,at,mid,received,target,pid,price_at,price=ref
            if sid in refs or version not in (1,2):raise RecoveryHold('duplicate/unsupported snapshot identity')
            refs[sid]=ref;asof=timestamp(at)
            if mid in obs_set:
                uses_m.add(mid);row=records.get(('observations',str(mid)))
                if row:
                    good=row['market_id']==market and row['kind']=='metadata' and timestamp(row['received_at'])==timestamp(received) and timestamp(received)<=asof+timedelta(seconds=5)
                    body=json.loads(row['payload'],parse_float=Decimal);value=(body.get('assetPriceTerms') or {}).get('priceToBeat')
                    if isinstance(value,dict):value=value.get('value')
                    if target is not None:good=good and value is not None and same_decimal(value,target)
                    if not good:conflicts.append(['observations',str(mid),'snapshot metadata/target provenance mismatch'])
            if pid in ticks_set:
                uses_p.add(pid);row=records.get(('stream_events',pid))
                if row:
                    good=timestamp(row['source_time'])==timestamp(price_at) and timestamp(price_at)<=asof+timedelta(seconds=5)
                    if price is not None:good=good and same_decimal(row['price'],price)
                    if not good:conflicts.append(['stream_events',pid,'snapshot price provenance mismatch'])
        if uses_m!=set(obs) or uses_p!=set(ticks):raise RecoveryHold('selected identity has no protected dependency')
        pred_ids=set()
        for pid,sid,market in deps['predictions']:
            if pid in pred_ids or sid not in refs or refs[sid][2]!=market:raise RecoveryHold('conflicting prediction/snapshot reference')
            pred_ids.add(pid)
        check()
        if file_binding(source)!=before or sha_file(dependencies,check)!=expected_dependency_sha:raise RecoveryHold('verification inputs changed')
        if conflicts:raise RecoveryHold('selected conflicts: '+canonical({'count':len(conflicts),'examples':conflicts[:20]}))
        catalog=[dict(dataset=t,key=k,sha256=digest(row)) for (t,k),row in sorted(records.items())]
        manifest=dict(format='AB72_SELECTED_RECOVERY_V1',production_authorized=False,source_binding=before,source_path=str(source.resolve()),
            source_sha256=expected_source_sha,dependency_sha256=expected_dependency_sha,
            source_schema_sha256=digest(schema),supporting_market_schema_sql=next(r[3] for r in schema if r[0]=='table' and r[1]=='markets'),source_integrity='ok',source_fk_violations=0,
            observations=len(obs),stream_events=len(ticks),supporting_markets=len(markets),
            snapshot_dependencies=len(refs),prediction_dependencies=len(pred_ids),
            selected_serialized_bytes=sum(len(canonical(r).encode()) for r in records.values()),
            records=catalog,selection_sha256=digest(catalog),
            supporting_market_hashes={k:digest(v) for k,v in sorted(markets.items())},
            references_sha256=digest([deps['snapshots'],deps['predictions']]))
        manifest['manifest_sha256']=digest(manifest)
        return manifest,records,markets,deps


def stage(root,verified,deadline,fault=None,guard=lambda:None):
    """Actual legacy-shaped rows and app-compatible pin maps; never a live core."""
    root=Path(root)
    if root.is_symlink() or not root.is_dir() or not root.name.startswith('generated-ab-recovery-') or root.stat().st_mode&0o077 or root.stat().st_uid!=os.getuid():raise RecoveryHold('isolated private recovery staging root required')
    if Path('/opt/tradebot') in root.resolve().parents:raise RecoveryHold('production staging forbidden')
    manifest,records,markets,deps=verified;path=root/'staged-core.db'
    if digest({k:v for k,v in manifest.items() if k!='manifest_sha256'})!=manifest['manifest_sha256']:raise RecoveryHold('manifest checksum mismatch')
    catalog=[dict(dataset=t,key=k,sha256=digest(row)) for (t,k),row in sorted(records.items())]
    if catalog!=manifest['records'] or {k:digest(v) for k,v in sorted(markets.items())}!=manifest['supporting_market_hashes'] or digest([deps['snapshots'],deps['predictions']])!=manifest['references_sha256']:
        raise RecoveryHold('verified selection changed before staging')
    if path.is_symlink():raise RecoveryHold('staged core symlink')
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('complete recovery deadline')
        guard()
    with closing(sqlite3.connect(path,timeout=.1)) as db:
        os.chmod(path,0o600);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL');db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        market_sql=manifest['supporting_market_schema_sql']
        if not re.match(r'^CREATE TABLE [\"\[]?markets(?:[\"\]]|\s|\()',market_sql,re.I):raise RecoveryHold('supporting market DDL mismatch')
        db.execute(market_sql.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
        db.executescript('''CREATE TABLE IF NOT EXISTS recovery_binding(id INTEGER PRIMARY KEY CHECK(id=1),manifest_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_records(dataset TEXT,key TEXT,record TEXT,sha256 TEXT,PRIMARY KEY(dataset,key));
CREATE TABLE IF NOT EXISTS recovery_dependencies(kind TEXT,key TEXT,record TEXT,PRIMARY KEY(kind,key));
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,market_id TEXT NOT NULL REFERENCES markets(id),received_at TEXT NOT NULL,source_time TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ab_legacy_pins(id INTEGER PRIMARY KEY REFERENCES observations(id),fingerprint TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ab_legacy_stream_pins(source TEXT,event_id TEXT,record TEXT NOT NULL,PRIMARY KEY(source,event_id));
CREATE TABLE IF NOT EXISTS ab_legacy_audit(dataset TEXT,key TEXT,fingerprint TEXT,PRIMARY KEY(dataset,key));''')
        def exact(table,columns,key_columns,values):
            check();where=' AND '.join(k+'=?' for k in key_columns);key=[values[columns.index(k)] for k in key_columns]
            old=db.execute('SELECT '+','.join(columns)+' FROM '+table+' WHERE '+where,key).fetchone()
            if old is not None:
                if tuple(old)!=tuple(values):raise RecoveryHold('staged identity/body conflict: '+table)
                return
            db.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in values)+')',values)
        allowed={'recovery_binding','recovery_records','recovery_dependencies','markets','observations','ab_legacy_pins','ab_legacy_stream_pins','ab_legacy_audit'}
        if any(r[0]!='table' or r[1] not in allowed for r in db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")):raise RecoveryHold('unexpected staged schema objects')
        before=db.total_changes
        try:
            db.execute('BEGIN IMMEDIATE')
            exact('recovery_binding',('id','manifest_sha256'),('id',),(1,manifest['manifest_sha256']))
            for key,row in markets.items():exact('markets',tuple(row),('id',),tuple(row.values()))
            for i,((table,key),row) in enumerate(sorted(records.items())):
                text=canonical(row);fp=digest(row)
                exact('recovery_records',('dataset','key','record','sha256'),('dataset','key'),(table,key,text,fp))
                if table=='observations':
                    exact('observations',COLUMNS[table],('id',),tuple(row[k] for k in COLUMNS[table]))
                    exact('ab_legacy_pins',('id','fingerprint'),('id',),(row['id'],fp));audit_key=key
                else:
                    exact('ab_legacy_stream_pins',('source','event_id','record'),('source','event_id'),(row['source'],row['event_id'],text));audit_key=canonical([row['source'],row['event_id']])
                exact('ab_legacy_audit',('dataset','key','fingerprint'),('dataset','key'),(table,audit_key,fp))
                if fault:fault(i)
            for kind,rows in (('snapshot',deps['snapshots']),('prediction',deps['predictions'])):
                for row in rows:exact('recovery_dependencies',('kind','key','record'),('kind','key'),(kind,str(row[0]),canonical(row)))
            expected_counts={'recovery_binding':1,'recovery_records':len(records),'recovery_dependencies':len(deps['snapshots'])+len(deps['predictions']),'markets':len(markets),'observations':manifest['observations'],'ab_legacy_pins':manifest['observations'],'ab_legacy_stream_pins':manifest['stream_events'],'ab_legacy_audit':len(records)}
            for table,count in expected_counts.items():
                if db.execute('SELECT count(*) FROM '+table).fetchone()[0]!=count:raise RecoveryHold('unexpected staged identity membership: '+table)
            if db.execute('PRAGMA foreign_key_check').fetchone():raise RecoveryHold('staged foreign key check')
            if [tuple(r) for r in db.execute('PRAGMA integrity_check(10)')]!=[('ok',)]:raise RecoveryHold('staged integrity check')
            check();db.commit();check()
            if fault:fault('after_commit')
        except BaseException:db.rollback();raise
        return dict(status='PASS_ISOLATED_SELECTED_STAGE',changed_rows=db.total_changes-before,
            manifest_sha256=manifest['manifest_sha256'],records=len(records),
            synchronous=db.execute('PRAGMA synchronous').fetchone()[0],runtime_activation='DISABLED',
            qualification_limit='selected rows/pin maps only; not full ApplicationStore bootstrap or production cutover')
