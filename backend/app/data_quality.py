"""Read-only coverage report for saved 15-minute history and BTC headlines."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from statistics import median

from collector import timestamp, utcnow


def _ranges(starts):
    ranges = []
    for at in sorted(set(starts)):
        if ranges and timestamp(at) == timestamp(ranges[-1]['last_start']) + timedelta(minutes=15):
            ranges[-1]['last_start'] = at
            ranges[-1]['intervals'] += 1
        else:
            ranges.append({'first_start': at, 'last_start': at, 'intervals': 1})
    return ranges


def report(db, as_of=None):
    """Report saved availability; no source requests or database writes."""
    cutoff = timestamp(as_of or utcnow().isoformat())
    chunks = db.execute('''SELECT result_json FROM historical_backfill_chunks
      WHERE julianday(window_end)<=julianday(?)
        AND julianday(attempted_at)<=julianday(?)''',
      (cutoff.isoformat(), cutoff.isoformat())).fetchall()
    missing = sorted({at for (raw,) in chunks
                      for at in json.loads(raw).get('missing_intervals', [])
                      if timestamp(at) < cutoff}, key=timestamp)
    earliest = db.execute('''SELECT MIN(start) FROM markets WHERE duration=900
      AND status='MARKET_STATUS_RESOLVED' AND final IS NOT NULL
      AND result IN ('UP','DOWN') AND julianday(start)<julianday(?)
      AND julianday(first_seen)<=julianday(?)''',
      (cutoff.isoformat(), cutoff.isoformat())).fetchone()[0]
    before = [at for at in missing if earliest is None or timestamp(at) < timestamp(earliest)]
    within = [at for at in missing if earliest is not None and timestamp(at) >= timestamp(earliest)]
    saved_without_result = []
    absent = []
    for at in within:
        row = db.execute('''SELECT 1 FROM markets WHERE duration=900
          AND julianday(start)=julianday(?) LIMIT 1''', (at,)).fetchone()
        (saved_without_result if row else absent).append(at)

    news_rows = db.execute('''SELECT published_at,first_seen FROM news_events
      WHERE asset_tag='BTC' AND julianday(first_seen)<=julianday(?)''',
      (cutoff.isoformat(),)).fetchall()
    delays = [(timestamp(seen)-timestamp(published)).total_seconds()
              for published,seen in news_rows if published]
    valid_delays = sorted(delay for delay in delays if delay >= 0)
    poll = db.execute('''SELECT MAX(received_at) FROM runs
      WHERE source='coindesk_rss' AND success=1
        AND julianday(received_at)<=julianday(?)''',
      (cutoff.isoformat(),)).fetchone()[0]
    return {
        'as_of': cutoff.isoformat(),
        'historical_15m': {
            'completed_chunks': len(chunks),
            'earliest_saved_resolved_start': earliest,
            'missing_before_first_saved_resolved': len(before),
            'missing_within_saved_range': len(within),
            'within_range_absent_from_saved_markets': len(absent),
            'within_range_saved_without_confirmed_result': len(saved_without_result),
            'within_range_missing_ranges': _ranges(within),
            'note': 'Saved gaps describe API/backfill coverage, not proof a contract did not exist.'},
        'btc_news': {
            'saved_headlines': len(news_rows),
            'with_publisher_time': len(delays),
            'publisher_time_after_first_seen': len(delays)-len(valid_delays),
            'first_seen_within_15m_of_publication': sum(delay <= 900 for delay in valid_delays),
            'first_seen_within_1h_of_publication': sum(delay <= 3600 for delay in valid_delays),
            'median_publication_to_first_seen_seconds': median(valid_delays) if valid_delays else None,
            'latest_successful_poll': poll,
            'poll_age_seconds': max(0,(cutoff-timestamp(poll)).total_seconds()) if poll else None,
            'note': 'One bounded CoinDesk RSS source; presence does not measure forecast value.'},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--as-of', help='UTC cutoff; default now')
    args = parser.parse_args()
    path = Path(args.db).resolve()
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        print(json.dumps(report(db, args.as_of), indent=2))


if __name__ == '__main__':
    main()
