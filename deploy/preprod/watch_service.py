"""Root-owned Benchmark run intent and heartbeat. No trading, deletes or shared-host operations."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.error import HTTPError

from controller import BENCHMARK_INSTANCE, Budget, DeploymentHold, HostBinding, _secure_file, require
from linux_actions import DISPLAY_ORIGIN, RUNTIME_SECRETS, WATCH_LEASE_SECONDS
from transition_control import ACTIVE, ON_AUTHORITY, _atomic_json, _operator, _read_active, session
from structured_probe_control import recurring_control

INTENT = ACTIVE.with_name('benchmark-watch-intent.json')
INSTALLED = Path('/usr/local/lib/tradebot-pp/controller.pyz')
BOOT = Path('/proc/sys/kernel/random/boot_id')
LOCK = Path('/run/tradebot-pp-deploy/controller.lock')
BINDING = (
    'instance',
    'source_sha',
    'controller_sha256',
    'artifact_sha256',
    'image_id',
    'trial_origin',
    'initial_a',
    'nonce',
)


def disarm():
    if INTENT.exists():
        _secure_file(INTENT)
        INTENT.unlink()
        fd = os.open(INTENT.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def binding():
    host = HostBinding.from_marker()
    host.validate()
    require(host.hostname == BENCHMARK_INSTANCE, 'watch_wrong_host')
    active = _read_active()
    require(
        active.get('trial_origin') == DISPLAY_ORIGIN
        and active.get('instance') == host.hostname
        and active['state'] == 'ready_off'
        and active.get('initial_a'),
        'watch_inactive_profile',
    )
    require(
        hashlib.sha256(_secure_file(INSTALLED, private=False)[0]).hexdigest()
        == active['controller_sha256'],
        'watch_controller_drift',
    )
    return {k: active[k] for k in BINDING}


def token():
    path = RUNTIME_SECRETS / 'operator_token'
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == 10001
        and info.st_nlink == 1
        and stat.S_IMODE(info.st_mode) == 0o400,
        'watch_operator_identity',
    )
    value = path.read_text().strip()
    require(len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'watch_operator_identity')
    return value


def failure_cleared(status):
    return not status.get('session_failure_code') or (
        status.get('session_failure_acknowledged') is True
        and status.get('collector_enabled') is False and status.get('process_running') is False
    )


def arm(expected_source, expected_anchor):
    bound = binding()
    require(
        bound['source_sha'] == expected_source and bound['initial_a'] == expected_anchor,
        'watch_binding_drift',
    )
    require(not INTENT.exists() and not INTENT.is_symlink(), 'watch_intent_exists')
    worker = recurring_control('status', Budget(15))
    require(
        worker.get('status') == 'running' and worker.get('source_sha') == expected_source,
        'watch_archive_worker_unavailable',
    )
    seen = _operator(token(), '/collector/status')
    require(
        seen['origin_id'] == DISPLAY_ORIGIN
        and not seen['collector_enabled']
        and not seen['process_running']
        and failure_cleared(seen)
        and seen.get('initialized'),
        'watch_start_state',
    )
    require(
        _operator(token(), '/collector/watch/arm').get('watch_explicit_off') is False, 'watch_arm_refused'
    )
    _atomic_json(
        INTENT,
        {'version': 1, 'state': 'armed', 'binding': bound, 'boot_id': BOOT.read_text().strip()},
        new=True,
    )
    return {'state': 'armed', 'source_sha': expected_source, 'origin': DISPLAY_ORIGIN}


def tick():
    if not INTENT.exists():
        return {'state': 'off'}
    document = json.loads(_secure_file(INTENT)[0])
    if document['state'] == 'held':
        return {'state': 'held', 'reason': document['reason']}
    require(document['version'] == 1 and document['state'] == 'armed', 'watch_invalid_intent')
    bound = binding()
    require(document['binding'] == bound, 'watch_binding_drift')
    boot = BOOT.read_text().strip()
    budget = Budget(60)
    reader = token()
    status = _operator(reader, '/collector/status')
    if status.get('origin_id') == DISPLAY_ORIGIN and status.get('watch_explicit_off') is True:
        disarm()
        return {'state': 'off'}
    require(
        status.get('origin_id') == DISPLAY_ORIGIN and failure_cleared(status),
        'watch_collector_failure',
    )
    worker = recurring_control('status', budget)
    if worker.get('status') != 'running' and boot != document['boot_id']:
        # systemd ran on a new kernel; restore only the exact previously
        # armed worker under the unchanged release and hosted readback proof.
        from trial_cloud_control import start

        if worker.get('status') == 'stopped':
            require(worker.get('source_sha') == bound['source_sha'], 'watch_worker_drift')
            recurring_control('stop', budget)
        start(INSTALLED)
        worker = recurring_control('status', budget)
    require(
        worker.get('status') == 'running' and worker.get('source_sha') == bound['source_sha'],
        'watch_archive_worker_unavailable',
    )
    if status['process_running'] and status['collector_enabled']:
        renewed = _operator(reader, '/collector/watch/renew')
        require(renewed['origin_id'] == DISPLAY_ORIGIN, 'watch_lease_mismatch')
        result = {'state': 'running', **renewed}
    else:
        require(
            not status['process_running']
            and not status['collector_enabled']
            and not status['lease_expired'],
            'watch_inconsistent_writer',
        )
        from install_controller import authorize_live_on

        require(not ON_AUTHORITY.exists(), 'watch_unreconciled_permit')
        authorize_live_on(WATCH_LEASE_SECONDS)
        cmd = f'session-v1 on {WATCH_LEASE_SECONDS} {bound["initial_a"]} {DISPLAY_ORIGIN}'
        owned = session(cmd, INSTALLED)
        require(owned['gate'] == 'PP_LIVE_ON', 'watch_on_unproven')
        result = {
            'state': 'running',
            'origin_id': DISPLAY_ORIGIN,
            'renewable_lease_seconds': WATCH_LEASE_SECONDS,
        }
    if boot != document['boot_id']:
        _atomic_json(INTENT, {**document, 'boot_id': boot})
    return result


def run(action, source=None, anchor=None):
    require(
        os.geteuid() == 0 and HostBinding.from_marker().hostname == BENCHMARK_INSTANCE, 'watch_wrong_host'
    )
    # Same serialization domain as CD, ON/OFF, worker setup and rotation.
    LOCK.parent.mkdir(mode=0o700, exist_ok=True)
    lockdir = LOCK.parent.lstat()
    require(
        stat.S_ISDIR(lockdir.st_mode) and lockdir.st_uid == 0 and not stat.S_IMODE(lockdir.st_mode) & 0o022,
        'unsafe_controller_lock_directory',
    )
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        i = os.fstat(fd)
        require(
            stat.S_ISREG(i.st_mode) and i.st_uid == 0 and stat.S_IMODE(i.st_mode) == 0o600,
            'unsafe_controller_lock',
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if action == 'tick':
                return {'state': 'controller_busy'}
            raise
        if action == 'arm':
            return arm(source, anchor)
        if action == 'off':
            disarm()
            return session('session-v1 off', INSTALLED)
        try:
            return tick()
        except (OSError, ValueError, DeploymentHold) as exc:
            # Connectivity errors can be brief during OS recovery. A previous
            # lease still expires on the database clock. Never create a fresh
            # lease when permissions or ownership could not be proved.
            if isinstance(exc, OSError) and not isinstance(exc, HTTPError):
                return {'state': 'unavailable', 'reason': type(exc).__name__}
            if INTENT.exists():
                doc = json.loads(_secure_file(INTENT)[0])
                _atomic_json(
                    INTENT,
                    {
                        **doc,
                        'state': 'held',
                        'reason': str(exc) if isinstance(exc, DeploymentHold) else type(exc).__name__,
                    },
                )
            raise
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['arm', 'off', 'tick'])
    p.add_argument('--source')
    p.add_argument('--anchor')
    args = p.parse_args()
    print(json.dumps(run(args.action, args.source, args.anchor)), flush=True)


if __name__ == '__main__':
    main()
