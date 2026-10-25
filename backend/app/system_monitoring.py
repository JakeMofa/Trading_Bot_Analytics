"""Bounded, read-only views of existing local soak telemetry. No remote calls."""
from collections import deque
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sqlite3
import time

MAX_SAMPLES = 288
MAX_READ_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
SERVICES = ('tradebot-api.service', 'tradebot-ensemble.service', 'tradebot-lifecycle.service')


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def mapping(value):
    return value if isinstance(value, dict) else {}


def elapsed(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return None
        return max(0, (datetime.now(timezone.utc) - stamp).total_seconds())
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def clean_sample(row):
    """Explicit projection: never forward arbitrary endpoint bodies or environment data."""
    if not isinstance(row, dict) or elapsed(row.get('captured_at')) is None:
        return None
    endpoints = mapping(row.get('endpoints'))
    health = mapping(endpoints.get('/health'))
    state = mapping(endpoints.get('/state/current'))
    cloud = mapping(endpoints.get('/cloud/status'))
    memory = mapping(row.get('memory_bytes'))
    total, available = number(memory.get('MemTotal')), number(memory.get('MemAvailable'))
    sample = {
        'captured_at': row['captured_at'],
        'cpu_percent': number(row.get('cpu_busy_percent_1s')),
        'ram_total_bytes': total,
        'ram_used_bytes': number(total - available) if total is not None and available is not None else None,
        'uptime_seconds': number(row.get('uptime_seconds')),
        'sqlite_bytes': number(row.get('sqlite_bytes')),
        'wal_bytes': number(row.get('wal_bytes')),
        'predictions': number(mapping(row.get('row_counts')).get('predictions')),
    }
    disk = mapping(row.get('disk_bytes'))
    for key in ('used', 'total', 'free'):
        sample['disk_' + key + '_bytes'] = number(disk.get(key))
    feeds = mapping(health.get('feeds'))
    for name in ('coinbase', 'polymarket'):
        feed = mapping(feeds.get(name + '_stream'))
        data = mapping(state.get(name))
        sample[name + '_age_seconds'] = number(data.get('age_seconds'))
        if sample[name + '_age_seconds'] is None:
            # Calculate age at capture time, never relative to the time of this request.
            try:
                captured = datetime.fromisoformat(row['captured_at'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(feed['last_data_at'].replace('Z', '+00:00'))
                sample[name + '_age_seconds'] = max(0, (captured - last).total_seconds())
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                pass
        sample[name + '_reconnects_cumulative'] = number(feed.get('reconnects'))
    datasets = cloud.get('datasets')
    if isinstance(datasets, list):
        counts = [number(mapping(item).get('rows_synced')) for item in datasets]
        sample['cloud_rows_synced'] = number(sum(counts)) if counts and all(value is not None for value in counts) else None
        for source in ('observations', 'stream_events'):
            records = [item for item in datasets if isinstance(item, dict) and item.get('dataset') == 'archive:' + source]
            sample[source + '_archive_checkpoint'] = number(records[0].get('last_source_id')) if records else None
    services = mapping(row.get('services'))
    sample['services'] = {}
    for name in SERVICES:
        info = mapping(services.get(name))
        sample['services'][name] = {
            'state': info.get('ActiveState') if info.get('ActiveState') in ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading') else 'unavailable',
            'restarts': int(info['NRestarts']) if str(info.get('NRestarts', '')).isdigit() else None,
        }
    return sample


def read_history(path, limit=MAX_SAMPLES):
    samples = deque(maxlen=min(MAX_SAMPLES, max(1, limit)))
    try:
        with Path(path).open('rb') as source:
            source.seek(0, 2)
            size = source.tell()
            offset = max(0, size - MAX_READ_BYTES)
            source.seek(offset)
            raw = source.read(MAX_READ_BYTES)
            if offset:
                raw = raw.partition(b'\n')[2]  # Discard the partial boundary line.
            for line in raw.splitlines():
                if len(line) > MAX_LINE_BYTES:
                    continue
                try:
                    sample = clean_sample(json.loads(line))
                    if sample is not None:
                        samples.append(sample)
                except (ValueError, TypeError, RecursionError, OverflowError):
                    continue
        ordered = sorted(samples, key=lambda item: datetime.fromisoformat(item['captured_at'].replace('Z', '+00:00')))
        return {'status': 'ok' if ordered else 'empty', 'items': ordered, 'limit': min(MAX_SAMPLES, max(1, limit))}
    except OSError:
        return {'status': 'unavailable', 'items': [], 'limit': min(MAX_SAMPLES, max(1, limit))}


def file_size(path, missing=None):
    try:
        return Path(path).stat().st_size
    except FileNotFoundError:
        return missing
    except OSError:
        return None


def host_status(db_path, history):
    latest = history['items'][-1] if history['items'] else {}
    age = elapsed(latest.get('captured_at'))
    host = {key: latest.get(key) for key in (
        'cpu_percent', 'ram_used_bytes', 'ram_total_bytes', 'disk_used_bytes',
        'disk_total_bytes', 'disk_free_bytes', 'uptime_seconds')}
    host.update({'captured_at': latest.get('captured_at'), 'age_seconds': age,
                 'status': 'unavailable' if age is None else 'stale' if age > 900 else 'ok'})
    # Resources that can be read cheaply without sampling/sleeping or subprocesses.
    try:
        host['uptime_seconds'] = float(Path('/proc/uptime').read_text().split()[0])
        mem = {line.split(':')[0]: int(line.split()[1]) * 1024
               for line in Path('/proc/meminfo').read_text().splitlines()
               if line.split(':')[0] in ('MemTotal', 'MemAvailable')}
        host['ram_total_bytes'] = mem['MemTotal']
        host['ram_used_bytes'] = mem['MemTotal'] - mem['MemAvailable']
    except (OSError, ValueError, KeyError, IndexError):
        pass
    try:
        disk = shutil.disk_usage(Path(db_path).resolve().parent)
        host.update(dict(zip(('disk_total_bytes', 'disk_used_bytes', 'disk_free_bytes'), disk)))
    except OSError:
        pass
    db_size = file_size(db_path)
    return {'host': host, 'sqlite': {'size_bytes': db_size,
            'wal_size_bytes': file_size(str(db_path) + '-wal', missing=0 if db_size is not None else None)},
            'services': latest.get('services', {name: {'state': 'unavailable', 'restarts': None} for name in SERVICES}),
            'services_captured_at': latest.get('captured_at'), 'services_stale': age is None or age > 900}


def read_ensemble(db_path):
    """Latest valid persisted ensemble, with provenance; never changes LiveState's baseline."""
    fields = ('id', 'market_id', 'model_version', 'as_of', 'created_at', 'probability_up',
              'probability_down', 'abstain_reason', 'decision_action', 'decision_confidence',
              'decision_summary', 'decision_label', 'decision_hold_direction',
              'suggested_action', 'suggested_confidence', 'component_scores')
    try:
        uri = Path(db_path).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as db:
            db.execute('PRAGMA query_only=ON')
            deadline = time.monotonic() + 1
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            columns = {item[1] for item in db.execute('PRAGMA table_info(predictions)')}
            selected = [field for field in fields if field in columns]
            if not {'model_version', 'probability_up', 'as_of', 'market_id', 'id'}.issubset(selected):
                return None
            rows = db.execute('SELECT ' + ','.join(selected) + " FROM predictions WHERE model_version='ensemble_v1' ORDER BY julianday(as_of) DESC,id DESC LIMIT 100").fetchall()
            for values in rows:
                item = dict(zip(selected, values))
                try:
                    p = float(item['probability_up'])
                    if not math.isfinite(p) or not 0 <= p <= 1 or elapsed(item['as_of']) is None:
                        continue
                    item['probability_up'], item['probability_down'] = p, 1 - p
                    scores = json.loads(item.get('component_scores') or '{}')
                    item['component_scores'] = {key: number(value) for key, value in mapping(scores).items() if key in ('baseline', 'case', 'news', 'market')}
                except (ValueError, TypeError, RecursionError):
                    continue
                item['source'] = 'persisted_predictions'
                item['experimental'] = True
                return item
    except (OSError, sqlite3.Error, ValueError):
        pass
    return None
