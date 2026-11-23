"""Compare the four Advisor FK indexes against the real projection read in private PG17."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from postgres.history_v2_transport import HistoryV2PostgresTransport as Transport
from postgres.history_v2_envelope import TABLE_KEYS

ORIGIN = 'generated_fk_fixture'
FIXTURES = {
    'markets': """(origin_id,market_id,source,slug,duration,start_time,end_time,start_epoch,end_epoch,
        status,first_seen,last_seen,payload,content_hash) SELECT %s,'m'||i,'generated','m'||i,900,
        '1970-01-01T00:00:00Z','1970-01-01T00:15:00Z',0,900,'closed','2026-01-01','2026-01-01','{}',repeat('a',64)""",
    'feature_snapshots': """SELECT %s,'s'||i,'m'||i,'2026-01-01',1,'{}','{}','{}',repeat('b',64)""",
    'protected_evidence': """(origin_id,evidence_id,source,event_id,kind,market_id,received_at,
        available_at,payload,content_hash) SELECT %s,'e'||i,'generated','v'||i,'example','m'||i,
        '2026-01-01','2026-01-01','{}',repeat('c',64)""",
    'snapshot_evidence': """SELECT %s,'s'||i,'e'||i""",
    'predictions': """(origin_id,prediction_id,snapshot_id,market_id,model_version,as_of,created_at,
        seconds_remaining,abstain_reason,assumptions_json,payload,content_hash)
        SELECT %s,'p'||i,'s'||i,'m'||i,'v1','2026-01-01','2026-01-01',30,'generated','{}','{}',repeat('d',64)""",
    'outcomes': """(origin_id,outcome_id,market_id,evidence_id,result,confirmed_at,available_at,payload,
        content_hash) SELECT %s,'o'||i,'m'||i,'e'||i,'UP','2026-01-01','2026-01-01','{}',repeat('e',64)""",
}
INDEXES = {
    'protected_evidence': ('origin_id','market_id'),
    'snapshot_evidence': ('origin_id','evidence_id'),
    'predictions': ('origin_id','snapshot_id','market_id','as_of'),
    'outcomes': ('origin_id','evidence_id','market_id'),
}


def page(fanout):
    records = []
    for i in range(1, 126):
        n = i * 73
        payload = dict(origin_id=ORIGIN, evidence_id=f'e{n}', snapshot_id=f's{n}',
                       prediction_id=f'p{n}', outcome_id=f'o{n}')
        for name in INDEXES:
            entity = 'core.' + name
            projected = dict(payload)
            if name == 'snapshot_evidence':
                projected['evidence_id'] = f'e{1 + (n - 1) // fanout * fanout}'
            key = json.dumps([projected[k] for k in TABLE_KEYS[entity]])
            records.append(dict(entity_type=entity, entity_id=key, payload=projected))
    return records


def sample(db, records):
    start = perf_counter()
    rows = Transport._projection_rows(db, records)
    elapsed = 1000 * (perf_counter() - start)
    assert len(rows) == 500 and all(v is not None for v in rows.values())
    payload = json.dumps(list(rows.values()), sort_keys=True, default=str).encode()
    return elapsed, sha256(payload).hexdigest()


def plan(db, record):
    relation, condition, values = Transport._table_and_condition(record)
    query = sql.SQL('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM {} WHERE {}').format(relation, condition)
    data = db.execute(query, values).fetchone()['QUERY PLAN'][0]
    return {k:data['Plan'].get(k) for k in ('Node Type','Index Name','Index Cond','Filter','Rows Removed by Filter','Actual Rows','Shared Hit Blocks')}


def trial(db):
    db.execute('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role')
    db.execute((ROOT / 'backend/postgres/history_v2_contract.sql').read_text())
    for name, seed in FIXTURES.items():
        db.execute('INSERT INTO history_v2.' + name + ' ' + seed + ' FROM generate_series(1,10000) i', (ORIGIN,))
    db.execute('ANALYZE')
    result = dict(scope='Generated local PG17, projection-read phase, database owner, warmed private socket',
                  server=db.execute('SHOW server_version').fetchone()['server_version'],
                  rows_per_table=10000, page_size=500, lookups_per_advised_table=125, cases={})
    result['cases']['one_snapshot_per_evidence'] = compare(db, 1)
    db.execute("UPDATE history_v2.snapshot_evidence SET evidence_id='e'||(1+(substring(snapshot_id FROM 2)::int-1)/16*16)")
    db.execute('VACUUM ANALYZE history_v2.snapshot_evidence')
    result['cases']['sixteen_snapshots_per_evidence'] = compare(db, 16)
    return result


def compare(db, fanout):
    records = page(fanout)
    result = dict(arms={})
    expected = None
    for stage in ('original', 'four_indexes', 'original_restored'):
        if stage == 'four_indexes':
            for name, columns in INDEXES.items():
                db.execute('CREATE INDEX candidate_' + name + ' ON history_v2.' + name + '(' + ','.join(columns) + ')')
        if stage == 'original_restored':
            for name in INDEXES:
                db.execute('DROP INDEX history_v2.candidate_' + name)
        _, current = sample(db, records)
        expected = expected or current
        assert expected == current
        values = []
        for _ in range(12):
            elapsed, current = sample(db, records)
            assert current == expected
            values.append(round(elapsed,4))
        arm = dict(plans={r['entity_type']:plan(db,r) for r in records[:4]},
                   page_ms=values, median_page_ms=round(median(values),4))
        if stage == 'four_indexes':
            arm['index_bytes'] = {name:db.execute('SELECT pg_relation_size(%s::regclass) AS size',
                ('history_v2.candidate_' + name,)).fetchone()['size'] for name in INDEXES}
        result['arms'][stage] = arm
    result['canonical_projection_result_sha256'] = expected
    return result


def run(bin_dir):
    def command(*args):
        subprocess.run(args, check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix='archive-fk-',dir='/tmp') as tmp:
        work = Path(tmp)
        data = work/'data'
        sock = work/'socket'
        sock.mkdir(mode=0o700)
        command(bin_dir/'initdb', '-D',data,'-A','trust','--no-locale','--encoding=UTF8')
        command(bin_dir/'pg_ctl','-D',data,'-l',work/'log','-o',f"-k {sock} -p 55312 -c listen_addresses=''",'start','-w')
        try:
            with psycopg.connect(host=str(sock), port=55312, dbname='postgres', autocommit=True,
                                 prepare_threshold=None, row_factory=dict_row) as db:
                if db.info.server_version // 10000 != 17:
                    raise RuntimeError('PostgreSQL 17 required')
                return trial(db)
        finally:
            command(bin_dir/'pg_ctl','-D',data,'stop','-m','fast','-w')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.pg_bin), indent=2) + '\n')
