"""Bounded local initial-A preparation under the host's one-use enter authority.

Never enables a collector, changes historical seals, transfers cloud data or
retires a partition. No runtime service calls this module automatically.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
import re
import uuid

from .archive_codec import ArchiveLimits, CycleBudget, encoded, sha256, wire
from .lifecycle import LifecycleHold, LifecycleRepository, validate_manifest_chain
from .pp_retirement_report import bound_catalog
from .rehearsal_profile import (BOUNDARY_ORIGINS, BOUNDARY_POLICY, TRIAL_ORIGIN, NEXT_TRIAL_ORIGIN, THIRD_TRIAL_ORIGIN,
    FOURTH_TRIAL_ORIGIN, FIFTH_TRIAL_ORIGIN, SIXTH_TRIAL_ORIGIN, SEVENTH_TRIAL_ORIGIN, TRIAL_ORIGINS,
    boundary_anchor, canonical_anchor, cycle_anchor, elapsed_cycle_binding, elapsed_cycle_seconds,
    TRIAL_PREPARATION_CHECKPOINT)

CONSUMER=TRIAL_PREPARATION_CHECKPOINT
RETAINED_SECOND_INITIAL_A='41c82044-0fb8-4900-bea0-7c43ba079ff0'
RETAINED_THIRD_A='15a239c9-2f9b-4bdc-bd89-7cd1e2812f45'
RETAINED_THIRD_B='381070ac-3624-4826-8dc6-7ea5a272f97e'
RETAINED_FOURTH_A='53505b6c-f9b2-4b4b-be55-e45f94a6841c'
RETAINED_FOURTH_SOURCE='17ba31ec7ccb3ade9b94247291721f65d863f5da'
RETAINED_FIFTH_A='c7fbfa88-f3b8-40a3-83fa-c01912220570'
RETAINED_FIFTH_B='7eb27e2f-f53b-4b50-98db-00a318853b0b'
RETAINED_FIFTH_SOURCE='74f2aa276ff68d44ef943295841380d198ca571b'
RETAINED_FIFTH_SEAL='1275e64a5f299881d6fb78d43735ee0563aa028421110a47fb84e70abc110b43'
RETAINED_FIFTH_SEALED_AT=datetime.fromisoformat('2026-11-23T20:15:20.379646+00:00')
RETAINED_FIFTH_SESSION='070bb486-2405-4695-8d67-e49a940bcb7b'
RETAINED_FIFTH_RAW=(24044,5690)
RETAINED_FIFTH_ACK=(25872,6149)
RETAINED_FIFTH_MANIFESTS=49
RETAINED_SIXTH_IDS=(
    'bf43a58d-4171-435a-b657-79c335b2eea3',
    'e07e981a-2617-43ac-a050-fcf4455a12f1',
    '77ee5f30-7c3d-4285-8807-7d5543cf4bde',
)
RETAINED_SIXTH_B_SEAL='c89d16e6066a3f33f0ce5ee1902a754ff2397d84d9c6c901b4fbb3c2cd51a85b'
RETAINED_SIXTH_B_RAW=24896
RETAINED_SIXTH_B_ACK=27528
RETAINED_SIXTH_B_MANIFESTS=50


def retained_third_fingerprint(db,writers):
    """Validate both retained03 catalogs locally; never replace independent cloud proof."""
    rows=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
        'ORDER BY created_at,generation_id LIMIT 3 FOR SHARE',(THIRD_TRIAL_ORIGIN,)).fetchall()
    old=next((row for row in writers if row['origin_id']==THIRD_TRIAL_ORIGIN),None)
    if (len(rows)!=2 or [row['generation_id'] for row in rows]!=[RETAINED_THIRD_A,RETAINED_THIRD_B]
            or [row['slot'] for row in rows]!=['A','B']
            or any(row['state']!='verified' or row['hold_reason'] is not None
                   or row['retired_at'] is not None for row in rows)
            or old is None or old['generation_id']!=RETAINED_THIRD_B or old['epoch']!=5
            or old['collector_enabled'] or old['collector_session_id'] is not None
            or old['collector_lease_expires_at'] is not None
            or rows[0]['sealed_at']!=rows[1]['started_at']):
        raise LifecycleHold('exact retained third trial A and B archives required before fourth admission')
    if db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s '
            'AND (acknowledged_at IS NULL OR generation_id IS NULL OR generation_id NOT IN (%s,%s)) LIMIT 1',
            (THIRD_TRIAL_ORIGIN,RETAINED_THIRD_A,RETAINED_THIRD_B)).fetchone():
        raise LifecycleHold('both retained third trial acknowledgements must be complete')
    snapshots=[]
    for row in rows:
        child='events_g_'+row['generation_id'].replace('-','')
        attached=db.execute("SELECT EXISTS(SELECT 1 FROM pg_inherits i "
            "JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE i.inhparent='raw.events'::regclass AND n.nspname='raw' AND c.relname=%s "
            "AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)) AS valid",
            (child,row['generation_id'])).fetchone()['valid']
        if row['partition_name']!=child or attached is not True:
            raise LifecycleHold('retained third trial partition attachment changed')
        catalog=LifecycleRepository._manifests(db,row['generation_id'])
        prefix='raw-v1/'+sha256(THIRD_TRIAL_ORIGIN.encode())+'/'+row['generation_id']+'/'
        if (not catalog or any(item['manifest_id']!=f'raw.events:{n:012d}'
                or item['object_key']!=prefix+item['sha256']+'.jsonl.gz'
                or item['verified_at'] is None
                or item['verification']!={'method':'fresh_authenticated_readback'} for n,item in enumerate(catalog))
                or not 1<=row['seal_count']<=64000
                or validate_manifest_chain(catalog,row)!=row['seal_hash']):
            raise LifecycleHold('retained third trial authenticated catalog or coverage changed')
        count=db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events WHERE origin_id=%s '
            'AND generation_id=%s LIMIT 64001) bounded',(THIRD_TRIAL_ORIGIN,row['generation_id'])).fetchone()['n']
        if count!=row['seal_count']:
            raise LifecycleHold('retained third trial raw count changed')
        snapshots.append(dict(generation=wire(row),manifests=wire(catalog)))
    return sha256(encoded(dict(generations=snapshots,writer=wire(old))))


def retained_fourth_fingerprint(db, writers):
    """Bind the stopped, unsealed trial04 partition to the trial05 admission."""
    rows = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                      'ORDER BY created_at,generation_id LIMIT 2 FOR SHARE',
                      (FOURTH_TRIAL_ORIGIN,)).fetchall()
    writer = next((row for row in writers if row['origin_id']==FOURTH_TRIAL_ORIGIN), None)
    if (len(rows)!=1 or writer is None or writer['generation_id']!=RETAINED_FOURTH_A
            or writer['epoch']!=3 or writer['collector_enabled']
            or writer['collector_session_id'] is not None or writer['collector_lease_expires_at'] is not None):
        raise LifecycleHold('exact stopped fourth trial writer required')
    row = rows[0]
    child = 'events_g_'+RETAINED_FOURTH_A.replace('-','')
    if (row['generation_id']!=RETAINED_FOURTH_A or row['partition_name']!=child
            or row['slot']!='A' or row['state']!='collecting' or row['sealed_at'] is not None
            or row['retired_at'] is not None or row['hold_reason'] is not None):
        raise LifecycleHold('exact unsealed fourth trial A required')
    attached = db.execute("SELECT EXISTS(SELECT 1 FROM pg_inherits i "
        "WHERE i.inhparent='raw.events'::regclass AND i.inhrelid=to_regclass(%s) "
        "AND pg_get_expr((SELECT relpartbound FROM pg_class WHERE oid=i.inhrelid),i.inhrelid)"
        "=format('FOR VALUES IN (%%L)',%s::text)) AS valid",
        ('raw.'+child, RETAINED_FOURTH_A)).fetchone()['valid']
    checkpoints = {entry['consumer']:entry['cursor'] for entry in db.execute(
        'SELECT consumer,cursor FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s '
        'AND consumer IN (%s,%s)',(FOURTH_TRIAL_ORIGIN,RETAINED_FOURTH_A,CONSUMER,
                                  'rehearsal:two-leg-session')).fetchall()}
    prepared = checkpoints.get(CONSUMER,{})
    admitted = checkpoints.get('rehearsal:two-leg-session',{})
    if (not attached or prepared.get('source_sha')!=RETAINED_FOURTH_SOURCE
            or prepared.get('initial_a')!=RETAINED_FOURTH_A
            or admitted.get('initial_a')!=RETAINED_FOURTH_A or admitted.get('lease_seconds')!=6600
            or LifecycleRepository._manifests(db,RETAINED_FOURTH_A)):
        raise LifecycleHold('retained fourth trial attachment or evidence changed')
    raw = db.execute('SELECT event_id,source,content_hash FROM raw.events WHERE origin_id=%s '
                     'AND generation_id=%s ORDER BY source,event_id LIMIT 660',
                     (FOURTH_TRIAL_ORIGIN,RETAINED_FOURTH_A)).fetchall()
    outbox = db.execute('SELECT id,generation_id,content_hash,acknowledged_at FROM ops.outbox '
                        'WHERE origin_id=%s ORDER BY id LIMIT 706',(FOURTH_TRIAL_ORIGIN,)).fetchall()
    if (len(raw)!=659 or len(outbox)!=705 or any(entry['generation_id']!=RETAINED_FOURTH_A
            or entry['acknowledged_at'] is None for entry in outbox)):
        raise LifecycleHold('retained fourth trial row or acknowledgement count changed')
    return sha256(encoded(wire(dict(generation=row,writer=writer,checkpoints=checkpoints,
                                    raw=raw,outbox=outbox))))


def _retained_outbox_fingerprint(db, origin, generation, expected):
    first = db.execute('SELECT min(id) AS id FROM ops.outbox WHERE generation_id=%s AND origin_id=%s',
                       (generation, origin)).fetchone()['id']
    count = pending = 0
    digest = hashlib.sha256()
    last = first
    # Callers hold the stopped writer rows. Hash the same ordered UTF-8 bytes
    # as the old aggregate, with an extra row allowed to detect overcounts.
    while last is not None and count <= expected:
        comparison = '>' if count else '>='
        page = db.execute(f"""SELECT max(id) AS last, count(*) AS n,
            count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending,
            string_agg(jsonb_build_array(id,content_hash,acknowledged_at)::text, chr(10) ORDER BY id) AS body
            FROM (SELECT id,content_hash,acknowledged_at FROM ops.outbox
                  WHERE generation_id=%s AND origin_id=%s AND id{comparison}%s
                  ORDER BY id LIMIT %s) page""",
            (generation, origin, last, min(1024, expected + 1 - count))).fetchone()
        if not page['n']:
            break
        if count:
            digest.update(b'\n')
        digest.update(page['body'].encode('utf-8'))
        count += page['n']
        pending += page['pending']
        last = page['last']
    return dict(n=count, pending=pending, digest=digest.hexdigest() if count else None)


def retained_fifth_fingerprint(db, writers):
    """Bind the exact retained trial05 pair without authorizing any removal."""
    rows = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                      'ORDER BY created_at,generation_id LIMIT 3 FOR SHARE',
                      (FIFTH_TRIAL_ORIGIN,)).fetchall()
    writer = next((row for row in writers if row['origin_id']==FIFTH_TRIAL_ORIGIN), None)
    if (len(rows)!=2 or [row['generation_id'] for row in rows]!=[RETAINED_FIFTH_A,RETAINED_FIFTH_B]
            or writer is None or writer['generation_id']!=RETAINED_FIFTH_B
            or writer['epoch']!=4 or writer['collector_enabled']
            or writer['collector_session_id'] is not None or writer['collector_lease_expires_at'] is not None):
        raise LifecycleHold('exact stopped fifth trial A and B required')
    a,b=rows
    if (a['slot']!='A' or a['state']!='verified' or a['seal_count']!=RETAINED_FIFTH_RAW[0]
            or a['seal_hash']!=RETAINED_FIFTH_SEAL or a['sealed_at']!=RETAINED_FIFTH_SEALED_AT
            or a['sealed_at']!=b['started_at'] or not a['verified_at']
            or b['slot']!='B' or b['state']!='collecting'
            or any(b[key] is not None for key in ('sealed_at','verified_at','seal_count','seal_hash'))
            or any(row['retired_at'] is not None or row['hold_reason'] is not None for row in rows)):
        raise LifecycleHold('retained fifth trial seal or successor changed')
    if db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s AND '
                  '(acknowledged_at IS NULL OR generation_id IS NULL OR generation_id NOT IN (%s,%s)) LIMIT 1',
                  (FIFTH_TRIAL_ORIGIN,RETAINED_FIFTH_A,RETAINED_FIFTH_B)).fetchone():
        raise LifecycleHold('both retained fifth trial acknowledgements must be complete')
    checkpoints = {entry['consumer']:entry['cursor'] for entry in db.execute(
        'SELECT consumer,cursor FROM archive.checkpoints WHERE origin_id=%s AND generation_id=%s '
        'AND consumer IN (%s,%s)',(FIFTH_TRIAL_ORIGIN,RETAINED_FIFTH_A,CONSUMER,
                                  'rehearsal:two-leg-session')).fetchall()}
    prepared=checkpoints.get(CONSUMER,{})
    admitted=checkpoints.get('rehearsal:two-leg-session',{})
    if (prepared.get('source_sha')!=RETAINED_FIFTH_SOURCE or prepared.get('policy')!=CONSUMER
            or prepared.get('initial_a')!=RETAINED_FIFTH_A or admitted.get('initial_a')!=RETAINED_FIFTH_A
            or admitted.get('session_id')!=RETAINED_FIFTH_SESSION or admitted.get('lease_seconds')!=6600):
        raise LifecycleHold('retained fifth trial admission evidence changed')
    snapshots=[]
    for index,row in enumerate(rows):
        generation=row['generation_id']
        child='events_g_'+generation.replace('-','')
        attached=db.execute("SELECT EXISTS(SELECT 1 FROM pg_inherits i "
            "JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE i.inhparent='raw.events'::regclass AND n.nspname='raw' AND c.relname=%s "
            "AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)) AS valid",
            (child,generation)).fetchone()['valid']
        if row['partition_name']!=child or attached is not True:
            raise LifecycleHold('retained fifth trial partition attachment changed')
        catalog=LifecycleRepository._manifests(db,generation)
        if (index==0 and (len(catalog)!=RETAINED_FIFTH_MANIFESTS or not bound_catalog(row,catalog))
                or index==1 and catalog):
            raise LifecycleHold('retained fifth trial authenticated catalog changed')
        # Aggregate only bounded immutable row identities and hashes in the database.
        # Return counts separately so a truncated or oversized generation fails closed.
        raw=db.execute("""SELECT count(*) AS n, encode(sha256(convert_to(
            string_agg(jsonb_build_array(source,event_id,content_hash)::text, E'\n'
                       ORDER BY source COLLATE "C",event_id COLLATE "C"),'UTF8')),'hex') AS digest
            FROM (SELECT source,event_id,content_hash FROM raw.events
                WHERE origin_id=%s AND generation_id=%s LIMIT %s) bounded""",
            (FIFTH_TRIAL_ORIGIN,generation,RETAINED_FIFTH_RAW[index]+1)).fetchone()
        outbox=_retained_outbox_fingerprint(db,FIFTH_TRIAL_ORIGIN,generation,RETAINED_FIFTH_ACK[index])
        if raw['n']!=RETAINED_FIFTH_RAW[index] or outbox['n']!=RETAINED_FIFTH_ACK[index] or outbox['pending']:
            raise LifecycleHold('retained fifth trial row or acknowledgement count changed')
        del outbox['pending']  # Preserve the existing trial05 receipt shape.
        snapshots.append(dict(generation=row,manifests=catalog,raw=raw,outbox=outbox))
    return sha256(encoded(wire(dict(generations=snapshots,writer=writer,checkpoints=checkpoints))))


def retained_sixth_fingerprint(db, writers):
    """Fingerprint the held B without changing any of the prior trial rows."""
    generations = db.execute('''SELECT * FROM archive.generations WHERE origin_id=%s
        ORDER BY created_at,generation_id LIMIT 4 FOR SHARE''', (SIXTH_TRIAL_ORIGIN,)).fetchall()
    writer = next((row for row in writers if row['origin_id'] == SIXTH_TRIAL_ORIGIN), None)
    if ([row['generation_id'] for row in generations] != list(RETAINED_SIXTH_IDS)
            or not writer or writer['generation_id'] != RETAINED_SIXTH_IDS[-1] or writer['epoch'] != 5
            or writer['collector_enabled'] or writer['collector_session_id'] is not None
            or writer['collector_lease_expires_at'] is not None):
        raise LifecycleHold('exact stopped sixth trial generation chain required')
    a, b, fresh = generations
    if ([(row['slot'], row['state']) for row in generations]
            != [('A', 'retired'), ('B', 'verified'), ('A', 'collecting')]
            or a['retired_at'] is None or a['sealed_at'] != b['started_at']
            or b['sealed_at'] != fresh['started_at'] or b['retired_at'] is not None
            or b['hold_reason'] is not None or b['seal_hash'] != RETAINED_SIXTH_B_SEAL
            or b['seal_count'] != RETAINED_SIXTH_B_RAW):
        raise LifecycleHold('retained sixth trial seal or successor changed')
    generation = RETAINED_SIXTH_IDS[1]
    attached = db.execute("""SELECT EXISTS(SELECT 1 FROM pg_inherits i
        WHERE i.inhparent='raw.events'::regclass AND i.inhrelid=to_regclass(%s)
        AND pg_get_expr((SELECT relpartbound FROM pg_class WHERE oid=i.inhrelid),i.inhrelid)
            =format('FOR VALUES IN (%%L)',%s::text)) AS valid""",
        ('raw.events_g_' + generation.replace('-', ''), generation)).fetchone()['valid']
    manifests = LifecycleRepository._manifests(db, generation)
    if not attached or len(manifests) != RETAINED_SIXTH_B_MANIFESTS or not bound_catalog(b, manifests):
        raise LifecycleHold('retained sixth trial B catalog changed')
    raw = db.execute("""SELECT count(*) AS n, encode(sha256(convert_to(
        string_agg(jsonb_build_array(source,event_id,content_hash)::text,E'\n'
                   ORDER BY source COLLATE "C",event_id COLLATE "C"),'UTF8')),'hex') AS digest
        FROM (SELECT source,event_id,content_hash FROM raw.events
              WHERE origin_id=%s AND generation_id=%s LIMIT %s) bounded""",
        (SIXTH_TRIAL_ORIGIN, generation, RETAINED_SIXTH_B_RAW + 1)).fetchone()
    outbox = _retained_outbox_fingerprint(db, SIXTH_TRIAL_ORIGIN, generation, RETAINED_SIXTH_B_ACK)
    if raw['n'] != RETAINED_SIXTH_B_RAW or outbox['n'] != RETAINED_SIXTH_B_ACK or outbox['pending']:
        raise LifecycleHold('retained sixth trial B count or acknowledgement changed')
    return sha256(encoded(wire(dict(generations=generations, writer=writer, manifests=manifests,
                                    raw=raw, outbox=outbox))))


def _existing_watch(db, anchor, checkpoint, writer, generations):
    if (not checkpoint or checkpoint['cursor'].get('initial_a') != anchor or not writer
            or writer['collector_enabled'] or writer['collector_session_id'] or writer['collector_lease_expires_at']
            or not any(str(g['generation_id']) == anchor and g['slot']=='A' for g in generations)):
        raise LifecycleHold('existing Benchmark origin or OFF anchor differs')
    current = next((g for g in generations if g['generation_id']==writer['generation_id']),None)
    if (not current or current['state']!='collecting' or current['hold_reason'] is not None
            or db.execute('SELECT to_regclass(%s) AS child',('raw.'+current['partition_name'],)).fetchone()['child'] is None):
        raise LifecycleHold('existing Benchmark generation unavailable')


def prepare(repository, initial_a, source_sha, *, execute=False, origin_id=TRIAL_ORIGIN,
            rehearsal_window_seconds=None):
    canonical_anchor(initial_a)
    if (execute is not True or repository.environment!='preprod' or origin_id not in (*TRIAL_ORIGINS,*BOUNDARY_ORIGINS)
            or not isinstance(source_sha,str) or not re.fullmatch('[0-9a-f]{40}',source_sha)):
        raise LifecycleHold('explicit exact trial preparation scope required')
    try:
        profile = elapsed_cycle_binding(origin_id, rehearsal_window_seconds)
    except ValueError as error:
        raise LifecycleHold(str(error)) from None
    from .rehearsal_profile import DISPLAY_ORIGIN, WATCH_POLICY
    boundary = origin_id in BOUNDARY_ORIGINS
    if boundary:
        profile = {'profile': WATCH_POLICY if origin_id==DISPLAY_ORIGIN else BOUNDARY_POLICY}
        if uuid.UUID(initial_a).int == 0:
            raise LifecycleHold('new diagnostic requires a distinct nonzero initial A')
    preserved = (RETAINED_THIRD_A,RETAINED_THIRD_B)
    if origin_id in (FIFTH_TRIAL_ORIGIN,SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN):
        preserved += (RETAINED_FOURTH_A,)
    if origin_id in (SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN):
        preserved += (RETAINED_FIFTH_A,RETAINED_FIFTH_B)
    if rehearsal_window_seconds is not None:
        preserved += RETAINED_SIXTH_IDS
    if origin_id in (FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN,SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN) and (
            uuid.UUID(initial_a).int==0 or initial_a in preserved):
        raise LifecycleHold('new trial requires a distinct nonzero initial A')
    with CycleBudget(ArchiveLimits(max_seconds=20)), repository.transaction() as db:
        identity=db.execute("""SELECT current_database()='tradebot_pp'
            AND session_user='tradebot_lifecycle' AND count(*)=1
            AND bool_and(singleton AND environment='preprod' AND database_name='tradebot_pp'
                         AND foundation_version=1) AS valid FROM ops.environment_identity""").fetchone()
        if not identity or identity['valid'] is not True:
            raise LifecycleHold('exact PP database and lifecycle identity required')
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('tradebot-pp-live-collector',0))")
        # Stored expired leases also require explicit durable OFF. Row locks
        # drain any previously admitted write; historical pointers never move.
        writers=db.execute("SELECT * FROM ops.writer_state WHERE origin_id LIKE 'pp-live-%' "
                           'ORDER BY origin_id FOR UPDATE').fetchall()
        if any(row['collector_enabled'] or row['collector_session_id'] is not None
               or row['collector_lease_expires_at'] is not None for row in writers):
            raise LifecycleHold('all PP collectors must be durably OFF before trial preparation')
        if db.execute('SELECT 1 FROM ops.writer_state WHERE collector_enabled LIMIT 1').fetchone():
            raise LifecycleHold('all database collector flags must be OFF')
        retained={}
        if origin_id in (FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN,SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN):
            retained['retained_trial03_sha256']=retained_third_fingerprint(db,writers)
        if origin_id in (FIFTH_TRIAL_ORIGIN,SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN):
            retained['retained_trial04_sha256']=retained_fourth_fingerprint(db,writers)
        if origin_id in (SIXTH_TRIAL_ORIGIN,SEVENTH_TRIAL_ORIGIN):
            retained['retained_trial05_sha256']=retained_fifth_fingerprint(db,writers)
        if rehearsal_window_seconds is not None:
            retained['retained_trial06_sha256']=retained_sixth_fingerprint(db,writers)
        if origin_id==THIRD_TRIAL_ORIGIN:
            # New03 follows only the exact archived failed02 initial A. Keep
            # its partition, pointer, seal and old authority entirely unchanged.
            prior=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                'ORDER BY created_at,generation_id LIMIT 2 FOR SHARE',(NEXT_TRIAL_ORIGIN,)).fetchall()
            old_writer=next((row for row in writers if row['origin_id']==NEXT_TRIAL_ORIGIN),None)
            if (len(prior)!=1 or prior[0]['generation_id']!=RETAINED_SECOND_INITIAL_A
                    or prior[0]['state']!='verified' or prior[0]['hold_reason'] is not None
                    or old_writer is None or old_writer['generation_id']!=RETAINED_SECOND_INITIAL_A):
                raise LifecycleHold('exact retained second trial archive required before third admission')
            catalog=db.execute('SELECT count(*) AS objects, sum(row_count) AS rows, '
                'bool_and(verified_at IS NOT NULL) AS verified FROM archive.manifests '
                'WHERE origin_id=%s AND generation_id=%s',
                (NEXT_TRIAL_ORIGIN,RETAINED_SECOND_INITIAL_A)).fetchone()
            attached=db.execute("SELECT EXISTS(SELECT 1 FROM pg_inherits i "
                "JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE i.inhparent='raw.events'::regclass AND n.nspname='raw' AND c.relname=%s "
                "AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)) AS valid",
                (prior[0]['partition_name'],RETAINED_SECOND_INITIAL_A)).fetchone()['valid']
            if attached is not True:
                raise LifecycleHold('retained second trial partition attachment changed')
            if (not catalog['objects'] or catalog['verified'] is not True
                    or catalog['rows']!=prior[0]['seal_count']
                    or db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s '
                        'AND acknowledged_at IS NULL LIMIT 1',(NEXT_TRIAL_ORIGIN,)).fetchone()):
                raise LifecycleHold('retained second trial archive or acknowledgements incomplete')
        existing=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                            'ORDER BY created_at,generation_id LIMIT 2 FOR UPDATE',(origin_id,)).fetchall()
        writer=next((row for row in writers if row['origin_id']==origin_id),None)
        expected=dict(initial_a=initial_a,source_sha=source_sha,policy=CONSUMER,**retained,**profile)
        if existing or writer:
            checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                'AND generation_id=%s AND consumer=%s',(origin_id,initial_a,CONSUMER)).fetchone()
            if origin_id==DISPLAY_ORIGIN and writer and writer['epoch']!=1:
                _existing_watch(db,initial_a,checkpoint,writer,existing)
                return dict(status='trial_ready_off',origin_id=origin_id,generation_id=initial_a,
                            collector_enabled=False,source_sha=source_sha,retirement_authorized=False,**profile)
            if (len(existing)!=1 or writer is None or writer['generation_id']!=initial_a or writer['epoch']!=1
                    or existing[0]['generation_id']!=initial_a or existing[0]['state']!='collecting'
                    or existing[0]['slot']!='A' or existing[0]['hold_reason'] is not None
                    or checkpoint is None or checkpoint['cursor']!=expected):
                raise LifecycleHold('trial already exists outside exact unused initial-A preparation')
            if db.execute('SELECT 1 FROM raw.events WHERE origin_id=%s LIMIT 1',(origin_id,)).fetchone() or \
                    db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s LIMIT 1',(origin_id,)).fetchone():
                raise LifecycleHold('prepared trial already contains evidence')
            if db.execute('SELECT to_regclass(%s) AS child',('raw.'+existing[0]['partition_name'],)).fetchone()['child'] is None:
                raise LifecycleHold('prepared initial A partition missing')
        else:
            now=db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
            child='events_g_'+uuid.UUID(initial_a).hex
            db.execute("""INSERT INTO archive.generations
                (origin_id,generation_id,slot,state,partition_name,created_at)
                VALUES(%s,%s,'A','prepared',%s,%s)""",(origin_id,initial_a,child,now))
            db.execute('SELECT archive.create_generation_partition(%s,%s)',(origin_id,initial_a))
            db.execute("UPDATE archive.generations SET state='collecting',started_at=%s WHERE generation_id=%s",(now,initial_a))
            db.execute('INSERT INTO ops.writer_state(origin_id,generation_id,epoch,collector_enabled,updated_at) '
                       'VALUES(%s,%s,1,false,%s)',(origin_id,initial_a,now))
            generation=dict(origin_id=origin_id,generation_id=initial_a)
            repository._checkpoint(db,generation,CONSUMER,expected)
            if origin_id == DISPLAY_ORIGIN:
                repository._checkpoint(db,generation,'structured:verified-acks-v1',{'rows':0})
    return dict(status='trial_ready_off',origin_id=origin_id,generation_id=initial_a,
                collector_enabled=False,source_sha=source_sha,retirement_authorized=False,**profile)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-a',required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    origin=os.environ.get('TRADEBOT_ORIGIN_ID')
    if not args.execute or origin not in (*TRIAL_ORIGINS, *BOUNDARY_ORIGINS):
        raise LifecycleHold('exact disabled trial preparation environment required')
    anchor=boundary_anchor(os.environ) if origin in BOUNDARY_ORIGINS else cycle_anchor(os.environ)
    if (anchor!=args.initial_a
            or any(os.environ.get(flag,'false').lower() not in ('false','0','off') for flag in
                   ('TRADEBOT_COLLECTOR_ENABLED','TRADEBOT_CLOUD_ENABLED','TRADEBOT_RETIREMENT_ENABLED',
                    'ENABLE_OPENAI_ANALYST','ENABLE_SUPABASE_SYNC','ENABLE_LOCAL_RETENTION'))):
        raise LifecycleHold('exact disabled trial preparation environment required')
    from .connection import connect
    from .migrate import validate_schema
    from .lifecycle_worker import read_dsn
    dsn=read_dsn(os.environ)
    factory=lambda:connect(dsn,environment='preprod')
    with factory() as db:validate_schema(db,'preprod')
    print(json.dumps(prepare(LifecycleRepository(factory),args.initial_a,args.source_sha,
                             execute=args.execute,origin_id=os.environ['TRADEBOT_ORIGIN_ID'],
                             rehearsal_window_seconds=elapsed_cycle_seconds(os.environ))),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
