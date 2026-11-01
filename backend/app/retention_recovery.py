"""Archive-backed recovery proof for an exact bounded raw-row deletion scope.

No cloud writes, production database opens, deletes, backups or snapshots here.
Caller supplies bytes obtained by authenticated private-object readback and the
current raw rows. Original payload TEXT is retained for byte-exact reconstruction;
archive payload JSON is compared with exact Decimal parsing, never float coercion.
"""
from datetime import datetime,timezone
from decimal import Decimal
import gzip
import hashlib
import io
import json
import sqlite3

from retention import canonical_time,canonical_manifest_time,_manifest_interval,RetentionError

COLUMNS={
 'observations':('id','market_id','received_at','source_time','kind','payload'),
 'stream_events':('source','event_id','received_at','source_time','price','size','side','payload')}
MAX_COMPRESSED=64*1024**2
MAX_RAW=256*1024**2
MAX_LINE=8*1024**2


class RecoveryError(ValueError):pass


def identity(dataset,row):
    if dataset=='observations':
        if type(row.get('id')) is not int:raise RecoveryError('invalid observation id')
        return (row['id'],)
    if dataset!='stream_events':raise RecoveryError('unsupported raw dataset')
    values=tuple(row.get(key) for key in ('source','event_id','received_at'))
    if not all(isinstance(value,str) for value in values):raise RecoveryError('invalid stream identity')
    return values


def _invalid_constant(value):
    raise RecoveryError('non-finite JSON value')


def _read_json(value):
    return json.loads(value,parse_float=Decimal,parse_constant=_invalid_constant)


def _json_value(value):
    if value is None:return ('null',)
    if type(value) is bool:return ('bool',value)
    if isinstance(value,(int,Decimal)):return ('number',Decimal(value))
    if isinstance(value,str):return ('string',value)
    if isinstance(value,list):return ('array',tuple(_json_value(x) for x in value))
    if isinstance(value,dict):return ('object',tuple(sorted((key,_json_value(x)) for key,x in value.items())))
    raise RecoveryError('unsupported JSON value')


def verify_archive(manifest,compressed,requested,bucket='market-raw'):
    dataset=(manifest.get('metadata') or {}).get('dataset')
    if dataset not in COLUMNS:raise RecoveryError('unsupported archive dataset')
    try:lo,hi=_manifest_interval(dataset,manifest,bucket)
    except (ValueError,TypeError,KeyError):raise RecoveryError('untrusted archive evidence') from None
    if (not isinstance(compressed,bytes) or len(compressed)>MAX_COMPRESSED
        or len(compressed)!=manifest.get('compressed_bytes')
        or hashlib.sha256(compressed).hexdigest()!=manifest.get('sha256')):
        raise RecoveryError('archive byte count or checksum mismatch')
    requested=set(requested);found={};seen=set();first=last=previous=None;count=total=0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
            while True:
                line=archive.readline(MAX_LINE+1)
                if not line:break
                total+=len(line);count+=1
                if len(line)>MAX_LINE or total>MAX_RAW or count>50000:
                    raise RecoveryError('archive resource limit')
                item=_read_json(line)
                if not isinstance(item,dict) or item.get('dataset')!=dataset or not isinstance(item.get('row'),dict):
                    raise RecoveryError('archive record schema mismatch')
                row=item['row'];key=identity(dataset,row)
                if dataset=='observations' and 'source_id' in row and row['source_id']!=row['id']:
                    raise RecoveryError('archive observation provenance mismatch')
                if not set(COLUMNS[dataset])<=row.keys():raise RecoveryError('archive columns missing')
                canonical_time(row['received_at'])
                primary=key if dataset=='observations' else key[:2]
                if primary in seen:raise RecoveryError('duplicate archive identity')
                seen.add(primary)
                order=key if dataset=='observations' else (row['received_at'],row['source'],row['event_id'])
                if previous is not None and order<=previous:raise RecoveryError('archive identity order mismatch')
                previous=order
                if first is None:first=row
                last=row
                if key in requested:found[key]=row
    except (OSError,EOFError,UnicodeError,json.JSONDecodeError,TypeError,KeyError,RetentionError):
        raise RecoveryError('archive decoding failed') from None
    if count!=manifest['event_count'] or first is None:raise RecoveryError('archive event count mismatch')
    ends=(identity(dataset,first),identity(dataset,last)) if dataset=='observations' else (
        (canonical_time(first['received_at']),first['source'],first['event_id']),
        (canonical_time(last['received_at']),last['source'],last['event_id']))
    if ends!=(lo,hi):raise RecoveryError('archive identity boundaries mismatch')
    if (canonical_time(first['received_at'])!=canonical_manifest_time(manifest['started_at'])
        or canonical_time(last['received_at'])!=canonical_manifest_time(manifest['ended_at'])):
        raise RecoveryError('archive time boundaries mismatch')
    proof={key:manifest[key] for key in ('bucket','object_path','sha256','compressed_bytes','event_count')}
    proof.update(dataset=dataset,readback_verified_at=datetime.now(timezone.utc).isoformat())
    return proof,found


