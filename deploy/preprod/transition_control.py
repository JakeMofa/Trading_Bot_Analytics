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

from controller import BENCHMARK_INSTANCE, Budget, Context, DeploymentHold, HostBinding, PP_INSTANCES, Request, _secure_file, require
from linux_actions import (BOUNDARY_ORIGIN, DISPLAY_ORIGIN, RETAINED_DISPLAY_ORIGINS, BOUNDARY_SMOKE_ORIGIN, LinuxActions, RUNTIME_SECRETS, allowed_session_seconds,
                           cycle_environment, cycle_profile_binding, live_origin, TRIAL_ORIGIN,
                           RETAINED_TRIAL_ORIGIN, RETAINED_TRIAL_ORIGINS)

ROOT = Path('/var/lib/tradebot-pp/deployments')
ACTIVE = ROOT / 'active-live-transition.json'
ENTER_AUTHORITY = Path('/run/tradebot-pp-deploy/live-enter.json')
ON_AUTHORITY = Path('/run/tradebot-pp-deploy/live-on.json')
TRIAL_AUTHORITY_REBIND_PENDING = RUNTIME_SECRETS / 'pp26-rebind-pending.json'
HEX64 = re.compile(r'[0-9a-f]{64}')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}')


def require_no_trial_authority_rebind():
    """Admission only: incomplete authority changes never permit ENTER or ON.

    Inspect metadata without following symlinks or parsing a potentially partial
    marker. OFF, LEAVE and read-only proof validation remain available.
    """
    try:
        TRIAL_AUTHORITY_REBIND_PENDING.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise DeploymentHold('trial_authority_rebind_pending') from None
    raise DeploymentHold('trial_authority_rebind_pending')


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
    initial_a: str | None = None
    trial_origin: str | None = None

    @classmethod
    def parse(cls, command):
        require(isinstance(command, str) and len(command) <= 512, 'invalid_transition_command')
        parts = command.split(' ')
        require(len(parts) in (8, 9, 10) and parts[0] == 'transition-v1', 'invalid_transition_command')
        request = cls(parts[3], parts[4], parts[5], parts[6], parts[7], parts[1], parts[2],
                      parts[8] if len(parts) >= 9 else None, parts[9] if len(parts) == 10 else None)
        request.validate()
        return request

    def validate(self):
        require(self.operation in ('enter', 'leave') and self.environment == 'preprod'
                and self.instance in PP_INSTANCES, 'wrong_transition_scope')
        Request(self.source_sha, self.artifact_sha256, self.controller_sha256, instance=self.instance).validate()
        require(IMAGE.fullmatch(self.image_id) is not None, 'invalid_transition_image')
        require(self.initial_a is None or self.operation == 'enter', 'invalid_pp_cycle_transition')
        if self.trial_origin==DISPLAY_ORIGIN:
            require(self.instance==BENCHMARK_INSTANCE,'quote_display_requires_benchmark_host')
        if self.operation=='enter':
            require(self.trial_origin not in RETAINED_TRIAL_ORIGINS,'retained_trial_is_read_only')
        cycle_environment(self.initial_a,self.trial_origin)

    def bindings(self):
        binding = {key: getattr(self, key) for key in ('environment', 'instance', 'operation',
            'source_sha', 'artifact_sha256', 'controller_sha256', 'image_id')}
        return binding | ({'initial_a': self.initial_a} if self.initial_a is not None else {}) | (
            {'trial_origin':self.trial_origin} if self.trial_origin is not None else {}) | cycle_profile_binding(self.trial_origin)


