"""Resume bounded historical Polymarket US 15-minute backfill across days."""
import argparse
from datetime import timedelta
import json

from collector import connect, timestamp, utcnow
from historical import backfill_window


def initialize_batch(db):
    db.execute('''CREATE TABLE IF NOT EXISTS historical_backfill_chunks (
      window_start TEXT NOT NULL, window_end TEXT NOT NULL,
      attempted_at TEXT NOT NULL, result_json TEXT NOT NULL,
      PRIMARY KEY(window_start, window_end))''')
    db.commit()


def chunks(end, days):
    if not 1 <= days <= 30:
        raise ValueError('days must be 1..30')
    if end.tzinfo is None or end != end.replace(minute=0, second=0, microsecond=0):
        raise ValueError('end must be a timezone-aware whole hour')
    for n in range(days * 3):
        finish = end - timedelta(hours=8 * n)
        yield finish - timedelta(hours=8), finish


def run(db, end, days, backfill=backfill_window, output=print):
    initialize_batch(db)
    completed = 0
    skipped = 0
    unresolved = 0
    points = 0
    failures = 0
    for start, finish in chunks(end, days):
        key = (start.isoformat(), finish.isoformat())
        prior = db.execute('''SELECT result_json FROM historical_backfill_chunks
            WHERE window_start=? AND window_end=?''', key).fetchone()
        if prior and not json.loads(prior[0])['price_history_failures'] and not json.loads(prior[0])['missing_intervals']:
            skipped += 1
            unresolved += len(json.loads(prior[0])['missing_intervals'])
            continue
        try:
            result = backfill(db, start, finish)
        except Exception as exc:
            failures += 1
            output(json.dumps({'window_start': key[0], 'error': f'{type(exc).__name__}: {exc}'}), flush=True)
            continue
        with db:
            db.execute('''INSERT INTO historical_backfill_chunks
              (window_start,window_end,attempted_at,result_json) VALUES(?,?,?,?)
              ON CONFLICT(window_start,window_end) DO UPDATE SET
              attempted_at=excluded.attempted_at,result_json=excluded.result_json''',
              (*key, utcnow().isoformat(), json.dumps(result)))
        completed += 1
        points += result['new_display_price_points']
        unresolved += len(result['missing_intervals'])
        failures += len(result['price_history_failures'])
        output(json.dumps({'window_start': key[0],
            'markets': result['resolved_markets_found'],
            'expected': result['expected_complete_intervals'],
            'missing': len(result['missing_intervals']),
            'new_price_points': result['new_display_price_points'],
            'price_failures': len(result['price_history_failures'])}), flush=True)
    return {'completed_chunks': completed, 'skipped_chunks': skipped,
            'missing_intervals': unresolved, 'new_price_points': points,
            'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--end', help='UTC whole-hour end; default current whole UTC hour')
    args = parser.parse_args()
    end = timestamp(args.end) if args.end else utcnow().replace(minute=0, second=0, microsecond=0)
    db = connect(args.db)
    try:
        print(json.dumps(run(db, end, args.days)), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()
