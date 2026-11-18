"""One bounded, synthetic PP Storage upload/readback probe; never retire data.

Run only after the exact policy and dedicated Auth identity have been reviewed
and applied. The random object is intentionally retained as audit evidence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import uuid

import httpx

from backend.postgres.supabase_storage import PROJECT_URL, BUCKET, read_token_file


ORIGIN = 'pp-live-pp'
ORIGIN_HASH = hashlib.sha256(ORIGIN.encode()).hexdigest()
MAX_BODY = 64 * 1024
MAX_ATTEMPTS = 5  # Auth identity, create, optional ambiguous reconciliation, readback, public denial.


class ProbeFailure(RuntimeError):
    pass


class BoundedClient:
    def __init__(self, client: httpx.Client, *, deadline: float):
        self.client = client
        self.deadline = deadline
        self.attempts = 0

    def seconds(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeFailure('probe deadline exceeded')
        return min(5.0, remaining)

    def request(self, method: str, url: str, *, headers: dict[str, str],
                content: bytes | None = None) -> httpx.Response:
        self.attempts += 1
        if self.attempts > MAX_ATTEMPTS:
            raise ProbeFailure('probe HTTP attempt cap reached')
        try:
            with self.client.stream(method, url, headers=headers, content=content,
                                    timeout=self.seconds(), follow_redirects=False) as response:
                body = bytearray()
                try:
                    for chunk in response.iter_raw():
                        body.extend(chunk)
                        if len(body) > MAX_BODY:
                            raise ProbeFailure('probe HTTP response exceeds bound')
                        self.seconds()
                except httpx.StreamConsumed:
                    # MockTransport may hand us an already-buffered response.
                    body = bytearray(response.content)
                    if len(body) > MAX_BODY:
                        raise ProbeFailure('probe HTTP response exceeds bound')
                return httpx.Response(response.status_code, headers=response.headers,
                                      content=bytes(body))
        except httpx.HTTPError:
            raise ProbeFailure('probe HTTP request failed') from None


def run_probe(api_key: str, access_token: str, uid: str, email: str, *,
              client: httpx.Client, deadline_seconds: float = 30,
              generation_id: uuid.UUID | None = None) -> dict:
    try:
        parsed_uid = uuid.UUID(uid)
    except (TypeError, ValueError, AttributeError):
        raise ProbeFailure('reviewed Auth UID required') from None
    if str(parsed_uid) != uid or parsed_uid.version != 4 or not 0 < deadline_seconds <= 180:
        raise ProbeFailure('reviewed UID or deadline invalid')
    if not isinstance(email, str) or not email:
        raise ProbeFailure('reviewed Auth email required')
    if (not isinstance(api_key, str) or not api_key.startswith('sb_publishable_') or
            len(api_key) <= len('sb_publishable_') or not access_token or
            api_key == access_token or access_token.startswith('sb_secret_') or
            access_token.startswith('sb_publishable_')):
        raise ProbeFailure('publishable project key and separate Auth bearer required')
    bounded = BoundedClient(client, deadline=time.monotonic() + deadline_seconds)
    auth = bounded.request('GET', PROJECT_URL + '/auth/v1/user', headers={
        'apikey': api_key, 'Authorization': 'Bearer ' + access_token,
        'Cache-Control': 'no-store'})
    if auth.status_code != 200:
        raise ProbeFailure('Auth identity preflight failed')
    try:
        user = auth.json()
    except ValueError:
        raise ProbeFailure('Auth identity response invalid') from None
    metadata = user.get('app_metadata') if isinstance(user, dict) else None
    if (not isinstance(user, dict) or user.get('id') != uid or user.get('email') != email or
            user.get('role') != 'authenticated' or not isinstance(metadata, dict) or
            metadata.get('tradebot_role') != 'pp_storage_archive' or
            metadata.get('tradebot_origin') != ORIGIN):
        raise ProbeFailure('Auth identity binding changed')
    generation = generation_id or uuid.uuid4()
    if generation.version != 4:
        raise ProbeFailure('synthetic generation UUID invalid')
    records = [{'probe': 'pp-storage-v1', 'origin': ORIGIN, 'generation': str(generation),
                'sequence': i} for i in (1, 2)]
    body = gzip.compress((''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n'
                                  for row in records)).encode(), mtime=0)
    if len(body) > MAX_BODY:
        raise ProbeFailure('synthetic object exceeds bound')
    digest = hashlib.sha256(body).hexdigest()
    key = f'raw-v1/{ORIGIN_HASH}/{generation}/{digest}.jsonl.gz'
    url = PROJECT_URL + f'/storage/v1/object/{BUCKET}/' + key
    headers = {'apikey': api_key, 'Authorization': 'Bearer ' + access_token,
               'Content-Type': 'application/gzip', 'x-upsert': 'false',
               'Cache-Control': 'no-store'}
    # Never retry the POST. A timeout may have committed the object; GET
    # reconciles that ambiguity using the exact random key and byte digest.
    ambiguous = False
    try:
        uploaded = bounded.request('POST', url, headers=headers, content=body)
        if uploaded.status_code not in (200, 201):
            # A duplicate random key is not a clean success; exact GET below
            # can prove the contents, but still reports an ambiguous upload.
            if uploaded.status_code not in (400, 409):
                raise ProbeFailure('create-only upload rejected')
            ambiguous = True
    except ProbeFailure as error:
        if str(error) != 'probe HTTP request failed':
            raise
        ambiguous = True
    get_headers = {'apikey': api_key, 'Authorization': 'Bearer ' + access_token,
                   'Cache-Control': 'no-store', 'Accept-Encoding': 'identity'}
    readback = bounded.request('GET', PROJECT_URL +
                               f'/storage/v1/object/authenticated/{BUCKET}/' + key,
                               headers=get_headers)
    if readback.status_code != 200 or readback.content != body:
        raise ProbeFailure('authenticated readback failed or bytes changed')
    public = bounded.request('GET', url, headers={'apikey': api_key,
                                                  'Cache-Control': 'no-store'})
    if public.status_code == 200:
        raise ProbeFailure('private object publicly readable')
    if public.status_code not in (400, 401, 403, 404):
        raise ProbeFailure('public denial response is inconclusive')
    return {'result': 'PASS', 'object_key': key, 'bytes': len(body),
            'sha256': digest, 'records': len(records), 'http_attempts': bounded.attempts,
            'ambiguous_upload_reconciled': ambiguous,
            'public_read_denied': True, 'object_retained': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--project-url', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--api-key-file', type=Path, required=True)
    parser.add_argument('--access-token-file', type=Path, required=True)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    if args.project_url != PROJECT_URL or args.bucket != BUCKET:
        raise SystemExit('unreviewed Supabase project or bucket')
    api_key = read_token_file(args.api_key_file)
    access_token = read_token_file(args.access_token_file)
    # No service-role bearer can be accepted as the reviewed Auth user; the
    # /auth/v1/user preflight checks the exact UID and metadata before writes.
    with httpx.Client(trust_env=False) as client:
        result = run_probe(api_key, access_token, args.uid, args.email, client=client)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
