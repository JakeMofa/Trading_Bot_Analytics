"""Root-owned PP one-shot raw archive control; never enables retirement."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import uuid

from controller import Budget, DeploymentHold, _secure_file, require
from linux_actions import PROJECT
from raw_archive_probe_profile import CLOUD_FILES, validate_raw_archive_profile
from structured_probe_control import (_stage_local_secret,
                                      preflight as structured_preflight)
from transition_control import _consume


AUTHORITY = Path('/run/tradebot-pp-deploy/raw-archive-probe.json')
CLOUD_DIR = Path('/etc/tradebot/cloud')
EXPECTED_MODULES = ('backend/postgres/pp_raw_archive_probe.py',
                    'backend/postgres/supabase_storage.py',
                    'backend/postgres/pp_history_connection.py',
                    'backend/postgres/history_v2_transport.py',
                    'backend/postgres/archive_transport.py')


def _storage_files():
    """Metadata only; no credential value is logged or placed in evidence."""
    directory = CLOUD_DIR.lstat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == 0
            and stat.S_IMODE(directory.st_mode) == 0o700,
            'unsafe_pp_cloud_directory')
    identities = set()
    for name, path in CLOUD_FILES.items():
        info = Path(path).lstat()
        mode = 0o644 if name == 'pp_history_ca' else 0o600
        minimum = {'pp_history_ca': 1, 'supabase_auth_email': 3,
                   'supabase_auth_uid': 36}.get(name, 20)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode
                and minimum <= info.st_size <= (16 * 1024 if name == 'pp_history_ca' else 4096),
                'unsafe_pp_raw_archive_secret')
        identity = (info.st_dev, info.st_ino)
        require(identity not in identities, 'aliased_pp_raw_archive_secret')
        identities.add(identity)
    uid = (CLOUD_DIR / 'supabase_auth_uid').read_text(encoding='ascii').strip()
    require(str(uuid.UUID(uid)) == uid, 'invalid_pp_storage_auth_identity')


def _compose(actions, context, budget, files, args, timeout):
    folder = context.source / 'deploy/preprod'
    command = ['docker', 'compose', '--env-file', '/dev/null',
               '--project-name', PROJECT,
               '--project-directory', str(folder)]
    for name in ('compose.yaml', 'runtime.compose.yaml', *files):
        command += ['-f', str(folder / name)]
    return budget.run([*command, '--profile', 'migration', '--profile',
                       'raw_archive_probe', *args], cwd=context.source,
                      env=actions._environment(context.image), timeout=timeout)


def preflight(installed: Path, budget: Budget):
    # Includes pinned host, ready_off, exact image/source, persistent services,
    # local/history files and the already qualified structured probe profile.
    context, actions, digest = structured_preflight(installed, budget)
    _storage_files()
    for name in EXPECTED_MODULES:
        path = context.source / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
                and info.st_size < 256 * 1024, 'raw_archive_module_not_in_release')
    base = actions._json(actions._compose(context, budget,
        ['config', '--format', 'json']))
    live = actions._json(_compose(actions, context, budget,
        ('runtime.live.compose.yaml',), ['config', '--format', 'json'], 15))
    probe = actions._json(_compose(actions, context, budget,
        ('runtime.live.compose.yaml', 'runtime.raw-archive-probe.compose.yaml'),
        ['config', '--format', 'json'], 15))
    validate_raw_archive_profile(base, live, probe, context.source, context.image)
    return context, actions, digest


def run(command: str, installed: Path):
    parts = command.split(' ')
    require(len(parts) == 2 and parts[0] == 'raw-archive-probe-v1'
            and parts[1] in ('preflight', 'execute'),
            'invalid_raw_archive_command')
    context, actions, controller_sha = preflight(installed, Budget(90))
    binding = {'environment': 'preprod', 'instance': 'tradebot-preprod-01',
               'source_sha': context.request.source_sha,
               'artifact_sha256': context.request.artifact_sha256,
               'controller_sha256': controller_sha, 'image_id': context.image}
    if parts[1] == 'preflight':
        return {'gate': 'PP_RAW_ARCHIVE_PREFLIGHT_PASS', **binding,
                'cloud_calls': 0, 'retirement': 'off'}

    permit = json.loads(_secure_file(AUTHORITY)[0])
    generation = permit.get('generation_id')
    seal_count = permit.get('expected_seal_count')
    manifest_count = permit.get('expected_manifest_count')
    require(isinstance(generation, str) and str(uuid.UUID(generation)) == generation
            and type(seal_count) is int and seal_count >= 0
            and type(manifest_count) is int and 0 <= manifest_count <= 128,
            'invalid_raw_archive_target')
    _consume(AUTHORITY, {**binding, 'scope': 'pp_raw_archive_one_shot',
                         'generation_id': generation,
                         'expected_seal_count': seal_count,
                         'expected_manifest_count': manifest_count})
    args = ['run', '--rm', '--no-deps', '--name',
            'tradebot-pp-deploy-' + actions.attempt_id + '-1',
            '--label', 'tradebot.deployment_attempt=' + actions.attempt_id,
            '--label', 'tradebot.deployment_source=' + context.request.source_sha,
            'raw_archive_probe', 'python', '-m', 'postgres.pp_raw_archive_probe',
            '--generation-id', generation, '--expected-seal-count', str(seal_count),
            '--expected-manifest-count', str(manifest_count), '--execute']
    name = args[args.index('--name') + 1]
    actions.oneoffs[name] = 'raw_archive_probe'
    result = None
    error = None
    with _stage_local_secret():
        try:
            output = _compose(actions, context, Budget(30),
                ('runtime.live.compose.yaml', 'runtime.raw-archive-probe.compose.yaml'),
                args, 25)
            result = actions._json(output)
        except Exception as caught:
            error = caught
        finally:
            # A timed-out CLI may leave its container alive. Prove exit under a
            # separate recovery budget before staging-file cleanup completes.
            actions._cleanup_oneoffs(context, Budget(30))
    if error is not None:
        raise DeploymentHold('pp_raw_archive_probe_failed') from None
    raw_rows = result.get('raw_rows')
    outbox_rows = result.get('outbox_rows')
    require(result.get('status') == 'cycle_complete'
            and result.get('raw_coverage') in ('partial', 'archived')
            and result.get('origin_id') == 'pp-live-pp'
            and result.get('generation_id') == generation
            and result.get('retirement') == 'off'
            and type(raw_rows) is int and 0 <= raw_rows <= 25
            and type(outbox_rows) is int and 0 <= outbox_rows <= 25
            and result.get('bounds') == {'rows': 25, 'decoded_bytes': 256 * 1024,
                                         'cloud_operations': 8, 'seconds': 20},
            'unsafe_raw_archive_result')
    return {'gate': 'PP_RAW_ARCHIVE_ONCE_PASS', 'origin_id': 'pp-live-pp',
            'generation_id': generation, 'raw_coverage': result['raw_coverage'],
            'raw_rows': raw_rows, 'outbox_rows': outbox_rows,
            'retirement': 'off', 'cloud_operations_max': 8}
