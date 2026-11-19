"""Bounded, read-only PP PostgreSQL and host sample for one live trial.

Run over the pinned operator SSH connection with ``sudo python3 -IS -`` and
this file on stdin. No database secret, raw payload, or price is emitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess

HOST = 'tradebot-preprod-01'
CONTAINER = 'tradebot-pp-foundation-postgres-1'
VOLUME = 'tradebot_pp_pgdata'
ORIGIN = 'pp-live-pp'
ROW_LIMIT = 10001
SEGMENT = re.compile(r'[0-9A-F]{24}(?:\.partial)?')
SQL_SHELL = ('export PGPASSWORD="$(cat /run/secrets/reader)"; '
             'exec psql -X -qAt --set ON_ERROR_STOP=1 -h 127.0.0.1 '
             '-U tradebot_reader -d tradebot_pp')
SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='3000ms';
SELECT json_build_object(
  'writer', (SELECT json_build_object('generation_id',generation_id,
      'epoch',epoch,'collector_enabled',collector_enabled,
      'lease_expires_at',collector_lease_expires_at)
    FROM ops.writer_state WHERE origin_id='pp-live-pp'),
  'generations', (SELECT coalesce(json_agg(json_build_object(
      'generation_id',g.generation_id,'slot',g.slot,'state',g.state,
      'bounded_raw_rows',(SELECT count(*) FROM (SELECT 1 FROM raw.events e
          WHERE e.generation_id=g.generation_id AND e.origin_id='pp-live-pp'
          LIMIT 10001) bounded),
      'relation_bytes',pg_total_relation_size(
          to_regclass('raw.'||quote_ident(g.partition_name))))
      ORDER BY g.created_at),'[]'::json)
    FROM archive.generations g WHERE g.origin_id='pp-live-pp'
      AND g.state<>'retired'),
  'relations',(SELECT jsonb_object_agg(nspname,totals) FROM (
    SELECT n.nspname, jsonb_build_object('heap',sum(pg_relation_size(c.oid)),
        'indexes',sum(pg_indexes_size(c.oid)),'total',sum(pg_total_relation_size(c.oid))) totals
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('raw','core','archive','ops') AND c.relkind='r'
      GROUP BY n.nspname) sizes),
  'wal_written_since_stats_reset',(SELECT wal_bytes FROM pg_stat_wal),
  'wal_stats_reset',(SELECT stats_reset FROM pg_stat_wal),
  'database_bytes',pg_database_size(current_database()),
  'temporary_bytes',(SELECT temp_bytes FROM pg_stat_database
     WHERE datname=current_database()));
COMMIT;
"""


class ObservationHold(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise ObservationHold(reason)


def run(args, *, input_bytes=None, timeout=10, max_output=65536):
    """Bounded child; no child stderr or credential value enters evidence."""
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        output, _ = process.communicate(input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise ObservationHold('child_deadline_exceeded') from None
    require(process.returncode == 0, 'read_only_child_failed')
    require(len(output) <= max_output, 'observation_output_too_large')
    return output


def host_binding(path=Path('/etc/tradebot/preprod-host.json')):
    require(os.geteuid() == 0 and socket.gethostname() == HOST, 'wrong_host_or_identity')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and
            not info.st_mode & 0o022 and info.st_size <= 4096,
            'unsafe_host_marker')
    marker = json.loads(path.read_text())
    require(marker.get('environment') == 'preprod' and marker.get('project') == 'Tradebot'
            and marker.get('production_data_copied') is False,
            'wrong_host_marker')


def container_binding(inspect):
    require(isinstance(inspect, list) and len(inspect) == 1, 'missing_pp_postgres')
    item = inspect[0]
    labels = item.get('Config', {}).get('Labels', {})
    require(item.get('Name') == '/' + CONTAINER and item.get('State', {}).get('Running') is True
            and labels.get('com.docker.compose.project') == 'tradebot-pp-foundation'
            and labels.get('com.docker.compose.service') == 'postgres'
            and not item.get('HostConfig', {}).get('PortBindings'),
            'unexpected_pp_postgres_binding')
    mounts = [m for m in item.get('Mounts', []) if m.get('Destination') == '/var/lib/postgresql/data']
    require(len(mounts) == 1 and mounts[0].get('Type') == 'volume'
            and mounts[0].get('Name') == VOLUME, 'unexpected_pp_postgres_volume')


def wal_allocation(mountpoint):
    root = Path(mountpoint)
    require(root.is_absolute() and root.name == '_data' and
            root.parent.name == VOLUME and root.parent.parent.name == 'volumes',
            'unexpected_pp_volume_mountpoint')
    folder = root / 'pg_wal'
    require(not root.is_symlink() and not folder.is_symlink() and folder.is_dir(),
            'unsafe_pg_wal_path')
    files = 0
    total = 0
    with os.scandir(folder) as entries:
        for entry in entries:
            files += 1
            require(files <= 256, 'pg_wal_file_bound_exceeded')
            if SEGMENT.fullmatch(entry.name):
                info = entry.stat(follow_symlinks=False)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        'unsafe_pg_wal_segment')
                total += info.st_size
    return {'wal_segment_bytes': total, 'wal_directory_entries': files}


