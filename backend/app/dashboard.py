"""Local, read-only status dashboard for the 15-minute BTC pipeline."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3

from collector import timestamp
from forecasts import CHECKPOINTS, CHECKPOINT_TOLERANCE, MODEL

HTML = Path(__file__).with_name('dashboard.html')
FRESH_SECONDS = 90


def _age(now, value):
    return max(0, (now - timestamp(value)).total_seconds()) if value else None


def status(db, now=None):
    """Return only saved evidence; never fetch or alter a source feed."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now.isoformat()
    row = db.execute('''SELECT id,slug,start,end,target,status FROM markets
      WHERE duration=900 AND julianday(start)<=julianday(?)
        AND julianday(end)>julianday(?)
      ORDER BY julianday(start) DESC LIMIT 1''', (cutoff, cutoff)).fetchone()
    market = None
    snapshot = None
    forecast = None
    if row:
        market_id, slug, start, end, target, market_status = row
        market = {'id': market_id, 'slug': slug, 'start': start, 'end': end,
                  'target_usd': target, 'status': market_status,
                  'seconds_remaining': max(0, (timestamp(end)-now).total_seconds())}
        saved = db.execute('''SELECT id,as_of,values_json,quality_json
          FROM feature_snapshots WHERE market_id=?
          ORDER BY julianday(as_of) DESC,id DESC LIMIT 1''', (market_id,)).fetchone()
        if saved:
            sid, as_of, values_json, quality_json = saved
            values = json.loads(values_json)
            quality = json.loads(quality_json)
            age = _age(now, as_of)
            snapshot = {'as_of': as_of, 'age_seconds': age,
                        'current': age <= FRESH_SECONDS,
                        'reference_price_usd': values.get('reference_price_usd'),
                        'distance_usd': values.get('distance_usd'),
                        'distance_pct': values.get('distance_pct'),
                        'price_status': quality.get('price', {}).get('status'),
                        'candle_status': quality.get('candle_status'),
                        'missing_features': quality.get('missing_features', [])}
            prediction = db.execute('''SELECT probability_up,abstain_reason,created_at
              FROM predictions WHERE snapshot_id=? AND model_version=?
              ORDER BY id DESC LIMIT 1''', (sid, MODEL)).fetchone()
            if prediction:
                p, reason, created = prediction
                forecast = {'model_version': MODEL, 'probability_up': p,
                            'abstain_reason': reason, 'created_at': created,
                            'current': snapshot['current'] and
                                       timestamp(created) < timestamp(end)}
    feed_rows = db.execute('''SELECT source,status,updated_at,last_data_at,reconnects
      FROM feed_health ORDER BY source''').fetchall()
    feeds = []
    for source, state, updated, last_data, reconnects in feed_rows:
        age = _age(now, last_data or updated)
        feeds.append({'source': source, 'reported_status': state,
                      'effective_status': 'stale' if age is not None and age > FRESH_SECONDS
                                          and state not in ('disabled', 'stopped') else state,
                      'age_seconds': age, 'reconnects': reconnects})
    news_rows = db.execute('''SELECT title,url,published_at,first_seen FROM news_events
      WHERE asset_tag='BTC' ORDER BY julianday(first_seen) DESC,id DESC LIMIT 5''').fetchall()
    news = [{'title': title, 'url': url, 'published_at': published,
             'first_seen': seen} for title, url, published, seen in news_rows]
    news_latest = db.execute('SELECT MAX(first_seen) FROM news_events').fetchone()[0]
    checkpoint_counts = {}
    for label, seconds in CHECKPOINTS.items():
        n = db.execute('''SELECT COUNT(DISTINCT p.market_id)
          FROM predictions p JOIN markets m ON m.id=p.market_id
          WHERE p.model_version=? AND p.probability_up IS NOT NULL
            AND m.duration=900 AND m.status='MARKET_STATUS_RESOLVED'
            AND m.final IS NOT NULL AND m.result IN ('UP','DOWN')
            AND ABS(p.seconds_remaining-?)<=?
            AND julianday(p.as_of)<julianday(m.end)
            AND julianday(p.created_at)<julianday(m.end)''',
            (MODEL, seconds, CHECKPOINT_TOLERANCE)).fetchone()[0]
        checkpoint_counts[label] = n
    return {'generated_at': cutoff, 'read_only': True,
            'market': market, 'snapshot': snapshot, 'forecast': forecast,
            'feeds': feeds, 'news': news,
            'news_last_seen': news_latest,
            'evaluation': {'distinct_confirmed_markets_by_checkpoint': checkpoint_counts,
                           'minimum_for_chronological_splits': 30,
                           'status': 'preliminary'}}


def open_readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def handler_for(path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                data, content_type = HTML.read_bytes(), 'text/html; charset=utf-8'
            elif self.path == '/api/status':
                try:
                    with open_readonly(path) as db:
                        data = json.dumps(status(db)).encode()
                    content_type = 'application/json; charset=utf-8'
                except (OSError, sqlite3.Error, ValueError) as exc:
                    self.send_error(503, f'Dashboard data unavailable: {type(exc).__name__}')
                    return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                             "style-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--once', action='store_true', help='Print one JSON status without a server')
    args = parser.parse_args()
    if args.once:
        with open_readonly(args.db) as db:
            print(json.dumps(status(db), indent=2))
        return
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(args.db))
    print(f'Read-only dashboard: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
