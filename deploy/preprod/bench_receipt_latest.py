"""Disposable local PG17 receipt-query comparison; no network/cloud DSN accepted.

Run with a PostgreSQL17 bin directory and a JSON output path. Creates and removes
its own private-socket cluster. Timings/plans and generated key lengths are not
hosted/runtime-role evidence. No migration, grant, application SQL or cap changes.
"""
from contextlib import contextmanager
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.archive_codec import encoded

ORIGIN='generated-latest-receipt-bench'
HOT_KEY=encoded([ORIGIN,'coinbase','BTC-USD']).decode()
A='00000000-0000-0000-0000-000000000001'
B='00000000-0000-0000-0000-000000000002'
C='00000000-0000-0000-0000-000000000003'
from postgres.history_v2_latest_receipts import RANK_SQL as RANK, INDEXED_SQL as LATERAL, INDEX_NAME
INDEX=(ROOT/'supabase/migrations/20261119103056_pp_receipt_latest_identity_index.sql').read_text()



def keys(count=73):
    return [('core.current_prices',HOT_KEY)] + [('core.candles',f'candle-{i:06d}') for i in range(1,count)]


def params(selected):
    return [k[0] for k in selected],[k[1] for k in selected],ORIGIN


def comparable(rows):
    return sorted(tuple(row.values()) for row in rows)


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]): yield from nodes(child)


def plan(db,query,selected):
    result=db.execute('EXPLAIN (ANALYZE,BUFFERS,SETTINGS,FORMAT JSON) '+query,params(selected)).fetchone()['QUERY PLAN'][0]
    return {'planning_ms':result['Planning Time'],'execution_ms':result['Execution Time'],
        'temp_read_blocks':result['Plan'].get('Temp Read Blocks',0),
        'temp_written_blocks':result['Plan'].get('Temp Written Blocks',0),
        'node_types':[n['Node Type'] for n in nodes(result['Plan'])],
        'index_names':sorted({n['Index Name'] for n in nodes(result['Plan']) if 'Index Name' in n}),
        'plan':result}


def measure(db,selected,*,indexed):
    expected=None
    samples={name:[] for name in ('rank','lateral')}
    for order in (('rank','lateral'),('lateral','rank'),('rank','lateral')):
        for name in order:
            query=RANK if name=='rank' else LATERAL
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                started=time.perf_counter()
                rows=db.execute(query,params(selected)).fetchall()
                elapsed=1000*(time.perf_counter()-started)
                value=comparable(rows)
                if expected is None: expected=value
                assert value == expected, 'receipt query semantic mismatch'
                samples[name].append(elapsed)
    return {'indexed':indexed,'keys':len(selected),'returned_rows':len(expected),
        'samples_ms':samples,'median_ms':{n:statistics.median(v) for n,v in samples.items()},
        'plans':{n:plan(db,q,selected) for n,q in [('rank',RANK),('lateral',LATERAL)]}}


def writes(db,start):
    rows=[(ORIGIN,C,start+i,'core.current_prices',HOT_KEY,'a'*64,'b'*64,'c'*64) for i in range(500)]
    samples=[]
    wal=[]
    for _ in range(3):
        before=db.execute('SELECT pg_current_wal_insert_lsn() AS position').fetchone()['position']
        with db.transaction() as transaction:
            started=time.perf_counter()
            HistoryV2PostgresTransport._insert_receipts(db,rows)
            samples.append(1000*(time.perf_counter()-started))
            after=db.execute('SELECT pg_current_wal_insert_lsn() AS position').fetchone()['position']
            wal.append(db.execute('SELECT pg_wal_lsn_diff(%s,%s) AS bytes',(after,before)).fetchone()['bytes'])
            # Same immutable fixture for every pair; rollback itself is outside
            # timing. This measures actual 25-row receipt INSERT statements only,
            # not whole importer/envelope/projection/commit or remote latency.
            transaction.force_rollback=True
    return {'rows_per_batch':500,'samples_ms':samples,'median_ms':statistics.median(samples),
        'wal_insert_bytes':[int(v) for v in wal]}


