"""Offline exact-window audit of existing HTTP and #185 ResearchWindow captures.

No network, database, retirement or collector operations. Input captures must be
kept separately; hashes bind the report to their exact JSON content. PASS means
capture parity only, never runtime qualification or model recomputation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import uuid

PHASES = ('collecting', 'sealed', 'retired')
RESEARCH = ('scope', 'inputs', 'saved_features', 'saved_forecasts',
            'official_outcome_labels', 'links', 'coverage')
PREDICTION = ('market_id', 'model_version', 'as_of', 'created_at', 'seconds_remaining',
              'probability_up', 'probability_down', 'abstain_reason')


def exact(value):
    # Decimal fields in the actual API are strings; reject float coercion.
    if isinstance(value, float):
        raise ValueError('floating JSON numbers are unsupported: retain original exact strings')
    if isinstance(value, dict):
        for item in value.values(): exact(item)
    elif isinstance(value, list):
        for item in value: exact(item)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(exact(value)).hexdigest()


def audit(bundle):
    exact(bundle)
    failures, gaps, results = [], [], []
    if not re.fullmatch('[0-9a-f]{40}', bundle.get('source_sha', '')):
        raise ValueError('full exact source SHA required')
    windows = bundle.get('windows', [])
    if len(windows) != 2:
        raise ValueError('exactly two independent generation windows required')
    seen = set()
    for window in windows:
        origin, generation = window['origin_id'], window['generation_id']
        if str(uuid.UUID(generation)) != generation or (origin, generation) in seen:
            raise ValueError('two distinct canonical generation UUIDs required')
        seen.add((origin, generation))
        phases = window['phases']
        if set(phases) != set(PHASES):
            raise ValueError('collecting, sealed and retired captures required')
        golden = None
        counts = {}
        for phase in PHASES:
            capture = phases[phase]
            research = capture['research']
            scope = research['scope']
            if (scope['origin_id'], scope['generation_id']) != (origin, generation):
                failures.append('foreign_research_scope')
            if not capture.get('research_artifact') or not capture.get('http_artifact'):
                gaps.append('original_capture_artifact_reference_missing')
            if not research.get('inputs') or not research.get('saved_features') or not research.get('saved_forecasts'):
                gaps.append('empty_predictor_evidence')
            if not research.get('official_outcome_labels'):
                gaps.append('official_outcome_labels_missing')
            semantic = {key: research[key] for key in RESEARCH}
            if golden is None: golden = semantic
            elif exact(semantic) != exact(golden): failures.append('research_payload_changed')
            ids = [row['event_id'] for row in research['inputs']]
            if len(set(ids)) != len(ids): failures.append('duplicate_input_identity')
            for row in research['inputs']:
                if (row['origin_id'], row['generation_id']) != (origin, generation):
                    failures.append('foreign_input_identity')
            http = capture['http']
            endpoint = '/history/predictions?limit=500'
            response = http.get(endpoint, {})
            body = response.get('body', {})
            if response.get('status_code') != 200 or body.get('origin_id') != origin or body.get('limit') != 500:
                failures.append('prediction_http_contract')
            rows = body.get('items', [])
            if len(rows) >= 500: gaps.append('bounded_prediction_history_may_be_truncated')
            mapped = {row['id']: row for row in rows}
            if len(mapped) != len(rows): failures.append('duplicate_http_prediction')
            selected = []
            for forecast in research['saved_forecasts']:
                item = mapped.get(forecast['prediction_id'])
                if item is None:
                    failures.append('saved_forecast_absent_from_http_history')
                elif any(item.get(key) != forecast.get(key) for key in PREDICTION):
                    failures.append('saved_forecast_http_value_changed')
                else: selected.append(item)
            for route in ('/history/coinbase-chart', '/history/context'):
                if http.get(route, {}).get('status_code') != 200:
                    failures.append('dashboard_history_http_unavailable')
            chart = http.get('/history/coinbase-chart', {}).get('body', {})
            if chart.get('truncated') is True: gaps.append('current_chart_truncated')
            counts[phase] = dict(input_count=len(ids), feature_count=len(research['saved_features']),
                forecast_count=len(selected), label_count=len(research['official_outcome_labels']),
                research_sha256=digest(semantic), capture_sha256=digest(capture),
                chart_status=chart.get('status'),
                context_status=http.get('/history/context', {}).get('body', {}).get('status'))
        results.append(dict(origin_id=origin, generation_id=generation, phases=counts))
    return dict(scope='offline_two_generation_capture_parity_only',
        result='FAIL' if failures else 'INCOMPLETE' if gaps else 'PASS',
        source_sha=bundle['source_sha'], bundle_sha256=digest(bundle), windows=results,
        failures=sorted(set(failures)), missing_evidence=sorted(set(gaps)),
        not_proven=['capture authenticity or receipt verification', 'real partition retirement or deadline',
            'whole-market coverage', 'feature or forecast recomputation',
            'historical chart availability (chart route selects current market)',
            'historical outcome API support (context route is unsupported)',
            'multi-generation window merge', 'live two-generation qualification'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 32 * 1024**2:
        raise ValueError('input exceeds 32 MiB')
    bundle = json.loads(args.input.read_text(), parse_float=lambda _: (_ for _ in ()).throw(ValueError('retain exact JSON strings')))
    result = audit(bundle)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write('\n')
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
