"""One bounded, proved raw-delete scope. No cloud calls or automatic enablement.

The caller supplies a hash-verified private recovery artifact and a fresh private
connection. Source identity callbacks record exact DELETE identities without
changing SQLite total_changes; attempted callbacks are not confused with commits.
"""
import hashlib
import json
import sqlite3
import time
from datetime import datetime,timezone
import retention
import retention_recovery as recovery


def warm_scope(db,dataset,keys):
    """Discarded full-row reads, outside the writer; never authorization facts."""
    columns=','.join(recovery.COLUMNS[dataset])
    where='id=?' if dataset=='observations' else 'source=? AND event_id=? AND received_at=?'
    for key in keys:db.execute('SELECT '+columns+' FROM '+dataset+' WHERE '+where,key).fetchone()


def affected_foreign_keys(db,dataset):
    checked=[]
    for (table,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        quoted='"'+table.replace('"','""')+'"'
        if any(row[2].lower()==dataset for row in db.execute('PRAGMA foreign_key_list('+quoted+')')):
            if db.execute('PRAGMA foreign_key_check('+quoted+')').fetchone() is not None:
                raise recovery.RecoveryError('affected foreign key violation')
            checked.append(table)
    return checked


def apply_proved_scope(db,proof):
    if db.in_transaction:raise recovery.RecoveryError('unlocked private connection required')
    if proof.get('format')!=1 or proof.get('status')!='PREPARED_NOT_APPLIED':raise recovery.RecoveryError('unreviewed proof format')
    saved=proof['recovery'];dataset=saved['dataset'];plan=proof['plan']
    if dataset not in recovery.COLUMNS:raise recovery.RecoveryError('unsupported dataset')
    expected={recovery.identity(dataset,row) for row in saved['records']}
    if not 1<=len(expected)<=1000:raise recovery.RecoveryError('scope must be1..1000 exact identities')
    if set(tuple(key) for key in plan['_approved'][dataset])!=expected:
        raise recovery.RecoveryError('approved identities differ from recovery proof')
    if any(plan['_approved'][other] for other in recovery.COLUMNS if other!=dataset):
        raise recovery.RecoveryError('only one proved dataset may be applied')
    if saved['scope']!='exact_raw_rows_only_not_database_backup':raise recovery.RecoveryError('wrong recovery scope')
    if retention.canonical_time(plan['cutoff'])>retention.retention_cutoff(datetime.now(timezone.utc),48):
        raise recovery.RecoveryError('cutoff would admit rows within48 hours')
    if retention.canonical_time(plan['cutoff'])!=retention.canonical_time(proof['cutoff']):
        raise recovery.RecoveryError('fixed cutoff differs from proved scope')
    fields=('bucket','object_path','sha256','compressed_bytes','event_count')
    verified={tuple(item[key] for key in fields) for item in saved['archives']}
    if any(tuple(item[key] for key in fields) not in verified for item in plan['_manifests']):
        raise recovery.RecoveryError('plan manifest differs from verified archive evidence')
    recovery.reconstruct_in_memory(saved)
    if db.execute('PRAGMA foreign_keys').fetchone()[0]!=1:raise recovery.RecoveryError('foreign keys must remain enabled')
    if not all(retention.timestamp_guards.available(db,table) for table in retention.SPECS):
        raise recovery.RecoveryError('qualified timestamp guards required; no scan fallback')
    original_main=db.execute('PRAGMA main.cache_size').fetchone()[0]
    original_temp=db.execute('PRAGMA temp.cache_size').fetchone()[0]
    attempted=[];committed=0;outcome=None;error=None
    result={'status':'STOP','dataset':dataset,'approved_rows':len(expected),'committed_rows':0}
    def record(*key):
        if len(attempted)>=1000:raise ValueError('delete scope exceeded')
        attempted.append(tuple(key));return 0
    def authorizer(action,first,second,database,trigger):
        if action in (sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH):return sqlite3.SQLITE_DENY
        if action in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) and database=='main':
            return sqlite3.SQLITE_OK if action==sqlite3.SQLITE_DELETE and first==dataset else sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_PRAGMA:
            read_only={'page_size','encoding','foreign_keys'}
            metadata={'index_list','index_info','table_info','foreign_key_list','foreign_key_check'}
            if first=='cache_size' or first in metadata:return sqlite3.SQLITE_OK
            if first in read_only and second is None:return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    try:
        db.execute('PRAGMA main.cache_size=-32768');db.execute('PRAGMA temp.cache_size=-16384')
        recovery.install_delete_scope(db,[saved])
        columns='OLD.id' if dataset=='observations' else 'OLD.source,OLD.event_id,OLD.received_at'
        db.create_function('retention_trial_deleted_identity',1 if dataset=='observations' else 3,record)
        db.execute(f'''CREATE TEMP TRIGGER retention_trial_record_delete AFTER DELETE ON main.{dataset}
                      BEGIN SELECT retention_trial_deleted_identity({columns}); END''')
        warm_started=time.monotonic();warm_scope(db,dataset,sorted(expected))
        result['unlocked_full_row_warm_seconds']=time.monotonic()-warm_started
        db.set_authorizer(authorizer)
        try:
            outcome=retention.apply_retention(db,plan,retention.RetentionConfig(True,48,1000),confirm=True)
        except BaseException as caught:
            error=caught;outcome=getattr(caught,'retention_progress',{})
        progress=outcome.get('datasets',{}).get(dataset,{})
        committed=progress.get('committed_rows_seen',progress.get('deleted_rows',0))
        result['apply']=outcome;result['committed_rows']=committed
        if error is not None:raise error
        if len(attempted)!=committed or len(set(attempted))!=committed or not set(attempted)<=expected:
            raise recovery.RecoveryError('delete identity/count reconciliation failed')
        where='id=?' if dataset=='observations' else 'source=? AND event_id=? AND received_at=?'
        if any(db.execute('SELECT 1 FROM '+dataset+' WHERE '+where,key).fetchone() for key in attempted):
            raise recovery.RecoveryError('deleted identity unexpectedly present')
        result['affected_fk_tables_checked']=affected_foreign_keys(db,dataset)
        if committed<=0:raise recovery.RecoveryError('no deletion trial completed')
        result['status']='PASS';result['skipped_rows']=len(expected)-committed
    except BaseException as caught:
        result.update(error_type=type(caught).__name__,committed_rows=committed)
        if isinstance(caught,retention.RetentionBudgetError):
            result.update(failed_phase=caught.phase,failed_write_seconds=caught.seconds,phase_seconds=caught.phase_seconds)
        elif hasattr(caught,'retention_failed_operation'):
            result['failed_phase']=caught.retention_failed_operation
        if isinstance(caught,recovery.RecoveryError):result['reason']=str(caught)
    finally:
        db.set_authorizer(None)
        if db.in_transaction:db.rollback()
        db.execute(f'PRAGMA main.cache_size={original_main}');db.execute(f'PRAGMA temp.cache_size={original_temp}')
    # One bounded dataset means at most one nonempty DELETE transaction.
    # A rolled-back callback list is never reported as committed deletion.
    result['attempted_identity_count']=len(attempted)
    if committed and committed!=len(attempted):
        result['status']='STOP';result['identity_commit_reconciliation']='UNKNOWN'
    else:
        identities=attempted if committed else []
        result['deleted_identities']=identities
        result['deleted_identities_sha256']=hashlib.sha256(json.dumps(identities,separators=(',',':')).encode()).hexdigest()
    return result
