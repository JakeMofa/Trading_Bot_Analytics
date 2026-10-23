"""Read-only initial-soak snapshot. Run as root on the VM; prints no credentials."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from urllib.request import urlopen


def cpu_sample():
    return [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integrity', action='store_true')
    parser.add_argument('--output', type=Path, help='Keep the latest 288 five-minute snapshots as JSONL')
    args = parser.parse_args()
    result = {'captured_at': datetime.now(timezone.utc).isoformat()}
    before = cpu_sample()
    time.sleep(1)
    delta = [new - old for new, old in zip(cpu_sample(), before)]
    result['cpu_busy_percent_1s'] = round(100 * (1 - (delta[3] + delta[4]) / max(1, sum(delta))), 2)
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.split(':')[0] in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}
    result['memory_bytes'] = memory
    disk = shutil.disk_usage('/opt/tradebot/data')
    result['disk_bytes'] = dict(zip(('total', 'used', 'free'), disk))
    result['uptime_seconds'] = float(Path('/proc/uptime').read_text().split()[0])
    services = {}
    for name in ('api', 'lifecycle', 'ensemble'):
        unit = f'tradebot-{name}.service'
        raw = subprocess.check_output(['systemctl', 'show', unit,
                                      '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID',
                                      '-p', 'NRestarts', '-p', 'MemoryCurrent', '-p', 'ExecMainStatus'], text=True)
        info = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
        pid = info.get('MainPID', '0')
        if pid != '0':
            entries = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
            env = dict(entry.split(b'=', 1) for entry in entries if b'=' in entry)
            info['openai_enabled'] = env.get(b'ENABLE_OPENAI_ANALYST') != b'false'
            info['retention_enabled'] = env.get(b'ENABLE_LOCAL_RETENTION') != b'false'
            info['openai_credentials_present'] = any(env.get(key) for key in
                                                       (b'OPENAI_API_KEY', b'OPENAPIKEY', b'OPENAI_KEY'))
        services[unit] = info
    result['services'] = services
    endpoints = {}
    for path in ('/health', '/state/current', '/forecast/current', '/models/current', '/cloud/status'):
        try:
            with urlopen('http://127.0.0.1:8000' + path, timeout=10) as response:
                value = json.load(response)
            if path == '/state/current':
                coinbase = value.get('coinbase') or {}
                value = {'market': value.get('market'), 'coinbase': {
                    key: coinbase.get(key) for key in ('price_usd', 'age_seconds', 'source_time', 'received_at')},
                    'missing_data': value.get('missing_data'), 'updated_at': value.get('updated_at')}
            endpoints[path] = value
        except Exception as error:
            endpoints[path] = {'error_type': type(error).__name__}
    result['endpoints'] = endpoints
    path = Path('/opt/tradebot/data/btc_intelligence.db')
    result['sqlite_bytes'] = path.stat().st_size
    wal = Path(str(path) + '-wal')
    result['wal_bytes'] = wal.stat().st_size if wal.exists() else 0
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result['row_counts'] = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                for table in ('observations', 'stream_events', 'markets',
                                              'feature_snapshots', 'predictions', 'ai_suggestions') if table in tables}
        if args.integrity:
            result['sqlite_integrity'] = [row[0] for row in db.execute('PRAGMA integrity_check')]
            result['foreign_key_violations'] = len(db.execute('PRAGMA foreign_key_check').fetchall())
    journal = subprocess.run(
        ['journalctl', '-u', 'tradebot-api', '-u', 'tradebot-lifecycle', '-u', 'tradebot-ensemble',
         '--since', '-30 minutes', '-p', 'warning', '--no-pager', '-q'],
        text=True, capture_output=True)
    result['journal_warning_error_lines'] = (
        len(journal.stdout.splitlines()) if journal.returncode == 0 and not journal.stderr else None)
    if args.output:
        previous = args.output.read_text().splitlines()[-287:] if args.output.exists() else []
        temporary = args.output.with_suffix('.tmp')
        with open(temporary, 'w') as output:
            os.chmod(temporary, 0o600)
            output.write('\n'.join(previous + [json.dumps(result, separators=(',', ':'))]) + '\n')
        temporary.replace(args.output)
        print('Read-only cloud-soak snapshot saved (maximum 288 samples)')
        return
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
