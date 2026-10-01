"""Retrospective, time-safe comparison of saved forecasts with prior-case evidence."""
import argparse
import json
import sqlite3
from pathlib import Path

from cases import match_cases
from collector import timestamp
from forecasts import CHECKPOINTS, CHECKPOINT_TOLERANCE, MODEL, _score

MIN_CASES = 5
CASE_LIMIT = 20


def evaluate_context(db):
    """Score a simple case proxy on exactly the markets where it was available.

    This proxy was not issued live. Case outcomes must have been observed before
    each saved forecast; future outcomes and late-seen headlines are excluded.
    """
    rows = db.execute('''SELECT p.market_id,p.snapshot_id,p.as_of,p.created_at,
        p.seconds_remaining,p.probability_up,m.end,m.result
      FROM predictions p JOIN markets m ON m.id=p.market_id
      JOIN feature_snapshots s ON s.id=p.snapshot_id
      WHERE p.model_version=? AND s.market_id=p.market_id AND s.as_of=p.as_of
        AND m.duration=900 AND m.status='MARKET_STATUS_RESOLVED'
        AND m.final IS NOT NULL AND m.result IN ('UP','DOWN')
      ORDER BY julianday(m.end),p.market_id,p.as_of''', (MODEL,)).fetchall()
    checkpoints = {}
    for label, target_seconds in CHECKPOINTS.items():
        selected = {}
        for market_id, sid, as_of, created, remaining, probability, end, result in rows:
            if abs(remaining-target_seconds) > CHECKPOINT_TOLERANCE:
                continue
            if not (timestamp(as_of) < timestamp(end) and timestamp(created) < timestamp(end)):
                continue
            candidate = (abs(remaining-target_seconds), timestamp(as_of), sid,
                         as_of, probability, end, result)
            if market_id not in selected or candidate[:2] < selected[market_id][:2]:
                selected[market_id] = candidate
        paired_case, paired_model, paired_even = [], [], []
        with_cases = with_news = 0
        case_counts = []
        for _, (_, _, sid, as_of, probability, _, result) in sorted(
                selected.items(), key=lambda item: (timestamp(item[1][5]), item[0])):
            if probability is None:
                continue
            context = match_cases(db, sid, limit=CASE_LIMIT)
            case_counts.append(context['eligible_markets'])
            if context['eligible_markets']:
                with_cases += 1
            news_count = db.execute('''SELECT COUNT(*) FROM news_events
              WHERE asset_tag='BTC' AND published_at IS NOT NULL
                AND julianday(published_at)<=julianday(?)
                AND julianday(first_seen)<=julianday(?)''', (as_of, as_of)).fetchone()[0]
            if news_count:
                with_news += 1
            matches = context['matches']
            if len(matches) < MIN_CASES:
                continue
            up = sum(match['outcome'] == 'UP' for match in matches)
            proxy = (up+1)/(len(matches)+2)  # Laplace smoothing; untrained.
            y = int(result == 'UP')
            paired_case.append((proxy, y))
            paired_model.append((float(probability), y))
            paired_even.append((.5, y))
        n = len(case_counts)
        checkpoints[label] = {
            'saved_forecasts': n,
            'markets_with_prior_known_cases': with_cases,
            'markets_with_prior_seen_btc_news': with_news,
            'case_count_min': min(case_counts) if case_counts else None,
            'case_count_max': max(case_counts) if case_counts else None,
            'paired_markets_with_at_least_5_cases': len(paired_case),
            'case_proxy': _score(paired_case),
            'saved_baseline_on_same_markets': _score(paired_model),
            'fifty_fifty_on_same_markets': _score(paired_even),
            'status': 'exploratory_30_plus_markets' if len(paired_case) >= 30
                      else 'insufficient_30_distinct_markets',
        }
    return {
        'scope': 'resolved_15_minute_markets_with_saved_live_forecasts',
        'saved_model': MODEL,
        'case_proxy': 'nearest_20_prior_known_distinct_markets_laplace_smoothed',
        'min_cases': MIN_CASES,
        'proxy_was_issued_live': False,
        'news_is_used_in_scores': False,
        'checkpoint_tolerance_seconds': CHECKPOINT_TOLERANCE,
        'checkpoints': checkpoints,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    args = parser.parse_args()
    path = Path(args.db).resolve()
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        print(json.dumps(evaluate_context(db), indent=2))


if __name__ == '__main__':
    main()
