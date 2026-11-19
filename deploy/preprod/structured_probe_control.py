"""Root-owned, PP-only one-shot structured history diagnostic control.

The installed controller invokes this module explicitly. Normal CD never
loads the extra Compose file. Preflight is read-only; execute requires a fresh
one-use root authority for the exact reviewed outbox page.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import uuid

from controller import Budget, DeploymentHold, HostBinding, _secure_file, require
from linux_actions import LinuxActions, PROJECT, RUNTIME_SECRETS
from structured_probe_profile import LOCAL_STAGED, validate_probe_profile
from transition_control import ACTIVE, _candidate, _consume, _image_binding, _owned_runtime, _read_active, TransitionRequest

AUTHORITY = Path('/run/tradebot-pp-deploy/structured-probe.json')
CLOUD_DIR = Path('/etc/tradebot/cloud')
STAGED_LOCAL = Path(LOCAL_STAGED)
CA_SHA256 = '807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
EXPECTED_MODULES = ('backend/postgres/pp_structured_probe.py',
                    'backend/postgres/pp_history_connection.py')
CHILD_REASON_CODES = {
    'archive_error': 'pp_structured_archive_error',
    'archive_limit': 'pp_structured_archive_limit',
    'archive_integrity': 'pp_structured_archive_integrity',
    'archive_unavailable': 'pp_structured_archive_unavailable',
    'lifecycle_hold': 'pp_structured_lifecycle_hold',
    'OperationalError': 'pp_structured_database_unavailable',
    'IntegrityError': 'pp_structured_database_integrity',
    'TimeoutError': 'pp_structured_timeout',
}
PUBLIC_FAILURE_CODES = frozenset(CHILD_REASON_CODES.values()) | {'pp_structured_probe_failed'}


def _public_child_failure(raw: bytes) -> str:
    """Accept only the child's fixed, non-sensitive failure envelope."""
    if len(raw) > 2048:
        return 'pp_structured_probe_failed'
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate key')
                result[key] = value
            return result
        report = json.loads(raw, object_pairs_hook=unique_pairs)
        if (type(report) is dict and set(report) ==
                {'status', 'reason', 'ack_status', 'retirement'} and
                report['status'] == 'HOLD' and
                report['ack_status'] == 'unconfirmed_after_error' and
                report['retirement'] == 'off' and
                type(report['reason']) is str):
            return CHILD_REASON_CODES.get(report['reason'], 'pp_structured_probe_failed')
    except (UnicodeError, ValueError, TypeError):
        pass
    return 'pp_structured_probe_failed'


def _files():
    directory = CLOUD_DIR.lstat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == 0
            and stat.S_IMODE(directory.st_mode) == 0o700,
            'unsafe_pp_cloud_directory')
    identities = set()
    for name, mode, limit in (('pp_history_dsn', 0o600, 4096),
                              ('pp_history_ca', 0o644, 16 * 1024)):
        path = CLOUD_DIR / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode
                and 0 < info.st_size <= limit, 'unsafe_pp_cloud_file')
        identity = (info.st_dev, info.st_ino)
        require(identity not in identities, 'duplicate_pp_cloud_file')
        identities.add(identity)
    pem = (CLOUD_DIR / 'pp_history_ca').read_text(encoding='ascii')
    require(pem.count('-----BEGIN CERTIFICATE-----') == 1,
            'invalid_pp_cloud_ca')
    require(hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() == CA_SHA256,
            'wrong_pp_cloud_ca')
    # The local lifecycle credential must remain separate from cloud secrets.
    local = (RUNTIME_SECRETS / 'lifecycle_dsn').lstat()
    require(stat.S_ISREG(local.st_mode) and local.st_uid == 10001
            and stat.S_IMODE(local.st_mode) == 0o400 and local.st_nlink == 1
            and 0 < local.st_size <= 4096,
            'unsafe_local_lifecycle_file')
    require(not STAGED_LOCAL.exists() and not STAGED_LOCAL.is_symlink(),
            'stale_probe_local_secret_requires_reconciliation')