def fixture(db,total):
    db.execute('TRUNCATE history_v2.structured_receipts,history_v2.generation_checkpoints,history_v2.candles,history_v2.current_prices CASCADE')
    # First case matches observed total, key count and join cardinality, not the
    # private actual identifiers/payloads/distribution. Longer case scales hot history.
    hot=37340 if total==42133 else int(total*.8862)
    db.execute('''INSERT INTO history_v2.structured_receipts
        (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,payload_hash,envelope_hash)
        SELECT %s,CASE WHEN i<=31162 THEN %s ELSE %s END,i,
            CASE WHEN i<=%s THEN 'core.current_prices' ELSE 'core.candles' END,
            CASE WHEN i<=%s THEN %s ELSE 'candle-'||lpad((i-%s)::text,6,'0') END,
            repeat('a',64),repeat('b',64),repeat('c',64) FROM generate_series(1,%s) i''',
        (ORIGIN,A,B,hot,hot,HOT_KEY,hot,total))
    db.execute('ANALYZE history_v2.structured_receipts')
    return hot


def semantic_checks(db,hot):
    selected=keys()
    outcomes=[]
    for label,selection in [('normal',selected),('missing',selected+[('core.markets','missing')])]:
        left=comparable(db.execute(RANK,params(selection)).fetchall())
        right=comparable(db.execute(LATERAL,params(selection)).fetchall())
        assert left==right
        outcomes.append({'case':label,'rows':len(left),'keys':len(selection),
                         'cardinality_guard_holds':len(left)!=len(selection)})
    with db.transaction() as transaction:
        db.execute('''INSERT INTO history_v2.structured_receipts
            (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,payload_hash,envelope_hash)
            VALUES(%s,%s,%s,'core.current_prices',%s,%s,%s,%s)''',(ORIGIN,C,hot,HOT_KEY,'a'*64,'b'*64,'c'*64))
        left=comparable(db.execute(RANK,params(selected)).fetchall())
        right=comparable(db.execute(LATERAL,params(selected)).fetchall())
        assert left==right and len(right)==len(selected)+1,'max-ID duplicate was hidden'
        outcomes.append({'case':'max_id_cross_generation_tie','rows':len(right),
                         'keys':len(selected),'cardinality_guard_holds':True})
        transaction.force_rollback=True
    # Force all hashes to collide in a generated query; exact identity residual
    # must still return the original rank multiset. The real md5 is not altered.
    db.execute("CREATE OR REPLACE FUNCTION pg_temp.colliding_hash(text) RETURNS text LANGUAGE sql IMMUTABLE AS $$SELECT repeat('0',32)$$")
    collision=LATERAL.replace('pg_catalog.md5(', 'pg_temp.colliding_hash(')
    assert comparable(db.execute(collision,params(selected)).fetchall()) == comparable(db.execute(RANK,params(selected)).fetchall())
    outcomes.append({'case':'forced_hash_collision_exact_residual','equal':True})
    import hashlib
    long_key=''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(128))
    with db.transaction() as transaction:
        db.execute('''INSERT INTO history_v2.structured_receipts
            (origin_id,generation_id,outbox_id,entity_type,entity_id,content_hash,payload_hash,envelope_hash)
            VALUES(%s,%s,%s,'core.markets',%s,%s,%s,%s)''',(ORIGIN,C,hot+1,long_key,'a'*64,'b'*64,'c'*64))
        selection=[('core.markets',long_key)]
        assert comparable(db.execute(RANK,params(selection)).fetchall()) == comparable(db.execute(LATERAL,params(selection)).fetchall())
        outcomes.append({'case':'long_identity_no_new_btree_limit','entity_id_bytes':len(long_key),'equal':True})
        transaction.force_rollback=True
    return outcomes


