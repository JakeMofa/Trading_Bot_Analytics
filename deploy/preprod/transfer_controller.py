"""One-release, code-only PP controller transfer over the pinned operator SSH route.

This tool is deliberately bound to the reviewed 701a68b source and existing
controller. It does not create a deployment authority or touch a database.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import struct
import subprocess
import sys
import zipfile


SOURCE = '701a68b433ed888c56ec48cc0555d0ff9e2e609e'
OLD = 'bdb11511039365990249846d1e5a521228255530db000a25181ad260f7aebee7'
NEW = 'c3fac37cb56945ad74d41188b8e22013a199fe8d656b87be4f4154676d3c9479'
FILES = {
    'install_controller.py': 'c141a9ac15326a3b8661f916c7c31292477bde331241a59c5b46873c1b1bf57e',
    'controller.py': 'c647fa951bc1419958cebd4e122847717c8a1c88813231102a4aec60ea238e1d',
    'transition_control.py': 'ab75cc19f11b55d696a8c7ca25c71649e3cb9651bbcf8251aa74d5e20a1934e0',
    'linux_actions.py': '561ff9c2152748997444b109f27c8eb37c83bb5ccd05532e9e5279f8a5a1d425',
}
ORDER = ('controller.pyz', *FILES)
HASHES = {'controller.pyz': NEW, **FILES}
ZIP_MEMBERS = frozenset((
    '__main__.py', 'controller.py', 'linux_actions.py', 'live_profile.py',
    'live_transition.py', 'transition_control.py', 'structured_probe_profile.py',
    'structured_probe_control.py', 'raw_archive_probe_profile.py',
    'raw_archive_probe_control.py'))
MAX_FILE = 256 * 1024
MAX_TOTAL = 1024 * 1024
MAGIC = b'TRADEBOT_PP_CONTROLLER_V1\n'
STAGE_PARENT = Path('/run/tradebot-pp-deploy')
STAGE = STAGE_PARENT / ('controller-stage-' + SOURCE[:12])
CURRENT = Path('/usr/local/lib/tradebot-pp/controller.pyz')
OLD_SAVED = Path('/usr/local/lib/tradebot-pp') / (OLD + '.pyz')
KEYS = Path('/var/lib/tradebot-pp-deploy/.ssh/authorized_keys')
ACTIVE = Path('/var/lib/tradebot-pp/deployments/active-live-transition.json')
HOST = 'ubuntu@18.119.253.233'
MARKER = Path('/etc/tradebot/preprod-host.json')
FORCED_PREFIX = 'restrict,command="/usr/local/bin/tradebot-pp-deploy" '


class TransferStop(Exception):
    """The scoped transfer cannot safely proceed."""


def require(condition, code):
    if not condition:
        raise TransferStop(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload_for(bundle, repo):
    """Export exact tracked source; local edits cannot enter the transfer."""
    blob = Path(bundle).read_bytes()
    contents = {'controller.pyz': blob}
    for name in FILES:
        result = subprocess.run(
            ['git', 'show', f'{SOURCE}:deploy/preprod/{name}'], cwd=repo,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=True)
        contents[name] = result.stdout
    output = bytearray(MAGIC)
    total = 0
    for name in ORDER:
        data = contents[name]
        require(len(data) <= MAX_FILE and digest(data) == HASHES[name], 'local_source_mismatch')
        total += len(data)
        require(total <= MAX_TOTAL, 'local_transfer_too_large')
        output.extend(struct.pack('>I', len(data)))
        output.extend(data)
    return bytes(output)


def read_exact(stream, size):
    chunks = []
    while size:
        chunk = stream.read(size)
        require(bool(chunk), 'truncated_transfer')
        chunks.append(chunk)
        size -= len(chunk)
    return b''.join(chunks)


def decode_payload(stream):
    require(read_exact(stream, len(MAGIC)) == MAGIC, 'invalid_transfer_header')
    contents = {}
    total = 0
    for name in ORDER:
        size = struct.unpack('>I', read_exact(stream, 4))[0]
        require(0 < size <= MAX_FILE, 'transfer_member_too_large')
        total += size
        require(total <= MAX_TOTAL, 'transfer_too_large')
        data = read_exact(stream, size)
        require(digest(data) == HASHES[name], 'transfer_digest_mismatch')
        contents[name] = data
    require(stream.read(1) == b'', 'transfer_trailing_data')
    try:
        with zipfile.ZipFile(io.BytesIO(contents['controller.pyz'])) as archive:
            members = archive.infolist()
            require(len(members) == len(ZIP_MEMBERS)
                    and {item.filename for item in members} == ZIP_MEMBERS
                    and all(stat.S_ISREG(item.external_attr >> 16) for item in members)
                    and sum(item.file_size for item in members) <= MAX_FILE,
                    'unexpected_bundle_members')
    except zipfile.BadZipFile:
        raise TransferStop('invalid_bundle_archive') from None
    return contents


def root_file(path, *, private=False):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'unsafe_host_file')
    if private:
        require(not info.st_mode & 0o077, 'unsafe_private_file')
    return path.read_bytes()


def root_directory(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,
            'unsafe_stage_parent')


def public_key(path=KEYS):
    lines = root_file(path).decode('ascii').splitlines()
    require(len(lines) == 1 and lines[0].startswith(FORCED_PREFIX), 'unexpected_deploy_key')
    key = lines[0][len(FORCED_PREFIX):]
    require(re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{68}(?: [A-Za-z0-9._@-]{1,100})?', key),
            'unexpected_deploy_key')
    return (key + '\n').encode('ascii')


def checked_host():
    marker = json.loads(root_file(MARKER))
    require(socket.gethostname() == 'tradebot-preprod-01'
            and marker.get('environment') == 'preprod'
            and marker.get('project') == 'Tradebot'
            and marker.get('live_collector_authorized') is False
            and marker.get('paid_ai_authorized') is False
            and marker.get('production_data_copied') is False,
            'wrong_host_binding')


def write_exclusive(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def stage_is_safe(path):
    info = path.lstat()
    return (stat.S_ISDIR(info.st_mode) and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o700)


def receive_and_install(stream, *, stage_parent=STAGE_PARENT, stage=STAGE,
                        current=CURRENT, old_saved=OLD_SAVED, key_file=KEYS,
                        invoke=None):
    """Root-only receiver. Validate every byte before installing any code."""
    require(os.geteuid() == 0, 'root_required')
    contents = decode_payload(stream)
    checked_host()
    root_directory(stage_parent)
    require(digest(root_file(current, private=True)) == OLD, 'unexpected_installed_controller')
    # Existing state must be stable and all one-use authorities absent.
    for name in ('authorization.json', 'live-enter.json', 'live-on.json',
                 'structured-probe.json', 'raw-archive-probe.json'):
        path = stage_parent / name
        require(not path.exists() and not path.is_symlink(), 'unused_authority_present')
    if ACTIVE.exists() or ACTIVE.is_symlink():
        active = json.loads(root_file(ACTIVE))
        require(active.get('state') == 'generated_restored', 'active_live_transition')
    # The public half of the already approved deploy key is passed to the
    # installer. Its private half is never read or transferred.
    key = public_key(key_file)
    os.mkdir(stage, 0o700)
    try:
        require(stage_is_safe(stage), 'unsafe_stage_directory')
        for name, data in contents.items():
            write_exclusive(stage / name, data)
        write_exclusive(stage / 'deploy-key.pub', key)
        fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        command = ['/usr/bin/python3', '-BEs', str(stage / 'install_controller.py'),
                   'install', '--bundle', str(stage / 'controller.pyz'),
                   '--sha256', NEW, '--public-key-file', str(stage / 'deploy-key.pub')]
        runner = invoke or subprocess.run
        result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        timeout=90, check=False)
        require(result.returncode == 0, 'installer_failed')
        require(digest(root_file(current, private=True)) == NEW, 'installed_digest_mismatch')
        require(digest(root_file(old_saved, private=True)) == OLD, 'previous_code_not_retained')
        return {'gate': 'CONTROLLER_INSTALLED_NOT_AUTHORIZED', 'source_sha': SOURCE,
                'previous_sha256': OLD, 'controller_sha256': NEW,
                'database_changed': False, 'authority_created': False}
    finally:
        # Remove only the exact scoped stage directory, never host data.
        for name in (*ORDER, 'deploy-key.pub'):
            (stage / name).unlink(missing_ok=True)
        stage.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--send', action='store_true')
    modes.add_argument('--receive', action='store_true')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--identity', type=Path)
    parser.add_argument('--known-hosts', type=Path)
    args = parser.parse_args(argv)
    if args.receive:
        require(not any((args.bundle, args.repo, args.identity, args.known_hosts)),
                'unexpected_receiver_argument')
        result = receive_and_install(sys.stdin.buffer)
        print(json.dumps(result, sort_keys=True))
        return
    require(all((args.bundle, args.repo, args.identity, args.known_hosts)),
            'missing_operator_argument')
    for path in (args.identity, args.known_hosts):
        require(path.is_file() and not path.is_symlink(), 'invalid_operator_file')
    payload = payload_for(args.bundle, args.repo)
    # The reviewed receiver source is passed as a fixed Python -c argument;
    # only the five verified payload members travel on stdin.
    code = Path(__file__).read_text()
    remote = ('sudo -n /usr/bin/timeout --signal=TERM --kill-after=5s 110s '
              '/usr/bin/python3 -I -c ' + shlex.quote(code) + ' --receive')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=7',
               '-o', 'UserKnownHostsFile=' + str(args.known_hosts), '-i', str(args.identity),
               HOST, remote]
    result = subprocess.run(command, input=payload, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=120, check=False)
    require(result.returncode == 0, 'remote_transfer_or_install_failed')
    outcome = json.loads(result.stdout)
    require(outcome.get('gate') == 'CONTROLLER_INSTALLED_NOT_AUTHORIZED'
            and outcome.get('controller_sha256') == NEW, 'unexpected_install_result')
    print(json.dumps(outcome, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (TransferStop, OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('PP controller transfer STOP; inspect sanitized host evidence') from None