@contextmanager
def _stage_local_secret(source=None, staged=None):
    """Give the capability-free root container a root0600 PP local DSN.

    The original lifecycle file is UID10001/0400 and cannot be read by UID0
    after cap_drop ALL. This short-lived credential copy is in root-only /run;
    it is never a database copy, configuration change or persistent mount.
    """
    source = source or RUNTIME_SECRETS / 'lifecycle_dsn'
    staged = staged or STAGED_LOCAL
    parent = staged.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
            and stat.S_IMODE(parent.st_mode) == 0o700,
            'unsafe_probe_staging_directory')
    path_before = source.lstat()
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(source_fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 10001
                and stat.S_IMODE(before.st_mode) == 0o400
                and before.st_nlink == 1 and 0 < before.st_size <= 4096,
                'unsafe_local_lifecycle_file')
        require((path_before.st_dev, path_before.st_ino) ==
                (before.st_dev, before.st_ino),
                'local_lifecycle_file_changed')
        value = os.read(source_fd, 4097)
        after = os.fstat(source_fd)
        path_after = source.lstat()
        require(len(value) == before.st_size and len(value) <= 4096
                and (before.st_dev, before.st_ino, before.st_mtime_ns,
                     before.st_size) ==
                    (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
                and (path_after.st_dev, path_after.st_ino, path_after.st_mtime_ns,
                     path_after.st_size) ==
                    (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size),
                'local_lifecycle_file_changed')
    finally:
        os.close(source_fd)
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    identity = None
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                'unsafe_probe_staged_file')
        with os.fdopen(descriptor, 'wb') as output:
            descriptor = -1
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        yield
    finally:
        if descriptor != -1:
            os.close(descriptor)
        # Stop the one-shot container before exiting this context. Even if
        # that stop failed, unlink the pathname and report cleanup failure.
        try:
            current = staged.lstat()
            require(identity is not None and
                    (current.st_dev, current.st_ino) == identity,
                    'probe_staged_file_replaced')
            staged.unlink()
            directory = os.open(staged.parent,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(directory)
            finally: os.close(directory)
        except (OSError, DeploymentHold):
            raise DeploymentHold('probe_local_secret_cleanup_failed') from None


def _compose(actions, context, budget, extra, args, timeout, *, capture_exit=False):
    folder = context.source / 'deploy/preprod'
    files = [folder / 'compose.yaml', folder / 'runtime.compose.yaml', *
             (folder / name for name in extra)]
    command = ['docker', 'compose', '--env-file', '/dev/null',
               '--project-name', PROJECT, '--project-directory', str(folder)]
    for path in files:
        command += ['-f', str(path)]
    result = budget.run([*command, '--profile', 'migration', '--profile',
                         'structured_probe', *args], cwd=context.source,
                        env=actions._environment(context.image), timeout=timeout,
                        **({'return_status': True, 'output_limit': 2048}
                           if capture_exit else {}))
    if capture_exit:
        status, stdout = result
        if status != 0:
            raise DeploymentHold(_public_child_failure(stdout))
        return stdout
    return result


def preflight(installed: Path, budget: Budget):
    HostBinding.from_marker().validate()
    require(ACTIVE.exists() and not ACTIVE.is_symlink(), 'pp_live_profile_required')
    active = _read_active()
    require(active['state'] == 'ready_off', 'pp_live_profile_not_ready')
    request = TransitionRequest('enter', *[active[key] for key in
        ('source_sha', 'artifact_sha256', 'controller_sha256', 'image_id')])
    context = _candidate(request)
    actions = _image_binding(context, budget)
    _owned_runtime(actions, context, budget)
    actions._runtime(context, budget, live=True,
                     **({'initial_a': active['initial_a']} | ({'trial_origin':active['trial_origin']} if active.get('trial_origin') else {})
                        if active.get('initial_a') else {}))
    require(not active.get('trial_origin'),'trial_cloud_profile_not_yet_qualified')
    _files()
    for name in EXPECTED_MODULES:
        path = context.source / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
                and info.st_size < 256 * 1024, 'probe_module_not_in_release')
    base = actions._json(actions._compose(context, budget,
        ['config', '--format', 'json']))
    live = actions._json(_compose(actions, context, budget,
        ('runtime.live.compose.yaml',), ['config', '--format', 'json'], 15))
    probe = actions._json(_compose(actions, context, budget,
        ('runtime.live.compose.yaml', 'runtime.structured-probe.compose.yaml'),
        ['config', '--format', 'json'], 15))
    validate_probe_profile(base, live, probe, context.source, context.image)
    raw, _ = _secure_file(installed, private=False)
    return context, actions, hashlib.sha256(raw).hexdigest()


