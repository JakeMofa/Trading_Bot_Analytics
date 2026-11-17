"""Root-owned, PP-only gate for the already deployed live transition.

The forced SSH command is the only remote caller.  This module never imports
application code from the candidate source and never starts the collector by
switching profiles.  Its persistent journal also enables permit-free OFF and
leave when the original one-use enter authority has been consumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.request
import uuid

from controller import Budget, Context, DeploymentHold, HostBinding, Request, _secure_file, require
from linux_actions import LinuxActions, RUNTIME_SECRETS

ROOT = Path('/var/lib/tradebot-pp/deployments')
ACTIVE = ROOT / 'active-live-transition.json'
ENTER_AUTHORITY = Path('/run/tradebot-pp-deploy/live-enter.json')
ON_AUTHORITY = Path('/run/tradebot-pp-deploy/live-on.json')
HEX64 = re.compile(r'[0-9a-f]{64}')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}')


def _utc(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'transition_authority_timezone_required')
    return result.astimezone(timezone.utc)


def _safe_root():
    info = ROOT.lstat()
    parent = ROOT.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and not parent.st_mode & 0o022
            and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,
            'unsafe_transition_root')


def _atomic_json(path, payload, *, new=False):
    _safe_root()
    raw = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(raw) <= 16384, 'transition_journal_too_large')
    temporary = path.with_name(path.name + '.pending-' + str(uuid.uuid4()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    if new:
        require(not path.exists() and not path.is_symlink(), 'active_transition_exists')
    else:
        _secure_file(path)
    os.replace(temporary, path)
    descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class TransitionRequest:
    operation: str
    source_sha: str
    artifact_sha256: str
    controller_sha256: str
    image_id: str
    environment: str = 'preprod'
    instance: str = 'tradebot-preprod-01'

    @classmethod
    def parse(cls, command):
        require(isinstance(command, str) and len(command) <= 512, 'invalid_transition_command')
        parts = command.split(' ')
        require(len(parts) == 8 and parts[0] == 'transition-v1', 'invalid_transition_command')
        request = cls(parts[3], parts[4], parts[5], parts[6], parts[7], parts[1], parts[2])
        request.validate()
        return request

    def validate(self):
        require(self.operation in ('enter', 'leave') and self.environment == 'preprod'
                and self.instance == 'tradebot-preprod-01', 'wrong_transition_scope')
        Request(self.source_sha, self.artifact_sha256, self.controller_sha256).validate()
        require(IMAGE.fullmatch(self.image_id) is not None, 'invalid_transition_image')

    def bindings(self):
        return {key: getattr(self, key) for key in ('environment', 'instance', 'operation',
            'source_sha', 'artifact_sha256', 'controller_sha256', 'image_id')}


def _consume(path, expected):
    """Consume one root-created, operation-scoped permit before mutation."""
    content, info = _secure_file(path)
    permit = json.loads(content)
    require(permit.get('version') == 1 and all(permit.get(k) == v for k, v in expected.items())
            and permit.get('paid_ai_enabled') is False and permit.get('cloud_enabled') is False
            and permit.get('retirement_enabled') is False and permit.get('production_data_mounted') is False,
            'transition_authority_scope_mismatch')
    nonce = permit.get('nonce')
    require(isinstance(nonce, str) and str(uuid.UUID(nonce)) == nonce, 'transition_authority_nonce_invalid')
    issued, expires = _utc(permit['issued_at']), _utc(permit['expires_at'])
    now = datetime.now(timezone.utc)
    require(issued <= now < expires and 0 < (expires-issued).total_seconds() <= 3600,
            'transition_authority_expired')
    receipt = path.with_name('consumed-' + path.stem + '-' + nonce + '.json')
    try:
        os.link(path, receipt, follow_symlinks=False)
    except FileExistsError:
        raise DeploymentHold('transition_authority_consumed') from None
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
        require(receipt.lstat().st_ino == info.st_ino, 'transition_authority_changed')
        path.unlink()
        os.fsync(directory)
    finally:
        os.close(directory)
    return nonce


def _read_active():
    content, _ = _secure_file(ACTIVE)
    data = json.loads(content)
    require(data.get('version') == 1 and data.get('environment') == 'preprod'
            and data.get('instance') == 'tradebot-preprod-01'
            and data.get('state') in ('entering', 'ready_off', 'leaving', 'generated_restored', 'recovery_unproven'),
            'invalid_active_transition')
    require(isinstance(data.get('nonce'), str) and str(uuid.UUID(data['nonce'])) == data['nonce']
            and re.fullmatch(r'[0-9a-f]{40}', data.get('source_sha', ''))
            and HEX64.fullmatch(data.get('artifact_sha256', ''))
            and HEX64.fullmatch(data.get('controller_sha256', ''))
            and IMAGE.fullmatch(data.get('image_id', '')),
            'invalid_active_transition_binding')
    return data


def _candidate(request):
    """Use only a completed, exact-source generated CD installation."""
    _safe_root()
    matches = []
    for folder in ROOT.glob('candidate-*'):
        info = folder.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,
                'unsafe_candidate_directory')
        journal_path = folder / 'controller-journal.json'
        if not journal_path.exists():
            continue
        raw, _ = _secure_file(journal_path)
        journal = json.loads(raw)
        if (journal.get('stage') == 'complete' and journal.get('gate') == 'PASS'
                and journal.get('source_sha') == request.source_sha
                and journal.get('artifact_sha256') == request.artifact_sha256
                and journal.get('image') == request.image_id):
            source = folder / 'source'
            require(source.is_dir() and not source.is_symlink(), 'missing_transition_source')
            matches.append((folder, source))
    require(len(matches) == 1, 'unique_deployed_source_required')
    folder, source = matches[0]
    return Context(Request(request.source_sha, request.artifact_sha256,
                           request.controller_sha256), source, folder, request.image_id)


def _image_binding(context, budget):
    actions = LinuxActions()
    output = actions._json(budget.run(['docker', 'image', 'inspect', context.image],
        env=actions._environment(context.image), timeout=10))
    require(isinstance(output, list) and len(output) == 1 and output[0].get('Id') == context.image
            and output[0].get('Config', {}).get('Labels', {}).get('tradebot.source_sha') == context.request.source_sha,
            'transition_image_source_mismatch')
    return actions


def _owned_runtime(actions, context, budget):
    """Refuse to recover over a foreign image or unexpected service container."""
    from linux_actions import PROJECT, SERVICES
    ids = actions._ids(context, budget, SERVICES, all=True)
    if ids:
        rows = actions._inspect(budget, ids)
        require(all(row.get('Image') == context.image
                and row.get('Config', {}).get('Labels', {}).get('com.docker.compose.project') == PROJECT
                and row['Config']['Labels'].get('com.docker.compose.service') in SERVICES
                and row['Config']['Labels'].get('com.docker.compose.oneoff', 'False') == 'False'
                for row in rows), 'foreign_runtime_blocks_transition')


def _same_active(active, request):
    require(all(active.get(k) == v for k, v in request.bindings().items() if k != 'operation'),
            'active_transition_binding_mismatch')


def transition(request, controller_path):
    from live_transition import LiveTransition
    HostBinding.from_marker().validate()
    request.validate()
    raw, _ = _secure_file(controller_path, private=False)
    require(hashlib.sha256(raw).hexdigest() == request.controller_sha256, 'controller_digest_mismatch')
    budget = Budget(600 if request.operation == 'enter' else 180)
    context = _candidate(request)
    actions = _image_binding(context, budget)
    _owned_runtime(actions, context, budget)
    if request.operation == 'enter':
        if ACTIVE.exists() or ACTIVE.is_symlink():
            active = _read_active()
            require(active['state'] == 'generated_restored', 'unfinished_transition_requires_leave')
            archived = ROOT / ('transition-' + active['nonce'] + '.json')
            require(not archived.exists() and not archived.is_symlink(), 'transition_archive_exists')
            os.replace(ACTIVE, archived)
        nonce = _consume(ENTER_AUTHORITY, {**request.bindings(), 'scope': 'pp_live_ready_off'})
        active = {**request.bindings(), 'version': 1, 'nonce': nonce, 'state': 'entering'}
        _atomic_json(ACTIVE, active, new=True)
        try:
            result = LiveTransition(actions, context, budget).enter()
            require(result.get('gate') == 'PP_LIVE_READY_OFF' and result.get('collector_enabled') is False,
                    'live_ready_off_not_proven')
            _atomic_json(ACTIVE, {**active, 'state': 'ready_off'})
            return result
        except Exception:
            # The component attempts restoration itself. A fresh recovery budget
            # covers a work-budget expiry without reusing the consumed permit.
            try:
                recovered = LiveTransition(actions, context, Budget(180)).leave()
                require(recovered.get('gate') == 'PP_GENERATED_RESTORED'
                        and recovered.get('collector_enabled') is False,
                        'generated_restoration_unproven')
                _atomic_json(ACTIVE, {**active, 'state': 'generated_restored'})
                raise DeploymentHold('pp_live_entry_failed_generated_restored') from None
            except DeploymentHold as error:
                if str(error) == 'pp_live_entry_failed_generated_restored':
                    raise
                _atomic_json(ACTIVE, {**active, 'state': 'recovery_unproven'})
                raise DeploymentHold('pp_live_entry_recovery_unproven') from None
            except Exception:
                _atomic_json(ACTIVE, {**active, 'state': 'recovery_unproven'})
                raise DeploymentHold('pp_live_entry_recovery_unproven') from None
    active = _read_active()
    _same_active(active, request)
    if active['state'] == 'generated_restored':
        actions._runtime(context, budget)
        actions._host_api()
        actions._host_operator()
        return {'gate': 'PP_GENERATED_RESTORED', 'collector_enabled': False,
                'origin_id': 'generated-pp', 'idempotent': True}
    _atomic_json(ACTIVE, {**active, 'state': 'leaving'})
    result = LiveTransition(actions, context, budget).leave()
    require(result.get('gate') == 'PP_GENERATED_RESTORED' and result.get('collector_enabled') is False,
            'generated_restoration_unproven')
    _atomic_json(ACTIVE, {**active, 'state': 'generated_restored'})
    return result


def _operator(token, path, *, seconds=None):
    method = 'POST' if path != '/collector/status' else 'GET'
    suffix = '?max_seconds=' + str(seconds) if seconds is not None else ''
    request = urllib.request.Request('http://127.0.0.1:8001' + path + suffix,
        headers={'Authorization': 'Bearer ' + token}, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=2) as response:
        raw = response.read(8193)
    require(len(raw) <= 8192, 'operator_response_too_large')
    return json.loads(raw)


def session(command, controller_path):
    """ON is one-use; OFF remains available when HTTP control has failed."""
    from live_transition import LiveTransition
    HostBinding.from_marker().validate()
    parts = command.split(' ')
    require(parts[0] == 'session-v1' and ((len(parts) == 3 and parts[1] == 'on'
        and parts[2].isdigit() and 1 <= int(parts[2]) <= 1800)
        or (parts == ['session-v1', 'off'])), 'invalid_session_command')
    active = _read_active()
    require(active['state'] in ('ready_off', 'entering', 'leaving', 'recovery_unproven'),
            'no_live_transition_to_control')
    request = TransitionRequest('leave', active['source_sha'], active['artifact_sha256'],
        active['controller_sha256'], active['image_id'])
    request.validate()
    raw, _ = _secure_file(controller_path, private=False)
    require(hashlib.sha256(raw).hexdigest() == request.controller_sha256, 'controller_digest_mismatch')
    context = _candidate(request)
    budget = Budget(90)
    actions = _image_binding(context, budget)
    _owned_runtime(actions, context, budget)
    if parts[1] == 'off':
        # The HTTP route drains the process when available. The lifecycle role
        # then proves durable OFF even if the operator process is unavailable.
        try:
            token_path = RUNTIME_SECRETS / 'operator_token'
            info = token_path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 10001
                    and stat.S_IMODE(info.st_mode) == 0o400, 'unsafe_operator_token')
            token = token_path.read_text().strip()
            require(HEX64.fullmatch(token) is not None, 'unsafe_operator_token')
            _operator(token, '/collector/off')
        except (OSError, ValueError, DeploymentHold, urllib.error.HTTPError):
            pass
        LiveTransition(actions, context, budget)._live_off()
        return {'gate': 'PP_LIVE_OFF', 'origin_id': 'pp-live-pp', 'collector_enabled': False}
    require(active['state'] == 'ready_off', 'live_profile_not_ready')
    seconds = int(parts[2])
    actions._runtime(context, budget, live=True)
    actions._host_operator(live=True)
    _consume(ON_AUTHORITY, {k: active[k] for k in ('environment', 'instance', 'source_sha',
        'artifact_sha256', 'controller_sha256', 'image_id')} |
        {'transition_nonce': active['nonce'], 'scope': 'pp_live_session_on', 'max_seconds': seconds})
    token_path = RUNTIME_SECRETS / 'operator_token'
    info = token_path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 10001 and stat.S_IMODE(info.st_mode) == 0o400,
            'unsafe_operator_token')
    token = token_path.read_text().strip()
    require(HEX64.fullmatch(token) is not None, 'unsafe_operator_token')
    try:
        accepted = _operator(token, '/collector/on', seconds=seconds)
        require(accepted.get('accepted') is True and accepted.get('origin_id') == 'pp-live-pp',
                'collector_on_not_accepted')
        deadline = time.monotonic() + 5
        while True:
            state = _operator(token, '/collector/status')
            if (state.get('origin_id') == 'pp-live-pp'
                    and state.get('collector_enabled') is True
                    and state.get('process_running') is True):
                expiry = _utc(state['lease_expires_at'])
                remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
                require(0 < remaining <= seconds + 15, 'collector_lease_exceeds_session_bound')
                return {'gate': 'PP_LIVE_ON', 'origin_id': 'pp-live-pp',
                        'collector_enabled': True, 'max_seconds': seconds}
            require(time.monotonic() < deadline, 'collector_on_not_durable')
            time.sleep(.2)
    except Exception:
        try:
            LiveTransition(actions, context, Budget(90))._live_off()
        except Exception:
            raise DeploymentHold('collector_on_failed_off_unproven') from None
        raise DeploymentHold('collector_on_failed_off_proven') from None
