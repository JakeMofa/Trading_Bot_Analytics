"""Default-off, bounded Supabase raw-object transport for CP6 qualification.

This adapter does not authorize local retirement or structured cloud sync. The
caller owns the lifecycle budget and must verify each uploaded object by fresh
authenticated readback before recording coverage.
"""
from __future__ import annotations

import json
import base64
import binascii
import os
from pathlib import Path
import re
import stat
import threading
import time
import zlib
from urllib.parse import quote
from uuid import UUID

import httpx

from .archive_codec import (ACTIVE_BUDGET, ArchiveIntegrityError, ArchiveLimit,
                            ArchiveUnavailable)


PROJECT_URL = 'https://xttdqeimdujweijxcuro.supabase.co'
BUCKET = 'market-raw'
KEY = re.compile(r'raw-v1/[0-9a-f]{64}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{64}\.jsonl\.gz\Z')
MAX_OBJECT_BYTES = 2 * 1024 * 1024
ERROR_BODY_BYTES = 4096
AUTH_BODY_BYTES = 8192
AUTH_WIRE_BYTES = 16384
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


def _read_machine_file(path: str | Path, *, minimum: int = 1) -> str:
    """Read a private machine-identity field without exposing its contents."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError('invalid Supabase machine credential file') from None
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o077 or
                not minimum <= info.st_size <= 4096):
            raise ValueError('invalid Supabase machine credential file')
        raw = os.read(descriptor, 4097)
        if len(raw) != info.st_size:
            raise ValueError('invalid Supabase machine credential file')
        value = raw.decode('ascii').strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError('invalid Supabase machine credential file')
        return value
    except (OSError, UnicodeError):
        raise ValueError('invalid Supabase machine credential file') from None
    finally:
        os.close(descriptor)


class _MachineSession:
    """One in-memory, restricted Auth session; failed refresh requires restart."""

    def __init__(self, api_key: str, email: str, password: str, uid: str,
                 client: httpx.Client):
        try:
            canonical_uid = str(UUID(uid))
        except (ValueError, AttributeError):
            raise ValueError('invalid Supabase machine identity') from None
        if (canonical_uid != uid or not email or '@' not in email or
                any(c.isspace() for c in email) or not password or
                any(c.isspace() for c in password) or api_key == password):
            raise ValueError('invalid Supabase machine identity')
        self._api_key = api_key
        self._email = email
        self._password = password
        self._uid = uid
        self._client = client
        self._lock = threading.Lock()
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires = 0.0
        self._blocked = False

    def _validate_access(self, access: str) -> float:
        """Sanity-check restricted claims; Storage still verifies the signature."""
        try:
            parts = access.split('.')
            if len(parts) != 3 or len(parts[1]) > 4096:
                raise ValueError('invalid token shape')
            claims = json.loads(base64.urlsafe_b64decode(
                parts[1] + '=' * (-len(parts[1]) % 4)))
            if (not isinstance(claims, dict) or claims.get('sub') != self._uid or
                    claims.get('role') != 'authenticated' or
                    claims.get('iss') != PROJECT_URL + '/auth/v1' or
                    not isinstance(claims.get('exp'), int) or
                    claims['exp'] <= time.time() + 20):
                raise ValueError('unexpected token claims')
            return claims['exp'] - time.time()
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            raise ValueError('invalid restricted Auth token') from None

    def block(self) -> None:
        with self._lock:
            self._blocked = True
            self._access = None
            self._refresh = None

    def token(self, deadline: float) -> str:
        if not self._lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise ArchiveUnavailable('Supabase Auth deadline exceeded')
        try:
            if self._blocked:
                raise ArchiveUnavailable('Supabase Auth session rejected')
            now = time.monotonic()
            if now >= deadline:
                raise ArchiveUnavailable('Supabase Auth deadline exceeded')
            if self._access and now < self._expires:
                return self._access
            grant = 'refresh_token' if self._refresh else 'password'
            payload = ({'refresh_token': self._refresh} if self._refresh else
                       {'email': self._email, 'password': self._password})
            budget = ACTIVE_BUDGET.get()
            timeout = deadline - now
            if budget:
                timeout = min(timeout, budget.request(0))
            try:
                with self._client.stream(
                        'POST', f'{PROJECT_URL}/auth/v1/token?grant_type={grant}',
                        headers={'apikey': self._api_key, 'Cache-Control': 'no-store',
                                 'Accept-Encoding': 'identity'},
                        json=payload, timeout=timeout, follow_redirects=False) as response:
                    if response.status_code >= 500:
                        raise ArchiveUnavailable('Supabase Auth temporarily unavailable')
                    if response.status_code != 200:
                        raise ValueError('Auth rejected')
                    session = json.loads(SupabaseStorageTransport._bounded_auth_body(
                        response, deadline=deadline))
                user = session.get('user')
                access = session.get('access_token')
                refresh = session.get('refresh_token')
                expires = session.get('expires_in')
                if (not isinstance(user, dict) or user.get('id') != self._uid or
                        session.get('token_type', '').lower() != 'bearer' or
                        not isinstance(access, str) or not 20 <= len(access) <= 8192 or
                        not isinstance(refresh, str) or not refresh or
                        len(refresh) > 4096 or any(c.isspace() for c in refresh) or
                        not isinstance(expires, int) or not 30 <= expires <= 86400 or
                        access in (self._api_key, self._password)):
                    raise ValueError('invalid Auth response')
                jwt_remaining = self._validate_access(access)
            except httpx.HTTPError:
                raise ArchiveUnavailable('Supabase Auth temporarily unavailable') from None
            except (ValueError, TypeError, AttributeError, ArchiveLimit,
                    zlib.error):
                self._blocked = True
                self._access = self._refresh = None
                raise ArchiveUnavailable('Supabase Auth session rejected') from None
            self._access, self._refresh = access, refresh
            effective_lifetime = min(expires, jwt_remaining)
            self._expires = (time.monotonic() + effective_lifetime -
                             min(30, effective_lifetime / 4))
            return access
        finally:
            self._lock.release()


class SupabaseStorageTransport:
    """Create-only Storage transport. Privileged mutation authority is unproven."""

    authority_scope = 'supabase-unqualified'

    def __init__(self, api_key: str, access_token: str | None, *, client: httpx.Client | None = None,
                 project_url: str = PROJECT_URL, bucket: str = BUCKET,
                 _machine_mode: bool = False):
        if (project_url != PROJECT_URL or bucket != BUCKET or not api_key or
                (access_token is None and not _machine_mode) or
                (access_token is not None and (not access_token or api_key == access_token)) or
                any(c.isspace() for c in api_key + (access_token or ''))):
            raise ValueError('unreviewed Supabase project, bucket or credential separation')
        self._api_key = api_key
        self._access_token = access_token
        self._client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None
        self._machine: _MachineSession | None = None

    @classmethod
    def from_token_files(cls, api_key_path: str | Path, access_token_path: str | Path,
                         **kwargs):
        return cls(read_token_file(api_key_path), read_token_file(access_token_path),
                   **kwargs)

    @classmethod
    def from_machine_files(cls, api_key_path: str | Path, email_path: str | Path,
                           password_path: str | Path, uid_path: str | Path, **kwargs):
        """Use restricted PP Auth files; refresh tokens remain process-local."""
        api_key = read_token_file(api_key_path)
        if not api_key.startswith('sb_publishable_'):
            raise ValueError('PP requires a Supabase publishable key')
        email = _read_machine_file(email_path)
        password = _read_machine_file(password_path, minimum=20)
        uid = _read_machine_file(uid_path, minimum=36)
        transport = cls(api_key, None, _machine_mode=True, **kwargs)
        transport._machine = _MachineSession(api_key, email, password, uid,
                                             transport._client)
        return transport

    def close(self):
        if self._owns_client:
            self._client.close()

    def _url(self, key: str, *, authenticated: bool) -> str:
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ArchiveIntegrityError('invalid archive object key')
        route = 'object/authenticated' if authenticated else 'object'
        return f'{PROJECT_URL}/storage/v1/{route}/{BUCKET}/{quote(key, safe="/")}'

    def _headers(self, *, upload: bool = False, deadline: float | None = None) -> dict[str, str]:
        if self._machine and deadline is None:
            raise ArchiveLimit('machine Auth requires a request deadline')
        token = (self._machine.token(deadline) if self._machine and deadline is not None
                 else self._access_token)
        headers = {'apikey': self._api_key, 'Authorization': 'Bearer ' + token,
                   'Cache-Control': 'no-store', 'Accept-Encoding': 'identity'}
        if upload:
            headers.update({'Content-Type': 'application/gzip', 'x-upsert': 'false'})
        return headers

    @staticmethod
    def _bounded_auth_body(response: httpx.Response, *, deadline: float) -> bytes:
        """Decode Auth JSON with separate wire/decompressed caps, even for gzip."""
        encoding = response.headers.get('content-encoding', 'identity').lower().strip()
        if encoding not in ('identity', 'gzip'):
            raise ArchiveLimit('unsupported Supabase Auth encoding')
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip' else None
        wire_bytes = 0
        body = bytearray()
        try:
            for chunk in response.iter_raw():
                if time.monotonic() >= deadline:
                    raise ArchiveUnavailable('Supabase Auth deadline exceeded')
                wire_bytes += len(chunk)
                if wire_bytes > AUTH_WIRE_BYTES:
                    raise ArchiveLimit('Supabase Auth wire response exceeds byte limit')
                part = (decoder.decompress(chunk, AUTH_BODY_BYTES - len(body) + 1)
                        if decoder else chunk)
                body.extend(part)
                if len(body) > AUTH_BODY_BYTES or (decoder and decoder.unconsumed_tail):
                    raise ArchiveLimit('Supabase Auth decoded response exceeds byte limit')
        except httpx.StreamConsumed:
            # MockTransport may return an already-decoded, fully buffered body.
            if wire_bytes:
                raise ArchiveLimit('Supabase Auth response stream changed') from None
            buffered = response.content
            if len(buffered) > AUTH_BODY_BYTES:
                raise ArchiveLimit('Supabase Auth decoded response exceeds byte limit')
            if time.monotonic() >= deadline:
                raise ArchiveUnavailable('Supabase Auth deadline exceeded')
            return buffered
        if decoder:
            body.extend(decoder.flush(AUTH_BODY_BYTES - len(body) + 1))
            if (len(body) > AUTH_BODY_BYTES or not decoder.eof or
                    decoder.unused_data):
                raise ArchiveLimit('invalid Supabase Auth gzip response')
        if time.monotonic() >= deadline:
            raise ArchiveUnavailable('Supabase Auth deadline exceeded')
        return bytes(body)

    @staticmethod
    def _bounded_body(response: httpx.Response, limit: int,
                      *, deadline: float | None = None) -> bytes:
        body = bytearray()
        try:
            for chunk in response.iter_raw():
                if deadline is not None and time.monotonic() >= deadline:
                    raise ArchiveUnavailable('Supabase request deadline exceeded')
                body.extend(chunk)
                if len(body) > limit:
                    raise ArchiveLimit('Supabase response exceeds byte limit')
        except httpx.StreamConsumed:
            # MockTransport responses may arrive fully buffered before stream().
            if deadline is not None and time.monotonic() >= deadline:
                raise ArchiveUnavailable('Supabase request deadline exceeded')
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
        deadline = time.monotonic() + timeout
        if not 0 < max_bytes <= MAX_OBJECT_BYTES:
            raise ArchiveLimit('invalid archive read bound')
        try:
            headers = self._headers(deadline=deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ArchiveUnavailable('authenticated archive read deadline exceeded')
            with self._client.stream('GET', url, headers=headers,
                                     timeout=remaining, follow_redirects=False) as response:
                if time.monotonic() >= deadline:
                    raise ArchiveUnavailable('authenticated archive read deadline exceeded')
                if response.status_code in (401, 403) and self._machine:
                    self._machine.block()
                if response.status_code != 200:
                    raise ArchiveUnavailable('authenticated archive read failed')
                length = response.headers.get('content-length')
                if length is not None and (not length.isdigit() or int(length) > max_bytes):
                    raise ArchiveLimit('Supabase response exceeds byte limit')
                return self._bounded_body(response, max_bytes, deadline=deadline)
        except httpx.HTTPError:
            raise ArchiveUnavailable('authenticated archive read failed') from None

    def put_if_absent(self, key: str, data: bytes, *, timeout_seconds: float) -> None:
        url = self._url(key, authenticated=False)
        timeout = self._timeout(timeout_seconds)
        deadline = time.monotonic() + timeout
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_OBJECT_BYTES:
            raise ArchiveLimit('invalid archive upload bound')
        try:
            headers = self._headers(upload=True, deadline=deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ArchiveUnavailable('create-only archive upload deadline exceeded')
            with self._client.stream('POST', url, headers=headers,
                                     content=data, timeout=remaining, follow_redirects=False) as response:
                if time.monotonic() >= deadline:
                    raise ArchiveUnavailable('create-only archive upload deadline exceeded')
                if response.status_code in (401, 403) and self._machine:
                    self._machine.block()
                if response.status_code in (200, 201):
                    return
                if response.status_code not in (400, 409):
                    raise ArchiveUnavailable('create-only archive upload failed')
                body = self._bounded_body(response, ERROR_BODY_BYTES, deadline=deadline)
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
        retry_timeout = min(retry_timeout, deadline - time.monotonic())
        if retry_timeout <= 0:
            raise ArchiveUnavailable('archive readback deadline exceeded')
        if self.read_authenticated(key, max_bytes=MAX_OBJECT_BYTES, timeout_seconds=retry_timeout) != data:
            raise ArchiveIntegrityError('existing archive object differs from proposed bytes')

    def put_structured(self, records: list[dict], *, timeout_seconds: float) -> None:
        raise ArchiveUnavailable('structured cloud sync is not qualified')

    def read_structured_authenticated(self, records: list[dict], *, max_bytes: int,
                                      timeout_seconds: float) -> list[dict]:
        raise ArchiveUnavailable('structured cloud readback is not qualified')