def build_manifest(dataset,current_rows,verified_objects):
    """Require archive coverage/equality for every original row; no implicit skip."""
    if dataset not in COLUMNS:raise RecoveryError('unsupported raw dataset')
    if not 1<=len(current_rows)<=1000:raise RecoveryError('recovery scope must be1..1000 rows')
    evidence=[];archived={}
    for proof,rows in verified_objects:
        required=('bucket','object_path','sha256','compressed_bytes','event_count','readback_verified_at')
        if proof.get('dataset')!=dataset or not all(key in proof for key in required):
            raise RecoveryError('recovery proof dataset or readback evidence missing')
        evidence.append(proof)
        for key,row in rows.items():
            if key in archived and archived[key]!=row:raise RecoveryError('conflicting archive rows')
            archived[key]=row
    output=[];seen=set()
    for raw in current_rows:
        key=identity(dataset,raw)
        if key in seen:raise RecoveryError('duplicate proposed identity')
        seen.add(key);cloud=archived.get(key)
        if cloud is None:raise RecoveryError('proposed row lacks readback archive coverage')
        for column in COLUMNS[dataset]:
            if column=='payload':
                try:equal=_json_value(_read_json(raw[column]))==_json_value(cloud[column])
                except (ValueError,TypeError):raise RecoveryError('raw payload cannot be reconstructed') from None
            else:equal=raw[column]==cloud[column]
            if not equal:raise RecoveryError('raw row differs from verified archive')
        canonical_time(raw['received_at'])
        nullable=('source_time',) if dataset=='observations' else ('size','side')
        for column in COLUMNS[dataset]:
            if column=='id':continue
            if raw[column] is None and column in nullable:continue
            if not isinstance(raw[column],str):raise RecoveryError('unsupported raw column type')
        output.append({column:raw[column] for column in COLUMNS[dataset]})
    return {'format':1,'scope':'exact_raw_rows_only_not_database_backup','dataset':dataset,
            'created_at':datetime.now(timezone.utc).isoformat(),'records':output,'archives':evidence}


def reconstruct_in_memory(manifest):
    """Demonstrate raw-only reconstruction; structured data is not backed up."""
    dataset=manifest['dataset'];columns=COLUMNS[dataset]
    db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
    try:
        if dataset=='observations':
            db.execute('CREATE TABLE markets(id TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO markets VALUES(?)',[(value,) for value in {row['market_id'] for row in manifest['records']}])
            db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,market_id TEXT NOT NULL REFERENCES markets(id),received_at TEXT NOT NULL,source_time TEXT,kind TEXT NOT NULL,payload TEXT NOT NULL)')
        else:
            db.execute('CREATE TABLE stream_events(source TEXT NOT NULL,event_id TEXT NOT NULL,received_at TEXT NOT NULL,source_time TEXT NOT NULL,price TEXT NOT NULL,size TEXT,side TEXT,payload TEXT NOT NULL,PRIMARY KEY(source,event_id))')
        rows=[tuple(row[column] for column in columns) for row in manifest['records']]
        db.executemany(f'INSERT INTO {dataset} VALUES({",".join("?" for _ in columns)})',rows)
        actual=db.execute(f'SELECT {",".join(columns)} FROM {dataset}').fetchall()
        if sorted(actual,key=repr)!=sorted(rows,key=repr):raise RecoveryError('raw reconstruction mismatch')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise RecoveryError('reconstruction foreign key mismatch')
        return {'reconstructed_rows':len(rows),'raw_columns_exact':True,'full_database_backup':False}
    finally:db.close()
