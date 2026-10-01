"""Read-only Polymarket US collector. Standard library only; no order APIs."""
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

PM = 'https://gateway.polymarket.us'
CB = 'https://api.exchange.coinbase.com'


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return dt.astimezone(timezone.utc)


def amount(value):
    if isinstance(value, dict):
        value = value.get('value')
    if value is None:
        return None
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError('Nonfinite price')
    return str(d)


def get_json(base, path, params=None):
    url = base + path + ('?' + urlencode(params) if params else '')
    req = Request(url, headers={'User-Agent': 'BTC-Intelligence-ReadOnly/0.1', 'Accept': 'application/json'})
    for attempt in range(4):
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry_after = exc.headers.get('Retry-After') if exc.headers else None
            try:
                delay = max(1, min(60, float(retry_after))) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            time.sleep(delay)


def normalize(raw):
    terms = raw.get('assetPriceTerms') or {}
    if (terms.get('asset') or {}).get('symbol', '').lower() != 'btc':
        return None
    if terms.get('marketType') != 'ASSET_PRICE_MARKET_TYPE_UP_DOWN':
        return None
    if terms.get('horizon') not in ('15m', '1h'):
        return None
    start, end = timestamp(terms['windowStart']), timestamp(terms['windowEnd'])
    duration = int((end-start).total_seconds())
    if duration != {'15m': 900, '1h': 3600}[terms['horizon']]:
        raise ValueError('Market duration conflicts with terms')
    target, final = amount(terms.get('priceToBeat')), amount(terms.get('settlementPrice'))
    # Only confirmed resolved terms produce a label, never exchange prices.
    result = None
    if raw.get('status') == 'MARKET_STATUS_RESOLVED' and final is not None and target is not None:
        result = 'UP' if Decimal(final) >= Decimal(target) else 'DOWN'
    return dict(id=str(raw['id']), slug=raw['slug'], duration=duration,
                start=start.isoformat(), end=end.isoformat(), target=target,
                final=final, result=result, status=raw.get('status'),
                index=terms.get('indexSymbol'), rules=raw.get('description'), raw=raw)


def session_state(market, now):
    start, end = timestamp(market['start']), timestamp(market['end'])
    if now < start:
        return 'scheduled'
    if now >= end:
        return 'resolved' if market['result'] else 'pending_result'
    if market['status'] != 'MARKET_STATUS_OPEN':
        return 'unavailable'
    return 'active' if market['target'] is not None else 'awaiting_target'


