from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('live_resource_observe', HERE / 'live_resource_observe.py')
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


class LiveResourceObserverTests(unittest.TestCase):
    def fixture(self):
        return {'writer': {'generation_id': 'generated-uuid', 'epoch': 2,
                           'collector_enabled': True, 'lease_expires_at': '2026-11-18T00:00:00Z'},
                'generations': [{'generation_id': 'generated-uuid', 'slot': 'A',
                                 'state': 'collecting', 'bounded_raw_rows': 4,
                                 'relation_bytes': 81920}],
                'database_bytes': 11000000, 'temporary_bytes': 0}

    def test_query_is_read_only_and_generation_bounded(self):
        self.assertIn('BEGIN READ ONLY', observer.SQL)
        self.assertIn("SET LOCAL statement_timeout='3000ms'", observer.SQL)
        self.assertIn('LIMIT 10001', observer.SQL)
        self.assertIn("origin_id='pp-live-pp'", observer.SQL)
        data = observer.validate_database_result(self.fixture())
        self.assertIs(data['generations'][0]['raw_count_exact_within_bound'], True)
        data['generations'][0]['bounded_raw_rows'] = 10001
        self.assertIs(observer.validate_database_result(data)['generations'][0]['raw_count_exact_within_bound'], False)
        data['generations'][0]['bounded_raw_rows'] = 10002
        with self.assertRaises(observer.ObservationHold):
            observer.validate_database_result(data)

    def test_wal_is_bounded_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / 'volumes' / observer.VOLUME / '_data'
            wal = data / 'pg_wal'
            wal.mkdir(parents=True)
            (wal / ('A' * 24)).write_bytes(b'x' * 16)
            (wal / 'archive_status').mkdir()
            self.assertEqual(observer.wal_allocation(data)['wal_segment_bytes'], 16)
            (wal / ('B' * 24)).symlink_to(wal / ('A' * 24))
            with self.assertRaises(observer.ObservationHold):
                observer.wal_allocation(data)

    def test_generated_host_sample_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder) / 'volumes' / observer.VOLUME / '_data'
            wal = mount / 'pg_wal'
            wal.mkdir(parents=True)
            (wal / ('A' * 24)).write_bytes(b'x' * 32)
            container = [{'Name': '/' + observer.CONTAINER,
                          'State': {'Running': True},
                          'Config': {'Labels': {'com.docker.compose.project': 'tradebot-pp-foundation',
                                                'com.docker.compose.service': 'postgres'}},
                          'HostConfig': {'PortBindings': {}},
                          'Mounts': [{'Destination': '/var/lib/postgresql/data',
                                      'Type': 'volume', 'Name': observer.VOLUME}]}]
            volume = [{'Name': observer.VOLUME, 'Mountpoint': str(mount)}]
            raw = [json.dumps(container).encode(), json.dumps(volume).encode(),
                   json.dumps(self.fixture()).encode()]
            with patch.object(observer, 'host_binding'), \
                 patch.object(observer, 'run', side_effect=raw) as commands, \
                 patch.object(observer, 'memory_available', return_value=1234):
                result = observer.collect('mid')
            self.assertEqual(commands.call_count, 3)
            self.assertEqual(result['origin_id'], 'pp-live-pp')
            self.assertEqual(result['database']['generations'][0]['bounded_raw_rows'], 4)
            self.assertEqual(result['wal_segment_bytes'], 32)
            self.assertEqual(result['host_memory_available_bytes'], 1234)
            serialized = json.dumps(result)
            self.assertNotIn('PGPASSWORD', serialized)
            self.assertNotIn('secret', serialized)


if __name__ == '__main__':
    unittest.main()
