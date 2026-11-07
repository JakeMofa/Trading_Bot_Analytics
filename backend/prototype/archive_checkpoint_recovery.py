"""Explicit sealed-generation cursor reconciliation; never seeds from global state."""
import json, time
from retention import _manifest_interval
from retention_recovery import verify_archive, build_manifest, identity
from raw_generations import Store, Stop, COLUMNS
import cloud_memory

def reconcile(connection,cloud,gid,dataset,deadline):
    if getattr(connection.store,'role',None)!='lifecycle' or connection.db.in_transaction:
        raise Stop('checkpoint reconciliation requires idle lifecycle worker')
    if dataset not in COLUMNS or not 0<deadline-time.monotonic()<=30:
        raise Stop('checkpoint reconciliation bound')
    if getattr(cloud,'deadline',deadline)>deadline:raise Stop('reconciliation transport exceeds original deadline')
    def guard():
        if time.monotonic()>=deadline:raise Stop('checkpoint reconciliation expired')
    connection.db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
    try:
        connection._refresh()
        state=connection.db.execute('SELECT state FROM ab_generations WHERE id=?',(gid,)).fetchone()
        if not state or state[0] not in ('sealed','draining'):raise Stop('reconciliation requires sealed generation')
        alias=next((a for a in connection.raw_attached if connection.db.execute('SELECT id FROM '+a+'.generation').fetchone()[0]==gid),None)
        if alias is None:raise Stop('generation raw unavailable for reconciliation')
        catalog=connection.db.execute('SELECT path,metadata FROM ab_manifests WHERE gen=? AND dataset=? ORDER BY path LIMIT 9',(gid,dataset)).fetchall()
        if not 1<=len(catalog)<=8:raise Stop('bounded reconciliation manifest scope required')
        file=connection.protocol.path(gid)
        def physical():
            result=[]
            for suffix in ('','-wal'):
                from pathlib import Path
                path=Path(str(file)+suffix)
                if not path.exists():continue
                st=path.stat()
                if suffix and st.st_size==0:continue
                result.append((suffix,st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns))
            return result
        before=physical()
        manifests=[]
        for path,text in catalog:
            manifest=json.loads(text)
            if manifest['object_path']!=path or not path.startswith(gid+'/') or manifest['metadata'].get('generation_id')!=gid:raise Stop('reconciliation manifest identity')
            lo,hi=_manifest_interval(dataset,manifest,'market-raw');manifests.append((lo,hi,manifest))
        manifests.sort(key=lambda value:value[:2]);previous=None;total=0;last=None;acknowledgements=[]
        key='id' if dataset=='observations' else '(received_at,source,event_id)'
        mark='?' if dataset=='observations' else '(?,?,?)'
        for lo,hi,manifest in manifests:
            guard()
            if previous is not None and lo<=previous:raise Stop('overlapping reconciled manifests')
            previous=hi
            order='id' if dataset=='observations' else 'received_at,source,event_id'
            cursor=connection.db.execute('SELECT '+','.join(COLUMNS[dataset])+' FROM '+alias+'.'+dataset+' WHERE '+key+'>='+mark+' AND '+key+'<='+mark+' ORDER BY '+order+' LIMIT 1001',(*lo,*hi))
            rows=[dict(zip(COLUMNS[dataset],row)) for row in cursor.fetchall()]
            if not 1<=len(rows)<=1000:raise Stop('reconciliation local row bound')
            for row in rows:Store.verify_ack_row(connection.protocol,gid,dataset,row)
            proof,found=verify_archive(manifest,cloud.download_bytes('market-raw',manifest['object_path']),{identity(dataset,r) for r in rows})
            build_manifest(dataset,rows,[(proof,found)])
            total+=len(rows);last=rows[-1]
            for row in rows:
                if dataset=='observations':where,args="e.id=?",(row['id'],)
                else:where,args="e.event_key=?",(row['source']+':'+row['event_id'],)
                receipt=connection.db.execute('SELECT e.id,r.sha256 FROM ab_events e JOIN ab_raw_receipts r ON r.id=e.id WHERE e.gen=? AND '+where,(gid,*args)).fetchone()
                acknowledgements.append(receipt)
        guard()
        # A cursor is valid only for a fully verified prefix, not disjoint islands.
        prefix=connection.db.execute('SELECT count(*) FROM '+alias+'.'+dataset+' WHERE '+key+'<='+mark,previous).fetchone()[0]
        if prefix!=total:raise Stop('reconciliation prefix coverage gap')
        name=connection.archive_checkpoint_name(dataset,gid)
        source_id=last.get('id');source_key=None if dataset=='observations' else cloud_memory._stream_cursor_key(last)
        target=(source_id,last['received_at'],source_key,total)
        prior=cloud_memory._checkpoint(connection,name)
        if prior!=(None,None,None,0) and prior!=target:raise Stop('conflicting generation checkpoint')
        def unchanged():
            guard()
            if before!=physical():raise Stop('reconciled raw changed')
            if connection.db.execute('SELECT state FROM ab_generations WHERE id=?',(gid,)).fetchone()!=state:raise Stop('reconciled generation changed')
            if connection.db.execute('SELECT path,metadata FROM ab_manifests WHERE gen=? AND dataset=? ORDER BY path LIMIT 9',(gid,dataset)).fetchall()!=catalog:raise Stop('reconciled catalog changed')
            for eid,sha in acknowledgements:
                if connection.db.execute("SELECT r.sha256 FROM ab_raw_receipts r JOIN ab_events e ON e.id=r.id WHERE e.id=? AND e.gen=? AND e.dataset=? AND e.status='committed'",(eid,gid,dataset)).fetchone()!=(sha,):raise Stop('reconciled receipt changed')
        unchanged()
        cloud_memory._cloud_checkpoint(cloud,name,source_id=source_id,source_time=last['received_at'],source_key=source_key,rows_synced=total,status='verified',detail=manifests[-1][2]['object_path'])
        unchanged()
        with connection:
            unchanged()
            if prior==(None,None,None,0):cloud_memory._save_checkpoint(connection,name,source_id=source_id,source_time=last['received_at'],source_key=source_key,rows_added=total,status='verified',detail=manifests[-1][2]['object_path'])
        return {'status':'verified','generation_id':gid,'dataset':dataset,'rows':total,'objects':len(manifests),'idempotent':prior==target}
    finally:connection.db.set_progress_handler(None,0)
