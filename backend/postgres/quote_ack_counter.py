"""Constant-cost receipt counts for a registered Benchmark collector session."""
from datetime import datetime

WATCH_ORIGIN = 'pp-live-pp-benchmark-watch'
SESSION = 'quote-display:session-v1'
ACK = 'quote-display:verified-acks-v1'


def _lock(db, origin):
    # Local transaction only. A concurrent cloud request never owns this lock.
    db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
               ('tradebot-quote-ack-session:'+origin,))


def register(store):
    """Start a counter before this writer can enqueue its first quote."""
    from psycopg.types.json import Jsonb
    if store.origin != WATCH_ORIGIN:
        raise ValueError('unexpected quote counter origin')
    with store.connection() as db:
        db.execute("SET LOCAL lock_timeout='750ms'")
        _lock(db,store.origin)
        row = db.execute("""SELECT generation_id,clock_timestamp() AS started
            FROM ops.writer_state WHERE origin_id=%s AND collector_enabled
              AND collector_lease_expires_at>clock_timestamp()""",(store.origin,)).fetchone()
        if row is None:
            raise RuntimeError('no active quote session to register')
        cursor = {'started_at': row['started'].isoformat(), 'generation_id': str(row['generation_id'])}
        db.execute("""INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at)
            VALUES(%s,%s,%s,%s) ON CONFLICT(origin_id,worker)
            DO UPDATE SET cursor=EXCLUDED.cursor,updated_at=EXCLUDED.updated_at""",
            (store.origin,SESSION,Jsonb(cursor),row['started']))
        return cursor['started_at']


def add_transitions(db, origin, created):
    """Account only real NULL-to-ACK transitions for the current collector start."""
    _lock(db,origin)
    session = db.execute('SELECT cursor FROM ops.worker_checkpoints WHERE origin_id=%s AND worker=%s',
                         (origin,SESSION)).fetchone()
    if not session:
        return
    cursor = session['cursor']
    start = datetime.fromisoformat(cursor['started_at'])
    count = sum(at >= start for at in created)
    if count:
        db.execute("""INSERT INTO archive.checkpoints AS current(origin_id,generation_id,consumer,cursor,acknowledged_at)
            VALUES(%s,%s,%s,jsonb_build_object('started_at',%s::text,'rows',%s::bigint),clock_timestamp())
            ON CONFLICT(origin_id,generation_id,consumer) DO UPDATE SET
              cursor=jsonb_build_object('started_at',EXCLUDED.cursor->>'started_at','rows',
                 (EXCLUDED.cursor->>'rows')::bigint + CASE
                   WHEN current.cursor->>'started_at'=EXCLUDED.cursor->>'started_at'
                   THEN (current.cursor->>'rows')::bigint ELSE 0 END),
              acknowledged_at=EXCLUDED.acknowledged_at""",
            (origin,cursor['generation_id'],ACK,cursor['started_at'],count))


def read(db, origin, started):
    # The registration establishes zero. An earlier process's delayed display
    # packet cannot borrow the current process's count or trigger a history scan.
    row = db.execute("""SELECT CASE WHEN a.cursor->>'started_at'=s.cursor->>'started_at'
            THEN (a.cursor->>'rows')::bigint ELSE 0 END AS n
        FROM ops.worker_checkpoints s LEFT JOIN archive.checkpoints a
          ON a.origin_id=s.origin_id AND a.generation_id=s.cursor->>'generation_id' AND a.consumer=%s
        WHERE s.origin_id=%s AND s.worker=%s AND s.cursor->>'started_at'=%s""",
        (ACK,origin,SESSION,started)).fetchone()
    return row['n'] if row else None
