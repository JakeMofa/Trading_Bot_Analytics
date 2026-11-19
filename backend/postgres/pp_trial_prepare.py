"""Bounded local initial-A preparation under the host's one-use enter authority.

Never enables a collector, changes historical seals, transfers cloud data or
retires a partition. No runtime service calls this module automatically.
"""
import argparse
import json
import os
import re
import uuid

from .archive_codec import ArchiveLimits, CycleBudget
from .lifecycle import LifecycleHold, LifecycleRepository
from .rehearsal_profile import TRIAL_ORIGIN, canonical_anchor, cycle_anchor

CONSUMER='trial:initial-a-prepare-v1'


def prepare(repository, initial_a, source_sha, *, execute=False):
    canonical_anchor(initial_a)
    if (execute is not True or repository.environment!='preprod'
            or not isinstance(source_sha,str) or not re.fullmatch('[0-9a-f]{40}',source_sha)):
        raise LifecycleHold('explicit exact trial preparation scope required')
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
        existing=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                            'ORDER BY created_at,generation_id LIMIT 2 FOR UPDATE',(TRIAL_ORIGIN,)).fetchall()
        writer=next((row for row in writers if row['origin_id']==TRIAL_ORIGIN),None)
        expected=dict(initial_a=initial_a,source_sha=source_sha,policy=CONSUMER)
        if existing or writer:
            checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                'AND generation_id=%s AND consumer=%s',(TRIAL_ORIGIN,initial_a,CONSUMER)).fetchone()
            if (len(existing)!=1 or writer is None or writer['generation_id']!=initial_a or writer['epoch']!=1
                    or existing[0]['generation_id']!=initial_a or existing[0]['state']!='collecting'
                    or existing[0]['slot']!='A' or existing[0]['hold_reason'] is not None
                    or checkpoint is None or checkpoint['cursor']!=expected):
                raise LifecycleHold('trial already exists outside exact unused initial-A preparation')
            if db.execute('SELECT 1 FROM raw.events WHERE origin_id=%s LIMIT 1',(TRIAL_ORIGIN,)).fetchone() or \
                    db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s LIMIT 1',(TRIAL_ORIGIN,)).fetchone():
                raise LifecycleHold('prepared trial already contains evidence')
            if db.execute('SELECT to_regclass(%s) AS child',('raw.'+existing[0]['partition_name'],)).fetchone()['child'] is None:
                raise LifecycleHold('prepared initial A partition missing')
        else:
            now=db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
            child='events_g_'+uuid.UUID(initial_a).hex
            db.execute("""INSERT INTO archive.generations
                (origin_id,generation_id,slot,state,partition_name,created_at)
                VALUES(%s,%s,'A','prepared',%s,%s)""",(TRIAL_ORIGIN,initial_a,child,now))
            db.execute('SELECT archive.create_generation_partition(%s,%s)',(TRIAL_ORIGIN,initial_a))
            db.execute("UPDATE archive.generations SET state='collecting',started_at=%s WHERE generation_id=%s",(now,initial_a))
            db.execute('INSERT INTO ops.writer_state(origin_id,generation_id,epoch,collector_enabled,updated_at) '
                       'VALUES(%s,%s,1,false,%s)',(TRIAL_ORIGIN,initial_a,now))
            repository._checkpoint(db,dict(origin_id=TRIAL_ORIGIN,generation_id=initial_a),CONSUMER,expected)
    return dict(status='trial_ready_off',origin_id=TRIAL_ORIGIN,generation_id=initial_a,
                collector_enabled=False,source_sha=source_sha,retirement_authorized=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-a',required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    if (not args.execute or os.environ.get('TRADEBOT_ORIGIN_ID')!=TRIAL_ORIGIN or cycle_anchor(os.environ)!=args.initial_a
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
    print(json.dumps(prepare(LifecycleRepository(factory),args.initial_a,args.source_sha,execute=args.execute)),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
