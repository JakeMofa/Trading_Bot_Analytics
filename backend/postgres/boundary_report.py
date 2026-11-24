"""Render four matched boundary rows from PP shadow evidence and canonical logs."""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
import sys

from .boundary_shadow import TAIL_SECONDS, boundary_epoch, utc
from .contract import source_timestamp


def epoch(value):
    return source_timestamp(value)[1]


def records(path, canonical=False):
    with open(path) as stream:
        for line in stream:
            if canonical:
                prefix, marker, line = line.partition('pp_boundary_trace ')
                if not marker:
                    continue
            if line.strip():
                yield json.loads(line)


def age_ms(later, earlier):
    if not later or not earlier:
        return None
    return round((epoch(later) - epoch(earlier)) * 1000, 3)


def first(rows, reader, stage, since=None, **fields):
    for row in rows:
        if row['reader'] != reader or row['stage'] != stage:
            continue
        if since is not None and epoch(row['ts_utc']) < since:
            continue
        if all(row.get(k) == v for k, v in fields.items()):
            return row
    return {}


def time_of(row):
    return row.get('ts_utc')


def sides(row):
    return row.get('best_bid') is not None and row.get('best_ask') is not None


def summary(start, canonical, shadow):
    for index in range(4):
        boundary = start + index * 900
        rows = sorted((r for r in [*canonical, *shadow]
                       if r.get('window_start') and epoch(r['window_start']) == boundary
                       and epoch(r['ts_utc']) < boundary + TAIL_SECONDS),
                      key=lambda r: r['mono_ns'])
        window_end = first(shadow, 'observer', 'window_end', window_start=utc(boundary))
        canonical_discovery = first(rows, 'canonical_rest', 'market_identified', boundary)
        predicted = first(rows, 'early_discovery', 'market_identified')
        market_ids = {str(r['market_id']) for r in rows if r.get('market_id')}
        slugs = {r['slug'] for r in rows if r.get('slug')}
        identity_ok = len(market_ids) == 1 and len(slugs) == 1
        in_window = [r for r in rows if epoch(r['ts_utc']) >= boundary
                     and (not r.get('received_at') or epoch(r['received_at']) >= boundary)]
        canon = first(in_window, 'canonical_rest', 'bbo_received')
        early = first(in_window, 'early_rest', 'quote')
        socket = first(in_window, 'websocket', 'quote')
        dash = first(in_window, 'dashboard_api', 'quote')
        ws_new = next((r for r in in_window if r['reader'] == 'websocket' and r['stage'] == 'quote'
                       and r.get('source_time_role') == 'order_book_transaction_time'
                       and r.get('source_time') and boundary <= epoch(r['source_time']) <= epoch(r['ts_utc'])), {})
        # The API exposes the latest stored observation and can skip the first.
        # Only associate receive/commit/visibility for the same saved quote.
        receipt = dash.get('received_at')
        matches = [r for r in in_window if receipt and dash.get('market_id') == r.get('market_id')
                   and r.get('received_at') and epoch(r['received_at']) == epoch(receipt)
                   and all(r.get(k) == dash.get(k) for k in ('best_bid', 'best_ask'))]
        matched = first(matches, 'canonical_rest', 'bbo_received')
        commits = [r for r in matches if matched.get('event_id') and r.get('event_id') == matched['event_id']]
        commit = first(commits, 'canonical_rest', 'commit_ack')
        elapsed = age_ms(time_of(dash), receipt) if identity_ok and commit else None
        counts = Counter()
        for r in rows:
            key = r['reader'] + '.' + r['stage']
            if 'status' in r and isinstance(r['status'], int) and r['status'] >= 400:
                key += '.' + str(r['status'])
            if r.get('reason'):
                key += '.' + r['reason']
            counts[key] += 1
        # Missing legs stay blank; mixed identities can never support a pass.
        comparable = bool(window_end and identity_ok and early and socket and canon)
        yield {
            'window_start': utc(boundary), 'market_ids': '|'.join(sorted(market_ids)),
            'observation_status': 'complete' if window_end else 'partial_or_absent',
            'identity_status': 'matched' if identity_ok else 'missing_or_ambiguous',
            'early_discovered_utc': time_of(predicted), 'canonical_discovered_utc': time_of(canonical_discovery),
            'early_rest_request_utc': time_of(first(rows, 'early_rest', 'request', boundary)),
            'canonical_request_utc': time_of(first(rows, 'canonical_rest', 'bbo_request', boundary)),
            'ws_subscribe_utc': time_of(first(rows, 'websocket', 'subscribe')),
            'canonical_first_utc': canon.get('received_at'), 'early_rest_first_utc': time_of(early),
            'websocket_first_utc': time_of(socket), 'ws_first_in_window_exchange_book_utc': time_of(ws_new),
            'canonical_first_two_sided_utc': time_of(first([r for r in in_window if sides(r)], 'canonical_rest', 'bbo_received')),
            'early_rest_first_two_sided_utc': time_of(first([r for r in in_window if sides(r)], 'early_rest', 'quote')),
            'ws_first_two_sided_utc': time_of(first([r for r in in_window if sides(r)], 'websocket', 'quote')),
            'first_canonical_commit_utc': time_of(first(in_window, 'canonical_rest', 'commit_ack',
                                                       event_id=canon.get('event_id'))) if canon.get('event_id') else None,
            'dashboard_first_utc': time_of(dash), 'displayed_quote_receipt_utc': receipt,
            'displayed_quote_commit_utc': time_of(commit),
            'boundary_to_canonical_receive_ms': age_ms(canon.get('received_at'), utc(boundary)),
            'canonical_minus_early_rest_ms': age_ms(canon.get('received_at'), time_of(early)) if identity_ok else None,
            'early_rest_minus_ws_ms': age_ms(time_of(early), time_of(socket)) if comparable else None,
            'displayed_receive_to_api_ms': elapsed,
            'displayed_within_5s': None if elapsed is None or elapsed < Decimal(0) else elapsed <= 5000,
            'three_reader_match': comparable,
            'event_counts': json.dumps(counts, sort_keys=True, separators=(',', ':'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-boundary-utc', required=True)
    parser.add_argument('--canonical-log', required=True, help='log capture containing pp_boundary_trace lines')
    parser.add_argument('--shadow-jsonl', required=True)
    args = parser.parse_args()
    rows = list(summary(boundary_epoch(args.first_boundary_utc), list(records(args.canonical_log, True)),
                        list(records(args.shadow_jsonl))))
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)


if __name__ == '__main__':
    main()
