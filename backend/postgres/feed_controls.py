"""Per-origin feed preferences and restricted private browser commands for PP."""
import hashlib
import hmac
import secrets
import time

from psycopg import Error
from psycopg.types.json import Jsonb

from .live_diagnostics import READ_CAPACITY_BACKOFF, connection_capacity

ORIGIN = 'pp-live-pp-benchmark-watch'
FEEDS = ('polymarket','coinbase','robinhood')
COMPONENTS = {'polymarket': ('polymarket',), 'coinbase': ('coinbase_stream','coinbase_candles'),
              'robinhood': ('robinhood',)}
PREFERENCE = 'feed_desired:'
ACTUAL = 'feed_actual:'
TTL = 1800


class RevisionConflict(ValueError):
    pass


def check_store(store):
    if store.origin != ORIGIN or store.settings.data_mode != 'pp_live' or store.settings.environment != 'preprod':
        raise ValueError('continuous Benchmark only')


def _rows(db):
    rows = db.execute("""SELECT w.collector_session_id::text AS session,
        w.collector_enabled AND w.collector_lease_expires_at>clock_timestamp() AS enabled,
        c.worker,c.cursor FROM ops.writer_state w LEFT JOIN ops.worker_checkpoints c
        ON c.origin_id=w.origin_id AND c.worker=ANY(%s) WHERE w.origin_id=%s""",
        ([PREFERENCE+s for s in FEEDS]+[ACTUAL+s for values in COMPONENTS.values() for s in values],ORIGIN)).fetchall()
    if not rows:
        raise ValueError('Benchmark origin not initialized')
    return rows


def _state(rows):
    saved = {row['worker']:row['cursor'] for row in rows if row['worker']}
    session = rows[0]['session'] if rows[0]['enabled'] else None
    result = {}
    for feed, components in COMPONENTS.items():
        requested = saved.get(PREFERENCE+feed, {'enabled':True,'revision':0})
        if type(requested.get('enabled')) is not bool or type(requested.get('revision')) is not int:
            raise ValueError('invalid durable feed preference')
        health = {}
        for component in components:
            actual = saved.get(ACTUAL+component) or {}
            health[component] = ('off' if not session else actual.get('state','unknown')
                                 if actual.get('session')==session else 'unknown')
        result[feed] = {**requested,'components':health}
    return result


def read_controls(store):
    check_store(store)
    with store.connection(True) as db:
        return _state(_rows(db))


def desired_feeds(store):
    check_store(store)
    for delay in READ_CAPACITY_BACKOFF:
        connection = None
        try:
            connection = store.connection(True)
            with connection as db:
                return {k:v['enabled'] for k,v in _state(_rows(db)).items()}
        except Error as error:
            # A retry borrows a fresh transaction. Admission pressure is
            # retryable only before the borrow succeeds; statement and
            # transaction timeouts may also surface on read-only commit.
            retryable = error.sqlstate in ('57014', '25P04') or (
                connection is None and connection_capacity(error, login=getattr(store, 'read_login', 'tradebot_app')))
            if delay is None or not retryable:
                raise
            time.sleep(delay)


def set_desired(store, feed, enabled, expected_revision):
    check_store(store)
    if feed not in FEEDS or type(enabled) is not bool or type(expected_revision) is not int or expected_revision<0:
        raise ValueError('invalid feed preference')
    with store.connection() as db:
        db.execute("SET LOCAL lock_timeout='800ms'")
        db.execute("SET LOCAL statement_timeout='1500ms'")
        # Per-feed serialization covers the first INSERT as well as updates.
        # Concurrent commands for different feeds have independent keys.
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(ORIGIN+':'+feed,))
        current = _state(_rows(db))[feed]
        if current['enabled'] == enabled:
            return current
        if current['revision'] != expected_revision:
            raise RevisionConflict('feed preference has changed')
        requested={'enabled':enabled,'revision':expected_revision+1}
        db.execute("""INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at)
            VALUES(%s,%s,%s,clock_timestamp()) ON CONFLICT(origin_id,worker)
            DO UPDATE SET cursor=EXCLUDED.cursor,updated_at=EXCLUDED.updated_at""",
            (ORIGIN,PREFERENCE+feed,Jsonb(requested)))
        return {**requested,'components':current['components']}


def record_effective(store, component, state, *, session_id):
    check_store(store)
    if component not in {part for values in COMPONENTS.values() for part in values} or state not in ('running','retrying','paused','held'):
        raise ValueError('invalid feed status')
    with store.connection() as db:
        db.execute("SET LOCAL statement_timeout='1500ms'")
        db.execute("""INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at)
            SELECT origin_id,%s,jsonb_build_object('state',%s::text,'session',collector_session_id::text),clock_timestamp()
            FROM ops.writer_state WHERE origin_id=%s AND collector_enabled AND collector_lease_expires_at>clock_timestamp()
                AND collector_session_id=%s::uuid FOR SHARE
            ON CONFLICT(origin_id,worker) DO UPDATE SET cursor=EXCLUDED.cursor,updated_at=EXCLUDED.updated_at""",
            (ACTUAL+component,state,ORIGIN,session_id))


def _signature(secret, payload):
    return hmac.new(secret.encode('ascii'),('private-feed-controls-v1:'+ORIGIN+':'+payload).encode('ascii'),
                    hashlib.sha256).hexdigest()


def mint(secret, now=None):
    expires=int(time.time() if now is None else now)+TTL
    payload=f'{expires}.{secrets.token_hex(16)}'
    return {'access_token':payload+'.'+_signature(secret,payload),'expires_at':expires,'origin':ORIGIN}


def verify(secret, bearer, now=None):
    if not isinstance(bearer,str) or not bearer.startswith('Bearer ') or len(bearer)>170:
        return False
    parts=bearer[7:].split('.')
    if len(parts)!=3:
        return False
    expiry,nonce,mac=parts
    if len(expiry)!=10 or not expiry.isascii() or not expiry.isdecimal() or len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce):
        return False
    at=time.time() if now is None else now
    return (0<int(expiry)-at<=TTL+1 and len(mac)==64 and mac.isascii()
            and hmac.compare_digest(_signature(secret,expiry+'.'+nonce),mac))
