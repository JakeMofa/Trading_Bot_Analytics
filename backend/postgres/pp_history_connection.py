"""Default-off PP-only Supabase history connection binding.

No deployed service constructs this factory. The connection secret stays in a
mounted file; errors deliberately omit connection strings and credentials.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import ssl
import stat
import time

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable


PP_POOLER_HOST = 'aws-1-us-west-2.pooler.supabase.com'
PP_POOLER_USER = 'tradebot_pp_history.xttdqeimdujweijxcuro'
PP_CA_DER_SHA256 = '807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
DEFAULT_DSN_FILE = Path('/run/secrets/pp_history_dsn')
DEFAULT_CA_FILE = Path('/run/secrets/pp_history_ca')


def _read_file(path: Path, *, max_bytes: int, private: bool) -> bytes:
    if not path.is_absolute():
        raise ArchiveIntegrityError('private PP history binding invalid')
    try:
        directory = path.parent.lstat()
        if (not stat.S_ISDIR(directory.st_mode) or
                directory.st_uid not in (0, os.geteuid()) or
                directory.st_mode & 0o022):
            raise ArchiveIntegrityError('private PP history binding invalid')
    except ArchiveIntegrityError:
        raise
    except OSError:
        raise ArchiveIntegrityError('private PP history binding unavailable') from None
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                    before.st_uid not in (0, os.geteuid()) or
                    not 1 <= before.st_size <= max_bytes or
                    (before.st_mode & (0o077 if private else 0o022)) or
                    (before.st_mode & 0o111)):
                raise ArchiveIntegrityError('private PP history binding invalid')
            value = os.read(descriptor, max_bytes + 1)
            after = os.fstat(descriptor)
            if (len(value) != before.st_size or len(value) > max_bytes or
                    (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) !=
                    (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)):
                raise ArchiveIntegrityError('private PP history binding changed')
            return value
        finally:
            os.close(descriptor)
    except ArchiveIntegrityError:
        raise
    except OSError:
        raise ArchiveIntegrityError('private PP history binding unavailable') from None


class PPHistoryConnectionFactory:
    """Create one bounded psycopg connection to the exact private PP origin.

    The configured DSN's path and TLS fields are validated again on every
    call. A single pooler host keeps libpq's per-host timeout bounded. Requests
    with less than two seconds left fail before opening a network connection.
    """

    def __init__(self, dsn_file: str | Path = DEFAULT_DSN_FILE,
                 ca_file: str | Path = DEFAULT_CA_FILE):
        self.dsn_file, self.ca_file = Path(dsn_file), Path(ca_file)
        if self.dsn_file == self.ca_file:
            raise ArchiveIntegrityError('private PP history files must differ')

    def _validated_dsn(self, timeout_seconds: float):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or
                not 2 <= timeout_seconds <= 60):
            raise ArchiveLimit('private PP history connect budget too small')
        deadline = time.monotonic() + timeout_seconds
        ca = _read_file(self.ca_file, max_bytes=16 * 1024, private=False)
        try:
            pem = ca.decode('ascii')
            if pem.count('-----BEGIN CERTIFICATE-----') != 1:
                raise ValueError('certificate count')
            fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        except (ValueError, UnicodeError):
            raise ArchiveIntegrityError('private PP history CA invalid') from None
        if fingerprint != PP_CA_DER_SHA256:
            raise ArchiveIntegrityError('private PP history CA mismatch')

        secret = _read_file(self.dsn_file, max_bytes=4096, private=True)
        try:
            from psycopg.conninfo import conninfo_to_dict

            values = conninfo_to_dict(secret.decode('utf-8').strip())
            expected = {
                'host': PP_POOLER_HOST, 'port': '5432', 'dbname': 'postgres',
                'user': PP_POOLER_USER, 'sslmode': 'verify-full',
                'sslrootcert': str(self.ca_file), 'connect_timeout': '5',
                'application_name': 'tradebot_pp_history',
            }
            if (set(values) != set(expected) | {'password'} or
                    any(values[key] != value for key, value in expected.items()) or
                    not isinstance(values['password'], str) or
                    len(values['password']) < 32):
                raise ValueError('unexpected connection scope')
        except Exception:
            raise ArchiveIntegrityError('private PP history DSN invalid') from None

        return secret, deadline

    def __call__(self, *, timeout_seconds: float):
        secret, deadline = self._validated_dsn(timeout_seconds)
        return self._open(secret, deadline)

    @staticmethod
    def _open(secret, deadline):
        remaining = deadline - time.monotonic()
        if remaining < 2:
            raise ArchiveLimit('private PP history connect budget exhausted')
        # libpq connect_timeout is integer seconds (and at least two). Floor
        # avoids giving connection establishment more time than the caller.
        connect_timeout = min(5, math.floor(remaining))
        connection = None
        try:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(secret.decode('utf-8').strip(),
                                         row_factory=dict_row,
                                         connect_timeout=connect_timeout)
            if time.monotonic() >= deadline:
                connection.close()
                raise ArchiveLimit('private PP history connection deadline reached')
            return connection
        except ArchiveLimit:
            raise
        except Exception:
            if connection is not None:
                connection.close()
            raise ArchiveUnavailable('private PP history connection unavailable') from None
