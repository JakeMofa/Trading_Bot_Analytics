"""Pure current-state health checks; receipt time never substitutes for source time."""
from datetime import datetime, timezone
from collector import timestamp


def degradation_reasons(snapshot, collector, now=None):
    now = now or datetime.now(timezone.utc)
    reasons = []
    def add(reason):
        if reason not in reasons:
            reasons.append(reason)
    def parsed(value, label):
        if value is None or value == '':
            add(label + '_missing')
            return None
        try:
            return timestamp(value)
        except (TypeError, ValueError, AttributeError, OverflowError):
            add(label + '_malformed')
            return None
    def fresh(value, label):
        at = parsed(value, label)
        if at is not None:
            age = (now - at).total_seconds()
            if age > 30:
                add(label + '_stale')
            elif age < -5:
                add(label + '_future')
    if collector.get('enabled') and not collector.get('running'):
        add('collector_not_running')
    if collector.get('error') is not None:
        add('collector_error')
    for item in snapshot.get('missing_data', []):
        if item not in ('trade_flow', 'btc_order_book'):
            add(item + '_missing')
    market = snapshot.get('market') or {}
    if not market.get('id') or not market.get('slug'):
        add('market_identity_missing')
    start = parsed(market.get('start'), 'market_start')
    end = parsed(market.get('end'), 'market_end')
    if end is not None and now >= end:
        add('market_expired')
    if start is not None and now < start:
        add('market_not_started')
    if start is not None and end is not None and end <= start:
        add('market_interval_invalid')
    quote = snapshot.get('polymarket') or {}
    if not quote.get('slug'):
        add('polymarket_identity_missing')
    elif quote['slug'] != market.get('slug') or (
            quote.get('market_id') is not None and str(quote['market_id']) != str(market.get('id'))):
        add('polymarket_market_mismatch')
    for source in ('coinbase', 'polymarket'):
        fresh((snapshot.get(source) or {}).get('source_time'), source + '_source_time')
        feed = snapshot.get('feeds', {}).get(source + '_stream', {})
        if feed.get('status') and feed['status'] != 'live':
            add(source + '_stream_' + feed['status'])
    feature = snapshot.get('feature_snapshot')
    if feature is None:
        add('feature_snapshot_missing')
    else:
        if str(feature.get('market_id')) != str(market.get('id')):
            add('feature_market_mismatch')
        fresh(feature.get('as_of'), 'feature_as_of')
    storage = snapshot.get('feeds', {}).get('storage_guard', {}).get('status')
    if storage in ('limit_reached', 'blocked'):
        add('storage_guard_' + storage)
    return reasons
