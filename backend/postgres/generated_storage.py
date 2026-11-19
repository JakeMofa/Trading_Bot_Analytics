"""Bounded generated-only durable local storage; never raw/cloud retirement.

Source outbox/raw rows remain. Acknowledgement requires committed append-only
bytes and a separate read-only transaction returning those exact bytes. The
sink is local PostgreSQL, not a remote backup or a Supabase receipt.
"""
from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveLimits, CycleBudget, encoded, sha256
from .history_v2_envelope import validate_outbox_stream
from .lifecycle import ArchiveWorker, LifecycleHold

ORIGIN='generated-pp'
HEADROOM=128
MAX_STORED_BYTES=128*1024**2
MAX_STORED_ROWS=100000
MAX_PAGES=4
LIMITS=ArchiveLimits(max_rows=250,max_requests=8,max_seconds=20,max_cycle_bytes=16*1024**2)


def requested(environ,mode,origin):
    value=environ.get('TRADEBOT_GENERATED_LOCAL_STORAGE','false')
    if value not in ('true','false') or (value=='true' and (mode!='generated' or origin!=ORIGIN)):
        raise LifecycleHold('exact generated-only local storage selection required')
    return value=='true'


def identity(db,*,readonly=False):
    extra=",current_setting('transaction_read_only') AS readonly" if readonly else ''
    row=db.execute("SELECT current_user AS role,current_database() AS database,"
        "current_setting('fsync') AS fsync,current_setting('full_page_writes') AS full_page_writes"+extra).fetchone()
    expected=dict(role='tradebot_lifecycle',database='tradebot_pp',fsync='on',full_page_writes='on')
    if readonly:expected['readonly']='on'
    if row != expected:
        raise LifecycleHold('generated local storage requires exact restricted lifecycle identity')


def store_page(repository,records,budget):
    generation=records[0]['generation_id']
    validate_outbox_stream(records,origin_id=ORIGIN,generation_id=generation)
    size=len(encoded(records))
    write_deadline=budget.clock()+budget.request(size)
    # Commit first; the independent read is never a read-your-uncommitted-write
    # check. An ambiguous commit leaves pending rows, and exact retry reconciles.
    with repository.transaction() as db:
        remaining=int(1000*(write_deadline-budget.clock()))
        if remaining<=0:raise ArchiveLimit('generated storage write deadline')
        db.execute("SELECT set_config('transaction_timeout',%s,true)",(f'{remaining}ms',))
        identity(db)
        db.execute("SET LOCAL synchronous_commit='on'")
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('generated-local-storage-v1',0))")
        used=db.execute('''SELECT count(*) AS rows,coalesce(sum(octet_length(envelope)),0) AS bytes
            FROM (SELECT envelope FROM archive.generated_outbox_storage LIMIT 100001) bounded''').fetchone()
        if used['rows']>MAX_STORED_ROWS or used['bytes']>MAX_STORED_BYTES:
            raise ArchiveLimit('generated local storage capacity reached')
        old=db.execute('''SELECT outbox_id,envelope,envelope_hash FROM archive.generated_outbox_storage
            WHERE origin_id=%s AND outbox_id=ANY(%s)''',(ORIGIN,[r['id'] for r in records])).fetchall()
        prior={row['outbox_id']:row for row in old}
        fresh=[]
        for record in records:
            value=encoded(record)
            if record['id'] in prior:
                row=prior[record['id']]
                if bytes(row['envelope']) != value or row['envelope_hash'] != sha256(value):
                    raise ArchiveIntegrityError('generated stored identity conflict')
            else: fresh.append((ORIGIN,record['id'],generation,value,sha256(value)))
        if (used['rows']+len(fresh)>MAX_STORED_ROWS or
                used['bytes']+sum(len(row[3]) for row in fresh)>MAX_STORED_BYTES):
            raise ArchiveLimit('generated local storage capacity reached')
        for offset in range(0,len(fresh),25):
            page=fresh[offset:offset+25]
            placeholders=','.join(['(%s,%s,%s,%s,%s)']*len(page))
            db.execute('''INSERT INTO archive.generated_outbox_storage
                (origin_id,outbox_id,generation_id,envelope,envelope_hash) VALUES '''+placeholders,
                [value for row in page for value in row])
    if budget.clock()>=write_deadline:raise ArchiveLimit('generated storage write deadline')
    budget.check()
    read_deadline=budget.clock()+budget.request(size)
    # A new authenticated connection/transaction sees only committed bytes.
    with repository.connection_factory() as db:
        with db.transaction():
            db.execute('SET TRANSACTION READ ONLY')
            remaining=int(1000*(read_deadline-budget.clock()))
            if remaining<=0:raise ArchiveLimit('generated storage read deadline')
            db.execute("SELECT set_config('transaction_timeout',%s,true),set_config('statement_timeout',%s,true)",
                       (f'{remaining}ms',f'{min(4000,remaining)}ms'))
            identity(db,readonly=True)
            rows=db.execute('''SELECT outbox_id,envelope,envelope_hash FROM archive.generated_outbox_storage
                WHERE origin_id=%s AND generation_id=%s AND outbox_id=ANY(%s) ORDER BY outbox_id''',
                (ORIGIN,generation,[r['id'] for r in records])).fetchall()
            if len(rows)!=len(records): raise ArchiveIntegrityError('generated durable readback incomplete')
            for row,record in zip(rows,records):
                value=encoded(record)
                if (row['outbox_id']!=record['id'] or bytes(row['envelope'])!=value or
                        row['envelope_hash']!=sha256(value)):
                    raise ArchiveIntegrityError('generated durable readback mismatch')
    budget.check()
    if budget.clock()>=read_deadline:raise ArchiveLimit('generated storage read deadline')
    repository.acknowledge(generation,records)
    budget.check()


def drain(repository):
    if repository.environment!='preprod' or repository.pending_outbox_limit!=10000:
        raise LifecycleHold('fixed isolated generated storage profile required')
    acknowledged=0
    with CycleBudget(LIMITS) as budget,repository.structured_sync_lock(ORIGIN):
        for _ in range(MAX_PAGES):
            generations=repository.structured_pending_generations(ORIGIN)
            if not generations:break
            generation=generations[0]['generation_id']
            rows=repository.outbox(generation,LIMITS.max_rows,LIMITS.max_decoded_bytes)
            if not rows:raise ArchiveIntegrityError('generated pending scope changed')
            records=ArchiveWorker.structured_records(rows)
            store_page(repository,records,budget)
            acknowledged+=len(records)
            # Bootstrap needs enough room for a bounded repeated acceptance;
            # periodic cycles can continue draining, without inflating admission.
            with repository.transaction() as db:
                pending=db.execute('''SELECT count(*) AS n FROM (SELECT 1 FROM ops.outbox
                    WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT 10001) bounded''',(ORIGIN,)).fetchone()['n']
            if pending<=10000-HEADROOM:break
        with repository.transaction() as db:
            pending=db.execute('''SELECT count(*) AS n FROM (SELECT 1 FROM ops.outbox
                WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT 10001) bounded''',(ORIGIN,)).fetchone()['n']
        if pending>10000-HEADROOM:
            raise LifecycleHold('generated acceptance headroom not proven')
        return {'scope':'durable_generated_local_storage','acknowledged':acknowledged,
            'pending':pending,'headroom':10000-pending,'raw_retirement_authorized':False,
            'cloud_receipts':False,'requests':budget.requests,'bytes':budget.bytes}
