"""Untrained 15-minute probability baseline and market-grouped evaluation."""
import argparse
from datetime import timezone
from decimal import Decimal
import json
from math import erf, log, sqrt

from collector import connect, timestamp, utcnow
from features import initialize as initialize_features

MODEL = 'gaussian_distance_v1'
CHECKPOINTS = {'T-10m': 600, 'T-5m': 300, 'T-1m': 60}
CHECKPOINT_TOLERANCE = 30


def initialize(db):
    initialize_features(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS predictions (
      id INTEGER PRIMARY KEY,
      snapshot_id INTEGER NOT NULL REFERENCES feature_snapshots(id),
      market_id TEXT NOT NULL REFERENCES markets(id),
      model_version TEXT NOT NULL, as_of TEXT NOT NULL,
      created_at TEXT NOT NULL, seconds_remaining REAL NOT NULL,
      probability_up TEXT, probability_down TEXT,
      abstain_reason TEXT, assumptions_json TEXT NOT NULL,
      UNIQUE(snapshot_id,model_version));
    CREATE INDEX IF NOT EXISTS predictions_market_time
      ON predictions(market_id,as_of);
    ''')


def baseline(values, quality):
    """Zero-drift log-price proxy; returns (UP probability, abstain reason)."""
    if quality['price']['status'] != 'fresh':
        return None, 'reference_price_not_fresh'
    if quality['candle_status'] not in ('fresh', 'lagging'):
        return None, 'completed_candles_missing_or_stale'
    required = ('target_usd', 'reference_price_usd', 'realized_volatility_15m', 'seconds_remaining')
    if any(values.get(name) is None for name in required):
        return None, 'required_feature_missing'
    target = Decimal(values['target_usd'])
    price = Decimal(values['reference_price_usd'])
    sigma = Decimal(values['realized_volatility_15m'])
    seconds = Decimal(str(values['seconds_remaining']))
    if target <= 0 or price <= 0 or sigma <= 0 or seconds <= 0:
        return None, 'invalid_or_zero_model_input'
    sigma_float = float(sigma)
    if sigma_float == 0:
        return None, 'volatility_below_float_precision'
    z = log(float(price / target)) / (sigma_float * sqrt(float(seconds / 60)))
    p = (1 + erf(z / sqrt(2))) / 2
    # Avoid impossible certainty from floating-point saturation.
    return min(1 - 1e-6, max(1e-6, p)), None


def forecast_snapshot(db, snapshot_id, now=None):
    """Persist a live forecast or abstention; never retroactively issue one."""
    initialize(db)
    now = now or utcnow()
    if now.tzinfo is None:
        raise ValueError('now needs timezone')
    now = now.astimezone(timezone.utc)
    row = db.execute('''SELECT s.market_id,s.as_of,s.values_json,s.quality_json,m.end
      FROM feature_snapshots s JOIN markets m ON m.id=s.market_id
      WHERE s.id=? AND m.duration=900''', (snapshot_id,)).fetchone()
    if not row:
        return None
    market_id, as_of, values_json, quality_json, end = row
    as_of_dt = timestamp(as_of)
    if not as_of_dt <= now < timestamp(end) or (now-as_of_dt).total_seconds() > 60:
        return None
    existing = db.execute('''SELECT probability_up,abstain_reason FROM predictions
      WHERE snapshot_id=? AND model_version=?''', (snapshot_id, MODEL)).fetchone()
    if existing:
        return dict(probability_up=existing[0], abstain_reason=existing[1])
    values, quality = json.loads(values_json), json.loads(quality_json)
    p, reason = baseline(values, quality)
    assumptions = {'model': 'zero_drift_normal_log_return',
                   'volatility': 'population_stddev_of_15_completed_one_minute_log_returns',
                   'price_source': 'Coinbase BTC-USD reference; Polymarket settles via BRTI',
                   'status': 'untrained_uncalibrated_proxy',
                   'probability_clamp': '0.000001..0.999999'}
    with db:
        db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,
          created_at,seconds_remaining,probability_up,probability_down,
          abstain_reason,assumptions_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          (snapshot_id, market_id, MODEL, as_of, now.isoformat(),
           values['seconds_remaining'], str(p) if p is not None else None,
           str(1-p) if p is not None else None, reason, json.dumps(assumptions)))
    return dict(probability_up=str(p) if p is not None else None, abstain_reason=reason)


def _score(rows):
    if not rows:
        return None
    n = len(rows)
    brier = sum((p-y)**2 for p, y in rows)/n
    log_loss = -sum(y*log(max(1e-15,min(1-1e-15,p)))+
                    (1-y)*log(1-max(1e-15,min(1-1e-15,p))) for p, y in rows)/n
    directional = [(p,y) for p,y in rows if p != .5]
    accuracy = (sum((p > .5) == bool(y) for p,y in directional)/len(directional)
                if directional else None)
    return {'markets': n, 'brier': brier, 'log_loss': log_loss,
            'directional_decisions': len(directional), 'directional_accuracy': accuracy}


def evaluate(db):
    """Evaluate one prediction per resolved market at each fixed time checkpoint."""
    initialize(db)
    records = db.execute('''SELECT p.market_id,p.as_of,p.created_at,p.seconds_remaining,
      p.probability_up,m.end,m.result
      FROM predictions p JOIN markets m ON m.id=p.market_id
      WHERE p.model_version=? AND m.duration=900 AND m.status='MARKET_STATUS_RESOLVED'
        AND m.final IS NOT NULL AND m.result IN ('UP','DOWN')
      ORDER BY julianday(m.end),p.market_id,p.as_of''', (MODEL,)).fetchall()
    resolved_markets = len({row[0] for row in records
                            if timestamp(row[1]) < timestamp(row[5])
                            and timestamp(row[2]) < timestamp(row[5])})
    total_confirmed = db.execute('''SELECT COUNT(*) FROM markets WHERE duration=900
      AND status='MARKET_STATUS_RESOLVED' AND final IS NOT NULL
      AND result IN ('UP','DOWN')''').fetchone()[0]
    by_checkpoint = {}
    for label, seconds in CHECKPOINTS.items():
        selected = {}
        for market_id, as_of, created_at, remaining, p_text, end, result in records:
            if abs(remaining-seconds) > CHECKPOINT_TOLERANCE:
                continue
            if not timestamp(as_of) < timestamp(end) or not timestamp(created_at) < timestamp(end):
                continue
            gap = abs(remaining-seconds)
            candidate = (gap, as_of, float(p_text) if p_text is not None else None,
                         1 if result == 'UP' else 0, end)
            if market_id not in selected or candidate[:2] < selected[market_id][:2]:
                selected[market_id] = candidate
        chronological = sorted(selected.items(), key=lambda item: (timestamp(item[1][4]), item[0]))
        pairs = [(item[1][2], item[1][3]) for item in chronological if item[1][2] is not None]
        baseline_pairs = [(.5, y) for _, y in pairs]
        bins = []
        for low in (0, .2, .4, .6, .8):
            high = round(low+.2, 1)
            subset = [(p, y) for p, y in pairs if low <= p < high or low == .8 and p == 1]
            bins.append({'range': [low, high], 'markets': len(subset),
                         'mean_forecast': sum(p for p, _ in subset)/len(subset) if subset else None,
                         'observed_up_rate': sum(y for _, y in subset)/len(subset) if subset else None})
        splits = None
        if len(pairs) >= 30:
            train_end, validation_end = int(len(pairs)*.6), int(len(pairs)*.8)
            splits = {name: {'model': _score(segment), 'fifty_fifty': _score([(.5,y) for _,y in segment])}
                      for name, segment in (('earliest_60pct',pairs[:train_end]),
                                            ('next_20pct',pairs[train_end:validation_end]),
                                            ('latest_20pct',pairs[validation_end:]))}
        by_checkpoint[label] = {'attempted_markets': len(selected),
                                'abstained_markets': len(selected)-len(pairs),
                                'eligible_markets': len(pairs), 'model': _score(pairs),
                                'fifty_fifty': _score(baseline_pairs),
                                'calibration': bins, 'chronological_splits': splits,
                                'split_status': 'available' if splits else 'need_30_distinct_markets'}
    return {'model_version': MODEL, 'duration_seconds': 900,
            'total_confirmed_markets': total_confirmed,
            'confirmed_markets_with_predictions': resolved_markets,
            'checkpoint_tolerance_seconds': CHECKPOINT_TOLERANCE,
            'checkpoints': by_checkpoint,
            'status': 'preliminary' if any(x['eligible_markets'] for x in by_checkpoint.values())
                      else 'no_confirmed_checkpoint_forecasts'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--report', action='store_true', help='Print evaluation JSON from confirmed outcomes')
    args = parser.parse_args()
    db = connect(args.db)
    try:
        if args.report:
            print(json.dumps(evaluate(db), indent=2))
        else:
            parser.error('Use --report to inspect evaluation')
    finally:
        db.close()


if __name__ == '__main__':
    main()