def full_page(db,dsn):
    """Actual rich transport, fixed 100ms waits and 320ms cold setup model.

    Raw/local inventory is excluded. Preparation is excluded. Exact A and newer
    B envelopes/projections are identical for rank and indexed reads. Includes
    explicit BEGIN/COMMIT waits; bytes are real local protocol, not WAN bandwidth.
    """
    from contextlib import contextmanager
    from datetime import datetime,timedelta,timezone
    from unittest.mock import patch
    import psycopg
    from psycopg.rows import dict_row
    from postgres.archive_codec import encoded
    from postgres.history_v2_envelope import TABLE_KEYS
    from postgres.history_v2_transport import HistoryV2PostgresTransport
    d='00000000-0000-0000-0000-000000000004'
    e='00000000-0000-0000-0000-000000000005'
    stamp=datetime(2026,11,19,tzinfo=timezone.utc)
    records=[]
    for i in range(500):
        table='core.candles'
        payload=dict(origin_id=ORIGIN,source='coinbase',symbol='BTC-USD',granularity=60,
            time=int(stamp.timestamp())+i*60,low='99.0000',high='101.0000',open='100.0000',
            close='100.1000',volume='1.00000000',first_seen=stamp.isoformat(),
            payload={'generated':True,'padding':'c'*1000},content_hash=f'{i+1:064x}')
        if i==499:
            table='core.current_prices'
            payload=dict(origin_id=ORIGIN,source='coinbase',symbol='BTC-USD',event_id='old',
                generation_id=d,source_time=stamp.isoformat(),source_epoch=str(int(stamp.timestamp())),
                received_at=stamp.isoformat(),available_at=stamp.isoformat(),price='100.2300',size=None,
                payload={'generated':True,'padding':'p'*1000},content_hash=f'{i+1:064x}')
        records.append(dict(id=1000001+i,origin_id=ORIGIN,generation_id=d,entity_type=table,
            entity_id=encoded([payload[k] for k in TABLE_KEYS[table]]).decode(),
            content_hash=payload['content_hash'],payload=payload))
    at=stamp+timedelta(seconds=1)
    newer={**records[-1],'id':1000501,'generation_id':e,'content_hash':'f'*64,
        'payload':{**records[-1]['payload'],'event_id':'new','generation_id':e,
            'source_time':at.isoformat(),'source_epoch':str(int(at.timestamp())),
            'received_at':at.isoformat(),'available_at':at.isoformat(),'price':'100.2400','content_hash':'f'*64}}
    identity=db.execute('SELECT current_database() db,current_user role').fetchone()
    def opened(**kwargs):return psycopg.connect(dsn,row_factory=dict_row,autocommit=True)
    with patch('postgres.history_v2_transport.PP_STRUCTURED_ORIGIN',ORIGIN):
        def transport(factory,generation=d,indexed=False):
            return HistoryV2PostgresTransport(factory,origin_id=ORIGIN,generation_id=generation,
                expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True,
                indexed_latest=indexed)
        transport(opened).put_structured(records,timeout_seconds=20)
        transport(opened,e).put_structured([newer],timeout_seconds=20)
        for table in ('structured_receipts','structured_revision_payloads','candles','current_prices'):
            db.execute('ANALYZE history_v2.'+table)
        traces=[]
        class Delayed:
            def __init__(self,inner):self.inner,self.depth,self.waits,self.sql=inner,0,0,0
            def __getattr__(self,name):return getattr(self.inner,name)
            def __enter__(self):self.inner.__enter__();return self
            def __exit__(self,*args):return self.inner.__exit__(*args)
            def wait(self):self.waits+=1;time.sleep(.1)
            def execute(self,*args,**kwargs):
                self.sql+=1
                if not self.depth:self.wait()
                return self.inner.execute(*args,**kwargs)
            @contextmanager
            def pipeline(self):
                self.depth+=1
                try:
                    with self.inner.pipeline():yield;self.wait()
                finally:self.depth-=1
            @contextmanager
            def transaction(self):
                self.wait()
                with self.inner.transaction():yield
                self.wait()
        def delayed(**kwargs):
            time.sleep(.32)
            connection=Delayed(opened());traces.append(connection);return connection
        samples={'rank':[],'indexed':[]}
        expected=None
        for order in (('rank','indexed'),('indexed','rank'),('rank','indexed')):
            for mode in order:
                started=time.perf_counter()
                value=transport(delayed,indexed=mode=='indexed').read_retirement_revisions(
                    records,max_bytes=4*1024**2,timeout_seconds=4)
                elapsed=time.perf_counter()-started
                canonical=(encoded(value[0]),value[1])
                if expected is None:expected=canonical
                assert canonical==expected,'rich envelope proof changed'
                samples[mode].append(dict(seconds=elapsed,waits=traces[-1].waits,sql=traces[-1].sql))
        return {'scope':'generated_full_rich_page_excludes_raw_and_local_inventory',
            'rows':500,'distinct_keys':500,'encoded_A_bytes':len(encoded(records)),
            'additional_newer_B_bytes':len(encoded(newer)), 'setup_model_seconds':.32,
            'wait_model_seconds':.1,'samples':samples,
            'median_seconds':{k:statistics.median(r['seconds'] for r in v) for k,v in samples.items()}}


