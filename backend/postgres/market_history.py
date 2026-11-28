"""Bounded market history over attached partitions and authenticated sealed objects."""
import asyncio
import base64
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
from threading import BoundedSemaphore

from .archive_codec import (ArchiveIntegrityError, ArchiveLimit, ArchiveLimits, ArchiveUnavailable,
                            CycleBudget, encoded, read_verified, row_cursor, sha256, wire)
from .archive_transport import ScopedArchiveTransport
from .contract import source_timestamp
from .domain import timestamp, utcnow
from .history import HistoryError
from .lifecycle import LifecycleHold, LifecycleRepository, validate_manifest_chain

MAX_GENERATIONS = 8
MAX_PAGE_BYTES = 2 * 1024 * 1024
LIMITS = ArchiveLimits(max_requests=MAX_GENERATIONS, max_seconds=4, request_timeout_seconds=3)
KEYS = ('origin_id','generation_id','market_id','source','event_id','kind','symbol','source_time',
        'source_epoch','received_at','available_at','price','size','payload','content_hash')


@dataclass(frozen=True)
class Window:
    market_id: str
    start: datetime
    end: datetime
    as_of: datetime

    @classmethod
    def parse(cls, market_id, start, end, as_of):
        try:
            if not isinstance(market_id, str) or not 1 <= len(market_id) <= 128:
                raise ValueError()
            for value in (start, end, as_of):
                source_timestamp(value)
            start, end, as_of = map(timestamp, (start, end, as_of))
            if not start < end <= start + timedelta(hours=1) or not start <= as_of <= utcnow():
                raise ValueError()
            return cls(market_id, start, end, as_of)
        except (ValueError, TypeError, OverflowError):
            raise HistoryError('invalid_window', 'specify a market, bounded UTC window and past decision time') from None

    def includes(self, row):
        match = ((row['source'] == 'polymarket_us' and row.get('market_id') == self.market_id)
                 or (row['source'] == 'polymarket_us' and row['kind'] == 'price'
                     and row.get('market_id') is None and row.get('symbol') == 'BTC-USD')
                 or (row['source'] == 'coinbase' and row.get('symbol') == 'BTC-USD'
                     and row['kind'] in ('price','candle')))
        receipt = timestamp(row['received_at'])
        return (match and self.start <= receipt < self.end and
                max(receipt, timestamp(row['available_at'])) <= self.as_of and
                (row['source_epoch'] is None or source_timestamp(self.as_of.isoformat())[1]
                 >= source_timestamp(row['source_time'])[1]))


def decode(cursor, scope):
    if cursor is None:
        return ['', '']
    try:
        if len(cursor) > 2048:
            raise ValueError()
        digest, after = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
        if digest != scope or not isinstance(after, list) or len(after) != 2 or not all(
                isinstance(v, str) and len(v) <= 1024 for v in after):
            raise ValueError()
        return after
    except (ValueError, UnicodeError, TypeError):
        raise HistoryError('invalid_cursor', 'cursor differs from requested history scope') from None


