"""Experimental ensemble over independently stored component probabilities.

Important invariants:
- gaussian_distance_v1 remains a separate baseline prediction row.
- unavailable components are excluded and remaining weights are renormalized.
- Polymarket/news evidence is timestamp-safe for the snapshot being scored.
- ensemble_v1 remains experimental until forward evaluation proves value.
"""
import json
import os
from datetime import timezone

from collector import connect, utcnow

DEFAULT_WEIGHTS = {'baseline': 0.6, 'case': 0.2, 'news': 0.1, 'market': 0.1}
MODEL = 'ensemble_v1'
NO_EDGE_BAND = float(os.getenv('ENSEMBLE_NO_EDGE_BAND', '0.05'))


def ensure_schema(db):
    cols = [r[1] for r in db.execute('PRAGMA table_info(predictions)').fetchall()]
    with db:
        if 'ensemble_up_prob' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN ensemble_up_prob TEXT')
        if 'ensemble_down_prob' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN ensemble_down_prob TEXT')
        if 'component_scores' not in cols:
            db.execute('ALTER TABLE predictions ADD COLUMN component_scores TEXT')
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
    cur_cols = [r[1] for r in db.execute('PRAGMA table_info(current_decisions)').fetchall()]
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


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _paired_probability(up, down):
    up, down = _as_float(up), _as_float(down)
    if up is None or down is None or up < 0 or down < 0 or (up + down) <= 0:
        return None
    return up / (up + down)


def implied_from_market(db, market_id, as_of=None):
    """Return timestamp-safe Polymarket UP implied probability from saved evidence."""
    params = [market_id]
    where = "market_id=? AND kind IN ('bbo','book','stream_book')"
    if as_of:
        where += ' AND julianday(received_at)<=julianday(?)'
        params.append(as_of)
    row = db.execute(
        f'''SELECT payload FROM observations WHERE {where}
            ORDER BY julianday(received_at) DESC,id DESC LIMIT 1''',
        tuple(params)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[0])
        data = payload.get('marketData') or payload.get('market_data') or payload

        probability = _paired_probability(
            (data.get('longQuote') or {}).get('value') if isinstance(data.get('longQuote'), dict)
            else data.get('longQuote'),
            (data.get('shortQuote') or {}).get('value') if isinstance(data.get('shortQuote'), dict)
            else data.get('shortQuote'))
        if probability is not None:
            return probability

        sample = (data.get('stats') or {}).get('lastPriceSample') or {}
        probability = _paired_probability(
            (sample.get('longPx') or {}).get('value') if isinstance(sample.get('longPx'), dict)
            else sample.get('longPx'),
            (sample.get('shortPx') or {}).get('value') if isinstance(sample.get('shortPx'), dict)
            else sample.get('shortPx'))
        return probability
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def case_probability_from_matches(db, snapshot_id, limit=5):
    from cases import match_cases
    result = match_cases(db, snapshot_id, limit)
    if not result or result.get('eligible_markets', 0) == 0:
        return None
    matches = result.get('matches', [])
    if not matches:
        return None
    ups = sum(1 for m in matches if m.get('outcome') == 'UP')
    return ups / len(matches)


def news_probability(db, snapshot_as_of, window_seconds=3600):
    """Simple experimental headline heuristic using only news knowable at snapshot_as_of."""
    rows = db.execute('''SELECT published_at,first_seen,title
      FROM news_events
      WHERE asset_tag='BTC'
        AND julianday(first_seen)<=julianday(?)
        AND julianday(first_seen)>=julianday(?) - (?/86400.0)
        AND (published_at IS NULL OR julianday(published_at)<=julianday(?))
      ORDER BY julianday(first_seen) DESC,id DESC''',
      (snapshot_as_of, snapshot_as_of, window_seconds, snapshot_as_of)).fetchall()
    if not rows:
        return None
    bull = ('pump', 'bull', 'rally', 'soars', 'surge', 'higher')
    bear = ('sell', 'bear', 'drop', 'falls', 'plunge', 'lower')
    score = 0
    for _published, _seen, title in rows:
        text = (title or '').lower()
        if any(word in text for word in bull):
            score += 1
        if any(word in text for word in bear):
            score -= 1
    probability = 0.5 + 0.05 * score
    return max(0.01, min(0.99, probability))


def research_signal(probability):
    if probability is None:
        return None
    if abs(probability - 0.5) <= NO_EDGE_BAND:
        return 'NO_EDGE'
    return 'BUY_UP' if probability > 0.5 else 'BUY_DOWN'


