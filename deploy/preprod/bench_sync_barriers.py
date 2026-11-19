"""Owned PG17 rich-page synchronization comparison. No external DSN/network input.

100/200ms waits are injected sensitivity inputs, not measured PP latency.
No CPU-quota, TLS/pooler, live intake or sustained throughput is emulated.
"""
import argparse,contextlib,inspect,json,math,statistics,subprocess,sys,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from test_sync_barriers_pg import SyncBarriersPG,page
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.cloud_origin_binding import TRIAL_ORIGIN,TRIAL_WRITER
from postgres.archive_codec import ArchiveLimit,ArchiveUnavailable,encoded,sha256

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=int,default=4)
    parser.add_argument('--rtt-ms',type=int,nargs='+',default=[0,100,200])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if not 1<=args.pairs<=20 or any(not 0<=n<=250 for n in args.rtt_ms):raise ValueError('bounded benchmark inputs required')
    baseline_ref='0c86b47c46ae5a39f5d1076555e7cf010163416c'
    source=subprocess.check_output(['git','show',baseline_ref+':backend/postgres/history_v2_transport.py'],cwd=ROOT,text=True)
    module=types.ModuleType('postgres._sync_barrier_baseline');module.__package__='postgres'
    exec(compile(source,'<pinned-history-v2-baseline>','exec'),module.__dict__)
    baseline=module.HistoryV2PostgresTransport
    fixture=SyncBarriersPG('test_paired_import_readback_replay_and_barrier_counts')
    output=dict(scope='owned_generated_pg17_not_PP',baseline=baseline_ref,
        candidate_source_sha256=sha256(inspect.getsource(HistoryV2PostgresTransport).encode()),
        unchanged=dict(rows=50,request_seconds=4,cycle_seconds=20,pending_cap=10000,decoded_bytes=256*1024),
        limitations=['injected_RTT_not_measured_PP','no_quarter_CPU_quota','no_TLS_or_pooler','no_local_ACK_cost','no_sustained_intake'],cases=[])
    fixture.setUpClass()
    try:
        import psycopg
        with fixture.admin() as db:
            output['versions']=dict(postgres=db.execute('SHOW server_version').fetchone()['server_version'],
                                    psycopg=psycopg.__version__,libpq=psycopg.pq.version())
        generation='00000000-0000-4000-8000-000000000022';records=page(generation)
        output.update(page_bytes=len(encoded(records)),page_sha256=sha256(encoded(records)))
        for delay_ms in args.rtt_ms:
            runs={key:[] for key in ('baseline','candidate')}
            for pair in range(args.pairs):
                for name in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
                    fixture.reset()
                    with fixture.connected(delay_ms/1000) as connection:
                        @contextlib.contextmanager
                        def factory(**_):yield connection
                        cls=baseline if name=='baseline' else HistoryV2PostgresTransport
                        kwargs={'sync_barriers':True} if name=='candidate' else {}
                        transport=cls(factory,origin_id=TRIAL_ORIGIN,generation_id=generation,
                            expected_database='postgres',expected_role=TRIAL_WRITER,retain_revisions=True,**kwargs)
                        start=time.monotonic();last=start;result={}
                        try:
                            transport.put_structured(records,timeout_seconds=4)
                            result.update(import_seconds=time.monotonic()-last,import_waits=connection.waits)
                            last=time.monotonic();prior=connection.waits
                            recovered=transport.read_structured_authenticated(records,max_bytes=256*1024,timeout_seconds=4)
                            assert encoded(recovered)==encoded(records),'exact output differs'
                            result.update(read_seconds=time.monotonic()-last,read_waits=connection.waits-prior,status='PASS')
                        except (ArchiveLimit,ArchiveUnavailable) as error:
                            result.update(status='HOLD',failure_type=type(error).__name__)
                        result.update(total_seconds=time.monotonic()-start)
                        runs[name].append(result)
            case=dict(injected_wait_ms=delay_ms,samples=runs,summary={})
            for name,values in runs.items():
                successes=[r for r in values if r['status']=='PASS'];times=sorted(r['total_seconds'] for r in successes)
                case['summary'][name]=dict(successes=len(successes),holds=len(values)-len(successes),
                    median_total_seconds=statistics.median(times) if times else None,
                    p95_total_seconds=times[max(0,math.ceil(.95*len(times))-1)] if times else None,
                    remote_stage_rows_per_second=50/statistics.median(times) if times else None)
            output['cases'].append(case)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(output,indent=2)+'\n')
        print(json.dumps(dict(page_bytes=output['page_bytes'],cases=[dict(injected_wait_ms=c['injected_wait_ms'],summary=c['summary']) for c in output['cases']]),indent=2))
    finally:fixture.tearDownClass()

if __name__=='__main__':main()
