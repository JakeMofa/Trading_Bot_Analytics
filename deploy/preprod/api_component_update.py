"""Root-initiated, exact-release dashboard API replacement on the running Benchmark watch."""

import argparse
from contextlib import contextmanager
from dataclasses import replace
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
from urllib.request import ProxyHandler, build_opener

# Use the controller installed by the accepted full release on the operator host.
if __name__ == '__main__':
    sys.path.insert(0, '/usr/local/lib/tradebot-pp/controller.pyz')

from controller import (
    BENCHMARK_INSTANCE,
    COMPRESSED_LIMIT,
    Budget,
    Request,
    _secure_file,
    extract_archive,
    require,
)
from linux_actions import DISPLAY_ORIGIN, LinuxActions, SERVICES
from live_transition import LiveTransition
from transition_control import (
    ROOT,
    TransitionRequest,
    _candidate,
    _image_binding,
    _owned_runtime,
    _operator,
    _read_active,
)
from structured_probe_control import recurring_control
from watch_service import INTENT, LOCK, binding, token


def schema(source):
    migrations = source / 'backend/postgres/migrations'
    files = sorted(migrations.iterdir())
    require(
        0 < len(files) <= 64
        and all(
            p.is_file() and not p.is_symlink() and re.fullmatch('[0-9]{4}_[a-z0-9_]+[.]sql', p.name)
            for p in files
        ),
        'invalid_api_schema_files',
    )
    return [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]


def compatible_build(current, candidate):
    old = schema(current)
    require(schema(candidate) == old, 'api_schema_change_requires_full_release')
    for filename in ('backend/requirements.txt', 'deploy/preprod/Dockerfile',
                     'deploy/preprod/runtime.compose.yaml', 'deploy/preprod/runtime.live.compose.yaml',
                     'deploy/preprod/runtime.live-boundary.compose.yaml',
                     'deploy/preprod/runtime.quote-display.compose.yaml'):
        require(
            (current / filename).read_bytes() == (candidate / filename).read_bytes(),
            'api_build_contract_changed',
        )
    return hashlib.sha256(json.dumps(old, separators=(',', ':')).encode()).hexdigest()


def watch(*, require_armed=True):
    bound = binding()
    active = _read_active()
    if require_armed:
        intent = json.loads(_secure_file(INTENT)[0])
        require(intent['state'] == 'armed' and intent['binding'] == bound, 'api_watch_not_armed')
    ctx = _candidate(
        TransitionRequest(
            'leave',
            active['source_sha'],
            active['artifact_sha256'],
            active['controller_sha256'],
            active['image_id'],
            instance=BENCHMARK_INSTANCE,
        )
    )
    return active, ctx


@contextmanager
def locked():
    with os.fdopen(os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC), 'r+b') as f:
        meta = os.fstat(f.fileno())
        require(
            stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o600,
            'unsafe_controller_lock',
        )
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def renew_existing(active):
    """Refresh a running owner's lease. No start/arm operation is reachable here."""
    if not INTENT.exists():
        return False
    intent = json.loads(_secure_file(INTENT)[0])
    require(intent['binding'] == binding(), 'api_watch_binding_changed')
    if intent['state'] != 'armed':
        return False
    credential = token()
    state = _operator(credential, '/collector/status')
    require(state.get('origin_id') == DISPLAY_ORIGIN, 'watch_wrong_origin')
    if state.get('watch_explicit_off') or not state['collector_enabled'] or not state['process_running']:
        return False
    worker = recurring_control('status', Budget(8))
    require(
        worker.get('status') == 'running' and worker.get('source_sha') == active['source_sha'],
        'watch_archive_worker_unavailable',
    )
    # The SQL operation rechecks the explicit OFF marker, capacity and current
    # process UUID under the writer lock. OFF racing this call wins.
    renewed = _operator(credential, '/collector/watch/renew')
    require(
        renewed['origin_id'] == DISPLAY_ORIGIN
        and renewed['epoch'] == state['epoch']
        and renewed['generation_id'] == state['generation_id'],
        'api_watch_owner_changed',
    )
    return True


@contextmanager
def continued_renewal(renew, *, needed, interval=12):
    running = renew()
    require(running or not needed, 'api_watch_not_running')
    stop = Event()
    failures = []

    def run():
        while not stop.wait(interval):
            try:
                if not renew():
                    return
            except Exception as error:
                failures.append(error)
                return

    heartbeat = Thread(target=run, daemon=True)
    if running:
        heartbeat.start()
    try:
        yield
        require(not failures, 'api_watch_renewal_failed')
    finally:
        stop.set()
        if running:
            heartbeat.join()