def compute_ensemble_for_snapshot(db, snapshot_id, weights=None):
    """Compute and persist experimental ensemble_v1 without modifying the baseline row."""
    from forecasts import MODEL as BASELINE_MODEL, forecast_snapshot

    weights = weights or DEFAULT_WEIGHTS
    ensure_schema(db)

    snapshot = db.execute('''SELECT market_id,as_of,values_json
      FROM feature_snapshots WHERE id=?''', (snapshot_id,)).fetchone()
    if not snapshot:
        return None
    market_id, as_of, values_json = snapshot
    values = json.loads(values_json or '{}')

    baseline_row = db.execute('''SELECT probability_up FROM predictions
      WHERE snapshot_id=? AND model_version=? LIMIT 1''',
      (snapshot_id, BASELINE_MODEL)).fetchone()
    if not baseline_row:
        forecast_snapshot(db, snapshot_id)
        baseline_row = db.execute('''SELECT probability_up FROM predictions
          WHERE snapshot_id=? AND model_version=? LIMIT 1''',
          (snapshot_id, BASELINE_MODEL)).fetchone()
    baseline_p = _as_float(baseline_row[0]) if baseline_row else None

    try:
        case_p = case_probability_from_matches(db, snapshot_id)
    except Exception:
        case_p = None
    try:
        news_p = news_probability(db, as_of)
    except Exception:
        news_p = None
    try:
        market_p = implied_from_market(db, market_id, as_of)
    except Exception:
        market_p = None

    available = {
        'baseline': baseline_p,
        'case': case_p,
        'news': news_p,
        'market': market_p,
    }
    component_scores = {}
    weighted = 0.0
    total_weight = 0.0
    for name, weight in weights.items():
        value = available.get(name)
        if value is None or weight is None or float(weight) <= 0:
            continue
        weight = float(weight)
        component_scores[name] = value
        weighted += weight * value
        total_weight += weight

    if total_weight <= 0:
        return None
    ensemble = weighted / total_weight

    try:
        from analysis import label_and_confidence
        from decision import decide_action
        component_confidences = {name: 1.0 for name in component_scores}
        label, label_conf = label_and_confidence(
            component_scores, ensemble, component_confidences)
        decision_action, decision_conf, decision_summary, decision_hold_dir = decide_action(
            db, market_id, component_scores, ensemble, component_confidences)
    except Exception:
        label = label_conf = decision_action = decision_conf = None
        decision_summary = decision_hold_dir = None

    suggested_action = research_signal(ensemble)
    suggested_confidence = round(abs(ensemble - 0.5) * 2, 3)
    seconds_remaining = float(values.get('seconds_remaining') or 0)
    now = utcnow().astimezone(timezone.utc).isoformat()
    assumptions = {
        'status': 'experimental_unvalidated_ensemble',
        'weights': weights,
        'weighting': 'renormalize_over_available_components',
        'components_present': sorted(component_scores),
        'baseline_model': BASELINE_MODEL,
    }

    with db:
        db.execute('''INSERT INTO predictions(
          snapshot_id,market_id,model_version,as_of,created_at,seconds_remaining,
          probability_up,probability_down,abstain_reason,assumptions_json,
          ensemble_up_prob,ensemble_down_prob,component_scores,
          decision_action,decision_confidence,decision_summary,decision_label,
          decision_hold_direction,suggested_action,suggested_confidence)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(snapshot_id,model_version) DO UPDATE SET
            created_at=excluded.created_at,
            seconds_remaining=excluded.seconds_remaining,
            probability_up=excluded.probability_up,
            probability_down=excluded.probability_down,
            abstain_reason=excluded.abstain_reason,
            assumptions_json=excluded.assumptions_json,
            ensemble_up_prob=excluded.ensemble_up_prob,
            ensemble_down_prob=excluded.ensemble_down_prob,
            component_scores=excluded.component_scores,
            decision_action=excluded.decision_action,
            decision_confidence=excluded.decision_confidence,
            decision_summary=excluded.decision_summary,
            decision_label=excluded.decision_label,
            decision_hold_direction=excluded.decision_hold_direction,
            suggested_action=excluded.suggested_action,
            suggested_confidence=excluded.suggested_confidence''',
          (snapshot_id, market_id, MODEL, as_of, now, seconds_remaining,
           str(ensemble), str(1 - ensemble), None, json.dumps(assumptions),
           str(ensemble), str(1 - ensemble), json.dumps(component_scores),
           decision_action, decision_conf, decision_summary, label,
           decision_hold_dir, suggested_action, suggested_confidence))

        db.execute('''INSERT INTO current_decisions(
          market_id,snapshot_id,decision_action,decision_summary,decision_label,
          decision_hold_direction,decision_confidence,ensemble_up_prob,component_scores,
          suggested_action,suggested_confidence,forecast_15m_action,
          forecast_15m_confidence,forecast_15m_probability,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(market_id) DO UPDATE SET
            snapshot_id=excluded.snapshot_id,
            decision_action=excluded.decision_action,
            decision_summary=excluded.decision_summary,
            decision_label=excluded.decision_label,
            decision_hold_direction=excluded.decision_hold_direction,
            decision_confidence=excluded.decision_confidence,
            ensemble_up_prob=excluded.ensemble_up_prob,
            component_scores=excluded.component_scores,
            suggested_action=excluded.suggested_action,
            suggested_confidence=excluded.suggested_confidence,
            forecast_15m_action=excluded.forecast_15m_action,
            forecast_15m_confidence=excluded.forecast_15m_confidence,
            forecast_15m_probability=excluded.forecast_15m_probability,
            updated_at=excluded.updated_at''',
          (market_id, snapshot_id, decision_action, decision_summary, label,
           decision_hold_dir, decision_conf, str(ensemble), json.dumps(component_scores),
           suggested_action, suggested_confidence, suggested_action,
           suggested_confidence, ensemble, now))

    return {
        'model_version': MODEL,
        'status': 'experimental',
        'ensemble_up': ensemble,
        'components': component_scores,
        'label': label,
        'label_confidence': label_conf,
        'decision_action': decision_action,
        'decision_confidence': decision_conf,
        'decision_summary': decision_summary,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--snapshot-id', type=int)
    args = parser.parse_args()
    db = connect(args.db)
    try:
        if args.snapshot_id:
            print(compute_ensemble_for_snapshot(db, args.snapshot_id))
    finally:
        db.close()
