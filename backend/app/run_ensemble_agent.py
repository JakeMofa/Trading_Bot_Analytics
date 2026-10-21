"""Periodic experimental ensemble agent.

The numerical ensemble can run continuously. OpenAI analysis is separately
opt-in through ENABLE_OPENAI_ANALYST=true and is rate-limited.
"""
import argparse
import os
import time
from datetime import datetime, timezone

from collector import connect
from ensemble import compute_ensemble_for_snapshot


def latest_active_snapshot_id(db):
    now = datetime.now(timezone.utc).isoformat()
    market = db.execute('''SELECT id FROM markets
      WHERE duration=900 AND julianday(start)<=julianday(?)
        AND julianday(end)>julianday(?)
      ORDER BY julianday(start) DESC LIMIT 1''', (now, now)).fetchone()
    if not market:
        return None, None
    market_id = market[0]
    snapshot = db.execute('''SELECT id FROM feature_snapshots
      WHERE market_id=? ORDER BY julianday(as_of) DESC,id DESC LIMIT 1''',
      (market_id,)).fetchone()
    return (snapshot[0] if snapshot else None), market_id


def ensure_ai_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS ai_suggestions (
      id INTEGER PRIMARY KEY,
      snapshot_id INTEGER,
      market_id TEXT,
      ai_action TEXT,
      ai_confidence REAL,
      ai_explanation TEXT,
      ai_hold_seconds REAL,
      created_at TEXT
    )''')
    cols = {row[1] for row in db.execute('PRAGMA table_info(ai_suggestions)')}
    if 'ai_hold_seconds' not in cols:
        db.execute('ALTER TABLE ai_suggestions ADD COLUMN ai_hold_seconds REAL')
    db.commit()


def maybe_run_ai(db, snapshot_id, market_id, ensemble_result):
    from ai_advisor2 import ai_suggest, is_enabled

    if not is_enabled():
        return None

    ensure_ai_schema(db)
    min_interval = float(os.getenv('OPENAI_ANALYST_MIN_INTERVAL_SECONDS', '60'))
    last = db.execute('''SELECT created_at FROM ai_suggestions
      WHERE market_id=? ORDER BY created_at DESC LIMIT 1''', (market_id,)).fetchone()
    if last and last[0]:
        try:
            previous = datetime.fromisoformat(last[0].replace('Z', '+00:00'))
            if (datetime.now(timezone.utc) - previous).total_seconds() < min_interval:
                return None
        except ValueError:
            pass

    # Phase 0 intentionally keeps this context small. Phase 10 will replace it
    # with a structured LiveState payload and leakage-safe historical summary.
    summary = (
        f"Experimental snapshot {snapshot_id} for Polymarket market {market_id}. "
        "Treat components as research signals and explain disagreements."
    )
    result = ai_suggest(
        summary,
        ensemble_prob=(ensemble_result or {}).get('ensemble_up'),
        components=(ensemble_result or {}).get('components'),
    )
    if not result:
        return None

    now = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute('''INSERT INTO ai_suggestions(
          snapshot_id,market_id,ai_action,ai_confidence,ai_explanation,
          ai_hold_seconds,created_at) VALUES(?,?,?,?,?,?,?)''',
          (snapshot_id, market_id, result.get('action'), result.get('confidence'),
           result.get('explanation'), result.get('hold_seconds'), now))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--interval', type=float, default=5.0,
                        help='Seconds between ensemble runs')
    args = parser.parse_args()
    print(f'Ensemble agent starting: db={args.db} interval={args.interval}s')
    db = connect(args.db)
    try:
        while True:
            try:
                snapshot_id, market_id = latest_active_snapshot_id(db)
                if snapshot_id:
                    now = datetime.now(timezone.utc).isoformat()
                    print(f'[{now}] ensemble snapshot={snapshot_id} market={market_id}')
                    result = compute_ensemble_for_snapshot(db, snapshot_id)
                    print(f'  result: {result}')
                    try:
                        ai_result = maybe_run_ai(
                            db, snapshot_id, market_id, result if isinstance(result, dict) else None)
                        if ai_result:
                            print(f'  optional AI analysis saved: {ai_result}')
                    except Exception as exc:
                        # AI is non-critical; never stop numerical collection/forecasting.
                        print(f'  optional AI error: {type(exc).__name__}: {exc}')
                else:
                    print(f'[{datetime.now(timezone.utc).isoformat()}] '
                          f'No active snapshot (market {market_id})')
            except Exception as exc:
                print(f'[{datetime.now(timezone.utc).isoformat()}] '
                      f'Ensemble error: {type(exc).__name__}: {exc}')
            time.sleep(args.interval)
    finally:
        db.close()


if __name__ == '__main__':
    main()