def _consume(path, expected):
    """Consume one root-created, operation-scoped permit before mutation."""
    content, info = _secure_file(path)
    permit = json.loads(content)
    require(permit.get('version') == 1 and all(permit.get(k) == v for k, v in expected.items())
            and permit.get('initial_a') == expected.get('initial_a')
            and permit.get('trial_origin') == expected.get('trial_origin')
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
            and data.get('instance') in PP_INSTANCES
            and data.get('state') in ('entering', 'ready_off', 'leaving', 'generated_restored', 'recovery_unproven'),
            'invalid_active_transition')
    require(isinstance(data.get('nonce'), str) and str(uuid.UUID(data['nonce'])) == data['nonce']
            and re.fullmatch(r'[0-9a-f]{40}', data.get('source_sha', ''))
            and HEX64.fullmatch(data.get('artifact_sha256', ''))
            and HEX64.fullmatch(data.get('controller_sha256', ''))
            and IMAGE.fullmatch(data.get('image_id', '')),
            'invalid_active_transition_binding')
    profile_origin=data.get('trial_origin')
    if profile_origin in RETAINED_DISPLAY_ORIGINS:
        # The previous release left a terminal journal with the same display
        # profile shape. Preserve its real identity in the returned record.
        require(data['state']=='generated_restored' and data['instance']==BENCHMARK_INSTANCE
                and data.get('initial_a') is not None,'invalid_active_transition_binding')
        profile_origin=DISPLAY_ORIGIN
    cycle_environment(data.get('initial_a'),profile_origin)
    expected_profile=({'profile':'boundary-diagnostic-v1'} if data.get('trial_origin') in RETAINED_DISPLAY_ORIGINS
                      else cycle_profile_binding(profile_origin))
    require(all(data.get(key)==expected_profile.get(key) for key in ('profile','window_seconds')),
            'invalid_active_cycle_profile')
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


def _image_binding(context, budget, *, watch_diagnostics=False):
    actions = LinuxActions(watch_diagnostics=watch_diagnostics)
    output = actions._json(budget.run(['docker', 'image', 'inspect', context.image],
        env=actions._environment(context.image), timeout=10))
    require(isinstance(output, list) and len(output) == 1 and output[0].get('Id') == context.image
            and output[0].get('Config', {}).get('Labels', {}).get('tradebot.source_sha') == context.request.source_sha,
            'transition_image_source_mismatch')
    return actions


def _owned_runtime(actions, context, budget):
    """Refuse to recover over a foreign image or unexpected service container."""
    from linux_actions import PROJECT, SERVICES, compatible_api_image
    ids = actions._ids(context, budget, SERVICES, all=True)
    if ids:
        rows = actions._inspect(budget, ids)
        require(all(compatible_api_image(context,row)
                and row.get('Config', {}).get('Labels', {}).get('com.docker.compose.project') == PROJECT
                and row['Config']['Labels'].get('com.docker.compose.service') in SERVICES
                and row['Config']['Labels'].get('com.docker.compose.oneoff', 'False') == 'False'
                for row in rows), 'foreign_runtime_blocks_transition')
        require(len(rows)<=len(SERVICES) and len({row['Config']['Labels']['com.docker.compose.service'] for row in rows})==len(rows),
                'foreign_runtime_blocks_transition')


def _same_active(active, request):
    require(all(active.get(k) == v for k, v in request.bindings().items() if k != 'operation'),
            'active_transition_binding_mismatch')


# Fixed public diagnostics: never stringify arbitrary adapter/SQL exceptions.
_TRANSITION_PHASES={'preflight','host_identity','profile','postgres','filesystem','generated_preflight',
    'durable_off','quiesce_ownership','quiesce','live_headroom','prepare_trial','live_start','live_ready_off',
    'cleanup_oneoffs','off_ownership','generated_headroom','generated_start','generated_runtime','generated_routes'}
_TRANSITION_CODES={'insufficient_host_headroom','unqualified_host_os','unsafe_secret_directory',
    'unprepared_foundation_secret','unprepared_runtime_secret','runtime_secret_binding_mismatch','unsafe_operator_token',
    'pp_live_durable_off_unproven','foreign_runtime_blocks_transition','quiesced_runtime_identity_changed',
    'owned_runtime_not_quiescent','pp_trial_preparation_unproven','generated_runtime_check_failed',
    'generated_api_readiness_timeout','generated_operator_readiness_timeout','generated_api_state_check_failed',
    'generated_operator_state_check_failed','deadline_exceeded','child_deadline_exceeded','child_failed',
    'host_api_wrong_state','operator_not_default_off','runtime_image_or_process_mismatch','runtime_flag_mismatch',
    'operator_connection_interrupted','deployment_oneoff_still_running','deployment_oneoff_not_removed',
    'oneoff_ownership_mismatch','oneoff_restart_not_fenced','generated_restoration_unproven','live_ready_off_not_proven'}
def _transition_failure(component,error):
    phase=getattr(component,'phase','unknown')
    code=str(error) if isinstance(error,DeploymentHold) and str(error) in _TRANSITION_CODES else 'transition_action_failed'
    return {'phase':phase if phase in _TRANSITION_PHASES else 'unknown','reason':code}


