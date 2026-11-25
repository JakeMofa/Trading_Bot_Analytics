"""PP first-quote diagnostic. Sample Linux counters; join samples on UTC offline.

Run sample on the VM host (not inside a container) and redirect stdout to JSONL.
`report` joins the existing DB observer and four-row boundary CSV; missing
observations stay null. No credentials, network clients or database queries.
"""
import argparse
import csv
import json
import os
import platform
import time
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path


def instant(value):
    if not value:
        return None
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timezone required')
    return value.timestamp()


def proc_text(path):
    try:
        return path.read_text()
    except (OSError, UnicodeError):
        return ''


def fields(path):
    return dict(line.split(None, 1) for line in proc_text(path).splitlines() if len(line.split(None, 1)) == 2)


def counter(value):
    return int(value) if value and value.isdigit() else None


def collect(proc, device):
    mem = fields(proc / 'meminfo').get('MemAvailable:', '').split()
    vm = fields(proc / 'vmstat')
    cpu = fields(proc / 'stat').get('cpu', '').split()
    values = {k: counter(vm.get(k)) for k in ('pswpin', 'pswpout', 'oom_kill', 'pgmajfault')}
    # The aggregate CPU first eight fields already include guest time.
    if len(cpu) >= 8 and all(x.isdigit() for x in cpu[:8]):
        ticks = list(map(int, cpu[:8]))
        values.update(cpu_total=sum(ticks), cpu_busy=sum(ticks)-ticks[3]-ticks[4], cpu_iowait=ticks[4])
    for resource in ('memory', 'cpu', 'io'):
        for scope, stats in fields(proc / 'pressure' / resource).items():
            totals = dict(x.split('=', 1) for x in stats.split() if '=' in x)
            if scope in ('some', 'full'):
                values[f'{resource}_{scope}_us'] = counter(totals.get('total'))
    # Linux diskstats uses 512-byte sectors. Select the filesystem's own
    # major:minor once; summing parent and child devices would double-count.
    for line in proc_text(proc / 'diskstats').splitlines():
        parts = line.split()
        if len(parts) >= 14 and ':'.join(parts[:2]) == device and all(parts[i].isdigit() for i in (5, 9, 12)):
            values.update(disk_read_bytes=512*int(parts[5]), disk_write_bytes=512*int(parts[9]),
                          disk_busy_ms=int(parts[12]))
            break
    return {'at_utc': datetime.now(timezone.utc).isoformat(), 'monotonic_ns': time.monotonic_ns(),
            'boot_id': proc_text(proc/'sys/kernel/random/boot_id').strip() or None,
            'device': device, 'mem_available_kib': counter(mem[0]) if len(mem) == 2 and mem[1]=='kB' else None,
            'counters': values}


def interval(previous, current):
    """Deltas are only valid for one host boot, clock and underlying device."""
    if not previous or not current['boot_id'] or current['boot_id'] != previous['boot_id'] or current['device'] != previous['device']:
        return {}
    ns = current['monotonic_ns'] - previous['monotonic_ns']
    if ns <= 0:
        return {}
    prev, now = previous['counters'], current['counters']
    def delta(key):
        a, b = prev.get(key), now.get(key)
        return b-a if a is not None and b is not None and b>=a else None
    data = {key: delta(key) for key in ('pswpin', 'pswpout', 'oom_kill', 'pgmajfault',
                                          'disk_read_bytes', 'disk_write_bytes', 'disk_busy_ms')}
    data['seconds'] = ns / 1e9
    total = delta('cpu_total')
    for key in ('cpu_busy', 'cpu_iowait'):
        count = delta(key)
        data[key+'_pct'] = round(100*count/total, 3) if total and count is not None and count <= total else None
    for resource in ('memory', 'cpu', 'io'):
        for scope in ('some', 'full'):
            key = f'{resource}_{scope}'
            micros = delta(key+'_us')
            data[key+'_stall_pct'] = round(100*micros/(ns/1000), 4) if micros is not None else None
    return data


def backlog(snapshot, sample_epoch, origin):
    if not snapshot or snapshot.get('origin_id') != origin:
        return None
    at = instant(snapshot['at_utc'])
    age = sample_epoch-at
    generations = snapshot.get('generations')
    if age < 0 or age > 60 or not generations:
        return None
    pending, oldest, missing_oldest = 0, [], False
    for g in generations:
        n = g.get('pending')
        if type(n) is not int or n < 0:
            return None
        pending += n
        oldest_at = instant(g.get('oldest_pending_at'))
        if n and oldest_at is None:
            missing_oldest = True
        elif n:
            oldest.append(oldest_at)
    return {'pending': pending, 'sample_age_seconds': round(age,3),
            'oldest_pending_seconds_at_observation': round(max(0, at-min(oldest)),3) if oldest and not missing_oldest else None}


