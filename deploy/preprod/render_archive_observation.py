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


MAX_OBSERVER_INTERVAL = 60


def archive_history(vm):
    """Calculate per-generation rates from consecutive observations only."""
    points = []
    previous_at = None
    previous = {}
    for row in vm:
        at = timestamp(row['at_utc'])
        elapsed = (at - previous_at).total_seconds() if previous_at else None
        consecutive = elapsed is not None and 0 < elapsed <= MAX_OBSERVER_INTERVAL
        current = {}
        for g in row['generations']:
            key = g['generation_id']
            total = g.get('acknowledged')
            pending = g.get('pending')
            retired = g.get('retired_at') or g.get('state') == 'retired'
            detached = g.get('partition_attached') is False
            before = previous.get(key)
            rate = age = None
            status = g.get('state') or UNKNOWN
            if retired or detached:
                status = 'Retired' if retired else 'Detached'
            else:
                if not row['writer'].get('collector_enabled') and status == 'collecting':
                    status = 'Collector off'
                if consecutive and before is not None and total is not None and total >= before:
                    rate = (total - before) / elapsed
                if pending and g.get('oldest_pending_at'):
                    seconds = (at - timestamp(g['oldest_pending_at'])).total_seconds()
                    if seconds >= 0:
                        age = seconds
                current[key] = total
            points.append((at, g.get('slot'), key, rate, age, pending, status))
        previous_at, previous = at, current
    return points


def trend_plot(points, column, title, unit, target=None):
    width, height = 800, 170
    left, right, top, bottom = 52, width - 18, 18, height - 35
    start, end = points[0][0], points[-1][0]
    duration = max(1, (end - start).total_seconds())
    peak = max([1, target or 0] + [p[column] for p in points if p[column] is not None])
    def y(value):
        return bottom - (bottom - top) * value / peak
    parts = [f'<h3>{title}</h3><svg viewBox="0 0 {width} {height}" role="img" aria-label="{title} in {unit}">',
             f'<path d="M{left} {top}V{bottom}H{right}" fill="none" stroke="#a9b9b7"/>',
             f'<text x="4" y="{top+5}">{peak:.1f}</text><text x="24" y="{bottom}">0</text>',
             f'<text x="{left}" y="{height-5}">{start:%H:%M:%S} UTC</text>',
             f'<text text-anchor="end" x="{right}" y="{height-5}">{end:%H:%M:%S} UTC</text>']
    if target is not None:
        parts.append(f'<path d="M{left} {y(target):.1f}H{right}" stroke="#9d5338" stroke-dasharray="5 4"><title>Target {target} {unit}</title></path>')
    sample_order = {at: i for i, at in enumerate(dict.fromkeys(p[0] for p in points))}
    prior = {}
    for p in points:
        at, slot, key = p[:3]
        value = p[column]
        if value is None:
            prior.pop(key, None)
            continue
        x = left + (right - left) * (at - start).total_seconds() / duration
        yy = y(value)
        color = '#17665a' if slot == 'A' else '#544a99'
        tip = escape(f'{at:%Y-%m-%d %H:%M:%S} UTC · {slot} · {key} · {value:.2f} {unit}')
        prev = prior.get(key)
        if (prev and sample_order[at] == sample_order[prev[0]] + 1
                and 0 < (at - prev[0]).total_seconds() <= MAX_OBSERVER_INTERVAL):
            parts.append(f'<line x1="{prev[1]:.1f}" y1="{prev[2]:.1f}" x2="{x:.1f}" y2="{yy:.1f}" stroke="{color}"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="2" fill="{color}"><title>{tip}</title></circle>')
        prior[key] = at, x, yy
    return ''.join(parts) + '</svg>'


def trend_history(vm):
    points = archive_history(vm)
    if not points:
        return '<h2>PP history</h2><p>Waiting for generation samples.</p>'
    details = [(at.strftime('%Y-%m-%d %H:%M:%S UTC'), slot, key, status,
                UNKNOWN if rate is None else f'{rate:.2f}', pending,
                f'{age:.1f}' if age is not None else ('Queue empty' if pending == 0 else UNKNOWN))
               for at, slot, key, rate, age, pending, status in points]
    return ''.join(['<h2>PP history</h2>',
                    '<p>Green shows A and purple shows B. The dashed line marks 14 ACK/s. Rates use consecutive samples of the same generation up to 60 seconds apart. An empty queue has no oldest age. Lines stop at missing values and retirement.</p>',
                    trend_plot(points, 3, 'ACKs per second', 'rows/s', 14),
                    trend_plot(points, 4, 'Oldest pending age', 'seconds'),
                    '<details><summary>Timestamped observations by generation</summary>',
                    table(['Time','Slot','Generation','State','ACK/s','Pending','Oldest age (s)'], details),
                    '</details>'])


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
        '<style>body{font:16px system-ui;margin:3vw;color:#183030}table{border-collapse:collapse}th,td{border:1px solid #bbc9c6;padding:.65em;text-align:left}th{background:#e8f2ef}svg{display:block;width:100%;max-width:960px}svg text{font:12px system-ui;fill:#324747}details{margin:1em 0}</style>',
        '<h1>PP archive observations</h1>', f'<p>{escape(origin)} · Generated {label({"at_utc": datetime.now(timezone.utc).isoformat()})}</p>',
        '<h2>Hosted PostgreSQL</h2><p>SQL counters cover all tracked statements for the indicated role. Connections cover all database clients, including the observer. Overlap shows the shared duration of the SQL and PP sample windows.</p>',
        table(['Role', 'Sample window', 'Statement calls Δ', 'Server execution Δ', 'Cumulative SQL ms', 'Connections', 'Overlap'], db_rows),
        f'<h2>Archive outbox</h2><p>{escape(vm_window)}</p>',
        table(['Slot', 'Generation', 'Pending rows', 'Oldest pending age', 'Acknowledged rows', 'ACK rate'], archive_rows),
        trend_history(vm),
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
