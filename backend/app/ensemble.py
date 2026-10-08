"""Ensemble logic: combine baseline, case, news and market implied probabilities.

This module is intentionally lightweight: it reads existing baseline predictions,
retrieves component signals if available, and writes ensemble columns into
predictions. It ensures DB schema has the new columns.
"""
import json
import sqlite3
from datetime import timezone
from collector import utcnow, connect

DEFAULT_WEIGHTS = {'baseline': 0.6, 'case': 0.2, 'news': 0.1, 'market': 0.1}
MODEL = 'ensemble_v1'


def ensure_schema(db):
    # Add columns if they don't exist
    cols = [r[1] for r in db.execute('PRAGMA table_info(predictions)').fetchall()]
    with db:
        if 'ensemble_up_prob' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN ensemble_up_prob TEXT')
        if 'ensemble_down_prob' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN ensemble_down_prob TEXT')
        if 'component_scores' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN component_scores TEXT')
        if 'model_version' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN model_version TEXT')
        if 'decision_action' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN decision_action TEXT')
        if 'decision_confidence' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN decision_confidence REAL')
        if 'decision_summary' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN decision_summary TEXT')
        if 'decision_label' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN decision_label TEXT')
        if 'decision_hold_direction' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN decision_hold_direction TEXT')
        if 'suggested_action' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN suggested_action TEXT')
        if 'suggested_confidence' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN suggested_confidence REAL')
    # Ensure a small table that stores the latest decision per market (persistent and quick lookup)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS current_decisions (
      market_id TEXT PRIMARY KEY,
      snapshot_id INTEGER,
      decision_action TEXT,
      decision_summary TEXT,
      decision_label TEXT,
      decision_confidence REAL,
      decision_hold_direction TEXT,
      suggested_action TEXT,
      suggested_confidence REAL,
      ensemble_up_prob TEXT,
      component_scores TEXT,
      updated_at TEXT,
      forecast_15m_action TEXT,
      forecast_15m_confidence REAL,
      forecast_15m_probability REAL
    );
    ''')
    # If the table existed before and lacks new columns, add them safely
    cur_cols = [r[1] for r in db.execute("PRAGMA table_info(current_decisions)").fetchall()]
    with db:
        if 'decision_hold_direction' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN decision_hold_direction TEXT')
        if 'suggested_action' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN suggested_action TEXT')
        if 'suggested_confidence' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN suggested_confidence REAL')
        if 'forecast_15m_action' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN forecast_15m_action TEXT')
        if 'forecast_15m_confidence' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN forecast_15m_confidence REAL')
        if 'forecast_15m_probability' not in cur_cols:
            db.execute('ALTER TABLE current_decisions ADD COLUMN forecast_15m_probability REAL')


def implied_from_market(db, market_id):
    # Try to find latest UP/DOWN last prices from observations table
    row = db.execute("""SELECT payload FROM observations WHERE market_id=? AND kind='latest_price' ORDER BY received_at DESC LIMIT 1""", (market_id,)).fetchone()
    if row:
        try:
            p = json.loads(row[0])
            up = float(p.get('up_last'))
            down = float(p.get('down_last'))
            if up >= 0 and down >= 0 and (up+down) > 0:
                return up/(up+down)
        except Exception:
            pass
    return None


def case_probability_from_matches(db, snapshot_id, limit=5):
    # Use existing cases.match_cases to retrieve matches and compute fraction UP
    from cases import match_cases
    result = match_cases(db, snapshot_id, limit)
    if not result or result.get('eligible_markets', 0) == 0:
        return None
    matches = result.get('matches', [])
    ups = sum(1 for m in matches if m.get('outcome') == 'UP')
    return ups/len(matches)


def news_probability(db, snapshot_as_of, window_seconds=3600):
    # Simple heuristic: look for fresh headlines within window_seconds before snapshot
    rows = db.execute("""SELECT publication_time,first_seen_time,headline FROM news
      WHERE julianday(first_seen_time) >= julianday(?) - (?/86400.0) ORDER BY first_seen_time DESC""",
                      (snapshot_as_of, window_seconds)).fetchall()
    if not rows:
        return None
    # Naive keyword scoring: +1 for bullish words, -1 for bearish words
    bull = ('pump','bull','rally','soars','surge','higher')
    bear = ('sell','bear','drop','falls','plunge','lower')
    score = 0
    for pub, seen, text in rows:
        txt = (text or '').lower()
        if any(w in txt for w in bull):
            score += 1
        if any(w in txt for w in bear):
            score -= 1
    # Map score to probability: center at 0.5, each net point shifts by 0.05
    p = 0.5 + 0.05 * score
    return max(0.01, min(0.99, p))


def compute_ensemble_for_snapshot(db, snapshot_id, weights=None):
    weights = weights or DEFAULT_WEIGHTS
    ensure_schema(db)
    # Get baseline prediction (existing or compute)
    row = db.execute('SELECT probability_up,market_id,as_of FROM predictions WHERE snapshot_id=? ORDER BY id DESC LIMIT 1', (snapshot_id,)).fetchone()
    baseline_p = None
    market_id = None
    as_of = None
    if row:
        baseline_p = float(row[0]) if row[0] is not None else None
        market_id = row[1]
        as_of = row[2]
    # If baseline missing, try to call forecast_snapshot (non-retroactive)
    if baseline_p is None:
        from forecasts import forecast_snapshot
        res = forecast_snapshot(db, snapshot_id)
        if res and res.get('probability_up'):
            baseline_p = float(res['probability_up'])
    case_p = None
    try:
        case_p = case_probability_from_matches(db, snapshot_id)
    except Exception:
        case_p = None
    news_p = None
    try:
        # snapshot's as_of is needed for news window
        if as_of:
            news_p = news_probability(db, as_of)
    except Exception:
        news_p = None
    market_p = None
    try:
        if market_id:
            market_p = implied_from_market(db, market_id)
    except Exception:
        market_p = None
    component_scores = {}
    total_weight = 0.0
    weighted = 0.0
    for name, w in weights.items():
        total_weight += w
        if name == 'baseline' and baseline_p is not None:
            weighted += w * baseline_p
            component_scores['baseline'] = baseline_p
        elif name == 'case' and case_p is not None:
            weighted += w * case_p
            component_scores['case'] = case_p
        elif name == 'news' and news_p is not None:
            weighted += w * news_p
            component_scores['news'] = news_p
        elif name == 'market' and market_p is not None:
            weighted += w * market_p
            component_scores['market'] = market_p
    if total_weight == 0:
        return None
    ensemble = weighted/total_weight
    # Save into predictions row (insert or update)
    # compute qualitative label and decision
    try:
        from analysis import label_and_confidence
        from decision import decide_action
        # component_probs for labeling: ensure all components present with defaults
        component_probs = {k: component_scores.get(k, 0.5) for k in weights.keys()}
        comp_confs = {k: 1.0 for k in component_probs}
        label, conf = label_and_confidence(component_probs, ensemble, comp_confs)
        decision_action, decision_conf, decision_summary, decision_hold_dir = decide_action(db, market_id or 'unknown', component_probs, ensemble, comp_confs)
    except Exception:
        label, conf, decision_action, decision_conf, decision_summary, decision_hold_dir = None, None, None, None, None, None

    # Add an immediate 'lean' suggested action so the UI can show an early directional signal.
    try:
        if ensemble is not None:
            if ensemble < 0.5:
                suggested_action = 'BUY_DOWN'
            else:
                suggested_action = 'BUY_UP'
            suggested_confidence = round(abs(ensemble - 0.5) * 2, 3)
        else:
            suggested_action = None
            suggested_confidence = None
    except Exception:
        suggested_action = None
        suggested_confidence = None

    with db:
        # Find existing prediction row for this snapshot and model_version
        pred = db.execute('SELECT id FROM predictions WHERE snapshot_id=? ORDER BY id DESC LIMIT 1', (snapshot_id,)).fetchone()
        if pred:
            pid = pred[0]
            db.execute('UPDATE predictions SET ensemble_up_prob=?, ensemble_down_prob=?, component_scores=?, model_version=?, decision_action=?, decision_confidence=?, decision_summary=?, decision_label=?, decision_hold_direction=?, suggested_action=?, suggested_confidence=? WHERE id=?',
                       (str(ensemble), str(1-ensemble), json.dumps(component_scores), MODEL, decision_action, str(decision_conf), decision_summary, label, decision_hold_dir, suggested_action, suggested_confidence, pid))
        else:
            # Insert a minimal prediction row for ensemble traceability
            now = utcnow().astimezone(timezone.utc).isoformat()
            db.execute('INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,created_at,seconds_remaining,probability_up,probability_down,ensemble_up_prob,ensemble_down_prob,component_scores,decision_action,decision_confidence,decision_summary,decision_label,decision_hold_direction,suggested_action,suggested_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (snapshot_id, market_id or 'unknown', MODEL, as_of or now, now, 0, None, None, str(ensemble), str(1-ensemble), json.dumps(component_scores), decision_action, str(decision_conf), decision_summary, label, decision_hold_dir, suggested_action, suggested_confidence))
        # Upsert into current_decisions so the dashboard can show the latest decision immediately and persistently
        now = utcnow().astimezone(timezone.utc).isoformat()
        # deterministic 15m quick forecast to persist
        try:
            forecast_action = 'BUY_UP' if ensemble is not None and ensemble > 0.5 else 'BUY_DOWN' if ensemble is not None else None
            forecast_conf = max(0.0, min(1.0, 2 * abs((ensemble or 0.5) - 0.5))) if ensemble is not None else None
            forecast_prob = float(ensemble) if ensemble is not None else None
        except Exception:
            forecast_action = None
            forecast_conf = None
            forecast_prob = None
        db.execute('INSERT OR REPLACE INTO current_decisions(market_id,snapshot_id,decision_action,decision_summary,decision_label,decision_hold_direction,decision_confidence,ensemble_up_prob,component_scores,suggested_action,suggested_confidence,forecast_15m_action,forecast_15m_confidence,forecast_15m_probability,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (market_id or 'unknown', snapshot_id, decision_action, decision_summary, label, decision_hold_dir, decision_conf, str(ensemble), json.dumps(component_scores), suggested_action, suggested_confidence, forecast_action, forecast_conf, forecast_prob, now))
    return {'ensemble_up': ensemble, 'components': component_scores, 'label': label, 'label_confidence': conf, 'decision_action': decision_action, 'decision_confidence': decision_conf, 'decision_summary': decision_summary}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--snapshot-id', type=int)
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    db = connect(args.db)
    try:
        if args.snapshot_id:
            print(compute_ensemble_for_snapshot(db, args.snapshot_id))
    finally:
        db.close()
