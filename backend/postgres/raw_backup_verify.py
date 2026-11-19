"""Verify staged raw backup bytes offline against a separately trusted catalog.

No upload, database access, restoration write, live-state or retirement action.
The required external inventory digest binds exact file bytes; its authenticity
and completeness must be established independently of the staged backup.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .archive_codec import (ArchiveError, ArchiveIntegrityError, ArchiveLimit,
                            ArchiveLimits, ArchiveUnavailable, encoded,
                            manifest_set_hash, row_cursor, sha256, unpack_chunk)

HASH = re.compile(r'^[0-9a-f]{64}$')
CODEC_LIMITS = ArchiveLimits()
INVENTORY_BYTES = 2 * 1024**2
MANIFEST_FIELDS = frozenset({'manifest_id', 'format_version', 'object_key', 'sha256',
                            'row_count', 'byte_count', 'coverage'})
COVERAGE_FIELDS = frozenset({'format_version', 'dataset', 'origin_id', 'generation_id',
                            'after', 'first', 'last', 'decoded_bytes',
                            'decoded_sha256', 'identity_sha256'})


@dataclass(frozen=True)
class RecoveryLimits:
    max_manifests: int = 128
    max_compressed_bytes: int = 64 * 1024**2
    max_decoded_bytes: int = 128 * 1024**2
    max_rows: int = 64000
    max_seconds: float = 60

    def __post_init__(self):
        for name, ceiling in (('max_manifests', 128), ('max_compressed_bytes', 64*1024**2),
                              ('max_decoded_bytes', 128*1024**2), ('max_rows', 64000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError('bounded raw recovery limits required')
        if (isinstance(self.max_seconds, bool) or not isinstance(self.max_seconds, (int, float))
                or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 60):
            raise ValueError('bounded raw recovery deadline required')


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _cursor(value):
    return (value is None or (isinstance(value, list) and len(value) == 2
            and all(isinstance(item, str) and 0 < len(item.encode('utf-8')) <= 4096
                    for item in value)))


def _check_scope(origin_id, generation_id):
    try:
        valid = (isinstance(origin_id, str) and 0 < len(origin_id.encode('utf-8')) <= 160
                 and str(uuid.UUID(generation_id)) == generation_id)
    except (ValueError, AttributeError, TypeError, UnicodeError):
        valid = False
    if not valid:
        raise ArchiveIntegrityError('exact raw recovery scope required')


def _directory(path):
    """Walk from / using directory descriptors; never follow a symlink."""
    path = Path(path)
    descriptor = None
    try:
        if not path.is_absolute() or any(part == '..' for part in path.parts):
            raise ArchiveIntegrityError('unsafe raw backup directory')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open('/', flags)
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        result, descriptor = descriptor, None
        return result
    except ArchiveError:
        raise
    except (OSError, ValueError):
        raise ArchiveUnavailable('raw backup directory unavailable') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_at(root_fd, key, maximum, check, *, expected_size=None):
    """Traverse only descriptor-relative plain directories and regular files."""
    descriptors = []
    try:
        parts = key.split('/')
        if not parts or any(part in ('', '.', '..') or '\\' in part for part in parts):
            raise ArchiveIntegrityError('unsafe staged raw object path')
        parent = root_fd
        for part in parts[:-1]:
            check()
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
            descriptors.append(parent)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=parent)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 1 <= before.st_size <= maximum
                or (expected_size is not None and before.st_size != expected_size)):
            raise ArchiveIntegrityError('staged raw file size or type mismatch')
        chunks, size = [], 0
        while True:
            check()
            chunk = os.read(descriptor, min(64*1024, maximum+1-size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise ArchiveLimit('staged raw file exceeds byte limit')
        after = os.fstat(descriptor)
        if (size != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ArchiveIntegrityError('staged raw file changed during verification')
        check()
        return b''.join(chunks)
    except ArchiveError:
        raise
    except (OSError, ValueError):
        raise ArchiveUnavailable('staged raw file unavailable') from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveIntegrityError('duplicate raw inventory field')
        result[key] = value
    return result


def _invalid_constant(_):
    raise ArchiveIntegrityError('invalid raw inventory JSON constant')


def _catalog(inventory, origin_id, generation_id, limits):
    if not isinstance(inventory, dict) or set(inventory) != {'generation', 'manifests'}:
        raise ArchiveIntegrityError('raw backup inventory shape mismatch')
    generation, manifests = inventory['generation'], inventory['manifests']
    if (not isinstance(generation, dict)
            or set(generation) != {'origin_id', 'generation_id', 'seal_count', 'seal_hash'}
            or generation['origin_id'] != origin_id or generation['generation_id'] != generation_id
            or type(generation['seal_count']) is not int or not 0 <= generation['seal_count'] <= limits.max_rows
            or not _hash(generation['seal_hash'])
            or not isinstance(manifests, list) or not 1 <= len(manifests) <= limits.max_manifests):
        raise ArchiveIntegrityError('raw backup inventory scope or bounds mismatch')
    after, count, compressed, decoded = None, 0, 0, 0
    for index, item in enumerate(manifests):
        if not isinstance(item, dict) or set(item) != MANIFEST_FIELDS:
            raise ArchiveIntegrityError('raw manifest shape mismatch')
        coverage = item['coverage']
        if (type(item['format_version']) is not int or item['format_version'] != 1
                or item['manifest_id'] != f'raw.events:{index:012d}'
                or not _hash(item['sha256'])
                or item['object_key'] != f'raw-v1/{sha256(origin_id.encode())}/{generation_id}/{item["sha256"]}.jsonl.gz'
                or type(item['row_count']) is not int or not 0 <= item['row_count'] <= CODEC_LIMITS.max_rows
                or type(item['byte_count']) is not int or not 1 <= item['byte_count'] <= CODEC_LIMITS.max_object_bytes
                or not isinstance(coverage, dict) or set(coverage) != COVERAGE_FIELDS):
            raise ArchiveIntegrityError('raw manifest identity or bounds mismatch')
        if (type(coverage['format_version']) is not int or coverage['format_version'] != 1
                or coverage['dataset'] != 'raw.events' or coverage['origin_id'] != origin_id
                or coverage['generation_id'] != generation_id or coverage['after'] != after
                or any(not _cursor(coverage[key]) for key in ('after', 'first', 'last'))
                or type(coverage['decoded_bytes']) is not int
                or not 1 <= coverage['decoded_bytes'] <= CODEC_LIMITS.max_decoded_bytes
                or not _hash(coverage['decoded_sha256']) or not _hash(coverage['identity_sha256'])):
            raise ArchiveIntegrityError('raw manifest coverage mismatch')
        if item['row_count'] == 0:
            if len(manifests) != 1 or coverage['first'] is not None or coverage['last'] is not None:
                raise ArchiveIntegrityError('empty raw chunk inside generation')
        elif (coverage['first'] is None or coverage['last'] is None
                or coverage['first'] > coverage['last']
                or (after is not None and coverage['first'] <= after)):
            raise ArchiveIntegrityError('raw manifest event order mismatch')
        count += item['row_count']; compressed += item['byte_count']; decoded += coverage['decoded_bytes']
        after = coverage['last']
    if count != generation['seal_count'] or manifest_set_hash(manifests) != generation['seal_hash']:
        raise ArchiveIntegrityError('raw backup generation catalog incomplete or changed')
    if compressed > limits.max_compressed_bytes or decoded > limits.max_decoded_bytes:
        raise ArchiveLimit('raw backup aggregate byte budget exceeded')
    return manifests, count, compressed, decoded


def verify_backup(inventory_path, *, expected_inventory_sha256, backup_root,
                  origin_id, generation_id, limits=RecoveryLimits(), clock=time.monotonic):
    """Verify complete staged raw scope, conditional on the trusted input catalog.

    Budgets are checked between local file/decode operations. They cannot cancel
    an arbitrary blocked filesystem/kernel operation. Only one chunk is decoded
    at a time. No decoded rows are returned or written.
    """
    started = clock()
    def check():
        if clock()-started >= limits.max_seconds:
            raise ArchiveLimit('raw backup verification deadline reached')
    _check_scope(origin_id, generation_id)
    if not _hash(expected_inventory_sha256):
        raise ArchiveIntegrityError('external raw inventory digest required')
    path = Path(inventory_path)
    directory = _directory(path.parent)
    try:
        raw = _read_at(directory, path.name, INVENTORY_BYTES, check)
    finally:
        os.close(directory)
    if sha256(raw) != expected_inventory_sha256:
        raise ArchiveIntegrityError('trusted raw inventory digest mismatch')
    try:
        inventory = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        manifests, expected_rows, compressed, decoded = _catalog(inventory, origin_id, generation_id, limits)
    except ArchiveError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ArchiveIntegrityError('raw backup inventory invalid') from None
    check()
    directory = _directory(backup_root)
    row_hash, identity_hash = hashlib.sha256(), hashlib.sha256(b'[')
    recovered, previous = 0, None
    try:
        for item in manifests:
            check()
            blob = _read_at(directory, item['object_key'], CODEC_LIMITS.max_object_bytes, check,
                            expected_size=item['byte_count'])
            try:
                rows = unpack_chunk(blob, item, CODEC_LIMITS)
                for row in rows:
                    cursor = row_cursor(row)
                    if previous is not None and cursor <= previous:
                        raise ArchiveIntegrityError('recovered raw event order mismatch')
                    row_hash.update(encoded(row)+b'\n')
                    if recovered:
                        identity_hash.update(b',')
                    identity_hash.update(encoded(cursor))
                    previous = cursor; recovered += 1
            except ArchiveError:
                raise
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                raise ArchiveIntegrityError('recovered raw data invalid') from None
            check()
    finally:
        os.close(directory)
    identity_hash.update(b']')
    if recovered != expected_rows:
        raise ArchiveIntegrityError('recovered raw generation row count mismatch')
    result = {'status': 'verified_staged_raw_backup', 'origin_id': origin_id, 'generation_id': generation_id,
              'inventory_sha256': expected_inventory_sha256, 'seal_hash': inventory['generation']['seal_hash'],
              'objects': len(manifests), 'rows': recovered, 'compressed_bytes': compressed,
              'decoded_bytes': decoded, 'recovered_rows_sha256': row_hash.hexdigest(),
              'recovered_identity_sha256': identity_hash.hexdigest(),
              'coverage': 'complete_generation_conditional_on_trusted_inventory',
              'historical_only': True, 'official_settlement': False, 'retirement_authority': False,
              'network_used': False, 'data_written': False}
    check()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--expected-inventory-sha256', required=True)
    parser.add_argument('--backup-root', required=True)
    parser.add_argument('--origin-id', required=True)
    parser.add_argument('--generation-id', required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_backup(args.inventory, expected_inventory_sha256=args.expected_inventory_sha256,
            backup_root=args.backup_root, origin_id=args.origin_id, generation_id=args.generation_id)
    except ArchiveError as error:
        print(json.dumps({'status': 'hold', 'code': error.code}))
        return 1
    except Exception:
        print(json.dumps({'status': 'hold', 'code': 'raw_backup_verification_failed'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
