"""Time a fixed synthetic PP transfer; creates objects only with --execute."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import zlib

import httpx

from postgres.supabase_storage import BUCKET, PROJECT_URL, SupabaseStorageTransport

# The read-only pp.15 pack measurement from the 4,845 retained raw events.
SIZES = (64139, 63443, 66029, 62054, 63457, 63041, 64757, 65171, 61357, 47101)
ORIGIN = 'pp-live-pp'
GENERATION = '7eb0e05c-8893-43e7-8869-b40d1078e3c6'
PREFIX = f'raw-v1/{hashlib.sha256(ORIGIN.encode()).hexdigest()}/{GENERATION}/'
DEADLINE_SECONDS = 60
REQUEST_SECONDS = 4


class TransferHold(RuntimeError):
    pass


def fixture(index, size):
    """A stable gzip member with the same wire size on every Python/zlib version."""
    # Stored DEFLATE blocks carry at most 32 KiB. The member has a 10-byte
    # gzip header, a five-byte header per block and an eight-byte trailer.
    blocks = (size - 18 + 32772) // 32773
    payload_bytes = size - 18 - blocks * 5
    prefix = f'{{"fixture":"synthetic_pp_transfer_v1","part":{index},"padding":"'.encode()
    suffix = b'"}\n'
    padding_length = payload_bytes - len(prefix) - len(suffix)
    seed = f'{GENERATION}/{index}'.encode()
    entropy = hashlib.shake_256(seed).digest((padding_length * 3 + 3) // 4)
    padding = base64.urlsafe_b64encode(entropy)[:padding_length]
    body = prefix + padding + suffix
    member = bytearray(bytes.fromhex('1f8b08000000000000ff'))
    for offset in range(0, len(body), 32768):
        block = body[offset:offset + 32768]
        final = offset + len(block) == len(body)
        member.extend(struct.pack('<BHH', int(final), len(block), len(block) ^ 0xffff))
        member.extend(block)
    member.extend(struct.pack('<II', zlib.crc32(body), len(body)))
    blob = bytes(member)
    if len(blob) != size or gzip.decompress(blob) != body:
        raise ValueError('unexpected fixture length or contents')
    return PREFIX + hashlib.sha256(blob).hexdigest() + '.jsonl.gz', blob


def objects():
    return [fixture(i, size) for i, size in enumerate(SIZES, 1)]


class RequestBounds:
    def __init__(self, items):
        self.started = time.monotonic()
        self.count = 0
        self.allowed = {('POST', PROJECT_URL + '/auth/v1/token?grant_type=password'): 1}
        for key, _ in items:
            self.allowed[('POST', f'{PROJECT_URL}/storage/v1/object/{BUCKET}/{key}')] = 1
            self.allowed[('GET', f'{PROJECT_URL}/storage/v1/object/authenticated/{BUCKET}/{key}')] = 2

    def timeout(self):
        remaining = DEADLINE_SECONDS - (time.monotonic() - self.started)
        if remaining <= 0:
            raise TransferHold('time_exhausted')
        return min(remaining, REQUEST_SECONDS)

    def request(self, request):
        self.timeout()
        binding = (request.method, str(request.url))
        if self.allowed.get(binding, 0) < 1:
            raise TransferHold('unexpected_or_repeated_request')
        if request.url.path.startswith('/storage/') and request.method == 'POST':
            if request.headers.get('x-upsert') != 'false':
                raise TransferHold('create_only_required')
        self.allowed[binding] -= 1
        self.count += 1

    def response(self, response):
        # A duplicate/ambiguous write could establish byte identity, but
        # cannot qualify fresh upload timing. Never replay a timed upload.
        if response.status_code not in (200, 201):
            raise TransferHold(f'http_{response.status_code}')


def measure(storage, items, bounds):
    report = {'synthetic_generation': GENERATION, 'uploads': [], 'first_reads': [],
              'final_reads': [], 'starts_collector': False, 'writes_retirement_records': False}

    def record(operation, key, blob):
        start = time.monotonic()
        if operation == 'uploads':
            storage.put_if_absent(key, blob, timeout_seconds=bounds.timeout())
        else:
            found = storage.read_authenticated(key, max_bytes=len(blob),
                                               timeout_seconds=bounds.timeout())
            if found != blob:
                raise TransferHold('exact_readback_failed')
        report[operation].append({'bytes': len(blob), 'seconds': time.monotonic() - start})
        bounds.timeout()

    for key, blob in items:
        record('uploads', key, blob)
        record('first_reads', key, blob)
    for key, blob in items:
        record('final_reads', key, blob)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    items = objects()
    if not args.execute:
        print(json.dumps({'generation': GENERATION, 'objects': [
            {'key': key, 'bytes': len(blob)} for key, blob in items]}))
        return 0
    bounds = RequestBounds(items)
    try:
        with httpx.Client(trust_env=False, follow_redirects=False,
                event_hooks={'request': [bounds.request], 'response': [bounds.response]}) as client:
            secrets = Path('/run/secrets')
            transport = SupabaseStorageTransport.from_machine_files(
                secrets/'pp_storage_api_key', secrets/'supabase_auth_email',
                secrets/'supabase_auth_password', secrets/'supabase_auth_uid', client=client)
            report = measure(transport, items, bounds)
        if bounds.count != 31 or any(bounds.allowed.values()):
            raise TransferHold('unexpected_request_count')
        print(json.dumps(dict(report, status='verified', requests=bounds.count,
                              total_seconds=time.monotonic() - bounds.started)))
    except Exception as error:
        reason = str(error) if isinstance(error, TransferHold) else type(error).__name__
        print(json.dumps({'status': 'hold', 'reason': reason, 'requests': bounds.count,
                          'seconds': time.monotonic() - bounds.started,
                          'possible_partial_objects_retained': True}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
