"""Periodic ensemble agent: compute ensemble for the active market snapshot at a configurable cadence.

Run with:
  python run_ensemble_agent.py --db data/btc_intelligence.db --interval 5

It is intentionally simple and resilient: logs to stdout, swallows exceptions, and sleeps between cycles.
"""
import argparse
import time
from datetime import datetime, timezone

from collector import connect, timestamp
from ensemble import compute_ensemble_for_snapshot


def latest_active_snapshot_id(db):
    now = datetime.now(timezone.utc).isoformat()
    m = db.execute("""SELECT id FROM markets WHERE duration=900 AND julianday(start)<=julianday(?) AND julianday(end)>julianday(?) ORDER BY julianday(start) DESC LIMIT 1""", (now, now)).fetchone()
    if not m:
        return None, None
    market_id = m[0]
    snap = db.execute('''SELECT id FROM feature_snapshots WHERE market_id=? ORDER BY julianday(as_of) DESC,id DESC LIMIT 1''', (market_id,)).fetchone()
    if not snap:
        return None, market_id
    return snap[0], market_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--interval', type=float, default=5.0, help='Seconds between runs')
    args = parser.parse_args()
    print(f'Ensemble agent starting: db={args.db} interval={args.interval}s')
    db = connect(args.db)
    try:
        while True:
            try:
                sid, mid = latest_active_snapshot_id(db)
                if sid:
                    print(f'[{datetime.now(timezone.utc).isoformat()}] Computing ensemble for snapshot {sid} (market {mid})')
                    res = compute_ensemble_for_snapshot(db, sid)
                    print(f'  result: {res}')
                    # After computing the ensemble, optionally ask the AI advisor for a short-horizon suggestion
                    try:
                        from ai_advisor2 import ai_suggest
                        # Rate-limit AI calls per market to once every 60s: check latest saved suggestion
                        last_ai = db.execute('SELECT created_at FROM ai_suggestions WHERE market_id=? ORDER BY created_at DESC LIMIT 1', (mid,)).fetchone()
                        allow_ai = True
                        if last_ai and last_ai[0]:
                            try:
                                last_time = datetime.fromisoformat(last_ai[0])
                                delta = (datetime.now(timezone.utc) - last_time).total_seconds()
                                if delta < 60:
                                    allow_ai = False
                            except Exception:
                                allow_ai = True
                        if allow_ai:
                            # Build a compact recent-history summary from past predictions (last 72h) to include in the prompt
                            history_rows = db.execute('''SELECT as_of,ensemble_up_prob,probability_up FROM predictions WHERE market_id=? AND julianday(as_of) >= julianday('now','-3 day') ORDER BY julianday(as_of) DESC LIMIT 200''', (mid,)).fetchall()
                            history_lines = []
                            for r in history_rows:
                                try:
                                    timestamp_txt = r[0]
                                    ens = r[1]
                                    prob = r[2]
                                    history_lines.append(f"{timestamp_txt} ensemble:{ens} prob:{prob}")
                                except Exception:
                                    continue
                            history_text = '\n'.join(history_lines[:200]) if history_lines else None
                            summary_text = f"Snapshot {sid} for market {mid}. Use the feature snapshot and recent prediction history for context."
                            ai = ai_suggest(summary_text, ensemble_prob=res.get('ensemble_up') if isinstance(res, dict) else None, components=res.get('components') if isinstance(res, dict) else None, history_text=history_text)
                            if ai:
                                # ensure ai_suggestions table exists and has hold_seconds column, then insert the latest suggestion
                                db.execute('''CREATE TABLE IF NOT EXISTS ai_suggestions (id INTEGER PRIMARY KEY, snapshot_id INTEGER, market_id TEXT, ai_action TEXT, ai_confidence REAL, ai_explanation TEXT, created_at TEXT)''')
                                # add column if missing
                                cols = [r[1] for r in db.execute("PRAGMA table_info(ai_suggestions)").fetchall()]
                                if 'ai_hold_seconds' not in cols and 'hold_seconds' not in cols:
                                    try:
                                        db.execute('ALTER TABLE ai_suggestions ADD COLUMN ai_hold_seconds REAL')
                                    except Exception:
                                        pass
                                now = datetime.now(timezone.utc).isoformat()
                                hold_val = ai.get('hold_seconds') if isinstance(ai.get('hold_seconds'), (int, float)) else None
                                # fallback hold duration when AI did not provide one: scale with confidence (0..1) into 0..15min (min 30s)
                                if hold_val is None:
                                    eff_conf = None
                                    try:
                                        if ai.get('confidence') is not None:
                                            eff_conf = float(ai.get('confidence'))
                                    except Exception:
                                        eff_conf = None
                                    if eff_conf is None:
                                        try:
                                            # try ensemble value from result
                                            cand = None
                                            if isinstance(res, dict):
                                                cand = res.get('ensemble_up') or res.get('ensemble_up_prob') or res.get('probability_up')
                                            if cand is not None:
                                                eff_conf = float(cand)
                                        except Exception:
                                            eff_conf = None
                                    if eff_conf is None:
                                        eff_conf = 0.5
                                    max_hold = 15 * 60
                                    hold_val = int(max(30, min(max_hold, (1.0 - eff_conf) * max_hold)))
                                db.execute('''INSERT INTO ai_suggestions (snapshot_id, market_id, ai_action, ai_confidence, ai_explanation, ai_hold_seconds, created_at) VALUES (?,?,?,?,?,?,?)''', (sid, mid, ai.get('action'), ai.get('confidence'), ai.get('explanation'), hold_val, now))
                                db.commit()
                                print(f'  ai suggestion saved: {ai} (hold_seconds: {hold_val})')
                        else:
                            print('  skipping AI: last suggestion was less than 60s ago')
                    except Exception as exc:
                        print(f'  ai advisor error: {type(exc).__name__} {exc}')
                else:
                    print(f'[{datetime.now(timezone.utc).isoformat()}] No active snapshot (market {mid}), sleeping')
            except Exception as exc:
                print(f'[{datetime.now(timezone.utc).isoformat()}] Error in ensemble loop: {type(exc).__name__} {exc}')
            time.sleep(args.interval)
    finally:
        db.close()


if __name__ == '__main__':
    main()
