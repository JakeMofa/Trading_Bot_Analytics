"""Install the dedicated PP Storage Auth files from a private operator stage.

This is an operator-only, offline host action. It never makes a cloud request,
starts a service, or enables raw retirement. A partial installation is a STOP
that requires inspection; it is never silently retried or overwritten.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import uuid


STAGE = Path('/home/ubuntu/.tradebot-pp-storage-stage')
CLOUD = Path('/etc/tradebot/cloud')
MARKER = Path('/etc/tradebot/preprod-host.json')
LOCK = Path('/run/tradebot-pp-deploy/controller.lock')
NAMES = ('pp_storage_api_key', 'supabase_auth_email',
         'supabase_auth_password', 'supabase_auth_uid')
STAGE_NAMES = (*NAMES, 'status')
MAX_SIZE = 4096


class InstallStop(Exception):
    """Failure with no credential content in its public message."""


def _check(condition, reason):
    if not condition:
        raise InstallStop(reason)


def _directory(path, owner, mode):
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise InstallStop('missing_directory') from None
    _check(stat.S_ISDIR(info.st_mode) and info.st_uid == owner
           and stat.S_IMODE(info.st_mode) == mode,
           'unsafe_directory')
    return (info.st_dev, info.st_ino)


def _read_exact(path, owner, mode, *, maximum=MAX_SIZE):
    try:
        before = path.lstat()
    except FileNotFoundError:
        raise InstallStop('missing_file') from None
    _check(stat.S_ISREG(before.st_mode), 'unsafe_file')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        modes = mode if isinstance(mode, tuple) else (mode,)
        _check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
               and info.st_uid == owner and stat.S_IMODE(info.st_mode) in modes
               and 0 < info.st_size <= maximum
               and (before.st_dev, before.st_ino) == (info.st_dev, info.st_ino),
               'unsafe_file')
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        current = path.lstat()
        binding = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                item.st_mtime_ns)
        _check(len(value) == info.st_size and binding(info) == binding(after)
               and binding(after) == binding(current), 'changed_file')
        return value, (info.st_dev, info.st_ino)
    finally:
        os.close(descriptor)


def _line(value, *, allow_no_lf=False):
    _check(b'\r' not in value and b'\x00' not in value,
           'invalid_secret_format')
    if allow_no_lf and b'\n' not in value:
        return value
    _check(value.endswith(b'\n') and value.count(b'\n') == 1,
           'invalid_secret_format')
    return value[:-1]


def _validate_values(values, expected_uid):
    # The separately staged publishable key may be an exact token file with
    # no terminal LF. Auth files originate from the provisioner with one LF.
    key = _line(values['pp_storage_api_key'], allow_no_lf=True)
    email = _line(values['supabase_auth_email'])
    password = _line(values['supabase_auth_password'])
    uid = _line(values['supabase_auth_uid'])
    _check(key.startswith(b'sb_publishable_') and len(key) <= 1024
           and not any(c <= 32 or c >= 127 for c in key), 'invalid_publishable_key')
    _check(re.fullmatch(rb'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9.-]+', email)
           is not None and len(email) <= 254, 'invalid_email')
    _check(re.fullmatch(rb'[0-9a-f]{64}', password) is not None
           and password != key, 'invalid_auth_password')
    _check(uid.decode('ascii') == expected_uid, 'auth_uid_mismatch')


def _host_binding(marker):
    parent = marker.parent.lstat()
    _check(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
           and not parent.st_mode & 0o022, 'unsafe_host_marker_parent')
    raw, _ = _read_exact(marker, 0, (0o600, 0o644), maximum=4096)
    data = json.loads(raw)
    _check(socket.gethostname() == 'tradebot-preprod-01'
           and data.get('environment') == 'preprod'
           and data.get('project') == 'Tradebot'
           and data.get('live_collector_authorized') is False
           and data.get('paid_ai_authorized') is False
           and data.get('production_data_copied') is False,
           'wrong_host_binding')


def install(expected_uid, *, stage=STAGE, cloud=CLOUD, marker=MARKER,
            lock=LOCK, stage_uid=None, check_host=True, root_uid=0):
    _check(os.geteuid() == root_uid, 'root_required')
    _check(isinstance(expected_uid, str)
           and str(uuid.UUID(expected_uid)) == expected_uid,
           'invalid_expected_uid')
    if check_host:
        _host_binding(marker)
    if stage_uid is None:
        stage_uid = pwd.getpwnam('ubuntu').pw_uid
    parent = stage.parent.lstat()
    _check(stat.S_ISDIR(parent.st_mode) and parent.st_uid in
           (stage_uid, root_uid) and not parent.st_mode & 0o022,
           'unsafe_stage_parent')
    stage_identity = _directory(stage, stage_uid, 0o700)
    _directory(cloud, root_uid, 0o700)
    _directory(lock.parent, root_uid, 0o700)
    lock_fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        lock_info = os.fstat(lock_fd)
        _check(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid == root_uid
               and stat.S_IMODE(lock_info.st_mode) == 0o600,
               'unsafe_controller_lock')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _check(set(os.listdir(stage)) == set(STAGE_NAMES),
               'unexpected_stage_files')
        status, status_identity = _read_exact(stage / 'status', stage_uid,
                                               0o400, maximum=128)
        _check(status == b'CREATED_VERIFIED_RESPONSE\n',
               'auth_creation_unconfirmed')
        # Existing destination, including a previous partial attempt, is a
        # reconciliation STOP. No overwrite or implicit credential rotation.
        _check(not any((cloud / name).exists() or (cloud / name).is_symlink()
                       for name in NAMES), 'destination_requires_reconciliation')
        values = {}
        identities = {status_identity}
        source_identities = {}
        for name in NAMES:
            value, identity = _read_exact(stage / name, stage_uid, 0o400)
            _check(identity not in identities, 'aliased_stage_file')
            identities.add(identity)
            source_identities[name] = identity
            values[name] = value
        source_identities['status'] = status_identity
        _validate_values(values, expected_uid)
        # Existing history connection files are deliberately untouched.
        history = {}
        for name in ('pp_history_dsn', 'pp_history_ca'):
            info = (cloud / name).lstat()
            _check(stat.S_ISREG(info.st_mode) and info.st_uid == root_uid
                   and stat.S_IMODE(info.st_mode) ==
                   (0o644 if name == 'pp_history_ca' else 0o600),
                   'unsafe_existing_history_file')
            history[name] = (info.st_dev, info.st_ino, info.st_size,
                             info.st_mtime_ns)
        for name in NAMES:
            destination = cloud / name
            descriptor = os.open(destination,
                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            try:
                with os.fdopen(descriptor, 'wb', closefd=False) as output:
                    _check(output.write(values[name]) == len(values[name]),
                           'short_secret_write')
                    output.flush()
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
            actual, _ = _read_exact(destination, root_uid, 0o600)
            _check(actual == values[name], 'destination_verification_failed')
        for name, old in history.items():
            info = (cloud / name).lstat()
            _check((info.st_dev, info.st_ino, info.st_size,
                    info.st_mtime_ns) == old, 'history_file_changed')
        dir_fd = os.open(cloud, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        # Stage deletion occurs after durable destination verification. A
        # failure leaves a STOP with the root-only destination in place.
        _check(_directory(stage, stage_uid, 0o700) == stage_identity,
               'stage_directory_changed')
        for name in STAGE_NAMES:
            current, identity = _read_exact(stage / name, stage_uid, 0o400,
                                            maximum=128 if name == 'status'
                                            else MAX_SIZE)
            _check(identity == source_identities[name]
                   and current == (status if name == 'status' else values[name]),
                   'stage_file_changed_before_cleanup')
        for name in STAGE_NAMES:
            (stage / name).unlink()
        stage.rmdir()
        return {'result': 'PP_STORAGE_AUTH_INSTALLED', 'files': len(NAMES),
                'cloud_calls': 0, 'services_restarted': 0,
                'retirement': 'off'}
    finally:
        os.close(lock_fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-uid', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        _check(args.execute, 'explicit_execute_required')
        print(json.dumps(install(args.expected_uid), sort_keys=True))
    except Exception:
        raise SystemExit('PP Storage Auth installation STOP; reconcile private stage and destinations') from None
