"""Bounded GET-only PP evidence via an existing loopback/SSH tunnel.

Never opens SSH, a DB, or a cloud connection; never starts or retires anything.
Bind ordinal 1 then 2 as the actual trial UUIDs become known. Binding files and
captures are create-only. The compare command requires both exact bindings.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import urlencode, urlsplit
import uuid

ORIGIN = 'pp-live-pp'
MAX_BYTES = 64 * 1024**2


def utc(): return datetime.now(timezone.utc).isoformat()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def identity(value):
    if str(uuid.UUID(value)) != value: raise ValueError('canonical generation UUID required')
    return value


def read_json(path):
    if path.stat().st_size > MAX_BYTES: raise ValueError('evidence file too large')
    def duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=duplicate)


def write_new(path, value):
    if len(canonical(value)) > MAX_BYTES: raise ValueError('output exceeds 64 MiB')
    with path.open('x') as out:
        json.dump(value, out, indent=2, allow_nan=False)
        out.write('\n')


def bindings(directory, *, complete=False):
    result = {}
    if set(path.name for path in directory.glob('generation-*.json')) - {'generation-1.json', 'generation-2.json'}:
        raise ValueError('unexpected generation binding file')
    for ordinal in (1, 2):
        path = directory / f'generation-{ordinal}.json'
        if path.exists():
            value = read_json(path)
            if value.get('ordinal') != ordinal or value.get('origin_id') != ORIGIN:
                raise ValueError('generation binding mismatch')
            result[str(ordinal)] = identity(value['generation_id'])
    if len(set(result.values())) != len(result) or (complete and len(result) != 2):
        raise ValueError('two distinct generation bindings required')
    return result


def bind(directory, ordinal, generation):
    identity(generation)
    directory.mkdir(exist_ok=True)
    old = bindings(directory)
    if ordinal == 2 and '1' not in old: raise ValueError('bind first generation before second')
    if generation in old.values(): raise ValueError('generation already bound')
    write_new(directory / f'generation-{ordinal}.json', dict(ordinal=ordinal,
        origin_id=ORIGIN, generation_id=generation, bound_at=utc()))


class HTTPFailure(ValueError):
    def __init__(self, response):
        super().__init__('non-success HTTP response')
        self.response = response


class LoopbackHTTP:
    """Direct IP sockets: no proxy, DNS, credentials, redirects or non-GETs."""
    def __init__(self, base_url, *, total_seconds=240, request_seconds=4, max_bytes=MAX_BYTES):
        parsed = urlsplit(base_url)
        if (parsed.scheme != 'http' or parsed.username or parsed.password or
                parsed.path not in ('', '/') or parsed.query or parsed.fragment or
                not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback):
            raise ValueError('plain loopback IP URL only; use a separately established SSH tunnel')
        if not 0 < request_seconds <= 4 or not request_seconds <= total_seconds <= 240:
            raise ValueError('request <=4s and total <=240s required')
        if not 1 <= max_bytes <= MAX_BYTES: raise ValueError('invalid byte budget')
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.deadline = time.monotonic() + total_seconds
        self.request_seconds, self.max_bytes, self.bytes = request_seconds, max_bytes, 0
        self.requests = 0

    def get(self, route, *, sse=False):
        if not route.startswith('/') or route.startswith('//') or '\r' in route or '\n' in route:
            raise ValueError('relative route required')
        begun, at = time.monotonic(), utc()
        deadline = min(self.deadline, begun+self.request_seconds)
        remaining = deadline-time.monotonic()
        if remaining <= 0 or self.requests >= 270: raise ValueError('capture request/deadline budget exhausted')
        connection = http.client.HTTPConnection(self.host, self.port, timeout=remaining)
        self.requests += 1
        chunks = bytearray()
        response = None
        def active_socket():
            return connection.sock or getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
        def abort():
            # Socket timeouts alone are idle timeouts. Shut down this request's
            # socket at the absolute deadline, including slowly trickled headers.
            sock = active_socket()
            if sock is not None:
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
        timer = threading.Timer(remaining, abort)
        timer.daemon = True
        timer.start()
        try:
            connection.request('GET', route, headers={'Accept': 'text/event-stream' if sse else 'application/json',
                                                     'Connection': 'close'})
            response = connection.getresponse()
            if sse and response.status == 200 and not (response.getheader('Content-Type') or '').startswith('text/event-stream'):
                raise ValueError('SSE content type mismatch')
            # getresponse() may consume the connection timeout; bound the body
            # by the same absolute deadline, including slow trickle responses.
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise ValueError('HTTP deadline exhausted')
                sock = active_socket()
                if sock is not None: sock.settimeout(remaining)
                chunk = response.read1(min(65536, self.max_bytes-self.bytes+1))
                self.bytes += len(chunk)
                if self.bytes > self.max_bytes: raise ValueError('capture byte budget exhausted')
                chunks.extend(chunk)
                if sse and (b'\n\n' in chunks or b'\r\n\r\n' in chunks):
                    break
                if not chunk: break
            if time.monotonic() >= deadline: raise ValueError('HTTP deadline exhausted')
            body = bytes(chunks)
            result = dict(route=route, observed_at=at, completed_at=utc(),
                elapsed_seconds=round(time.monotonic()-begun, 6), status_code=response.status,
                body_sha256=hashlib.sha256(body).hexdigest(), body_base64=base64.b64encode(body).decode())
            if response.status != 200:
                try: result['body'] = json.loads(body)
                except (ValueError, UnicodeError): pass
                raise HTTPFailure(result)
            if sse:
                if b'\n\n' not in body and b'\r\n\r\n' not in body:
                    raise ValueError('complete SSE frame missing')
                frame = body.replace(b'\r\n', b'\n').split(b'\n\n', 1)[0]
                data = [line[5:].lstrip() for line in frame.split(b'\n') if line.startswith(b'data:')]
                if not data: raise ValueError('complete SSE data frame missing')
                result['body'] = json.loads(b'\n'.join(data))
                result['scope'] = 'first_complete_sse_frame_only'
            else:
                result['body'] = json.loads(body)
            return result
        finally:
            timer.cancel()
            connection.close()


def validate_state(state):
    if (state.get('environment'), state.get('data_mode'), state.get('origin_id')) != ('preprod', 'pp_live', ORIGIN):
        raise ValueError('state environment/mode/origin mismatch')
    if not state.get('generated_at'): raise ValueError('server generated_at missing')


def collect(client, generation, phase, *, expected, source_sha, max_pages=128):
    identity(generation)
    if generation not in expected.values() or not re.fullmatch('[0-9a-f]{40}', source_sha):
        raise ValueError('bound generation and full source SHA required')
    if phase not in ('retained', 'retired') or not 1 <= max_pages <= 128:
        raise ValueError('bounded retained/retired capture required')
    result = dict(scope='bounded_read_only_http_capture', origin_id=ORIGIN,
        generation_id=generation, expected_generations=expected, phase=phase,
        operator_declared_source_sha=source_sha, source_identity_independently_proven=False,
        started_at=utc(), responses=[], rows=[], missing_evidence=[])
    for route in ('/state/current', '/events', '/history/predictions?limit=500',
                  '/history/coinbase-chart', '/history/context'):
        captured = client.get(route, sse=route == '/events')
        result['responses'].append(captured)
        body = captured['body']
        if route in ('/state/current', '/events'):
            validate_state(body)
            if not body.get('market') or not body.get('feature_snapshot') or not body.get('forecast'):
                result['missing_evidence'].append('current_market_feature_or_saved_forecast_missing')
            if body.get('missing_data'):
                result['missing_evidence'].append('state_reports_missing_data')
        elif route.startswith('/history/predictions'):
            if body.get('origin_id') != ORIGIN or body.get('limit') != 500 or not isinstance(body.get('items'), list):
                raise ValueError('prediction history contract mismatch')
            ids = [item['id'] for item in body['items']]
            if len(ids) != len(set(ids)): raise ValueError('duplicate prediction ID')
            if not ids: result['missing_evidence'].append('saved_predictions_empty')
            if len(ids) == 500: result['missing_evidence'].append('prediction_history_pagination_unavailable')
        elif route == '/history/coinbase-chart':
            if body.get('status') != 'ok' or not body.get('points') or body.get('truncated'):
                result['missing_evidence'].append('current_chart_missing_or_truncated')
        elif body.get('status') == 'unsupported':
            result['missing_evidence'].append('historical_context_outcomes_unsupported')
    cursor, seen, previous, fixed_provenance = None, set(), None, None
    for _ in range(max_pages):
        route = f'/history/archive/{generation}?' + urlencode({'limit': 500, **({'after_event_id': cursor} if cursor else {})})
        captured = client.get(route)
        result['responses'].append(captured)
        body, provenance = captured['body'], captured['body'].get('provenance', {})
        if (provenance.get('origin_id'), provenance.get('generation_id'), provenance.get('dataset')) != (ORIGIN, generation, 'raw.events'):
            raise ValueError('raw history scope mismatch')
        state, tier = provenance.get('state'), provenance.get('tier')
        if phase == 'retained' and (state not in ('sealed', 'verified') or tier != 'local_postgres'):
            raise ValueError('retained generation must be sealed/verified and attached locally')
        if phase == 'retired' and (state != 'retired' or tier != 'authenticated_archive'):
            raise ValueError('retired generation must use authenticated archive')
        stable = (state, tier, provenance.get('sealed_at'))
        if fixed_provenance is not None and stable != fixed_provenance:
            raise ValueError('generation changed while reading')
        fixed_provenance = stable
        rows = body.get('rows')
        if not isinstance(rows, list) or len(rows) > 500: raise ValueError('invalid raw page')
        for row in rows:
            if (row.get('origin_id'), row.get('generation_id')) != (ORIGIN, generation):
                raise ValueError('foreign raw row')
            key = (row['source'], row['event_id'])
            if key in seen or (previous is not None and key <= previous):
                raise ValueError('duplicate or unordered raw identity')
            # Preserve exact source spelling and NULLs; never float-coerce epochs.
            for name in ('price', 'size', 'source_epoch'):
                if row.get(name) is not None:
                    if not isinstance(row[name], str) or not Decimal(row[name]).is_finite():
                        raise ValueError('raw decimals/epochs must remain exact finite strings')
            seen.add(key); previous = key
        result['rows'].extend(rows)
        next_cursor = body.get('next_cursor')
        if body.get('complete') is not (next_cursor is None): raise ValueError('raw completion contract mismatch')
        if next_cursor is None: break
        if not rows or next_cursor == cursor: raise ValueError('raw cursor did not progress')
        try:
            decoded = json.loads(base64.urlsafe_b64decode(next_cursor[3:]+'='*(-len(next_cursor[3:])%4)))
        except Exception: raise ValueError('invalid cursor') from None
        if not next_cursor.startswith('v1.') or decoded != [generation, *previous]:
            raise ValueError('raw cursor identity mismatch')
        cursor = next_cursor
    else: raise ValueError('raw history exceeds explicit page bound')
    if not result['rows']: result['missing_evidence'].append('raw_history_empty')
    if len(expected) != 2: result['missing_evidence'].append('second_trial_uuid_not_bound_yet')
    result.update(completed_at=utc(), raw_rows_sha256=digest(result['rows']), row_count=len(result['rows']),
        not_proven=['source/image attestation', 'partition removal or deadline', 'continuous SSE',
                    'clock synchronization', 'historical chart parity', 'official labels', 'feature recomputation'])
    result['result'] = 'INCOMPLETE' if result['missing_evidence'] else 'CAPTURED'
    return result


def compare(directory, captures):
    expected = bindings(directory, complete=True)
    if len(captures) != 4: raise ValueError('two retained and two retired captures required')
    indexed = {}
    for item in captures:
        if item.get('scope') != 'bounded_read_only_http_capture' or item.get('result') not in ('CAPTURED', 'INCOMPLETE'):
            raise ValueError('incomplete/failed capture shape')
        key = (item['generation_id'], item['phase'])
        if key in indexed or key[0] not in expected.values() or item['origin_id'] != ORIGIN:
            raise ValueError('duplicate/foreign capture')
        if item.get('raw_rows_sha256') != digest(item['rows']) or item.get('row_count') != len(item['rows']):
            raise ValueError('capture row hash/count mismatch')
        for response in item['responses']:
            raw = base64.b64decode(response['body_base64'], validate=True)
            if hashlib.sha256(raw).hexdigest() != response['body_sha256']:
                raise ValueError('response bytes hash mismatch')
            if response['route'] != '/events' and json.loads(raw) != response['body']:
                raise ValueError('response bytes/parsed body mismatch')
        archive_rows = [row for response in item['responses'] if response['route'].startswith('/history/archive/')
                        for row in response['body']['rows']]
        if archive_rows != item['rows']: raise ValueError('capture rows differ from HTTP response')
        if any(expected.get(k) != v for k, v in item['expected_generations'].items()):
            raise ValueError('capture generation binding changed')
        indexed[key] = item
    output, gaps = [], []
    for generation in expected.values():
        before, after = (indexed[(generation, phase)] for phase in ('retained', 'retired'))
        if before['operator_declared_source_sha'] != after['operator_declared_source_sha']:
            raise ValueError('source SHA changed across retirement')
        if canonical(before['rows']) != canonical(after['rows']): raise ValueError('raw rows changed after retirement')
        def predictions(capture):
            return {row['id']: row for response in capture['responses']
                    if response['route'] == '/history/predictions?limit=500' for row in response['body']['items']}
        left, right = predictions(before), predictions(after)
        if any(right.get(key) != row for key, row in left.items()):
            raise ValueError('saved prediction history missing or changed')
        gaps.extend(gap for item in (before, after) for gap in item['missing_evidence']
                    if gap != 'second_trial_uuid_not_bound_yet')
        output.append(dict(generation_id=generation, row_count=len(before['rows']),
                           raw_rows_sha256=digest(before['rows']), saved_predictions_matched=len(left),
                           retained_capture_sha256=digest(before), retired_capture_sha256=digest(after)))
    return dict(scope='offline_two_generation_http_raw_and_prediction_parity',
                result='INCOMPLETE' if gaps else 'PASS', raw_history_result='PASS',
                saved_prediction_result='INCOMPLETE' if 'saved_predictions_empty' in gaps else 'PASS', windows=output, missing_evidence=sorted(set(gaps)),
                not_proven=captures[0]['not_proven'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pin = commands.add_parser('bind'); pin.add_argument('--ordinal', type=int, choices=(1, 2), required=True)
    pin.add_argument('--generation', required=True)
    capture = commands.add_parser('capture'); capture.add_argument('--ordinal', type=int, choices=(1, 2), required=True)
    capture.add_argument('--base-url', required=True); capture.add_argument('--phase', choices=('retained', 'retired'), required=True)
    capture.add_argument('--source-sha', required=True); capture.add_argument('--max-pages', type=int, default=128)
    capture.add_argument('--total-seconds', type=float, default=240); capture.add_argument('--request-seconds', type=float, default=4)
    capture.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('compare'); check.add_argument('--captures', type=Path, nargs=4, required=True)
    check.add_argument('--output', type=Path, required=True)
    for sub in (pin, capture, check): sub.add_argument('--binding-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'bind': bind(args.binding_dir, args.ordinal, args.generation); return 0
    if args.output.exists(): raise ValueError('output already exists')
    if args.command == 'capture':
        expected = bindings(args.binding_dir)
        generation = expected[str(args.ordinal)]
        client = LoopbackHTTP(args.base_url, total_seconds=args.total_seconds,
                              request_seconds=args.request_seconds)
        class Recording:
            def __init__(self): self.responses = []
            def get(self, route, **options):
                response = client.get(route, **options)
                self.responses.append(response)
                return response
        recording = Recording()
        try:
            result = collect(recording, generation, args.phase, expected=expected,
                             source_sha=args.source_sha, max_pages=args.max_pages)
        except Exception as error:
            if isinstance(error, HTTPFailure): recording.responses.append(error.response)
            # Preserve successfully received exact bodies even when a later gate
            # fails; errors never turn partial rows into an apparently complete run.
            write_new(args.output, dict(scope='failed_read_only_http_capture', result='FAIL',
                generation_id=generation, phase=args.phase, expected_generations=expected,
                operator_declared_source_sha=args.source_sha, completed_at=utc(),
                failure_type=type(error).__name__, failure_reason=str(error)[:256], responses=recording.responses))
            return 1
    else: result = compare(args.binding_dir, [read_json(path) for path in args.captures])
    write_new(args.output, result)
    return 1 if result.get('result') == 'INCOMPLETE' else 0


if __name__ == '__main__': raise SystemExit(main())