def run(command: str, installed: Path):
    parts = command.split(' ')
    require(parts[:2] == ['structured-probe-v1', 'preflight'] and len(parts) == 2
            or parts[:2] == ['structured-probe-v1', 'execute'] and len(parts) == 2,
            'invalid_probe_command')
    context, actions, controller_sha = preflight(installed, Budget(90))
    binding = {'environment': 'preprod', 'instance': 'tradebot-preprod-01',
               'source_sha': context.request.source_sha,
               'artifact_sha256': context.request.artifact_sha256,
               'controller_sha256': controller_sha, 'image_id': context.image}
    if parts[1] == 'preflight':
        return {'gate': 'PP_STRUCTURED_PREFLIGHT_PASS', **binding,
                'cloud_calls': 0, 'retirement': 'off'}

    # The permit is root-owned and one-use. Its exact page target is reviewed
    # out of band; caller-supplied arguments never select cloud rows or files.
    permit = json.loads(_secure_file(AUTHORITY)[0])
    generation = permit.get('generation_id')
    state = permit.get('expected_state')
    first = permit.get('expected_first_outbox_id')
    require(isinstance(generation, str) and str(uuid.UUID(generation)) == generation
            and state in ('collecting', 'sealed', 'verified')
            and type(first) is int and first > 0,
            'invalid_probe_target')
    _consume(AUTHORITY, {**binding, 'scope': 'pp_structured_one_shot',
                         'generation_id': generation, 'expected_state': state,
                         'expected_first_outbox_id': first})
    args = ['run', '--rm', '--no-deps', '--name',
            'tradebot-pp-deploy-' + actions.attempt_id + '-1',
            '--label', 'tradebot.deployment_attempt=' + actions.attempt_id,
            '--label', 'tradebot.deployment_source=' + context.request.source_sha,
            'structured_probe', 'python', '-m', 'postgres.pp_structured_probe',
            '--generation-id', generation, '--expected-state', state,
            '--expected-first-outbox-id', str(first), '--execute']
    name = args[args.index('--name') + 1]
    actions.oneoffs[name] = 'structured_probe'
    result = None
    error = None
    with _stage_local_secret():
        try:
            raw = _compose(actions, context, Budget(30),
                ('runtime.live.compose.yaml', 'runtime.structured-probe.compose.yaml'),
                args, 25, capture_exit=True)
            result = actions._json(raw)
        except Exception as caught:
            error = caught
        finally:
            # Docker may keep the container running after its CLI child times
            # out. A fresh recovery budget proves exit or reports STOP.
            actions._cleanup_oneoffs(context, Budget(30))
    if error is not None:
        reason = str(error) if isinstance(error, DeploymentHold) else ''
        raise DeploymentHold(reason if reason in PUBLIC_FAILURE_CODES
                             else 'pp_structured_probe_failed') from None
    count = result.get('acknowledged')
    require(result.get('status') == 'acknowledged'
            and result.get('origin_id') == 'pp-live-pp'
            and result.get('retirement') == 'off'
            and result.get('raw_archive') == 'not_started'
            and type(count) is int and 1 <= count <= 25,
            'unsafe_probe_result')
    return {'gate': 'PP_STRUCTURED_ONCE_PASS', 'origin_id': 'pp-live-pp',
            'acknowledged': result['acknowledged'], 'retirement': 'off',
            'cloud_operations_max': 2}


# Only the root operator installer invokes these operations, under the same
# controller lock as CD and transitions. Persist ownership before Docker runs.
SYNC_STATE = ACTIVE.with_name('structured-sync-owner.json')


ARCHIVE_STATE = ACTIVE.with_name('sealed-archive-owner.json')


def _require_stopped(path):
    require(not path.exists() and not path.is_symlink(),
            'stop_recurring_structured_sync_first' if path == SYNC_STATE else 'stop_recurring_archive_first')


def fence_recurring_sync():
    for path in (SYNC_STATE, ARCHIVE_STATE):
        _require_stopped(path)


