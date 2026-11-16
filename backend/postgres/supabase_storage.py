"""Default-off, bounded Supabase raw-object transport for CP6 qualification.

This adapter does not authorize local retirement or structured cloud sync. The
caller owns the lifecycle budget and must verify each uploaded object by fresh
authenticated readback before recording coverage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote

import httpx

from .archive_codec import (ACTIVE_BUDGET, ArchiveIntegrityError, ArchiveLimit,
                            ArchiveUnavailable)


PROJECT_URL = 'https://xttdqeimdujweijxcuro.supabase.co'
BUCKET = 'market-raw'
KEY = re.compile(r'raw-v1/[0-9a-f]{64}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{64}\.jsonl\.gz\Z')
MAX_OBJECT_BYTES = 2 * 1024 * 1024
ERROR_BODY_BYTES = 4096
EXISTS_CODES = frozenset({'KeyAlreadyExists', 'ResourceAlreadyExists', 'Duplicate'})


def read_token_file(path: str | Path) -> str:
    """Read only a private regular secret file; never put its value in errors."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError('invalid Supabase credential file') from None
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o077 or
                not 20 <= info.st_size <= 4096):
            raise ValueError('invalid Supabase credential file')
        raw = os.read(descriptor, 4097)
        if len(raw) != info.st_size:
            raise ValueError('invalid Supabase credential file')
        token = raw.decode('ascii').strip()
        if not token or any(character.isspace() for character in token):
            raise ValueError('invalid Supabase credential file')
        return token
    except (OSError, UnicodeError) as error:
        raise ValueError('invalid Supabase credential file') from None
    finally:
        os.close(descriptor)


class SupabaseStorageTransport:
    """Create-only Storage transport. Privileged mutation authority is unproven."""

    authority_scope = 'supabase-unqualified'

    def __init__(self, api_key: str, access_token: str, *, client: httpx.Client | None = None,
                 project_url: str = PROJECT_URL, bucket: str = BUCKET):
        if (project_url != PROJECT_URL or bucket != BUCKET or not api_key or not access_token or
                api_key == access_token or any(c.isspace() for c in api_key + access_token)):
            raise ValueError('unreviewed Supabase project, bucket or credential separation')
        self._api_key = api_key
        self._access_token = access_token
        self._client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None

    @classmethod
    def from_token_files(cls, api_key_path: str | Path, access_token_path: str | Path,
                         **kwargs):
        return cls(read_token_file(api_key_path), read_token_file(access_token_path),
                   **kwargs)

    def close(self):
        if self._owns_client:
            self._client.close()

    def _url(self, key: str, *, authenticated: bool) -> str:
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ArchiveIntegrityError('invalid archive object key')
        route = 'object/authenticated' if authenticated else 'object'
        return f'{PROJECT_URL}/storage/v1/{route}/{BUCKET}/{quote(key, safe="/")}'

    def _headers(self, *, upload: bool = False) -> dict[str, str]:
        headers = {'apikey': self._api_key, 'Authorization': 'Bearer ' + self._access_token,
                   'Cache-Control': 'no-store', 'Accept-Encoding': 'identity'}
        if upload:
            headers.update({'Content-Type': 'application/gzip', 'x-upsert': 'false'})
        return headers

    @staticmethod
    def _bounded_body(response: httpx.Response, limit: int) -> bytes:
        body = bytearray()
        try:
            for chunk in response.iter_raw():
                body.extend(chunk)
                if len(body) > limit:
                    raise ArchiveLimit('Supabase response exceeds byte limit')
        except httpx.StreamConsumed:
            # MockTransport responses may arrive fully buffered before stream().
            body = bytearray(response.content)
            if len(body) > limit:
                raise ArchiveLimit('Supabase response exceeds byte limit')
        return bytes(body)

    @staticmethod
    def _timeout(value: float) -> float:
        if not isinstance(value, (int, float)) or not 0 < value <= 60:
            raise ArchiveLimit('invalid cloud request deadline')
        return float(value)

    def read_authenticated(self, key: str, *, max_bytes: int,
                           timeout_seconds: float) -> bytes:
        url = self._url(key, authenticated=True)
        timeout = self._timeout(timeout_seconds)
        if not 0 < max_bytes <= MAX_OBJECT_BYTES:
            raise ArchiveLimit('invalid archive read bound')
        try:
            with self._client.stream('GET', url, headers=self._headers(),
                                     timeout=timeout, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ArchiveUnavailable('authenticated archive read failed')
                length = response.headers.get('content-length')
                if length is not None and (not length.isdigit() or int(length) > max_bytes):
                    raise ArchiveLimit('Supabase response exceeds byte limit')
                return self._bounded_body(response, max_bytes)
        except httpx.HTTPError:
            raise ArchiveUnavailable('authenticated archive read failed') from None

    def put_if_absent(self, key: str, data: bytes, *, timeout_seconds: float) -> None:
        url = self._url(key, authenticated=False)
        timeout = self._timeout(timeout_seconds)
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_OBJECT_BYTES:
            raise ArchiveLimit('invalid archive upload bound')
        try:
            with self._client.stream('POST', url, headers=self._headers(upload=True),
                                     content=data, timeout=timeout, follow_redirects=False) as response:
                if response.status_code in (200, 201):
                    return
                if response.status_code not in (400, 409):
                    raise ArchiveUnavailable('create-only archive upload failed')
                body = self._bounded_body(response, ERROR_BODY_BYTES)
                try:
                    detail = json.loads(body)
                except (ValueError, UnicodeError):
                    raise ArchiveUnavailable('create-only archive upload failed') from None
                if not isinstance(detail, dict) or not any(detail.get(name) in EXISTS_CODES
                                                            for name in ('code', 'error')):
                    raise ArchiveUnavailable('create-only archive upload failed')
        except httpx.HTTPError:
            raise ArchiveUnavailable('create-only archive upload failed') from None
        budget = ACTIVE_BUDGET.get()
        retry_timeout = budget.request(len(data)) if budget else timeout
        if self.read_authenticated(key, max_bytes=MAX_OBJECT_BYTES, timeout_seconds=retry_timeout) != data:
            raise ArchiveIntegrityError('existing archive object differs from proposed bytes')

    def put_structured(self, records: list[dict], *, timeout_seconds: float) -> None:
        raise ArchiveUnavailable('structured cloud sync is not qualified')

    def read_structured_authenticated(self, records: list[dict], *, max_bytes: int,
                                      timeout_seconds: float) -> list[dict]:
        raise ArchiveUnavailable('structured cloud readback is not qualified')
