"""Synthetic I7 qualification only: never accepts an existing database path.

Creates generated fixture data in TemporaryDirectory, not a database copy. Reports
build time, page growth, query speed and writer exclusion. This is not permission
to build production indexes and does not predict cold production disk latency.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent / 'app'))
from collector import connect
from streaming import initialize
from features import _price, price_query
from feature_price_indexes import create_price_indexes


def benchmark(rows):
    with tempfile.TemporaryDirectory(prefix='tradebot-synthetic-price-') as folder:
        path=Path(folder)/'generated.db'
        db=connect(str(path)); initialize(db)
        origin=datetime(2026,10,31,tzinfo=timezone.utc)
        def data():
            for i in range(rows):
                stamp=origin+timedelta(seconds=i)
                yield ('coinbase',str(i),(stamp+timedelta(seconds=1)).isoformat(),
                       stamp.isoformat(),f'60000.{i%100:02d}',None,None,'{}')
        db.executemany('INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)',data())
        db.execute("INSERT INTO reference_prices(received_at,source_time,source,price,payload) SELECT received_at,source_time,source,price,payload FROM stream_events")
        db.commit()
        cutoff=origin+timedelta(seconds=rows)
        def queries():
            times=[]
            for _ in range(5):
                start=time.perf_counter(); result=_price(db,cutoff)
                times.append(time.perf_counter()-start)
            return result,times
        before,times_before=queries()
        pages_before=db.execute('PRAGMA page_count').fetchone()[0]
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        started,attempt_done=threading.Event(),threading.Event()
        stats={}
        def build():
            owner=sqlite3.connect(path,timeout=1)
            try:
                owner.execute('BEGIN IMMEDIATE');started.set()
                start=time.perf_counter();create_price_indexes(owner)
                stats['build_seconds']=time.perf_counter()-start
                assert attempt_done.wait(3),'writer probe did not finish'
                owner.commit()
            except BaseException as error:
                stats['error_type']=type(error).__name__
                owner.rollback();started.set()
            finally:owner.close()
        worker=threading.Thread(target=build);worker.start()
        try:
            assert started.wait(3),'index transaction did not start'
            writer=sqlite3.connect(path,timeout=0.05)
            try:
                start=time.perf_counter()
                try:
                    writer.execute("INSERT INTO runs(received_at,source,success,detail) VALUES('fixture','fixture',1,'fixture')")
                    raise AssertionError('concurrent writer unexpectedly acquired index transaction')
                except sqlite3.OperationalError as error:
                    assert getattr(error,'sqlite_errorcode',None)==sqlite3.SQLITE_BUSY
                    stats['writer_busy_seconds']=time.perf_counter()-start
            finally:writer.close()
        finally:
            attempt_done.set();worker.join(30)
        assert not worker.is_alive() and 'error_type' not in stats,stats
        after,times_after=queries();assert after==before
        # Prove the writer resumes after schema transaction completes.
        with db:db.execute("INSERT INTO runs(received_at,source,success,detail) VALUES('fixture','fixture',1,'fixture')")
        plans={table:db.execute('EXPLAIN QUERY PLAN '+price_query(table,key),(cutoff.isoformat(),)*2).fetchall()
               for table,key in (('stream_events','event_id'),('reference_prices','id'))}
        assert not any('TEMP B-TREE' in row[3] for plan in plans.values() for row in plan),plans
        growth=(db.execute('PRAGMA page_count').fetchone()[0]-pages_before)*page_size
        db.close()
        return dict(stats,rows_per_table=rows,index_page_growth_bytes=growth,
                    query_median_before_seconds=statistics.median(times_before),
                    query_median_after_seconds=statistics.median(times_after),
                    query_output_equivalence=True,writer_resumed=True,plans=plans,
                    production_qualification=False,fixture='generated temporary data; no database copy')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows',type=int,default=100000)
    args=parser.parse_args()
    if not 1000<=args.rows<=1000000:parser.error('rows must be 1000..1000000')
    print(json.dumps(benchmark(args.rows),indent=2))