def transition(request, controller_path):
    from live_transition import LiveTransition
    binding = HostBinding.from_marker()
    request.validate()
    require(request.instance == binding.hostname, 'wrong_transition_scope')
    if request.operation=='enter':
        require_no_trial_authority_rebind()
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
        component=LiveTransition(actions,context,budget,**_cycle_args(active))
        try:
            result=component.enter()
            require(result.get('gate')=='PP_LIVE_READY_OFF' and result.get('collector_enabled') is False,
                    'live_ready_off_not_proven')
            _atomic_json(ACTIVE,{**active,'state':'ready_off'})
            return result
        except Exception as error:
            original=_transition_failure(component,error)
            if not component.mutation_started:
                # A failed read-only preflight grants no recovery mutation.
                _atomic_json(ACTIVE,{**active,'state':'recovery_unproven',
                                    'entry_failure':original,'recovery_attempted':False})
                return {'gate':'BLOCKED','reason':'pp_live_entry_preflight_failed',
                        'entry_failure':original,'recovery_attempted':False,'recovery':'not_performed'}
            # Exactly one recovery attempt, with a fresh full budget even if
            # entry exhausted its work budget. The component does not recover.
            recovery=LiveTransition(actions,context,Budget(180),**_cycle_args(active))
            try:
                recovered=recovery.leave()
                require(recovered.get('gate')=='PP_GENERATED_RESTORED'
                        and recovered.get('collector_enabled') is False,'generated_restoration_unproven')
            except Exception as recovery_error:
                failed=_transition_failure(recovery,recovery_error)
                _atomic_json(ACTIVE,{**active,'state':'recovery_unproven',
                                    'entry_failure':original,'recovery_attempted':True,'recovery_failure':failed})
                return {'gate':'BLOCKED','reason':'pp_live_entry_recovery_unproven',
                        'entry_failure':original,'recovery_attempted':True,'recovery_failure':failed,'recovery':'unproven'}
            _atomic_json(ACTIVE,{**active,'state':'generated_restored','entry_failure':original,'recovery_attempted':True})
            return {'gate':'BLOCKED','reason':'pp_live_entry_failed_generated_restored',
                    'entry_failure':original,'recovery_attempted':True,'recovery':'generated_restored',
                    'collector_enabled':False,'origin_id':'generated-pp'}
    active = _read_active()
    _same_active(active, request)
    if active['state'] == 'generated_restored':
        actions._runtime(context, budget)
        actions._host_api()
        actions._host_operator()
        return {'gate': 'PP_GENERATED_RESTORED', 'collector_enabled': False,
                'origin_id': 'generated-pp', 'idempotent': True}
    _atomic_json(ACTIVE, {**active, 'state': 'leaving'})
    result = LiveTransition(actions, context, budget, **_cycle_args(active)).leave()
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


def _prove_off(transition, source_sha, budget):
    from structured_probe_control import recurring_control
    try:
        transition._live_off()
    except DeploymentHold:
        transition.actions._cleanup_oneoffs(transition.context, budget)
        # A stopped source may still have a durable lease. Release only owned
        # workers from this exact release before retrying the same OFF proof.
        stopped = False
        for archive in (False, True):
            state = recurring_control('status', budget, archive=archive)
            if state['status'] == 'running':
                require(state['source_sha'] == source_sha, 'recurring_worker_source_mismatch')
                require(recurring_control('stop', budget, archive=archive)['status'] == 'off',
                        'recurring_worker_stop_unproven')
                stopped = True
                break
        if not stopped:
            raise
        transition._live_off()


def _cycle_args(active):
    initial_a = active.get('initial_a')
    return ({'initial_a': initial_a} | ({'trial_origin':active['trial_origin']}
            if active.get('trial_origin') else {})) if initial_a is not None else {}


