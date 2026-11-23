"""Render local Supabase SQL and PP observer JSONL samples as a single HTML snapshot."""

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path


UNKNOWN = 'Unknown'


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Sample timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def samples(path):
    if not path.exists():
        return []
    rows = []
    with path.open() as stream:
        for line in stream:
            # A concurrent append may still be writing the last record.
            if line.strip() and line.endswith('\n'):
                row = json.loads(line)
                if row.get('at_utc'):
                    rows.append(row)
    return sorted(rows, key=lambda row: timestamp(row['at_utc']))


def label(row):
    return timestamp(row['at_utc']).strftime('%Y-%m-%d %H:%M:%S UTC')


def table(headers, rows):
    head = ''.join(f'<th>{escape(col)}</th>' for col in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(str(col))}</td>' for col in row) + '</tr>' for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def snapshot(hosted, vm, origin, roles):
    vm = [r for r in vm if r.get('origin_id') == origin and r.get('writer')]
    # Use the PP samples inside the latest hosted interval when available.
    vm_pair = vm[-2:]
    scoped = [r for r in hosted if r['role'] in roles]
    if scoped:
        last_role = scoped[-1]['role']
        pair = [r for r in scoped if r['role'] == last_role][-2:]
        if len(pair) == 2:
            start, end = (timestamp(r['at_utc']) for r in pair)
            aligned = [r for r in vm if start <= timestamp(r['at_utc']) <= end]
            if len(aligned) >= 2:
                vm_pair = [aligned[0], aligned[-1]]
    current = vm_pair[-1] if vm_pair else None
    previous = vm_pair[0] if len(vm_pair) == 2 else None
    db_rows, archive_rows = [], []
    for role in roles:
        readings = [r for r in hosted if r['role'] == role]
        if not readings:
            db_rows.append((role,) + (UNKNOWN,) * 6)
            continue
        last = readings[-1]
        delta_calls = delta_ms = window = overlap = UNKNOWN
        if len(readings) > 1:
            first = readings[-2]
            start, end = timestamp(first['at_utc']), timestamp(last['at_utc'])
            window = f'{label(first)} → {label(last)}'
            if previous and current:
                overlap = f'{max(0.0, (min(end, timestamp(current["at_utc"])) - max(start, timestamp(previous["at_utc"]))).total_seconds()):.1f} s'
            if (end > start and last.get('stats_reset') and last['stats_reset'] == first.get('stats_reset')
                    and all(r.get(k) is not None for r in (first, last) for k in ('calls', 'execution_ms'))):
                calls = int(last['calls']) - int(first['calls'])
                ms = float(last['execution_ms']) - float(first['execution_ms'])
                if calls >= 0 and ms >= 0:
                    delta_calls, delta_ms = calls, f'{ms:.2f} ms'
        db_rows.append((role, window if window != UNKNOWN else label(last), delta_calls, delta_ms, last.get('execution_ms', UNKNOWN),
                        last.get('connections') if last.get('connections') is not None else UNKNOWN, overlap))
    if current:
        older = {g['generation_id']: g for g in previous['generations']} if previous else {}
        for g in current['generations']:
            pending, total = g.get('pending'), g.get('acknowledged')
            age = rate = UNKNOWN
            if pending == 0:
                age = 'Queue empty'
            elif pending and g.get('oldest_pending_at'):
                seconds = (timestamp(current['at_utc']) - timestamp(g['oldest_pending_at'])).total_seconds()
                if seconds >= 0:
                    age = f'{seconds:.1f} s'
            before = older.get(g['generation_id'], {}).get('acknowledged')
            if before is not None and total is not None and total >= before:
                seconds = (timestamp(current['at_utc']) - timestamp(previous['at_utc'])).total_seconds()
                if seconds > 0:
                    rate = f'{(total-before)/seconds:.2f}/s'
            archive_rows.append((g.get('slot'), g['generation_id'], pending, age, total, rate))
    vm_window = 'Waiting for PP observer samples'
    if current:
        vm_window = (label(previous) + ' → ' if previous else '') + label(current)
    return '\n'.join([
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>PP archive observations</title>',
        '<style>body{font:16px system-ui;margin:3vw;color:#183030}table{border-collapse:collapse}th,td{border:1px solid #bbc9c6;padding:.65em;text-align:left}th{background:#e8f2ef}</style>',
        '<h1>PP archive observations</h1>', f'<p>{escape(origin)} · Generated {label({"at_utc": datetime.now(timezone.utc).isoformat()})}</p>',
        '<h2>Hosted PostgreSQL</h2><p>SQL counters cover all tracked statements for the indicated role. Connections cover all database clients, including the observer. Overlap shows the shared duration of the SQL and PP sample windows.</p>',
        table(['Role', 'Sample window', 'Statement calls Δ', 'Server execution Δ', 'Cumulative SQL ms', 'Connections', 'Overlap'], db_rows),
        f'<h2>Archive outbox</h2><p>{escape(vm_window)}</p>',
        table(['Slot', 'Generation', 'Pending rows', 'Oldest pending age', 'Acknowledged rows', 'ACK rate'], archive_rows),
        '<p>SQL counters come from Supabase. Archive counters come from the PP release observer. Each rate uses observations from the same source and generation. Where available, PP observations fall inside the latest hosted sample window.</p></html>',
    ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hosted', required=True, type=Path)
    parser.add_argument('--vm', required=True, type=Path)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--role', required=True, action='append')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(snapshot(samples(args.hosted), samples(args.vm), args.origin, args.role))