def write_json(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(json.dumps(value, sort_keys=True).encode())
        f.flush()
        os.fsync(f.fileno())
    os.replace(f.name, path)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def component_record(active, new_source, new_artifact, new_image, checksum):
    return {
        'version': 1,
        'scope': 'benchmark-api-component-v1',
        'nonce': active['nonce'],
        'instance': BENCHMARK_INSTANCE,
        'origin': DISPLAY_ORIGIN,
        'initial_a': active['initial_a'],
        'collector_source_sha': active['source_sha'],
        'collector_artifact_sha256': active['artifact_sha256'],
        'collector_image': active['image_id'],
        'api_source_sha': new_source,
        'api_artifact_sha256': new_artifact,
        'api_image': new_image,
        'api_schema_sha256': checksum,
    }


def build(source_sha, artifact, archive):
    active, ctx = watch()
    request = Request(source_sha, artifact, active['controller_sha256'], instance=BENCHMARK_INSTANCE)
    request.validate()
    budget = Budget(300)
    actions = _image_binding(ctx, budget, watch_diagnostics=True)
    actions._host_headroom()
    folder = ROOT / ('api-' + artifact)
    folder.mkdir(mode=0o700, exist_ok=True)
    meta = folder.lstat()
    require(
        stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o700,
        'unsafe_api_stage',
    )
    raw = archive.read(COMPRESSED_LIMIT + 1)
    require(
        len(raw) <= COMPRESSED_LIMIT and hashlib.sha256(raw).hexdigest() == artifact,
        'api_artifact_mismatch',
    )
    # Immutable destination per attempt permits retries after interrupted builds.
    dest = Path(tempfile.mkdtemp(prefix='candidate-', dir=folder))
    source = dest / 'source'
    extract_archive(io.BytesIO(raw), source, request, budget)
    digest = compatible_build(ctx.source, source)
    image_path = dest / 'image-id'
    budget.run(
        [
            'docker',
            'build',
            '--quiet',
            '--iidfile',
            str(image_path),
            '--label',
            'tradebot.source_sha=' + source_sha,
            '--label',
            'tradebot.api_schema_sha256=' + digest,
            '--label',
            'tradebot.api_artifact_sha256=' + artifact,
            '-f',
            str(source / 'deploy/preprod/Dockerfile'),
            str(source),
        ],
        env=actions._environment('unused'),
        timeout=240,
    )
    image = image_path.read_text().strip()
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', image), 'unbound_api_image')
    info = actions._json(
        budget.run(['docker', 'image', 'inspect', image], env=actions._environment(image))
    )[0]
    require(
        info['Id'] == image
        and info['Config']['User'] == '10001:10001'
        and all(
            info['Config']['Labels'].get(k) == v
            for k, v in {
                'tradebot.source_sha': source_sha,
                'tradebot.api_artifact_sha256': artifact,
                'tradebot.api_schema_sha256': digest,
            }.items()
        ),
        'api_build_binding_drift',
    )
    rec = component_record(active, source_sha, artifact, image, digest)
    write_json(folder / 'prepared.json', rec)
    return rec


def protected_state(ctx, actions, budget):
    actions._postgres(ctx, budget)
    services = {}
    for service in ('postgres', 'operator', 'calculation', 'lifecycle'):
        ids = actions._ids(ctx, budget, [service])
        require(len(ids) == 1, 'missing_protected_service')
        row = actions._inspect(budget, ids)[0]
        require(row['State']['Running'], 'protected_service_stopped')
        services[service] = {
            'id': row['Id'],
            'started_at': row['State']['StartedAt'],
            'pid': row['State']['Pid'],
        }
    state = json.loads(
        actions._reader_sql(
            budget,
            """SELECT json_build_object('session',collector_session_id,
        'epoch',epoch,'generation',generation_id,'enabled',collector_enabled AND
        collector_lease_expires_at > clock_timestamp(),'ttl',extract(epoch FROM collector_lease_expires_at-clock_timestamp()))
        FROM ops.writer_state WHERE origin_id='pp-live-pp-benchmark-watch'""",
        )
    )
    require(state['enabled'] and state['session'] and state['ttl'] > 0, 'watch_lease_lost')
    ledger = json.loads(
        actions._reader_sql(
            budget,
            """SELECT json_agg(json_build_array(name,checksum) ORDER BY version)
        FROM (SELECT version,name,checksum FROM ops.schema_migrations ORDER BY version LIMIT 65) checked""",
        )
    )
    require(ledger == [list(row) for row in schema(ctx.source)], 'deployed_schema_files_mismatch')
    return {
        'containers': services,
        'writer': {k: v for k, v in state.items() if k != 'ttl'},
        'schema': actions._schema_ledger(budget),
    }, state['ttl']


def api_identity(ctx, actions, budget):
    ids = actions._ids(ctx, budget, ['api'])
    require(len(ids) == 1, 'missing_api_instance')
    row = actions._inspect(budget, ids)[0]
    return {
        'id': row['Id'],
        'pid': row['State']['Pid'],
        'started_at': row['State']['StartedAt'],
        'image': row['Image'],
    }


def progress(actions, budget):
    return json.loads(
        actions._reader_sql(
            budget,
            """
        SELECT json_build_object('utc',clock_timestamp(),'latest_outbox_id',
            (SELECT id FROM ops.outbox o WHERE o.origin_id=w.origin_id AND o.generation_id=w.generation_id
             ORDER BY id DESC LIMIT 1),'verified_rows',
            (SELECT (cursor->>'rows')::bigint FROM archive.checkpoints a WHERE a.origin_id=w.origin_id
             AND a.generation_id=w.generation_id AND a.consumer='structured:verified-acks-v1'))
        FROM ops.writer_state w WHERE w.origin_id='pp-live-pp-benchmark-watch'""",
        )
    )


def api_up(ctx, active, actions, budget, image):
    live = LiveTransition(
        actions,
        replace(ctx, image=image),
        budget,
        initial_a=active['initial_a'],
        trial_origin=DISPLAY_ORIGIN,
    )
    live._compose_live(
        ['up', '-d', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '20', 'api'], timeout=25
    )
    ids = actions._ids(ctx, budget, ['api'])
    require(
        len(ids) == 1 and actions._inspect(budget, ids)[0]['Image'] == image, 'api_recreate_wrong_image'
    )
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 5
    while True:
        with opener.open('http://127.0.0.1:8000/state/current', timeout=2) as response:
            state = json.loads(response.read(65537))
        if state.get('origin_id') == DISPLAY_ORIGIN and type(state['collector']['enabled']) is bool:
            break
        require(time.monotonic() < deadline, 'api_state_unhealthy')
        time.sleep(0.2)
    with opener.open('http://127.0.0.1:8000/events', timeout=3) as events:
        lines = [events.readline(65537) for _ in range(2)]
        snapshot = next((json.loads(line[5:]) for line in lines if line.startswith(b'data:')), None)
        require(snapshot and snapshot.get('origin_id') == DISPLAY_ORIGIN, 'api_sse_unhealthy')


def switch(ctx, active, actions, budget, target, previous, *, probe=api_up):
    journal = ctx.staging / 'benchmark-api-component.json'

    def set_receipt(value):
        if value is None:
            journal.unlink(missing_ok=True)
        else:
            write_json(journal, value)

    try:
        probe(ctx, active, actions, budget, target['api_image'])
        set_receipt(target)
        actions._runtime(ctx, budget, live=True, initial_a=active['initial_a'], trial_origin=DISPLAY_ORIGIN)
    except Exception:
        set_receipt(previous)
        probe(ctx, active, actions, Budget(40), previous['api_image'] if previous else ctx.image)
        raise


def recover(artifact):
    """Recover an interrupted exchange to its recorded predecessor without touching any writer."""
    with locked():
        active, ctx = watch(require_armed=False)
        pending = ctx.staging / 'benchmark-api-update-pending.json'
        if not pending.exists():
            return {'state': 'complete'}
        with continued_renewal(lambda: renew_existing(active), needed=False):
            entry = json.loads(_secure_file(pending)[0])
            require(
                entry['candidate']['api_artifact_sha256'] == artifact
                and entry['candidate']['nonce'] == active['nonce'],
                'recovery_candidate_binding_mismatch',
            )
            previous = entry['previous']
            actions = _image_binding(ctx, Budget(10), watch_diagnostics=True)
            marker = ctx.staging / 'benchmark-api-component.json'
            if previous:
                require(
                    previous['nonce'] == active['nonce'] and previous['collector_image'] == ctx.image,
                    'invalid_rollback_receipt',
                )
                write_json(marker, previous)
            else:
                marker.unlink(missing_ok=True)
            api_up(ctx, active, actions, Budget(40), previous['api_image'] if previous else ctx.image)
            actions._runtime(
                ctx, Budget(25), live=True, initial_a=active['initial_a'], trial_origin=DISPLAY_ORIGIN
            )
            pending.unlink()
            return {'state': 'rolled_back', 'collector_source_sha': active['source_sha']}


def apply(artifact):
    with locked():
        active, ctx = watch()
        with continued_renewal(lambda: renew_existing(active), needed=True):
            budget = Budget(55)
            actions = _image_binding(ctx, budget, watch_diagnostics=True)
            _owned_runtime(actions, ctx, budget)
            actions._runtime(
                ctx, budget, live=True, initial_a=active['initial_a'], trial_origin=DISPLAY_ORIGIN
            )
            candidate = json.loads(_secure_file(ROOT / ('api-' + artifact) / 'prepared.json')[0])
            require(
                candidate
                == component_record(
                    active,
                    candidate['api_source_sha'],
                    artifact,
                    candidate['api_image'],
                    candidate['api_schema_sha256'],
                ),
                'api_candidate_binding_drift',
            )
            marker = ctx.staging / 'benchmark-api-component.json'
            previous = json.loads(_secure_file(marker)[0]) if marker.exists() else None
            before, ttl = protected_state(ctx, actions, budget)
            previous_api = api_identity(ctx, actions, budget)
            require(previous_api['image'] != candidate['api_image'], 'api_candidate_already_installed')
            before_progress = progress(actions, budget)
            require(ttl >= 85, 'wait_for_fresh_watch_renewal')
            pending = ctx.staging / 'benchmark-api-update-pending.json'
            require(not pending.exists(), 'unfinished_api_update')
            # Arm a host-owned rollback before the first mutation. It becomes a cheap no-op
            # when the final gate removed the pending record, even if SSH has disconnected.
            installed = Path('/usr/local/lib/tradebot-pp/benchmark-api-update.py')
            require(
                Path(__file__).resolve() == installed and installed.stat().st_uid == 0,
                'unqualified_api_helper',
            )
            subprocess.run(
                [
                    '/usr/bin/systemd-run',
                    '--quiet',
                    '--collect',
                    '--on-active=75s',
                    '/usr/bin/python3',
                    '-I',
                    str(installed),
                    'recover',
                    '--artifact',
                    artifact,
                ],
                check=True,
                timeout=8,
            )
            write_json(pending, {'previous': previous, 'candidate': candidate})
            try:
                switch(ctx, active, actions, budget, candidate, previous)
            except Exception:
                restored, _ = protected_state(ctx, actions, Budget(25))
                require(restored == before, 'protected_state_changed_on_recovery')
                actual = actions._inspect(Budget(10), actions._ids(ctx, Budget(10), ['api']))[0]['Image']
                require(
                    actual == (previous['api_image'] if previous else ctx.image), 'api_rollback_unproven'
                )
                pending.unlink()
                raise
            after, _ = protected_state(ctx, actions, budget)
            require(before == after, 'protected_services_or_writer_changed')
            current_api = api_identity(ctx, actions, budget)
            require(
                current_api['id'] != previous_api['id'] and current_api['image'] == candidate['api_image'],
                'api_change_unproven',
            )
            after_progress = progress(actions, budget)
            pending.unlink()
            return dict(
                gate='PP_BENCHMARK_API_UPDATE_PASS',
                before=before,
                after=after,
                api=candidate,
                api_before=previous_api,
                api_after=current_api,
                progress_before=before_progress,
                progress_after=after_progress,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'apply', 'recover'])
    parser.add_argument('--source')
    parser.add_argument('--artifact', required=True)
    args = parser.parse_args()
    require(
        os.geteuid() == 0 and re.fullmatch('[a-f0-9]{64}', args.artifact), 'invalid_benchmark_api_command'
    )
    if args.action == 'build':
        result = build(args.source, args.artifact, sys.stdin.buffer)
    elif args.action == 'recover':
        result = recover(args.artifact)
    else:
        result = apply(args.artifact)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