def local_page(db, origin, generation, window, after, limit):
    # Project normalized fields. Exclude the large raw feed document from both
    # transport and rendering. Check an oversized payload before fetching it.
    from psycopg import sql
    # The generation comes from the database catalog. Derive the partition's
    # canonical identifier independently, then quote it as an SQL identifier.
    child = 'events_g_' + uuid.UUID(generation).hex
    fields = ','.join(k for k in KEYS if k != 'payload')
    # PostgreSQL sizes one bounded keyset page before sending JSON over the
    # connection. Up to eight candidate generations can coexist in one result.
    rows = db.execute(sql.SQL(f"""WITH candidates AS MATERIALIZED (SELECT {fields},
        payload FROM raw.{{}}
        WHERE origin_id=%s AND generation_id=%s AND received_at>=%s AND received_at<%s
        AND received_at<=%s AND available_at<=%s AND (source_epoch IS NULL OR source_epoch<=%s)
        AND ((market_id=%s AND source='polymarket_us') OR
             (source='polymarket_us' AND market_id IS NULL AND symbol='BTC-USD' AND kind='price') OR
             (source='coinbase' AND symbol='BTC-USD' AND kind IN ('price','candle')))
        AND (source COLLATE "C",event_id COLLATE "C")>(%s,%s)
        ORDER BY source COLLATE "C",event_id COLLATE "C" LIMIT %s),
        sized AS (SELECT *,sum(octet_length(payload::text)+512) OVER
            (ORDER BY source COLLATE "C",event_id COLLATE "C") AS bytes FROM candidates)
        SELECT {fields},CASE WHEN bytes<=%s THEN payload END AS payload
        FROM sized ORDER BY source COLLATE "C",event_id COLLATE "C" """).format(sql.Identifier(child)),
        (origin, generation, window.start, window.end, window.as_of, window.as_of,
         source_timestamp(window.as_of.isoformat())[1], window.market_id, *after, limit+1, MAX_PAGE_BYTES)).fetchall()
    page = [dict(row, tier='local_postgres') for row in rows[:limit] if row['payload'] is not None]
    if rows and not page:
        raise ArchiveLimit('normalized history event exceeds byte bound')
    return wire(page), row_cursor(page[-1]) if len(rows) > len(page) else None


def archived_page(generation, manifests, transport, window, after, budget):
    # Only one authenticated object per generation per request. A filtered
    # empty page can still advance through the manifest by its proven last key.
    if validate_manifest_chain(manifests, generation) != generation['seal_hash']:
        raise ArchiveIntegrityError('sealed manifest catalog changed')
    for index, m in enumerate(manifests):
        last = m['coverage']['last']
        if last is None or last <= after:
            continue
        rows = read_verified(transport, m, budget)
        page = [dict(((k, row[k]) for k in KEYS), tier='authenticated_archive')
                for row in rows if row_cursor(row) > after and window.includes(row)]
        return page, last if index+1 < len(manifests) else None
    return [], None


def merge(pages, *, limit, scope):
    # Each input proves ordering only up through its cursor. Withhold later
    # keys until ALL inputs cross that frontier, even across empty pages.
    bounds = [bound for _, bound in pages if bound is not None]
    frontier = min(bounds) if bounds else None
    unique = {}
    for rows, _ in pages:
        for row in rows:
            key = tuple(row_cursor(row))
            if frontier is not None and list(key) > frontier:
                continue
            prior = unique.setdefault(key, row)
            if prior['content_hash'] != row['content_hash']:
                raise ArchiveIntegrityError('conflicting history event identity')
    items, size = [], 0
    for key in sorted(unique):
        row = unique[key]
        size += len(encoded(row))
        if len(items) == limit or size > MAX_PAGE_BYTES:
            if not items:
                raise ArchiveLimit('single history item exceeds page byte bound')
            frontier = row_cursor(items[-1])
            break
        items.append(row)
    cursor = base64.urlsafe_b64encode(encoded([scope, frontier])).decode() if frontier else None
    return items, cursor


class BoundedHistoryReader:
    def __init__(self):
        self.slot = BoundedSemaphore(1)

    async def read_async(self, *args, **kwargs):
        # Reserve before submitting to the executor; a disconnected browser
        # cannot free the slot while its background database read is running.
        if not self.slot.acquire(blocking=False):
            raise HistoryError('history_busy', 'market history reader busy')
        task = asyncio.create_task(asyncio.to_thread(self._read, *args, **kwargs))
        def finished(done):
            self.slot.release()
            if not done.cancelled():
                done.exception()
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    def read(self, *args, **kwargs):
        if not self.slot.acquire(blocking=False):
            raise HistoryError('history_busy', 'market history reader busy')
        try:
            return self._read(*args, **kwargs)
        finally:
            self.slot.release()