def session(command, controller_path):
    """ON is one-use; OFF remains available when HTTP control has failed."""
    from live_transition import LiveTransition
    binding = HostBinding.from_marker()
    parts = command.split(' ')
    require(parts[:2] == ['session-v1', 'on'] and len(parts) in (3, 4, 5)
            or parts == ['session-v1', 'off'], 'invalid_session_command')
    if parts[1]=='on':
        require_no_trial_authority_rebind()
    active = _read_active()
    require(active['instance'] == binding.hostname, 'wrong_transition_scope')
    cycle = _cycle_args(active)
    if parts[1] == 'on':
        require(active.get('trial_origin') not in RETAINED_TRIAL_ORIGINS,'retained_trial_is_read_only')
        initial_a = parts[3] if len(parts) >= 4 else None
        trial_origin = parts[4] if len(parts) == 5 else None
        require(trial_origin == active.get('trial_origin'),'pp_trial_session_binding_mismatch')
        require(initial_a == active.get('initial_a'), 'pp_cycle_session_binding_mismatch')
        require(re.fullmatch(r'[0-9]{1,4}', parts[2]) is not None, 'invalid_session_command')
        seconds = int(parts[2])
        require(allowed_session_seconds(seconds,scoped=bool(cycle),origin=trial_origin),
                'invalid_session_command')
    require(active['state'] in ('ready_off', 'entering', 'leaving', 'recovery_unproven'),
            'no_live_transition_to_control')
    request = TransitionRequest('leave', active['source_sha'], active['artifact_sha256'],
        active['controller_sha256'], active['image_id'], instance=active['instance'])
    request.validate()
    raw, _ = _secure_file(controller_path, private=False)
    require(hashlib.sha256(raw).hexdigest() == request.controller_sha256, 'controller_digest_mismatch')
    context = _candidate(request)
    budget = Budget(90)
    actions = _image_binding(context, budget)
    _owned_runtime(actions, context, budget)
    if parts[1] == 'off':
        if active.get('trial_origin') == DISPLAY_ORIGIN:
            from watch_service import disarm
            disarm()
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
        _prove_off(LiveTransition(actions, context, budget, **cycle), request.source_sha, budget)
        return {'gate': 'PP_LIVE_OFF', 'origin_id': live_origin(active.get('trial_origin')), 'collector_enabled': False}
    require(active['state'] == 'ready_off', 'live_profile_not_ready')
    if active.get('trial_origin') == BOUNDARY_SMOKE_ORIGIN:
        from structured_probe_control import fence_recurring_sync
        fence_recurring_sync()
    elif active.get('trial_origin'):
        from trial_cloud_control import require_ready
        require_ready(context,active['initial_a'],budget,
                      **({'boundary_origin': active['trial_origin']} if active['trial_origin'] in (BOUNDARY_ORIGIN,DISPLAY_ORIGIN) else {}))
    actions._runtime(context, budget, live=True, **cycle)
    actions._host_operator(live=True,**({'trial_origin':active['trial_origin']} if active.get('trial_origin') else {}))
    actions._live_filesystem(context, budget)
    token_path = RUNTIME_SECRETS / 'operator_token'
    info = token_path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 10001 and stat.S_IMODE(info.st_mode) == 0o400,
            'unsafe_operator_token')
    token = token_path.read_text().strip()
    require(HEX64.fullmatch(token) is not None, 'unsafe_operator_token')
    if cycle:
        state = _operator(token, '/collector/status')
        require((active.get('trial_origin') == DISPLAY_ORIGIN or state.get('generation_id') == cycle['initial_a'])
                and state.get('collector_enabled') is False,
                'pp_cycle_initial_generation_not_ready')
    _consume(ON_AUTHORITY, {k: active[k] for k in ('environment', 'instance', 'source_sha',
        'artifact_sha256', 'controller_sha256', 'image_id')} |
        {'transition_nonce': active['nonce'], 'scope': 'pp_live_session_on', 'max_seconds': seconds} | cycle
        | cycle_profile_binding(active.get('trial_origin')))
    try:
        accepted = _operator(token, '/collector/on', seconds=seconds)
        require(accepted.get('accepted') is True and accepted.get('origin_id') == live_origin(active.get('trial_origin')),
                'collector_on_not_accepted')
        deadline = time.monotonic() + 5
        while True:
            state = _operator(token, '/collector/status')
            if (state.get('origin_id') == live_origin(active.get('trial_origin'))
                    and state.get('collector_enabled') is True
                    and state.get('process_running') is True):
                expiry = _utc(state['lease_expires_at'])
                remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
                require(0 < remaining <= seconds + 15, 'collector_lease_exceeds_session_bound')
                return {'gate': 'PP_LIVE_ON', 'origin_id': live_origin(active.get('trial_origin')),
                        'collector_enabled': True, 'max_seconds': seconds} | cycle | cycle_profile_binding(active.get('trial_origin'))
            require(time.monotonic() < deadline, 'collector_on_not_durable')
            time.sleep(.2)
    except Exception:
        try:
            LiveTransition(actions, context, Budget(90), **cycle)._live_off()
        except Exception:
            raise DeploymentHold('collector_on_failed_off_unproven') from None
        raise DeploymentHold('collector_on_failed_off_proven') from None