def jsonl(path):
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def summarize_span(rows, start, end):
    """Summarize intervals wholly inside a measured PP time span."""
    if end is None or end < start:
        return None
    points = [row for row in rows if start <= instant(row['at_utc']) <= end]
    intervals = [row['interval_ending_here'] for row in points
                 if 0 < row['interval_ending_here'].get('seconds', 0) <= instant(row['at_utc'])-start]
    summary = {'duration_seconds': round(end-start, 3), 'samples_in_span': len(points),
               'intervals_wholly_in_wait': len(intervals),
               'covered_seconds': round(sum(item['seconds'] for item in intervals), 3)}
    memory = [row['mem_available_kib'] for row in points if row['mem_available_kib'] is not None]
    summary['min_mem_available_kib'] = min(memory, default=None)
    for key in ('pswpin','pswpout','oom_kill','disk_read_bytes','disk_write_bytes','disk_busy_ms'):
        counters = [item.get(key) for item in intervals]
        summary[key] = sum(counters) if counters and all(v is not None for v in counters) else None
    for key in ('memory_some_stall_pct','memory_full_stall_pct','io_full_stall_pct','cpu_busy_pct','cpu_iowait_pct'):
        rates = [item.get(key) for item in intervals]
        summary['peak_'+key] = max((v for v in rates if v is not None), default=None)
    pending = [row['archive']['pending'] for row in points if row.get('archive') is not None]
    summary['max_observed_pending'] = max(pending, default=None)
    return summary


def build_report(samples, observations, boundaries, origin):
    observations = sorted((o for o in observations if o.get('origin_id') == origin and o.get('at_utc')),
                          key=lambda o: instant(o['at_utc']))
    observed_times = [instant(o['at_utc']) for o in observations]
    starts = [instant(row['window_start']) for row in boundaries]
    if len(starts) not in (1, 4) or any(t % 900 for t in starts) or any(b-a != 900 for a,b in zip(starts,starts[1:])):
        raise ValueError('one or four consecutive exact quarter-hour UTC boundaries required')
    windows = [dict(window_start=row['window_start'],
                    first_quote_utc={k: row.get(k) or None for k in
                    ('early_rest_first_utc','websocket_first_utc','canonical_first_utc','dashboard_first_utc')},
                    samples=[]) for row in boundaries]
    previous = None
    for sample in samples:
        ts = instant(sample['at_utc'])
        diff = interval(previous, sample)
        previous = sample
        i = bisect_right(starts, ts)-1
        if i < 0 or ts >= starts[-1]+900:
            continue
        j = bisect_right(observed_times, ts)-1
        windows[i]['samples'].append({'at_utc': sample['at_utc'], 'seconds_since_boundary': round(ts-starts[i],3),
            'device': sample['device'], 'mem_available_kib': sample['mem_available_kib'], 'interval_ending_here': diff,
            'archive': backlog(observations[j] if j>=0 else None, ts, origin)})
    for window in windows:
        start = instant(window['window_start'])
        end = instant(window['first_quote_utc']['dashboard_first_utc'])
        window['during_wait_for_dashboard'] = summarize_span(window['samples'], start, end) if end is not None and end < start+900 else None
    return {'origin_id': origin, 'windows': windows}


def profile_report(samples, profile):
    rows, previous = [], None
    for sample in samples:
        rows.append({'at_utc': sample['at_utc'], 'mem_available_kib': sample['mem_available_kib'],
                     'interval_ending_here': interval(previous, sample)})
        previous = sample
    return [{'mode': run['mode'], 'started_at_utc': run['started_at_utc'], 'ended_at_utc': run['ended_at_utc'],
             'resources': summarize_span(rows, instant(run['started_at_utc']), instant(run['ended_at_utc']))}
            for run in profile['runs']]


def sample_host(args):
    if platform.system() != 'Linux' or not (1 <= args.interval <= 60 and 1 <= args.seconds <= 5400):
        raise ValueError('Linux host, interval 1..60 s and duration 1..5400 s required')
    dev = args.filesystem.stat().st_dev
    device = f'{os.major(dev)}:{os.minor(dev)}'
    start = time.monotonic()
    while True:
        print(json.dumps(collect(Path('/proc'), device), separators=(',', ':')), flush=True)
        remaining = start + args.seconds - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest='command', required=True)
    sample = cmds.add_parser('sample')
    sample.add_argument('--interval', type=int, default=5)
    sample.add_argument('--seconds', type=int, required=True)
    sample.add_argument('--filesystem', type=Path, default=Path('/'), help='path on database volume filesystem')
    report = cmds.add_parser('report')
    report.add_argument('--samples', type=Path, required=True)
    report.add_argument('--db-observations', type=Path)
    report.add_argument('--boundaries', type=Path, required=True, help='first-quote CSV containing one or four window_start rows')
    report.add_argument('--origin', required=True)
    quiet = cmds.add_parser('quiet-report')
    quiet.add_argument('--samples', type=Path, required=True)
    quiet.add_argument('--profile', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'sample':
        sample_host(args)
    elif args.command == 'quiet-report':
        print(json.dumps(profile_report(jsonl(args.samples), json.loads(args.profile.read_text()))))
    else:
        with args.boundaries.open(newline='') as f:
            output = build_report(jsonl(args.samples), jsonl(args.db_observations) if args.db_observations else (),
                                  list(csv.DictReader(f)), args.origin)
        print(json.dumps(output, separators=(',', ':')))


if __name__ == '__main__':
    main()