class MarketHistory(BoundedHistoryReader):
    def __init__(self, store, raw_factory=None):
        super().__init__()
        self.store, self.raw_factory = store, raw_factory

    def _read(self, window, cursor, limit):
        origin = self.store.settings.origin_id
        budget = CycleBudget(LIMITS)
        pages, cold, missing = [], [], []
        tiers = set()
        with self.store.connection(readonly=True) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            db.execute("SET LOCAL statement_timeout='2000ms'")
            db.execute("SET LOCAL lock_timeout='250ms'")
            # Partition retirement must wait until the catalog and local pages
            # have been read. Release the DB connection before any remote I/O.
            db.execute('LOCK TABLE ONLY raw.events IN ACCESS SHARE MODE')
            generations = db.execute("""SELECT g.*,
                EXISTS (SELECT FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
                    WHERE i.inhparent='raw.events'::regclass AND c.relnamespace='raw'::regnamespace
                    AND c.relname=g.partition_name AND pg_get_expr(c.relpartbound,c.oid)
                        =format('FOR VALUES IN (%%L)',g.generation_id)) AS attached
                FROM archive.generations g WHERE origin_id=%s
                AND started_at<=%s AND (sealed_at IS NULL OR sealed_at>=%s)
                AND state<>'prepared' ORDER BY started_at,generation_id LIMIT %s""",
                (origin, min(window.as_of, window.end), window.start, MAX_GENERATIONS+1)).fetchall()
            if len(generations) > MAX_GENERATIONS:
                raise ArchiveLimit('too many candidate generations; narrow the decision time')
            late_generations = False
            if window.as_of > window.end:
                late_generations = db.execute("""SELECT EXISTS (SELECT FROM archive.generations
                    WHERE origin_id=%s AND started_at>%s AND started_at<=%s AND state<>'prepared') AS present""",
                    (origin, window.end, window.as_of)).fetchone()['present']
            ids = [g['generation_id'] for g in generations]
            scope = sha256(encoded([origin, window.market_id, window.start, window.end, window.as_of, ids]))
            after = decode(cursor, scope)
            for gen in generations:
                budget.check()
                gid = gen['generation_id']
                if gen['state'] == 'retired':
                    if self.raw_factory:
                        cold.append((gen, LifecycleRepository._manifests(db, gid)))
                    else:
                        missing.append(gid)
                elif not gen['attached']:
                    missing.append(gid)
                else:
                    rows, bound = local_page(db, origin, gid, window, after, limit)
                    pages.append((rows, bound))
                    tiers.add('local_postgres')
        if cold:
            with closing(self.raw_factory()) as raw:
                for gen, manifests in cold:
                    gid = gen['generation_id']
                    transport = ScopedArchiveTransport(raw, None, origin_id=origin, generation_id=gid)
                    try:
                        pages.append(archived_page(gen, manifests, transport, window, after, budget))
                        tiers.add('authenticated_archive')
                    except (ArchiveUnavailable, LifecycleHold):
                        missing.append(gid)
        budget.check()
        items, next_cursor = merge(pages, limit=limit, scope=scope)
        # Catalog coverage describes retained records. It cannot prove that
        # the upstream feed delivered every update during this time.
        covered_to = window.start
        for gen in generations:
            if gen['started_at'] > covered_to:
                break
            covered_to = max(covered_to, gen.get('sealed_at') or window.as_of)
        reasons = []
        if not ids or covered_to < min(window.end, window.as_of):
            reasons.append('generation_time_gap')
        if late_generations:
            reasons.append('later_generations_not_checked_for_late_arrivals')
        if missing:
            reasons.append('missing_generations')
        covered = not reasons
        return {'items':items, 'next_cursor':next_cursor if not missing else None,
                'coverage':{'complete':covered, 'reasons':reasons, 'generation_ids':ids, 'missing_generations':missing,
                            'meaning':'captured records in generations intersecting the requested receipt-time window',
                            'includes_btc_usd_references':True, 'tiers':sorted(tiers)},
                'origin_id':origin, 'as_of':window.as_of.isoformat()}
