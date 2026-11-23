"""Report persisted quotes during a verifier attempt using saved release evidence."""
import argparse
from datetime import timedelta
import json
from pathlib import Path

from render_archive_observation import samples, timestamp


def load(path):
    return json.loads(path.read_text())


def generation(row, key):
    return next((g for g in row['generations'] if g['generation_id'] == key), {})


def physically_retired(g):
    return (g.get('state') == 'retired' and bool(g.get('retired_at'))
            and g.get('relation_exists') is False and g.get('partition_attached') is False)


def quote_count(g):
    value = g.get('polymarket_quotes', {}).get('rows')
    return value if type(value) is int and value >= 0 else None


def build(directory, origin, observed_after):
    """observed_after is a trusted UTC timestamp obtained *after* receipt delivery."""
    attempt = load(directory / 'attempt-1.json')
    inventory = load(directory / 'inventory-1.json')
    db = [r for r in samples(directory / 'live-db.jsonl') if r.get('origin_id') == origin]
    if not db:
        raise ValueError('No snapshots match the supplied PP origin')
    a, b = attempt['sealed'], attempt['collecting']
    if not any(generation(r, a).get('slot') == 'A' and generation(r, b).get('slot') == 'B' for r in db):
        raise ValueError('Observer has no snapshot matching both attempt generations')
    if (inventory.get('sealed'), inventory.get('collecting')) != (a, b):
        raise ValueError('Inventory belongs to a different attempt')
    successes = directory / 'retire-1.json'
    failures = directory / 'retire-1-failure.json'
    if successes.exists() == failures.exists():
        raise ValueError('Exactly one success or failure receipt is required')
    receipt = load(successes if successes.exists() else failures)
    success = receipt['status'] == 'retired_pp' and receipt.get('retirement_authorized') is True
    if successes.exists() and (not success or (receipt.get('sealed'), receipt.get('collecting')) != (a,b)):
        raise ValueError('Success receipt is not bound to the supplied generations')
    accounting = receipt['phase_accounting']
    elapsed = accounting['elapsed_seconds']
    # The dispatch record precedes the remote verifier. The receipt observation
    # follows it. Their intersection with the measured process duration yields
    # an interval guaranteed to fall inside that verifier, despite launch delay.
    earliest = timestamp(attempt['started_at'])
    latest = timestamp(observed_after)
    duration = timedelta(seconds=elapsed)
    if duration <= timedelta(0) or latest - earliest < duration:
        raise ValueError('Wall-clock bounds conflict with the measured verifier duration')
    inner_start, inner_end = latest - duration, earliest + duration
    observations = []
    for row in db:
        at = timestamp(row['at_utc'])
        if inner_start <= at <= inner_end:
            source = generation(row, b)
            count = quote_count(source)
            if (source.get('slot') == 'B' and source.get('partition_attached') is True and
                    row['writer'].get('generation_id') == b and count is not None):
                observations.append((row['at_utc'], count))
    delta = None
    if len(observations) >= 2 and all(r[1] >= l[1] for l,r in zip(observations, observations[1:])):
        delta = observations[-1][1] - observations[0][1]
    fresh = None
    removed = False
    for row in db:
        old = generation(row, a)
        if not physically_retired(old):
            continue
        removed = True
        key = row['writer'].get('generation_id')
        new = generation(row, key)
        if (success and key not in (a,b) and new.get('slot') == 'A'
                and new.get('partition_attached') is True and new.get('started_at')
                and timestamp(new['started_at']) >= timestamp(old['retired_at'])
                and timestamp(row['at_utc']) >= timestamp(new['started_at'])
                and (quote_count(new) or 0) > 0):
            fresh = dict(at_utc=row['at_utc'],generation_id=key,persisted_polymarket_quotes=quote_count(new))
            break
    phases = accounting['phases']
    raw = phases.get('raw_local_compare', {}).get('calls', 0)
    if accounting.get('failed_phase') == 'raw_local_compare':
        raw = max(0, raw - 1)
    completed = phases.get('structured_compare', {}).get('calls', 0)
    if accounting.get('failed_phase') == 'structured_compare':
        completed = max(0, completed-1)
    return {
        'origin_id':origin, 'sealed_a':a, 'collecting_b':b,
        'dispatch_at':attempt['started_at'], 'receipt_known_by':observed_after,
        'verifier_elapsed_seconds':elapsed, 'status':receipt['status'],
        'retirement_authorized':receipt.get('retirement_authorized'),
        'failure_reason':receipt.get('reason'),
        'raw_objects_compared':raw, 'raw_objects_required':inventory['inventory']['raw_objects'],
        'structured_pages_compared':completed,
        'structured_pages_required':inventory['inventory']['structured_pages_examined'],
        'conservative_verifier_interval_utc':([inner_start.isoformat(),inner_end.isoformat()]
                                              if inner_start <= inner_end else None),
        'b_count_observations':len(observations),
        'b_first_time_and_count':observations[0] if observations else None,
        'b_last_time_and_count':observations[-1] if observations else None,
        'b_quote_count_increase':delta, 'old_a_physical_removal_observed':removed,
        'fresh_a_after_removal':fresh,
        'interpretation':'Counts cover persisted Polymarket quotes between observer samples. Gaps in upstream delivery can occur inside this interval.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--receipt-known-by',required=True,help='Timestamp from a saved event known to follow the retirement receipt.')
    args=parser.parse_args()
    print(json.dumps(build(args.directory,args.origin,args.receipt_known_by),indent=2))
