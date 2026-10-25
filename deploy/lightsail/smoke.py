"""Private, read-only production smoke checks. Never print response bodies or secrets."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

def check_secrets(body):
    path = Path('/opt/tradebot/.env')
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        name, value = line.split('=', 1)
        if any(token in name.upper() for token in ('SECRET', 'API_KEY', 'KEY_ID', 'PASSWORD', 'TOKEN')):
            value = value.strip().strip('\"\'')
            assert not (len(value) >= 8 and value.encode() in body), 'credential found in response'


CORE = ('/health', '/state/current', '/forecast/current', '/models/current', '/cloud/status')
PHASE = ('/system/status', '/system/history', '/dashboard', '/history/predictions', '/history/context', '/history/coinbase-chart')


def _get(path):
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=15) as response:
        content_type = response.headers.get('Content-Type', '')
        if path == '/events':
            assert 'text/event-stream' in content_type, 'SSE content type'
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                line = response.readline(2 * 1024 * 1024)
                if line.startswith(b'data: '):
                    check_secrets(line)
                    return json.loads(line[6:])
            raise AssertionError('SSE data frame missing')
        body = response.read(16 * 1024 * 1024)
        check_secrets(body)
        if path == '/dashboard':
            assert 'text/html' in content_type and b'<html' in body.lower(), 'dashboard HTML'
            assert all(label in body for label in (b'Market', b'Models', b'History', b'System'))
            return 'HTML'
        assert 'application/json' in content_type, 'JSON content type'
        return json.loads(body)


def get(path):
    try:
        return _get(path)
    except AssertionError as error:
        raise AssertionError(path + ': ' + str(error)) from None
    except Exception as error:
        raise AssertionError(path + ': request failed (' + type(error).__name__ + ')') from None


def check(legacy=False):
    result = {path: get(path) for path in CORE + (() if legacy else PHASE)}
    health = result['/health']
    assert health['status'] == 'ok', 'live engine degraded'
    assert health['collector']['running'], 'collector stopped'
    assert health['collector'].get('error') is None, 'collector error'
    state = result['/state/current']
    assert state.get('market') and state.get('coinbase'), 'market/price missing'
    for name in ('coinbase_stream', 'polymarket_stream'):
        feed = health.get('feeds', {}).get(name, {})
        assert feed.get('status') in ('live', 'running'), name + ' disconnected'
        stamp = feed.get('last_data_at')
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds()
        assert 0 <= age < 90, name + ' stale'
    result['/events'] = get('/events')
    assert result['/events'].get('coinbase'), 'SSE live state missing'
    if not legacy:
        system = result['/system/status']
        assert system['collector']['running'], 'system collector stopped'
        assert system['openai_enabled'] is False and system['retention_enabled'] is False, 'disabled flags changed'
        assert system['sqlite']['size_bytes'] > 0, 'SQLite missing'
        assert 0 <= len(result['/system/history']['items']) <= 288, 'unbounded telemetry'
        assert 'ensemble_v1' in result['/models/current']['models'], 'ensemble missing'
        for feed in system['feeds'].values():
            assert not (feed['status'] in ('live', 'running') and (feed['age_seconds'] is None or feed['age_seconds'] > 90)), 'stale feed mislabeled'
        assert all(row.get('last_source_key') is None and row.get('detail') is None for row in result['/cloud/status'].get('datasets', [])), 'private cloud diagnostics exposed'
    return {'endpoints': {path: 'PASS' for path in result}, 'live_health': health['status'],
            'collector': 'running', 'cloud_status': result['/cloud/status'].get('status'),
            'lifecycle_status': result['/cloud/status'].get('lifecycle', {}).get('status')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--attempts', type=int, default=1)
    args = parser.parse_args()
    for attempt in range(args.attempts):
        try:
            print(json.dumps(check(args.legacy), sort_keys=True))
            return
        except Exception as error:
            if attempt + 1 == args.attempts:
                # Avoid echoing HTTP response or arbitrary exception details.
                print(json.dumps({'smoke': 'FAIL', 'error_type': type(error).__name__,
                                  'check': str(error) if isinstance(error, AssertionError) else 'request failed'}))
                raise SystemExit(1)
            time.sleep(5)


if __name__ == '__main__':
    main()