def _write_sync_owner(owner, path=None):
    path = path or SYNC_STATE
    import json
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as out:
        json.dump(owner, out)
        out.flush()
        os.fsync(out.fileno())
    parent = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def recurring_start(installed):
    import time
    _require_stopped(SYNC_STATE)
    budget = Budget(120)
    context, actions, digest = preflight(installed, budget)
    require(digest == context.request.controller_sha256,
            'recurring_controller_digest_mismatch')
    name = 'tradebot-pp-sync-' + actions.attempt_id
    owner = dict(attempt_id=actions.attempt_id, image=context.image,
                 source_sha=context.request.source_sha)
    _write_sync_owner(owner)
    # Reuse the exact validated probe network, image, secrets and isolation.
    # Only the two mutually exclusive mode flags and the module differ.
    args = ['run', '--detach', '--no-deps', '--name', name,
            '--label', 'tradebot.deployment_attempt=' + actions.attempt_id,
            '--label', 'tradebot.deployment_source=' + context.request.source_sha,
            '-e', 'TRADEBOT_PP_STRUCTURED_ONE_SHOT=false',
            '-e', 'TRADEBOT_PP_STRUCTURED_RECURRING=true',
            'structured_probe', 'python', '-m', 'postgres.pp_structured_service']
    try:
        with _stage_local_secret():
            _compose(actions, context, budget,
                     ('runtime.live.compose.yaml', 'runtime.structured-probe.compose.yaml'),
                     args, 30)
            for _ in range(20):
                row = _sync_container(owner, budget)
                require(row and row['State']['Running'], 'recurring_worker_failed_start')
                raw = budget.run(['docker', 'logs', '--tail', '8', row['Id']],
                                 env=actions._environment(context.image), timeout=5)
                if any(line == b'{"status": "structured_worker_ready"}'
                       for line in raw.splitlines()):
                    break
                time.sleep(0.25)
            else:
                raise DeploymentHold('recurring_worker_readiness_timeout')
    except Exception:
        recurring_control('stop', Budget(60))
        raise
    return {'status': 'started', 'retirement': 'off'}


def _sync_container(owner, budget, *, archive=False):
    attempt, image, source = (owner.get(k, '') for k in ('attempt_id', 'image', 'source_sha'))
    require(re.fullmatch('[a-f0-9]{32}', attempt) and
            re.fullmatch('sha256:[a-f0-9]{64}', image) and
            re.fullmatch('[a-f0-9]{40}', source), 'bad_recurring_worker_owner')
    name = ('tradebot-pp-sealed-' if archive else 'tradebot-pp-sync-') + attempt
    env = LinuxActions._environment(image)
    ids = budget.run(['docker', 'ps', '-a', '--no-trunc', '--filter',
                      'name=^/' + name + '$', '--format', '{{.ID}}'],
                     env=env, timeout=10).decode().split()
    if not ids:
        return None
    require(len(ids) == 1 and re.fullmatch('[a-f0-9]{64}', ids[0]),
            'ambiguous_recurring_worker')
    row = LinuxActions()._inspect(budget, ids)[0]
    labels = row['Config']['Labels']
    require(row['Image'] == image and row['Id'] == ids[0] and row['Name'] == '/' + name
            and labels.get('com.docker.compose.project') == PROJECT
            and labels.get('com.docker.compose.service') == ('sealed_archive' if archive else 'structured_probe')
            and labels.get('tradebot.deployment_attempt') == attempt
            and labels.get('tradebot.deployment_source') == source
            and row['HostConfig']['RestartPolicy']['Name'] in ('no', ''),
            'recurring_worker_ownership_mismatch')
    return row


def recurring_control(operation, budget, *, archive=False):
    path = ARCHIVE_STATE if archive else SYNC_STATE
    import json
    require(operation in ('stop', 'status'), 'bad_recurring_worker_operation')
    if not path.exists() and not path.is_symlink():
        return {'status': 'off'}
    owner = json.loads(_secure_file(path)[0])
    row = _sync_container(owner, budget, archive=archive)
    if operation == 'status':
        return {'status': 'running' if row and row['State']['Running'] else 'stopped',
                'source_sha': owner['source_sha'], 'retirement': 'off'}
    if row:
        env = LinuxActions._environment(owner['image'])
        if row['State']['Running']:
            budget.run(['docker', 'stop', '--time', '30', row['Id']], env=env, timeout=35)
        row = _sync_container(owner, budget, archive=archive)
        if row:
            require(not row['State']['Running'], 'recurring_worker_still_running')
            budget.run(['docker', 'rm', row['Id']], env=env, timeout=8)
        require(_sync_container(owner, budget, archive=archive) is None, 'recurring_worker_still_present')
    path.unlink()
    return {'status': 'off'}
