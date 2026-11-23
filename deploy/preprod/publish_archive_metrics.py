"""Publish aggregate Grafana Cloud metrics from local PP observer JSONL files."""

import argparse
import base64
from datetime import timedelta
from http.client import HTTPSConnection
import json
from pathlib import Path
import re
import os
import stat
from urllib.parse import urlsplit
from uuid import UUID

from render_archive_observation import samples, timestamp


def point(measurement, labels, fields, observed):
    tags = ','.join(f'{key}={value}' for key, value in labels.items())
    values = ','.join(f'{key}={value}' for key, value in fields.items())
    nanos = int(observed.timestamp()) * 1_000_000_000 + observed.microsecond * 1000
    return f'{measurement},{tags} {values} {nanos}'


def archive_points(row, origin, previous=None):
    observed = timestamp(row['at_utc'])
    if row.get('origin_id') != origin or not row.get('writer'):
        return
    older = {}
    elapsed = None
    if previous and previous.get('origin_id') == origin and previous.get('writer', {}).get('collector_enabled'):
        elapsed = (observed - timestamp(previous['at_utc'])).total_seconds()
        older = {g['generation_id']: g for g in previous['generations']}
    for gen in row['generations']:
        if gen.get('retired_at'):
            continue
        if gen['slot'] not in ('A', 'B'):
            raise ValueError('Unsupported archive slot')
        labels = dict(origin=origin, slot=gen['slot'], generation=str(UUID(gen['generation_id'])))
        fields = {k: int(gen[src]) for k, src in [('acknowledged_rows_total', 'acknowledged'),
                  ('pending_rows', 'pending')] if gen.get(src) is not None}
        prior_count = older.get(gen['generation_id'], {}).get('acknowledged')
        count = fields.get('acknowledged_rows_total')
        if (row['writer'].get('collector_enabled') and prior_count is not None and count is not None
                and count >= prior_count and elapsed and elapsed > 0):
            fields['ack_rate'] = round((count - prior_count) / elapsed, 6)
            fields['ack_interval_seconds'] = round(elapsed, 6)
        if fields.get('pending_rows') == 0:
            fields['oldest_pending_age_seconds'] = 0
        elif gen.get('oldest_pending_at'):
            age = (observed - timestamp(gen['oldest_pending_at'])).total_seconds()
            if age >= 0:
                fields['oldest_pending_age_seconds'] = round(age, 6)
        if fields:
            yield point('pp_archive', labels, fields, observed)
        writer = row['writer']
        if gen['generation_id'] == writer.get('generation_id') and isinstance(writer.get('collector_enabled'), bool):
            collector = {'enabled': int(writer['collector_enabled'])}
            quotes = gen.get('polymarket_quotes') or {}
            if quotes.get('rows') is not None:
                collector['polymarket_quotes'] = int(quotes['rows'])
            if quotes.get('newest_receipt'):
                collector['last_quote_receipt_timestamp_seconds'] = timestamp(quotes['newest_receipt']).timestamp()
            yield point('pp_collector', labels, collector, observed)


def hosted_points(rows, origin, roles):
    connection_samples = set()
    for row in rows:
        if row['role'] not in roles:
            continue
        observed = timestamp(row['at_utc'])
        if row.get('execution_ms') is not None and row.get('calls') is not None:
            yield point('pp_archive_sql', dict(origin=origin, role=row['role']), dict(
                execution_seconds_total=float(row['execution_ms']) / 1000,
                calls_total=int(row['calls'])), observed)
        if observed not in connection_samples and row.get('connections') is not None:
            yield point('pp_archive', dict(origin=origin), dict(client_connections=int(row['connections'])), observed)
            connection_samples.add(observed)


def send(endpoint, tenant, token, lines):
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.grafana.net')
            or url.username or url.password or url.port or url.query or url.fragment
            or url.path != '/api/v1/push/influx/write'):
        raise ValueError('Expected a Grafana Cloud HTTPS Influx write endpoint')
    auth = base64.b64encode(f'{tenant}:{token}'.encode()).decode()
    connection = HTTPSConnection(url.hostname, timeout=20)
    try:
        connection.request('POST', url.path, ('\n'.join(lines) + '\n').encode(),
                           {'Content-Type': 'text/plain', 'Authorization': f'Basic {auth}'})
        response = connection.getresponse()
        if response.status // 100 != 2:
            raise RuntimeError(f'Grafana ingestion returned HTTP {response.status}')
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vm', required=True, type=Path)
    parser.add_argument('--hosted', required=True, type=Path)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--role', required=True, action='append')
    parser.add_argument('--since-utc', required=True, help='Exclusive start for this export')
    parser.add_argument('--through-utc', required=True, help='Inclusive end for this export')
    parser.add_argument('--endpoint')
    parser.add_argument('--tenant')
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    if not all(re.fullmatch(r'[A-Za-z0-9_-]+', v) for v in [args.origin, *args.role]):
        parser.error('Origin and role must be tag-safe identifiers')
    start, end = timestamp(args.since_utc), timestamp(args.through_utc)
    if not timedelta(0) < end - start <= timedelta(days=1):
        parser.error('Export one positive observation interval of up to one day')
    if args.send and not (args.endpoint and args.tenant and args.tenant.isdecimal() and args.token_file):
        parser.error('Sending requires an endpoint, numeric tenant and local token file')
    def selected(path):
        return [r for r in samples(path) if start < timestamp(r['at_utc']) <= end]
    lines = []
    previous = None
    for row in samples(args.vm):
        if row.get('origin_id') == args.origin and row.get('writer'):
            if start < timestamp(row['at_utc']) <= end:
                lines.extend(archive_points(row, args.origin, previous))
            previous = row
    lines.extend(hosted_points(selected(args.hosted), args.origin, args.role))
    if args.send and lines:
        with args.token_file.open() as credential:
            info = os.fstat(credential.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                parser.error('Token file must be private to its owner')
            token = credential.read().strip()
        if not token:
            parser.error('The local token file is empty')
        for offset in range(0, len(lines), 500):
            send(args.endpoint, args.tenant, token, lines[offset:offset+500])
    print(json.dumps({'points': len(lines), 'sent': len(lines) if args.send else 0,
                      'since': start.isoformat(), 'through': end.isoformat()}))


if __name__ == '__main__':
    main()