def validate_database_result(data):
    require(isinstance(data, dict) and isinstance(data.get('writer'), dict)
            and isinstance(data.get('generations'), list)
            and len(data['generations']) <= 2,
            'invalid_pp_database_sample')
    writer = data['writer']
    require(isinstance(writer.get('epoch'), int)
            and isinstance(writer.get('collector_enabled'), bool),
            'invalid_pp_writer_sample')
    for row in data['generations']:
        require(row.get('slot') in ('A', 'B') and
                row.get('state') in ('prepared', 'collecting', 'sealed', 'verified')
                and isinstance(row.get('bounded_raw_rows'), int)
                and 0 <= row['bounded_raw_rows'] <= ROW_LIMIT
                and isinstance(row.get('relation_bytes'), int)
                and row['relation_bytes'] >= 0,
                'invalid_pp_generation_sample')
        row['raw_count_exact_within_bound'] = row['bounded_raw_rows'] < ROW_LIMIT
    require(all(isinstance(data.get(key), int) and data[key] >= 0
                for key in ('database_bytes', 'temporary_bytes')),
            'invalid_pp_storage_sample')
    return data


def memory_available(path=Path('/proc/meminfo')):
    values = dict(line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)
    text = values.get('MemAvailable', '').strip().split()
    require(len(text) == 2 and text[0].isdigit() and text[1] == 'kB',
            'memory_availability_unavailable')
    return int(text[0]) * 1024


def collect(phase):
    host_binding()
    inspect = json.loads(run(['docker', 'inspect', CONTAINER], timeout=8))
    container_binding(inspect)
    volumes = json.loads(run(['docker', 'volume', 'inspect', VOLUME], timeout=8))
    require(isinstance(volumes, list) and len(volumes) == 1
            and volumes[0].get('Name') == VOLUME, 'unexpected_pp_volume')
    result = json.loads(run(['docker', 'exec', '-i', CONTAINER, 'sh', '-ec', SQL_SHELL],
                            input_bytes=SQL.encode(), timeout=8, max_output=32768))
    validate_database_result(result)
    disk = shutil.disk_usage('/')
    return {'scope': 'pp_live_read_only_resource_sample', 'phase': phase,
            'observed_at_utc': datetime.now(timezone.utc).isoformat(),
            'origin_id': ORIGIN, 'database': result,
            **wal_allocation(volumes[0].get('Mountpoint')),
            'filesystem_free_bytes': disk.free,
            'host_memory_available_bytes': memory_available(),
            'raw_count_semantics': 'bounded_exact_below_10001_otherwise_lower_bound',
            'cloud_archive': 'NOT_MEASURED', 'retirement': 'NOT_MEASURED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=('before', 'mid', 'after'))
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.phase), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, ObservationHold):
        print(json.dumps({'scope': 'pp_live_read_only_resource_sample',
                          'phase': args.phase, 'result': 'INCOMPLETE'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
