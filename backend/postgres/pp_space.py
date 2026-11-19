"""Fresh PP reserve sample on the host-qualified PostgreSQL filesystem bind."""
import os
from pathlib import Path
import stat
import time

FLOOR = 10 * 1024**3
BIND = '/run/secrets/lifecycle_dsn'


def sample():
    started = time.monotonic()
    try:
        # Check only mount metadata. Never open or read the secret.
        info = os.lstat(BIND)
        device = f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'
        mounts = [line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()]
        matches = [row for row in mounts if len(row) >= 10 and row[4] == BIND]
        if (not stat.S_ISREG(info.st_mode) or len(matches) != 1 or matches[0][2] != device
                or 'ro' not in matches[0][5].split(',')):
            raise ValueError('unverified mount')
        space = os.statvfs(BIND)
        free = space.f_frsize * space.f_bavail
        if space.f_frsize <= 0 or space.f_bavail < 0 or time.monotonic() - started > 2:
            raise ValueError('unavailable or stale sample')
    except (OSError, ValueError, UnicodeError):
        return {'filesystem_free_bytes': None, 'filesystem_floor_bytes': FLOOR,
                'space_hold': 'pp_filesystem_sample_unavailable'}
    return {'filesystem_free_bytes': free, 'filesystem_floor_bytes': FLOOR,
            'space_hold': 'pp_filesystem_reserve' if free < FLOOR else None}
