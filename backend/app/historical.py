"""Bounded retrospective Polymarket US 15-minute metadata and display-price backfill."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import time

from collector import PM, amount, connect, get_json, normalize, record, save_market, timestamp, utcnow


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS historical_market_prices (
      market_id TEXT NOT NULL REFERENCES markets(id),
      source_time INTEGER NOT NULL, long_price TEXT, short_price TEXT,
      retrieved_at TEXT NOT NULL,
      PRIMARY KEY(market_id,source_time));
    CREATE INDEX IF NOT EXISTS historical_market_prices_time
      ON historical_market_prices(source_time);
    ''')


def discover_past(start, end, fetch=get_json, max_pages=10):
    """Use administrative dates only to narrow the search; verify typed market windows."""
    found = {}
    for page in range(max_pages):
        rows = fetch(PM, '/v1/markets', {
            'limit': 100, 'offset': page*100, 'closed': 'true', 'categories': 'crypto',
            'endDateMin': (start-timedelta(hours=1)).isoformat(),
            'endDateMax': (end+timedelta(hours=1)).isoformat()}).get('markets')
        if not isinstance(rows, list):
            raise ValueError('Unexpected market-list response')
        for raw in rows:
            market = normalize(raw)
            if market and market['duration'] == 900 and market['result'] in ('UP','DOWN'):
                if start <= timestamp(market['start']) and timestamp(market['end']) <= end:
                    found[market['id']] = market
        if len(rows) < 100:
            return sorted(found.values(), key=lambda m: m['start'])
    raise RuntimeError('Historical market pagination cap reached; no complete result claimed')


def save_price_history(db, market, history, retrieved_at):
    if not isinstance(history, list):
        raise ValueError('Unexpected price-history response')
    start, end = int(timestamp(market['start']).timestamp()), int(timestamp(market['end']).timestamp())
    stored = 0
    for row in history:
        if not isinstance(row, dict) or 'timestamp' not in row:
            raise ValueError('Unexpected price-history point')
        t = int(row['timestamp'])
        if not start <= t <= end:
            continue
        long_price, short_price = amount(row.get('longPrice')), amount(row.get('shortPrice'))
        if long_price is None and short_price is None:
            continue
        for price in (long_price, short_price):
            if price is not None and not 0 <= Decimal(price) <= 1:
                raise ValueError('Display price outside 0..1')
        stored += db.execute('''INSERT OR IGNORE INTO historical_market_prices
          (market_id,source_time,long_price,short_price,retrieved_at) VALUES(?,?,?,?,?)''',
          (market['id'],t,long_price,short_price,retrieved_at)).rowcount
    return stored


def expected_windows(start,end):
    cursor = int(start.timestamp())
    cursor = (cursor+899)//900*900
    return [datetime.fromtimestamp(t,timezone.utc).isoformat()
            for t in range(cursor,int(end.timestamp())-899,900)]


def backfill_window(db,start,end,fetch=get_json,pause=time.sleep):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError('Window timestamps need timezones')
    start,end = start.astimezone(timezone.utc),end.astimezone(timezone.utc)
    if not timedelta(0) < end-start <= timedelta(hours=8) or end > utcnow():
        raise ValueError('Use a completed window of at most eight hours')
    initialize(db)
    markets = discover_past(start,end,fetch)
    stored_points = 0
    failures = []
    for market in markets:
        old = db.execute('SELECT result,final FROM markets WHERE id=?',(market['id'],)).fetchone()
        if old is None or old != (market['result'],market['final']):
            with db:
                save_market(db,market,utcnow().isoformat())
        try:
            history = fetch(PM,'/v1/price-history',{
                'symbol':market['slug'],
                'timestamp.startTimestamp':int(timestamp(market['start']).timestamp()),
                'timestamp.endTimestamp':int(timestamp(market['end']).timestamp()),
                'fidelity':1}).get('history')
            with db:
                stored_points += save_price_history(db,market,history,utcnow().isoformat())
        except Exception as exc:
            failures.append({'market_id':market['id'],'error':type(exc).__name__})
            record(db,'polymarket_history',False,f"{market['slug']}: {type(exc).__name__}: {exc}")
        pause(.1)
    found_starts = {market['start'] for market in markets}
    missing = [window for window in expected_windows(start,end) if window not in found_starts]
    result = {'window_start':start.isoformat(),'window_end':end.isoformat(),
              'expected_complete_intervals':len(expected_windows(start,end)),
              'resolved_markets_found':len(markets),
              'missing_intervals':missing,
              'new_display_price_points':stored_points,
              'price_history_failures':failures,
              'provenance':'retrieved_after_market_close; not live observations or forecasts'}
    record(db,'polymarket_history',not failures and not missing,json.dumps(result))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/btc_intelligence.db')
    parser.add_argument('--hours',type=int,default=8,help='Completed hours to backfill, 1..8')
    parser.add_argument('--end',help='UTC ISO end time for an older bounded chunk; default is current whole hour')
    args=parser.parse_args()
    if not 1<=args.hours<=8:
        parser.error('hours must be 1..8')
    end=timestamp(args.end) if args.end else utcnow().replace(minute=0,second=0,microsecond=0)
    start=end-timedelta(hours=args.hours)
    db=connect(args.db)
    try:
        print(json.dumps(backfill_window(db,start,end),indent=2))
    finally:
        db.close()


if __name__=='__main__': main()