def discover(now, durations=(900,)):
    found = {}
    # Bounded pagination: a cap is an explicit error, not silent incomplete discovery.
    for offset in range(0, 2000, 100):
        data = get_json(PM, '/v1/markets', dict(limit=100, offset=offset,
                        active='true', closed='false', categories='crypto'))
        if not isinstance(data.get('markets'), list):
            raise ValueError('Unexpected Polymarket response')
        for raw in data['markets']:
            m = normalize(raw)
            if m and m['duration'] in durations and timestamp(m['start']) <= now < timestamp(m['end']):
                if m['duration'] in found and found[m['duration']]['id'] != m['id']:
                    raise ValueError('Ambiguous active market for duration')
                found[m['duration']] = m
        if len(data['markets']) < 100:
            return found
        time.sleep(.25)
    raise RuntimeError('Discovery pagination limit reached')


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS markets (
      id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, duration INTEGER NOT NULL,
      start TEXT NOT NULL, end TEXT NOT NULL, target TEXT, final TEXT, result TEXT,
      status TEXT, index_symbol TEXT, rules TEXT, first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL, raw_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS observations (
      id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(id),
      received_at TEXT NOT NULL, source_time TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS candles (
      source TEXT NOT NULL, symbol TEXT NOT NULL, granularity INTEGER NOT NULL,
      time INTEGER NOT NULL, low TEXT, high TEXT, open TEXT, close TEXT, volume TEXT,
      first_seen TEXT, PRIMARY KEY(source,symbol,granularity,time));
    CREATE TABLE IF NOT EXISTS reference_prices (
      id INTEGER PRIMARY KEY, received_at TEXT NOT NULL, source_time TEXT,
      source TEXT NOT NULL, price TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, received_at TEXT NOT NULL, source TEXT NOT NULL,
      success INTEGER NOT NULL, detail TEXT NOT NULL);
    ''')
    if 'first_seen' not in {row[1] for row in db.execute('PRAGMA table_info(candles)')}:
        db.execute('ALTER TABLE candles ADD COLUMN first_seen TEXT')
    return db


def save_market(db, m, received):
    values = (m['id'], m['slug'], m['duration'], m['start'], m['end'], m['target'],
              m['final'], m['result'], m['status'], m['index'], m['rules'], received,
              received, json.dumps(m['raw']))
    db.execute('''INSERT INTO markets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET target=excluded.target, final=excluded.final,
      result=excluded.result,status=excluded.status,last_seen=excluded.last_seen,
      raw_json=excluded.raw_json,rules=excluded.rules''', values)
    save_observation(db, m['id'], received, 'metadata', m['raw'], m['raw'].get('updatedAt'))


def save_observation(db, market_id, received, kind, payload, source_time=None):
    db.execute('INSERT INTO observations(market_id,received_at,source_time,kind,payload) VALUES(?,?,?,?,?)',
               (market_id, received, source_time, kind, json.dumps(payload)))


def save_candles(db, rows, start, end):
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError('Unexpected candle schema')
        t, low, high, op, cl, vol = row
        if not start <= int(t) < end:
            continue
        prices = [amount(x) for x in (low, high, op, cl, vol)]
        if Decimal(prices[0]) > Decimal(prices[1]) or Decimal(prices[4]) < 0:
            raise ValueError('Invalid candle range or volume')
        db.execute('''INSERT INTO candles(source,symbol,granularity,time,low,high,open,close,volume,first_seen)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,symbol,granularity,time) DO UPDATE SET
          low=excluded.low,high=excluded.high,open=excluded.open,close=excluded.close,
          volume=excluded.volume,first_seen=COALESCE(candles.first_seen,excluded.first_seen)''',
          ('coinbase', 'BTC-USD', 60, int(t), *prices, utcnow().isoformat()))


def backfill(db, hours):
    end = int(utcnow().timestamp()) // 60 * 60  # exclude current unfinished candle
    start = end - hours * 3600
    for cursor in range(start, end, 300*60):
        finish = min(cursor+300*60, end)
        rows = get_json(CB, '/products/BTC-USD/candles', dict(granularity=60,
               start=datetime.fromtimestamp(cursor, timezone.utc).isoformat(),
               end=datetime.fromtimestamp(finish, timezone.utc).isoformat()))
        with db:
            save_candles(db, rows, cursor, finish)
        time.sleep(.4)
    count = db.execute('SELECT COUNT(*) FROM candles WHERE time>=? AND time<?', (start,end)).fetchone()[0]
    return dict(requested_minutes=hours*60, stored_minutes=count, missing_minutes=hours*60-count)


def refresh_recent_candles(db, minutes=20):
    """Refresh completed one-minute Coinbase candles in one bounded request."""
    if not 16 <= minutes <= 300:
        raise ValueError('minutes must be 16..300')
    end = int(utcnow().timestamp()) // 60 * 60
    start = end - minutes * 60
    rows = get_json(CB, '/products/BTC-USD/candles', dict(
        granularity=60,
        start=datetime.fromtimestamp(start, timezone.utc).isoformat(),
        end=datetime.fromtimestamp(end, timezone.utc).isoformat()))
    with db:
        save_candles(db, rows, start, end)
    count = db.execute("""SELECT COUNT(*) FROM candles WHERE source='coinbase'
        AND symbol='BTC-USD' AND granularity=60 AND time>=? AND time<?""",
        (start, end)).fetchone()[0]
    return dict(requested_minutes=minutes, stored_minutes=count,
                missing_minutes=minutes-count)


def record(db, source, success, detail):
    with db:
        db.execute('INSERT INTO runs(received_at,source,success,detail) VALUES(?,?,?,?)',
                   (utcnow().isoformat(), source, int(success), str(detail)))


def collect_once(db, durations=(900,)):
    messages = []
    try:
        markets = discover(utcnow(), durations)
        received = utcnow().isoformat()
        for duration in durations:
            m = markets.get(duration)
            if not m:
                messages.append(f'{duration//60}m: no current market found')
                continue
            with db:
                save_market(db,m,received)
            messages.append(f"{duration//60}m: {m['slug']} target={m['target']} state={session_state(m,utcnow())}")
            try:
                kind = 'bbo'
                try:
                    book = get_json(PM, '/v1/markets/'+quote(m['slug'], safe='')+'/bbo')
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
                    kind = 'book'
                    book = get_json(PM, '/v1/markets/'+quote(m['slug'], safe='')+'/book')
                if not isinstance(book.get('marketData'), dict):
                    raise ValueError('Missing marketData')
                with db:
                    save_observation(db,m['id'],utcnow().isoformat(),kind,book,book['marketData'].get('transactTime'))
            except Exception as exc:
                detail = f"{m['slug']} endpoint={kind}: {exc}"
                record(db,'polymarket_quotes',False,detail)
                messages.append(f'Quotes unavailable: {detail}')
        record(db,'polymarket_discovery',True,', '.join(messages))
    except Exception as exc:
        record(db,'polymarket_discovery',False,exc)
        messages.append(f'Discovery failed: {exc}')
    # Resolve previous markets separately from discovery of the new active one.
    placeholders = ','.join('?' for _ in durations)
    pending = db.execute(f"SELECT slug FROM markets WHERE end<=? AND result IS NULL AND duration IN ({placeholders}) ORDER BY end LIMIT 10", (utcnow().isoformat(), *durations)).fetchall()
    for (slug,) in pending:
        try:
            raw = get_json(PM, '/v1/market/slug/'+quote(slug,safe=''))['market']
            m = normalize(raw)
            if m:
                with db:
                    save_market(db,m,utcnow().isoformat())
        except Exception as exc:
            record(db,'polymarket_resolution',False,f'{slug}: {exc}')
    try:
        ticker = get_json(CB, '/products/BTC-USD/ticker')
        if amount(ticker.get('price')) is None:
            raise ValueError('Missing BTC price')
        with db:
            db.execute('INSERT INTO reference_prices(received_at,source_time,source,price,payload) VALUES(?,?,?,?,?)',
                       (utcnow().isoformat(),ticker.get('time'),'coinbase',amount(ticker['price']),json.dumps(ticker)))
        messages.append('BTC reference (Coinbase, not settlement): '+amount(ticker['price']))
        record(db,'coinbase_ticker',True,'stored')
    except Exception as exc:
        record(db,'coinbase_ticker',False,exc)
        messages.append(f'BTC reference failed: {exc}')
    return messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', choices=('15m', '1h', 'both'), default='15m', help='Default: collect only 15-minute markets')
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--backfill-hours', type=int, default=0)
    parser.add_argument('--cycles', type=int, default=1, help='Bounded cycles; no background process')
    parser.add_argument('--interval', type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 120 or args.interval < 15 or not 0 <= args.backfill_hours <= 720:
        parser.error('cycles 1..120, interval >=15s, backfill hours 0..720 required')
    durations = {'15m': (900,), '1h': (3600,), 'both': (900,3600)}[args.duration]
    db = connect(args.db)
    try:
        if args.backfill_hours:
            try:
                coverage = backfill(db,args.backfill_hours)
                record(db,'coinbase_backfill',True,coverage)
                print('Candle coverage:', coverage, flush=True)
            except Exception as exc:
                record(db,'coinbase_backfill',False,exc)
                print('Backfill failed:', exc, flush=True)
        for cycle in range(args.cycles):
            print('\n'.join(collect_once(db,durations)), flush=True)
            if cycle+1 < args.cycles:
                time.sleep(args.interval)
        failures = db.execute('SELECT source,detail FROM runs WHERE success=0 ORDER BY id DESC LIMIT 5').fetchall()
        if failures:
            print('Recent recorded failures:', failures, flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()
