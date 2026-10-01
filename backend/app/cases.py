"""Timestamp-safe exploratory matches among previously observed live markets."""
import argparse
from decimal import Decimal, InvalidOperation
import json

from collector import connect, normalize

FEATURE_SCALES = {
    'distance_pct': Decimal('0.1'),
    'realized_volatility_15m': Decimal('0.001'),
    'return_5m': Decimal('0.005'),
    'seconds_remaining': Decimal('300'),
}


def _features(values, quality):
    if quality.get('price', {}).get('status') != 'fresh' or quality.get('candle_status') not in ('fresh', 'lagging'):
        return None
    try:
        features = {name: Decimal(str(values[name])) for name in FEATURE_SCALES}
    except (InvalidOperation, KeyError, TypeError):
        return None
    if not all(value.is_finite() for value in features.values()):
        return None
    return features


def _distance(target, case):
    return sum(abs(target[name] - case[name]) / scale
               for name, scale in FEATURE_SCALES.items())


def match_cases(db, snapshot_id, limit=5):
    """Return at most one case per older market, using only outcomes known at as_of.

    The fixed feature scales make this an exploratory retrieval score, not a
    trained probability. Retrospective markets without live snapshots are not eligible.
    """
    if not 1 <= limit <= 20:
        raise ValueError('limit must be 1..20')
    target = db.execute('''SELECT s.market_id,s.as_of,s.values_json,s.quality_json,m.duration
      FROM feature_snapshots s JOIN markets m ON m.id=s.market_id WHERE s.id=?''',
      (snapshot_id,)).fetchone()
    if not target:
        raise ValueError('Snapshot not found')
    market_id, as_of, values_json, quality_json, duration = target
    if duration != 900:
        raise ValueError('Only 15-minute snapshots are supported')
    vector = _features(json.loads(values_json), json.loads(quality_json))
    if vector is None:
        return {'snapshot_id': snapshot_id, 'as_of': as_of,
                'eligible_markets': 0, 'matches': [], 'reason': 'target_features_unavailable'}
    rows = db.execute('''SELECT s.id,s.market_id,s.as_of,s.values_json,s.quality_json,
       m.slug,m.end
      FROM feature_snapshots s JOIN markets m ON m.id=s.market_id
      WHERE m.duration=900 AND s.market_id<>? AND m.result IN ('UP','DOWN')
        AND julianday(m.end)<=julianday(?)
        AND julianday(s.as_of)<julianday(m.end)
      ORDER BY s.market_id,s.as_of''', (market_id, as_of)).fetchall()
    known = {}
    for row in rows:
        case_market = row[1]
        if case_market in known:
            continue
        observations = db.execute('''SELECT id,received_at,payload FROM observations
          WHERE market_id=? AND kind='metadata' AND julianday(received_at)<=julianday(?)
          ORDER BY julianday(received_at),id''', (case_market, as_of)).fetchall()
        for obs_id, received, payload in observations:
            observed = normalize(json.loads(payload))
            if observed and observed['result'] in ('UP', 'DOWN'):
                known[case_market] = (received, obs_id, observed['result'])
                break
    best = {}
    for row in rows:
        sid, case_market, case_asof, case_values, case_quality, slug, end = row
        if case_market not in known:
            continue
        case_vector = _features(json.loads(case_values), json.loads(case_quality))
        if case_vector is None:
            continue
        score = _distance(vector, case_vector)
        candidate = {'market_id': case_market, 'market_slug': slug,
                     'snapshot_id': sid, 'snapshot_as_of': case_asof,
                     'outcome': known[case_market][2],
                     'outcome_known_at': known[case_market][0],
                     'outcome_observation_id': known[case_market][1],
                     'distance': str(score),
                     'features': {name: str(value) for name, value in case_vector.items()}}
        if case_market not in best or score < Decimal(best[case_market]['distance']):
            best[case_market] = candidate
    matches = sorted(best.values(), key=lambda item: (Decimal(item['distance']), item['market_id']))
    return {'snapshot_id': snapshot_id, 'as_of': as_of,
            'eligible_markets': len(matches), 'matches': matches[:limit],
            'method': 'fixed_scale_L1_exploratory_v1',
            'reason': None if matches else 'no_prior_known_live_cases'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--snapshot-id', type=int)
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    db = connect(args.db)
    try:
        snapshot_id = args.snapshot_id
        if snapshot_id is None:
            row = db.execute('SELECT id FROM feature_snapshots ORDER BY id DESC LIMIT 1').fetchone()
            if row is None:
                parser.error('No feature snapshots stored')
            snapshot_id = row[0]
        print(json.dumps(match_cases(db, snapshot_id, args.limit), indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
