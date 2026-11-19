"""Offline dashboard evidence audit; never opens a network or database connection.

Input: JSONL records {at, source_sha, endpoint, latency_ms, state} captured from
/state/current or /events. Optional --generations is live-generations.jsonl.
Abstentions are valid honest output, but never count as numerical predictions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

MAX_INPUT = 64 * 1024 * 1024


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (ValueError, AttributeError, TypeError):
        return None


def age(at, value):
    value = instant(value)
    return round((at-value).total_seconds(), 6) if at and value else None


def probability(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        value = Decimal(str(value))
        return value.is_finite() and 0 <= value <= 1
    except InvalidOperation:
        return False


def pick(value, keys):
    return {key: value[key] for key in keys if key in value} if isinstance(value, dict) else None


def state_metadata(state):
    """Allowlist only: preserve decimal strings and absence, never headers/secrets."""
    result = pick(state, ('environment', 'data_mode', 'origin_id', 'generated_at',
                          'updated_at', 'revision', 'storage_status', 'missing_data')) or {}
    for name, keys in {
        'market': ('id', 'start', 'end', 'active'),
        'coinbase': ('event_id', 'generation_id', 'source_time', 'received_at', 'status'),
        'polymarket': ('event_id', 'market_id', 'source_time', 'received_at', 'status'),
        'forecast': ('prediction_id', 'snapshot_id', 'market_id', 'model_version',
                     'as_of', 'created_at', 'probability_up', 'probability_down', 'abstain_reason'),
        'live_estimate': ('market_id', 'model_version', 'as_of', 'snapshot_as_of',
                          'probability_up', 'probability_down', 'abstain_reason', 'source'),
    }.items():
        result[name] = pick(state.get(name), keys)
    result['collector'] = pick(state.get('collector'), ('enabled',))
    feature = state.get('feature_snapshot')
    result['feature_snapshot'] = pick(feature, ('snapshot_id', 'market_id', 'as_of'))
    if isinstance(feature, dict):
        quality = feature.get('quality') or {}
        result['feature_snapshot']['quality'] = pick(quality, ('candle_status', 'candle_age_seconds', 'missing_features')) or {}
        result['feature_snapshot']['quality']['price'] = pick(quality.get('price'), ('status', 'source_time', 'received_at', 'age_seconds'))
    result['feeds'] = {name: pick(feed, ('status', 'last_data_at', 'age_seconds',
                                        'freshness_basis', 'market_match'))
                       for name, feed in (state.get('feeds') or {}).items()}
    return result


def capture(endpoint, payload, *, at, latency_ms, source_sha, monotonic_seconds):
    result = dict(at=at, endpoint=endpoint, latency_ms=latency_ms,
                  source_sha=source_sha, monotonic_seconds=monotonic_seconds)
    if endpoint in ('/state/current', '/events'):
        result['state'] = state_metadata(payload)
    elif endpoint.startswith('/history/predictions'):
        result['history'] = [pick(item, ('id', 'prediction_id', 'snapshot_id', 'market_id',
                                         'as_of', 'created_at', 'probability_up', 'abstain_reason'))
                             for item in payload.get('items', [])[:5]]
    else:
        return None
    return result


def classify(state, at, name):
    output = state.get(name)
    result = {'classification': 'unavailable', 'issues': [], 'prediction_id': None}
    if not isinstance(output, dict):
        return result
    market, feature = state.get('market') or {}, state.get('feature_snapshot') or {}
    quality = feature.get('quality') or {}
    price = quality.get('price') or {}
    result.update(prediction_id=output.get('prediction_id'), market_id=output.get('market_id'),
                  as_of=output.get('as_of'), probability_up=output.get('probability_up'),
                  abstain_reason=output.get('abstain_reason'),
                  forecast_age_seconds=age(at, output.get('as_of')),
                  feature_age_seconds=age(at, feature.get('as_of')),
                  input_price_age_seconds=age(at, (state.get('coinbase') or {}).get('source_time')
                                                if name == 'live_estimate' else price.get('source_time')))
    reasons = result['issues']
    start, end = instant(market.get('start')), instant(market.get('end'))
    if not (at and start and end and start <= at < end and market.get('active') is True):
        reasons.append('market_not_active_at_observation')
    if not market.get('id') or output.get('market_id') != market.get('id'):
        reasons.append('prior_or_unbound_market')
    if feature.get('market_id') != market.get('id'):
        reasons.append('feature_market_mismatch')
    if not (result['forecast_age_seconds'] is not None and 0 <= result['forecast_age_seconds'] <= 30):
        reasons.append('forecast_stale_or_time_missing')
    if not (result['feature_age_seconds'] is not None and 0 <= result['feature_age_seconds'] <= 30):
        reasons.append('feature_stale_or_time_missing')
    if name == 'forecast' and output.get('as_of') != feature.get('as_of'):
        reasons.append('saved_snapshot_time_mismatch')
    if name == 'forecast' and (not output.get('prediction_id') or
                              not output.get('snapshot_id') or
                              output.get('snapshot_id') != feature.get('snapshot_id')):
        reasons.append('saved_prediction_snapshot_binding_missing')
    if name == 'live_estimate':
        if output.get('snapshot_as_of') != feature.get('as_of'):
            reasons.append('live_snapshot_time_mismatch')
        if output.get('as_of') != (state.get('coinbase') or {}).get('source_time'):
            reasons.append('live_tick_time_mismatch')
    p, reason = output.get('probability_up'), output.get('abstain_reason')
    if p is None and output.get('probability_down') is not None:
        reasons.append('down_probability_without_up_probability')
    if p is None:
        result['classification'] = 'truthful_abstain' if isinstance(reason, str) and reason.strip() else 'unavailable'
        if not reason:
            reasons.append('missing_probability_and_abstain_reason')
    elif (not probability(p) or not probability(output.get('probability_down')) or reason
          or abs(Decimal(str(p)) + Decimal(str(output.get('probability_down'))) - 1) > Decimal('0.000000000001')):
        result['classification'] = 'invalid'
        reasons.append('invalid_probability_or_conflicting_abstain')
    else:
        result['classification'] = 'active_numeric'
        source = instant(price.get('source_time'))
        asof = instant(feature.get('as_of'))
        if name == 'forecast':
            if not (source and asof and 0 <= (asof-source).total_seconds() <= 30
                    and price.get('status') == 'fresh'):
                reasons.append('saved_input_price_stale_or_missing')
            if quality.get('candle_status') not in ('fresh', 'lagging'):
                reasons.append('saved_candles_stale_or_missing')
        else:
            input_age = result['input_price_age_seconds']
            if input_age is None or not 0 <= input_age <= 10:
                reasons.append('live_tick_outside_dashboard_ten_second_limit')
            candle_age = quality.get('candle_age_seconds')
            if not isinstance(candle_age, (float, int, Decimal)) or isinstance(candle_age, bool) or not 0 <= float(candle_age) + (result['feature_age_seconds'] or 0) < 120:
                reasons.append('live_candles_stale_or_missing')
    if reasons and result['classification'] in ('active_numeric', 'truthful_abstain'):
        result['classification'] = 'stale_or_unbound'
    return result


def summarize(records, generations=()):
    samples, missing, failures = [], [], []
    for record in records:
        if record.get('endpoint') not in ('/state/current', '/events'):
            continue
        state, observed_at = record.get('state'), instant(record.get('at'))
        if not isinstance(state, dict) or not observed_at:
            missing.append('state_or_observation_time_missing')
            continue
        issues = []
        if (state.get('environment'), state.get('data_mode'), state.get('origin_id')) != ('preprod', 'pp_live', 'pp-live-pp'):
            issues.append('wrong_environment_mode_or_origin')
        at = instant(state.get('generated_at'))
        delta = age(observed_at, state.get('generated_at'))
        if at is None:
            issues.append('state_generated_time_missing_or_invalid')
        elif delta < -2 or delta > 10:
            # Different hosts: this delta combines clock offset and delivery.
            # It cannot establish that the server's own forecast inputs aged.
            missing.append('cross_host_clock_or_delivery_not_qualified')
        if not record.get('source_sha'):
            missing.append('source_sha_missing')
        row = dict(at=record['at'], endpoint=record['endpoint'], source_sha=record.get('source_sha'),
                   market_id=(state.get('market') or {}).get('id'),
                   price_generation_id=(state.get('coinbase') or {}).get('generation_id'),
                   server_generated_at=state.get('generated_at'),
                   operator_minus_server_generated_seconds=delta,
                   comparison_clock='server_generated_at',
                   issues=issues, saved=classify(state, at, 'forecast'),
                   live=classify(state, at, 'live_estimate'))
        samples.append(row)
        failures.extend(issues)
        for kind in ('saved', 'live'):
            if row[kind]['classification'] in ('invalid', 'stale_or_unbound'):
                failures.append(kind+'_invalid_stale_or_unbound_output')
    samples.sort(key=lambda r: instant(r['at']))
    counts = {kind: dict(Counter(r[kind]['classification'] for r in samples)) for kind in ('saved', 'live')}
    saved_ids = {r['saved']['prediction_id'] for r in samples if r['saved']['classification'] == 'active_numeric'}
    switches = []
    observations = sorted((g for g in generations if instant((g.get('writer') or {}).get('at_utc'))),
                          key=lambda g: instant(g['writer']['at_utc']))
    for left, right in zip(observations, observations[1:]):
        before, after = left['writer'], right['writer']
        if before.get('generation_id') == after.get('generation_id'):
            continue
        low, high = instant(before['at_utc']), instant(after['at_utc'])
        prior = [r for r in samples if instant(r.get('server_generated_at')) and instant(r['server_generated_at']) <= low]
        later = [r for r in samples if instant(r.get('server_generated_at')) and instant(r['server_generated_at']) >= high]
        switches.append({'from_generation_id': before.get('generation_id'),
                         'to_generation_id': after.get('generation_id'),
                         'observed_after_utc': before['at_utc'], 'observed_by_utc': after['at_utc'],
                         'exact_switch_timestamp': None,
                         'before': prior[-1] if prior else None, 'after': later[0] if later else None,
                         'numeric_on_both_sides': bool(prior and later and all(
                             r[k]['classification'] == 'active_numeric'
                             for r in (prior[-1], later[0]) for k in ('saved', 'live')))})
    if not samples:
        missing.append('rich_state_payloads_missing_legacy_observer_ids_are_insufficient')
    if not switches:
        missing.append('generation_switch_not_demonstrated')
    elif any(not s['before'] or not s['after'] for s in switches):
        missing.append('before_after_switch_state_missing')
    market_transitions = [dict(before=left, after=right)
                          for left, right in zip(samples, samples[1:])
                          if left['market_id'] and right['market_id'] and left['market_id'] != right['market_id']]
    numeric_missing = []
    if len(saved_ids) < 3:
        numeric_missing.append('fewer_than_three_active_numeric_saved_predictions')
    if not counts['live'].get('active_numeric'):
        numeric_missing.append('active_numeric_live_estimate_not_demonstrated')
    if not switches or any(not s['numeric_on_both_sides'] for s in switches):
        numeric_missing.append('numeric_saved_and_live_output_on_both_switch_sides_not_demonstrated')
    return {'scope': 'offline_dashboard_payload_evidence_only',
            'integrity_result': 'FAIL' if failures else 'INCOMPLETE' if missing else 'PASS',
            'numeric_forecast_result': 'FAIL' if failures else 'INCOMPLETE' if missing or numeric_missing else 'PASS',
            'samples': len(samples), 'classifications': counts,
            'clock_evidence': {
                'input_age_basis': 'server_generated_at; not operator wall clock',
                'operator_minus_server_generated_seconds_min': min(
                    (r['operator_minus_server_generated_seconds'] for r in samples
                     if r['operator_minus_server_generated_seconds'] is not None), default=None),
                'operator_minus_server_generated_seconds_max': max(
                    (r['operator_minus_server_generated_seconds'] for r in samples
                     if r['operator_minus_server_generated_seconds'] is not None), default=None),
                'delta_is_not_pure_offset': True,
                'delivery_or_clock_review_band_seconds': [-2, 10],
                'synchronized_wall_clocks_proven': False},
            'distinct_active_numeric_saved_predictions': len(saved_ids),
            'failures': sorted(set(failures)), 'missing_evidence': sorted(set(missing)),
            'numeric_missing_evidence': numeric_missing, 'switches': switches,
            'market_transitions': market_transitions,
            'observations': samples,
            'historical_items_observed_not_current_numeric_proof': sum(
                len(r.get('history') or []) for r in records),
            'not_proven': ['rendered browser display', 'continuous SSE coverage', 'collector/lease ownership',
                           'archive correctness or retirement authority', 'prediction quality or calibration']}


def read_jsonl(path):
    if path.stat().st_size > MAX_INPUT:
        raise ValueError('evidence input exceeds 64 MiB')
    with path.open() as stream:
        return [json.loads(line, parse_float=Decimal) for line in stream if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--generations', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(read_jsonl(args.input), read_jsonl(args.generations) if args.generations else ())
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, default=str, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('integrity_result', 'numeric_forecast_result', 'classifications')}))
    return 0 if result['numeric_forecast_result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
