"""Read-only, bounded telemetry for the continuous PP Benchmark origin."""
import asyncio
import time
from datetime import datetime, timezone

from .domain import timestamp

ORIGIN = 'pp-live-pp-benchmark-watch'
FEEDS = ('coinbase_stream', 'coinbase_candles', 'polymarket_catalog', 'polymarket_book',
         'polymarket_reference', 'robinhood_reference')
ISSUES = ('auth', 'rate_limit', 'http_4xx', 'http_5xx', 'transport', 'invalid', 'retry', 'write')
_counts = {}
_sender = None


def classify_status(status):
    if status in (401, 403):
        return 'auth'
    if status == 429:
        return 'rate_limit'
    return 'http_5xx' if status >= 500 else 'http_4xx'


def source_monitor(sender):
    """One collector process owns a bounded session and these cumulative counters."""
    global _sender
    _counts.clear()
    _sender = sender if sender is not None and sender.origin == ORIGIN else None
    heartbeat()


def heartbeat():
    if _sender is not None:
        _sender.send({'type': 'source_health', 'counts': dict(_counts)})


def issue(feed, reason):
    if _sender is None or feed not in FEEDS or reason not in ISSUES:
        return
    import logging
    key = feed + '/' + reason
    _counts[key] = _counts.get(key, 0) + 1
    logging.getLogger(__name__).warning('pp_feed_event source=%s reason=%s count=%d',
                                       feed, reason, _counts[key])
    heartbeat()


def valid_counts(counts):
    if not isinstance(counts, dict) or len(counts) > len(FEEDS) * len(ISSUES):
        return False
    keys = {f'{feed}/{reason}' for feed in FEEDS for reason in ISSUES}
    return all(key in keys and type(value) is int and 0 <= value < 2**53
               for key, value in counts.items())


def archive_status(store):
    # Both active and draining windows remain visible. The statement timeout
    # bounds aggregate work if the data grows beyond this diagnostic profile.
    with store.connection(True) as db:
        db.execute("SET LOCAL statement_timeout='1200ms'")
        db.execute("SET LOCAL lock_timeout='100ms'")
        rows = db.execute("""
            SELECT g.slot, g.generation_id::text AS generation, g.state,
                   g.generation_id=w.generation_id AS current,
                   COALESCE(w.collector_enabled AND w.collector_lease_expires_at>statement_timestamp(),false) AS enabled,
                   totals.pending, (ack.cursor->>'rows')::bigint AS acknowledged, totals.oldest_age,
                   extract(epoch FROM statement_timestamp())::float8 AS observed_at
            FROM ops.writer_state w JOIN archive.generations g ON g.origin_id=w.origin_id
            LEFT JOIN archive.checkpoints ack ON ack.origin_id=g.origin_id AND ack.generation_id=g.generation_id
                AND ack.consumer='structured:verified-acks-v1'
            CROSS JOIN LATERAL (
                SELECT count(*) AS pending,
                       COALESCE(extract(epoch FROM statement_timestamp() -
                         min(created_at)),0)::float8 AS oldest_age
                FROM ops.outbox WHERE origin_id=g.origin_id AND generation_id=g.generation_id
                    AND acknowledged_at IS NULL
            ) totals WHERE w.origin_id=%s AND g.state IN ('collecting','sealed','verified','prepared')
            ORDER BY g.slot""", (store.origin,)).fetchall()
    return list(rows)


class BenchmarkTelemetry:
    def __init__(self, store, state):
        self.store, self.state = store, state
        self.lock = asyncio.Lock()
        self.sampled = float('-inf')
        self.windows = None

    async def snapshot(self):
        async with self.lock:
            if time.monotonic() - self.sampled >= 15:
                try:
                    self.windows = await asyncio.to_thread(archive_status, self.store)
                except Exception:
                    self.windows = None
                self.sampled = time.monotonic()
        active = next((w for w in (self.windows or ()) if w['current']),None)
        self.state.benchmark_window = ({k:active[k] for k in ('slot','generation','state','observed_at')}
                                       if active else None)
        state = self.state.snapshot()
        now = datetime.now(timezone.utc)
        refs = {}
        for source, key in (('coinbase','coinbase'), ('polymarket','polymarket_reference'),
                            ('robinhood','robinhood_reference')):
            observation = state.get(key) or {}
            refs[source] = {basis: (now - timestamp(observation[field])).total_seconds()
                            for basis, field in (('provider','source_time'), ('pp_receipt','received_at'))
                            if observation.get(field)}
        return {'origin': self.store.origin, 'observed_at': now.timestamp(), 'windows': self.windows,
                'reference_age': refs, 'feed_enabled': {f:v['enabled'] for f,v in (state.get('feed_controls') or {}).items()},
                'source_health': self.state.source_health,
                'quote_counts': state['quote_counts'], 'database_quote_received_at': self.state.durable_quote_received_at}
