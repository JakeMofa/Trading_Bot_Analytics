"""Publish aggregate Grafana Cloud metrics from local PP observer JSONL files."""

import argparse
import base64
from datetime import timedelta
from http.client import HTTPSConnection
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

from render_archive_observation import samples, timestamp


def point(measurement, labels, fields, observed):
    tags = ','.join(f'{key}={value}' for key, value in labels.items())
    values = ','.join(f'{key}={value}' for key, value in fields.items())
    nanos = int(observed.timestamp()) * 1_000_000_000 + observed.microsecond * 1000
    return f'{measurement},{tags} {values} {nanos}'


def archive_points(row, origin):
    observed = timestamp(row['at_utc'])
    if row.get('origin_id') != origin or not row.get('writer'):
        return
    for gen in row['generations']:
        if gen['slot'] not in ('A', 'B'):
            raise ValueError('Unsupported archive slot')
        labels = dict(origin=origin, slot=gen['slot'], generation=str(UUID(gen['generation_id'])))
        fields = {k: int(gen[src]) for k, src in [('acknowledged_rows_total', 'acknowledged'),
                  ('pending_rows', 'pending')] if gen.get(src) is not None}
        if fields.get('pending_rows') == 0:
            fields['oldest_pending_age_seconds'] = 0
        elif gen.get('oldest_pending_at'):
            age = (observed - timestamp(gen['oldest_pending_at'])).total_seconds()
            if age >= 0:
                fields['oldest_pending_age_seconds'] = round(age, 6)
        if fields:
            yield point('pp_archive', labels, fields, observed)


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
    lines = [p for r in selected(args.vm) for p in archive_points(r, args.origin)]
    lines.extend(hosted_points(selected(args.hosted), args.origin, args.role))
    if args.send and lines:
        token = args.token_file.read_text().strip()
        if not token:
            parser.error('The local token file is empty')
        for offset in range(0, len(lines), 500):
            send(args.endpoint, args.tenant, token, lines[offset:offset+500])
    print(json.dumps({'points': len(lines), 'sent': len(lines) if args.send else 0,
                      'since': start.isoformat(), 'through': end.isoformat()}))


if __name__ == '__main__':
    main()
