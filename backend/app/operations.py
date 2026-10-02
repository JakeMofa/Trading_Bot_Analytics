"""Local collector controls and consistent SQLite backup/recovery (no orders)."""
import argparse
import asyncio
from contextlib import contextmanager, closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time


def paths(database):
    database = Path(database).resolve()
    # macOS limits Unix socket paths to 104 bytes; use a short private directory.
    root = Path(tempfile.gettempdir()) / f'btc-collector-{os.getuid()}'
    root.mkdir(mode=0o700, exist_ok=True)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise RuntimeError('Collector control directory must be private to this user')
    token = hashlib.sha256(str(database).encode()).hexdigest()[:24]
    return root / f'{token}.lock', root / f'{token}.sock'


@contextmanager
def collector_lock(database):
    lock_path, socket_path = paths(database)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A collector already owns this database') from None
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({'pid': os.getpid(), 'database': str(Path(database).resolve())}))
        lock.flush()
        try:
            yield socket_path
        finally:
            socket_path.unlink(missing_ok=True)
            fcntl.flock(lock, fcntl.LOCK_UN)


def status(database):
    lock_path, _ = paths(database)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            try:
                owner = json.load(lock)
            except (ValueError, OSError):
                owner = {}
            return {'running': True, **owner}
        fcntl.flock(lock, fcntl.LOCK_UN)
    return {'running': False, 'database': str(Path(database).resolve())}


async def control_server(socket_path, stop):
    socket_path.unlink(missing_ok=True)

    async def handle(reader, writer):
        try:
            request = await asyncio.wait_for(reader.readline(), 2)
            if request == b'stop\n':
                stop.set()
                writer.write(b'stop requested\n')
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=str(socket_path))
    os.chmod(socket_path, 0o600)
    return server


def stop_collector(database, timeout=45):
    if not status(database)['running']:
        if fresh_unmanaged_collector(database):
            raise RuntimeError('Legacy collector is active; no controlled shutdown available')
        return status(database)
    _, socket_path = paths(database)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(socket_path))
        client.sendall(b'stop\n')
        if client.recv(100) != b'stop requested\n':
            raise RuntimeError('Collector did not acknowledge shutdown')
    deadline = time.monotonic() + timeout
    while status(database)['running']:
        if time.monotonic() >= deadline:
            raise TimeoutError('Graceful shutdown still pending; no forced kill performed')
        time.sleep(.1)
    return status(database)


def fresh_unmanaged_collector(database):
    path = Path(database).resolve()
    if not path.exists():
        return False
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='feed_health'").fetchone():
            return False
        return bool(db.execute("SELECT 1 FROM feed_health WHERE source='rest_supervisor' AND status='running' AND julianday('now')-julianday(updated_at)<90.0/86400").fetchone())


def start_collector(database, max_storage_mb=2048):
    if status(database)['running']:
        raise RuntimeError('Collector is already running')
    if fresh_unmanaged_collector(database):
        raise RuntimeError('Fresh collector heartbeat without control lock; stop the legacy process first')
    database = Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name('streaming.py').resolve()
    log = database.with_suffix(database.suffix + '.collector.log')
    with log.open('ab') as output:
        child = subprocess.Popen([sys.executable, str(script), '--db', str(database),
                                  '--seconds', '0', '--max-storage-mb', str(max_storage_mb)],
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 start_new_session=True, cwd=str(script.parents[2]))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = status(database)
        if state['running'] and state.get('pid') == child.pid and paths(database)[1].exists():
            return {**state, 'log': str(log), 'note': 'Process started; inspect feed health for readiness'}
        if child.poll() is not None:
            raise RuntimeError(f'Collector exited ({child.returncode}); inspect {log}')
        time.sleep(.1)
    raise TimeoutError(f'Start not confirmed; inspect status and {log} before retrying')


def verify(db):
    check = [row[0] for row in db.execute('PRAGMA integrity_check')]
    foreign = db.execute('PRAGMA foreign_key_check').fetchall()
    if check != ['ok'] or foreign:
        raise ValueError('SQLite integrity or foreign-key validation failed')


def backup(source, destination, timeout=60):
    """Use SQLite's online API, include committed WAL data, never overwrite evidence."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination or any(Path(str(destination) + suffix).exists()
                                    for suffix in ('', '-wal', '-shm')):
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sqlite-backup-', dir=destination.parent)
    os.close(fd)
    deadline = time.monotonic() + timeout

    def progress(code, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('Backup deadline exceeded; destination not published')

    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst, pages=256, progress=progress, sleep=.05)
                verify(dst)
                dst.execute('PRAGMA journal_mode=DELETE')
        with open(temporary, 'rb') as saved:
            os.fsync(saved.fileno())
        # Atomic publication that fails if another command created the destination.
        os.link(temporary, destination)
        return {'database': str(destination), 'bytes': destination.stat().st_size,
                'integrity': 'ok', 'source': str(source)}
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'start', 'stop', 'restart', 'backup', 'recover'])
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--destination', help='New backup/recovery path; existing files are never overwritten')
    parser.add_argument('--max-storage-mb', type=int, default=2048)
    args = parser.parse_args()
    if args.max_storage_mb < 1:
        parser.error('max storage must be at least 1 MiB')
    if args.action in ('backup', 'recover') and not args.destination:
        parser.error('--destination is required')
    try:
        if args.action in ('backup', 'recover'):
            result = backup(args.db, args.destination)
        elif args.action == 'status':
            result = status(args.db)
            result['fresh_unmanaged_heartbeat'] = not result['running'] and fresh_unmanaged_collector(args.db)
        else:
            if args.action in ('stop', 'restart'):
                result = stop_collector(args.db)
            if args.action in ('start', 'restart'):
                result = start_collector(args.db, args.max_storage_mb)
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
