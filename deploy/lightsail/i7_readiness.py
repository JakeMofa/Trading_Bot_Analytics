"""Read-only assessment of saved sanitized production evidence; never executes.

No SSH, SQLite, configuration writes or deployment operations. A positive result
only permits review, not installation. Estimates must come from separate actual
VM qualification, not a local warm-cache benchmark.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

EXPECTED_REVISION = 'd56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
GUARD_BYTES = 4096 * 1024**2
BUDGET_FIELDS = ('index_growth_bytes', 'wal_growth_bytes', 'collection_growth_bytes',
                 'temporary_disk_bytes', 'reserve_bytes')


def assess(snapshot, budget=None, now=None, bridge_policy=None):
    reasons = []
    now = now or datetime.now(timezone.utc)
    guard_bytes = GUARD_BYTES
    bridge_valid = False
    if bridge_policy is not None:
        try:
            applied=datetime.fromisoformat(bridge_policy['applied_at'])
            due=datetime.fromisoformat(bridge_policy['review_due_at'])
            bridge_valid=(bridge_policy['status']=='BRIDGE_ACTIVE'
                          and bridge_policy['revision']==EXPECTED_REVISION
                          and bridge_policy['old_guard_mib']==4096 and bridge_policy['guard_mib']==5120
                          and 0<=(now-applied).total_seconds()<(due-applied).total_seconds()<=86400)
        except (KeyError,TypeError,ValueError):pass
        if bridge_valid:guard_bytes=5120*1024**2
        else:reasons.append('INVALID_OR_OVERDUE_BRIDGE_POLICY')
    try:
        age = (now - datetime.fromisoformat(snapshot['at'])).total_seconds()
        if not 0 <= age <= 300:
            reasons.append('STALE_OR_FUTURE_EVIDENCE')
    except (KeyError, ValueError, TypeError):
        reasons.append('MISSING_EVIDENCE_TIMESTAMP')
    if snapshot.get('revision') != EXPECTED_REVISION:
        reasons.append('UNEXPECTED_REVISION')
    if snapshot.get('tracked_clean') is not True:
        reasons.append('TRACKED_CHECKOUT_NOT_CLEAN')
    if snapshot.get('original_helper_restored') is not True or snapshot.get('authorization_absent') is not True:
        reasons.append('DEPLOYMENT_CONTROLS_NOT_RESTORED')
    for name in ('tradebot-api', 'tradebot-ensemble', 'tradebot-lifecycle'):
        service = snapshot.get('services', {}).get(name, {})
        if service.get('ActiveState') != 'active' or service.get('UnitFileState') != 'enabled':
            reasons.append('SERVICE_NOT_ACTIVE_ENABLED:' + name)
        if any(service.get(k) is not True for k in ('openai_off', 'retention_off', 'paid_credentials_absent')):
            reasons.append('UNSAFE_OR_UNKNOWN_FLAGS:' + name)
    actual=snapshot.get('services', {}).get('tradebot-api', {})
    correct_guard=(actual.get('guard_mib')==5120 if bridge_valid else actual.get('guard4096') is True)
    if not correct_guard:
        reasons.append('GUARD_CHANGED_OR_UNKNOWN')
    health = snapshot.get('endpoints', {}).get('/health', {})
    if health.get('collector_running') is not True:
        reasons.append('COLLECTOR_NOT_RUNNING')
    feeds = health.get('feeds', {})
    if feeds.get('storage_guard', {}).get('status') == 'limit_reached':
        reasons.append('STORAGE_GUARD_LATCHED')
    for name in ('coinbase_stream', 'polymarket_stream'):
        feed = feeds.get(name, {})
        try:
            feed_age = (now - datetime.fromisoformat(feed['last_data_at'].replace('Z', '+00:00'))).total_seconds()
            fresh = 0 <= feed_age < 30
        except (KeyError, TypeError, ValueError, AttributeError):
            fresh = False
        if feed.get('status') != 'live' or not fresh:
            reasons.append('FEED_NOT_FRESH_LIVE:' + name)
    storage = snapshot.get('storage', {})
    valid = all(type(storage.get(k)) is int and storage[k] >= 0 for k in ('db_bytes', 'wal_bytes', 'free_bytes'))
    headroom = None
    if not valid:
        reasons.append('UNKNOWN_STORAGE')
    else:
        headroom = guard_bytes - storage['db_bytes'] - storage['wal_bytes']
        if headroom <= 0:
            reasons.append('STORAGE_GUARD_REACHED')
    qualified = (isinstance(budget, dict) and budget.get('vm_qualified') is True
                 and all(type(budget.get(k)) is int and budget[k] > 0 for k in BUDGET_FIELDS))
    if not qualified:
        reasons.append('INDEX_BUILD_BUDGET_UNQUALIFIED')
    elif valid:
        growth = sum(budget[k] for k in ('index_growth_bytes', 'wal_growth_bytes', 'collection_growth_bytes', 'reserve_bytes'))
        if headroom <= growth:
            reasons.append('INSUFFICIENT_GUARD_HEADROOM')
        if storage['free_bytes'] <= growth + budget['temporary_disk_bytes']:
            reasons.append('INSUFFICIENT_FILESYSTEM_RESERVE')
    return {'status': 'STOP' if reasons else 'READY_FOR_OPERATOR_REVIEW',
            'reasons': reasons, 'guard_bytes': guard_bytes, 'headroom_bytes': headroom,
            'execution_authorized': False, 'database_integrity': 'NOT_CHECKED',
            'next': 'Resolve STOP reasons under reviewed constraints; never bypass guard or reuse prior exception.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--budget', type=Path)
    parser.add_argument('--bridge-policy', type=Path)
    args = parser.parse_args()
    result = assess(json.loads(args.snapshot.read_text()),
                    json.loads(args.budget.read_text()) if args.budget else None,
                    bridge_policy=json.loads(args.bridge_policy.read_text()) if args.bridge_policy else None)
    print(json.dumps(result, indent=2))
    return 2 if result['status'] == 'STOP' else 0


if __name__ == '__main__':
    raise SystemExit(main())
