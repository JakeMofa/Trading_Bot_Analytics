"""Offline metrics from sanitized archive evidence; no credentials or network.

Run: python -m postgres.retirement_telemetry EVIDENCE [--candidate EVIDENCE]
Nested phase totals are observations, never additive elapsed time or authority.
"""
import argparse
import json
import math
from pathlib import Path

from .retirement_accounting import PHASES

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
WORKLOAD = frozenset(('local_open', 'local_finish', 'inventory', 'raw_read_decode',
    'raw_local_compare', 'structured_local_page', 'structured_readback',
    'structured_compare', 'permit_drop'))
HISTORY = frozenset(('history_connect', 'history_identity_checkpoint',
    'history_exact_revisions', 'history_latest_receipts', 'history_newer_revisions',
    'history_projections'))
COMPLETED = frozenset(('retained_archive_audit_verified', 'fresh_readback_verified'))
LATE = 'retained_archive_audit_after_operation_deadline'


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _number(value, *, count=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0 or (count and type(value) is not int):
        return None
    return value


def _boolean(value):
    return value if type(value) is bool else None


def _rank(phases, names):
    rows = [dict(phase=name, **phases[name]) for name in names
            if name in phases and phases[name]['seconds'] is not None]
    return sorted(rows, key=lambda row: (-row['seconds'], row['phase']))[:3]


def summarize(evidence):
    """Allowlist metrics only; failed-span calls are attempts, not completed work."""
    if not isinstance(evidence, dict):
        raise ValueError('archive telemetry requires an evidence object')
    accounting = _mapping(evidence.get('phase_accounting'))
    phases = {}
    for name, row in _mapping(accounting.get('phases')).items():
        if name in PHASES and isinstance(row, dict):
            phases[name] = {key: _number(row.get(key), count=key in ('calls', 'requests', 'logical_bytes'))
                           for key in ('calls', 'seconds', 'max_seconds', 'requests', 'logical_bytes')}
            calls, seconds = phases[name]['calls'], phases[name]['seconds']
            phases[name]['attempt_mean_seconds'] = (
                round(seconds / calls, 6) if calls and seconds is not None else None)
    status = evidence.get('status')
    status = status if isinstance(status, str) else None
    raw_failed = failed = accounting.get('failed_phase')
    raw_exhausted = exhausted = accounting.get('exhausted_limit')
    failed = failed if isinstance(failed, str) and failed in PHASES else None
    exhausted = exhausted if exhausted in ('seconds', 'requests', 'bytes') else None
    unavailable = accounting.get('diagnostics_unavailable') is not False
    completed = status in COMPLETED or status == LATE
    # An inconsistent report cannot become completed evidence through formatting.
    if raw_failed is not None or raw_exhausted is not None:
        completed = False
    outcome = ('completed_late' if status == LATE or evidence.get('operation_deadline_met') is False
               else 'completed') if completed else (
        'held' if status in ('HOLD', 'held') else 'unknown')
    inventory = _mapping(evidence.get('inventory'))
    reported_completed = _mapping(evidence.get('completed'))
    limits = _mapping(evidence.get('limits'))
    expected = (_number(inventory.get('raw_objects'), count=True),
                _number(inventory.get('structured_rows'), count=True))
    observed = (_number(evidence.get('objects_read'), count=True),
                _number(evidence.get('structured_count'), count=True))
    coverage = None if None in (*expected, *observed) else expected == observed
    return {
        'schema_version': 1, 'outcome': outcome, 'readback_completed': completed,
        'retirement_authorized': False,
        'original_trial_satisfied': _boolean(evidence.get('original_trial_satisfied')),
        'operation_deadline_met': _boolean(evidence.get('operation_deadline_met')),
        'reported_coverage_matches_inventory': coverage,
        'elapsed_seconds': _number(accounting.get('elapsed_seconds')),
        'outer_elapsed_seconds': _number(evidence.get('outer_elapsed_seconds')),
        'reported_remaining_seconds': _number(accounting.get('remaining_seconds')),
        'remaining_time_is_observed_only': True,
        'requests': _number(accounting.get('requests'), count=True),
        'logical_bytes': _number(accounting.get('logical_bytes'), count=True),
        'byte_semantics': 'logical_budget_charges_not_wire_bytes',
        'failed_phase': failed, 'exhausted_limit': exhausted,
        'diagnostics_unavailable': unavailable,
        'counts': {
            'expected_raw_objects': _number(inventory.get('raw_objects'), count=True),
            'expected_structured_rows': _number(inventory.get('structured_rows'), count=True),
            'inventory_structured_pages': _number(inventory.get('structured_pages_examined'), count=True),
            'reported_objects_read': _number(evidence.get('objects_read'), count=True),
            'reported_structured_rows': _number(evidence.get('structured_count'), count=True),
            'explicit_completed_raw_objects': _number(reported_completed.get('raw_objects'), count=True),
            'explicit_completed_structured_pages': _number(reported_completed.get('structured_pages'), count=True),
            'explicit_required_structured_pages': _number(reported_completed.get('structured_pages_required'), count=True),
            'raw_read_decode_attempts': phases.get('raw_read_decode', {}).get('calls'),
            'structured_readback_attempts': phases.get('structured_readback', {}).get('calls'),
        },
        'limits': {key: _number(limits.get(key), count=key in ('requests', 'logical_bytes'))
                   for key in ('seconds', 'per_page_seconds', 'requests', 'logical_bytes')},
        'first_page': {'succeeded': _boolean(evidence.get('first_page_succeeded')),
                       'rows': _number(evidence.get('first_page_rows'), count=True),
                       'seconds': _number(evidence.get('first_page_seconds')),
                       'latest_receipts_seconds': _number(evidence.get('first_page_latest_receipts_seconds'))},
        'workload_bottlenecks': _rank(phases, WORKLOAD),
        'history_bottlenecks': _rank(phases, HISTORY),
        'phases': phases, 'phase_totals_must_not_be_summed': True,
    }


def _scope(evidence):
    inventory = _mapping(evidence.get('inventory'))
    values = (evidence.get('sealed'), evidence.get('manifest_digest'),
              _number(inventory.get('raw_objects'), count=True),
              _number(inventory.get('structured_rows'), count=True))
    if any(not isinstance(value, str) or not value for value in values[:2]):
        return None
    return None if any(value is None for value in values[2:]) else values


def _delta(before, after):
    return None if before is None or after is None else round(after - before, 6)


def compare(baseline, candidate):
    """Permit performance percentages only for completed, bound, equal scopes."""
    before, after = summarize(baseline), summarize(candidate)
    a_scope, b_scope = _scope(baseline), _scope(candidate)
    scope = 'missing' if a_scope is None or b_scope is None else (
        'matched' if a_scope == b_scope else 'mismatched')
    eligible = (scope == 'matched' and before['outcome'] == after['outcome'] == 'completed'
                and not before['diagnostics_unavailable'] and not after['diagnostics_unavailable']
                and before['reported_coverage_matches_inventory'] is True
                and after['reported_coverage_matches_inventory'] is True)
    elapsed_before, elapsed_after = before['elapsed_seconds'], after['elapsed_seconds']
    reduction = None
    if eligible and elapsed_before is not None and elapsed_before > 0 and elapsed_after is not None:
        reduction = round(100 * (elapsed_before - elapsed_after) / elapsed_before, 6)
    return {'baseline': before, 'candidate': after,
        'comparison': {'scope': scope, 'performance_comparable': eligible,
            'elapsed_reduction_percent': reduction,
            'elapsed_seconds_delta': _delta(elapsed_before, elapsed_after),
            'requests_delta': _delta(before['requests'], after['requests']),
            'logical_bytes_delta': _delta(before['logical_bytes'], after['logical_bytes']),
            'phase_seconds_delta': {name: _delta(before['phases'].get(name, {}).get('seconds'),
                                               after['phases'].get(name, {}).get('seconds'))
                                    for name in sorted(before['phases'].keys() | after['phases'].keys())},
            'phase_attempt_mean_seconds_delta': {
                name: _delta(before['phases'].get(name, {}).get('attempt_mean_seconds'),
                             after['phases'].get(name, {}).get('attempt_mean_seconds'))
                for name in sorted(before['phases'].keys() | after['phases'].keys())},
            'deltas_are_observations_not_completion_or_authority': True}}


def load_evidence(path):
    with Path(path).open('rb') as source:
        payload = source.read(MAX_EVIDENCE_BYTES + 1)
    if len(payload) > MAX_EVIDENCE_BYTES:
        raise ValueError('archive telemetry evidence exceeds file bound')
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError('archive telemetry requires an evidence object')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence')
    parser.add_argument('--candidate')
    args = parser.parse_args(argv)
    try:
        baseline = load_evidence(args.evidence)
        result = compare(baseline, load_evidence(args.candidate)) if args.candidate else summarize(baseline)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        # Do not echo arbitrary file contents, paths, credentials or parser errors.
        print(json.dumps({'status': 'invalid_telemetry_evidence', 'retirement_authorized': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