def run(bin_dir,output):
    import psycopg
    from psycopg.rows import dict_row
    def command(args,**kwargs):
        return subprocess.run([str(v) for v in args],check=True,capture_output=True,text=True,**kwargs)
    with tempfile.TemporaryDirectory(prefix='receipt-plan-',dir='/tmp') as folder:
        root=Path(folder); data=root/'db';socket=root/'socket';socket.mkdir(mode=0o700)
        command([bin_dir/'initdb','-D',data,'-A','trust','--no-locale','--encoding=UTF8'])
        command([bin_dir/'pg_ctl','-D',data,'-l',root/'log','-o',f"-k {socket} -p 55458 -c listen_addresses=''",'start','-w'])
        try:
            with psycopg.connect(f'host={socket} port=55458 dbname=postgres',autocommit=True,
                                 row_factory=dict_row,prepare_threshold=None) as db:
                version=db.execute('SHOW server_version_num').fetchone()['server_version_num']
                assert 170000<=int(version)<180000,'PG17 required'
                db.execute('CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;CREATE ROLE tradebot_pp_history NOLOGIN')
                db.execute((ROOT/'backend/postgres/history_v2_contract.sql').read_text())
                db.execute((ROOT/'supabase/migrations/20261118012340_structured_receipts_v2.sql').read_text())
                db.execute((ROOT/'supabase/migrations/20261119020000_pp_structured_revision_payloads.sql').read_text())
                db.execute("SET work_mem='4MB';SET statement_timeout='15s'")
                result={'scope':'generated_local_pg17_no_cloud','server_version_num':version,
                    'prepare_threshold':None,'work_mem':'4MB','index_variant':'md5_exact_residual_no_include','cases':[]}
                for total in (42133,250000):
                    hot=fixture(db,total)
                    case={'receipts':total,'hot_key_revisions':hot,'stages':[]}
                    case['write_no_index']=writes(db,total+1)
                    case['stages'].append(measure(db,keys(),indexed=False))
                    started=time.perf_counter();db.execute(INDEX)
                    case['index_build_seconds']=time.perf_counter()-started
                    case['index_bytes']=db.execute("SELECT pg_relation_size(%s) n",('history_v2.'+INDEX_NAME,)).fetchone()['n']
                    case['write_indexed']=writes(db,total+1)
                    db.execute('ANALYZE history_v2.structured_receipts')
                    case['stages'].append(measure(db,keys(),indexed=True))
                    case['max_key_page']=measure(db,keys(500),indexed=True)
                    case['semantics']=semantic_checks(db,hot)
                    case['full_rich_page']=full_page(db,f'host={socket} port=55458 dbname=postgres')
                    result['cases'].append(case)
                    db.execute('DROP INDEX history_v2.'+INDEX_NAME)
                    output.write_text(json.dumps(result,indent=2,default=str)+'\n')
                    print(json.dumps({k:v for k,v in case.items() if k not in ('stages','max_key_page')}),flush=True)
        finally:
            command([bin_dir/'pg_ctl','-D',data,'stop','-m','fast','-w'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.pg_bin,args.output)
