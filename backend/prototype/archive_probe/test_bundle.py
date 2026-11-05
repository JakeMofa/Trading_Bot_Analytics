"""Loopback acceptance for an isolated zipapp. Run with only these two files."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from zipfile import ZipFile

BUNDLE = Path(sys.argv.pop(1)).resolve()
PREFIX = '/storage/v1/object/'
KEY_PREFIX = 'market-raw/ab72-readiness/2026-11-03-v1/'


class Endpoint(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.server.requests.append(('GET', self.path))
        if (self.headers.get('Authorization') != 'Bearer fixture' or
                self.headers.get('apikey') != 'fixture' or
                not self.path.startswith(PREFIX+'authenticated/'+KEY_PREFIX)):
            self.send_error(403)
            return
        if self.server.body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.server.body + (b'corrupt' if self.server.corrupt else b''))

    def do_POST(self):
        self.server.requests.append(('POST', self.path))
        size = int(self.headers['Content-Length'])
        if (self.headers.get('x-upsert') != 'false' or not 0 < size <= 65536 or
                not self.path.startswith(PREFIX+KEY_PREFIX) or self.server.body is not None):
            self.send_error(409)
            return
        self.server.body = self.rfile.read(size)
        self.send_response(201)
        self.end_headers()


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Endpoint)
        self.server.body = None
        self.server.corrupt = False
        self.server.requests = []
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.shutdown)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = dict(
            endpoint=f'http://127.0.0.1:{self.server.server_port}',
            expected_uid=123,
            identity=dict(active='active', user='tradebot', directory='/opt/tradebot', uid=123,
                          cwd='/opt/tradebot', command=['/opt/tradebot/.venv/bin/python',
                                                        'backend/app/run_cloud_lifecycle.py','run']),
            config=dict(SUPABASE_URL='https://xttdqeimdujweijxcuro.supabase.co',
                        SUPABASE_RAW_BUCKET='market-raw', ENABLE_SUPABASE_SYNC='true',
                        SUPABASE_SECRET_KEY='fixture'),
        )

    def run_probe(self, fixture=None, bundle=BUNDLE):
        path = self.root/'mock.json'
        path.write_text(json.dumps(self.fixture if fixture is None else fixture))
        result = subprocess.run([sys.executable, '-IS', str(bundle), '--mock', str(path)],
                                cwd=self.root, env={}, capture_output=True, text=True, timeout=10)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_verified_round_trip(self):
        status, report = self.run_probe()
        self.assertEqual((status, report['result'], report['attempts'], report['rows']), (0,'PASS',3,2))
        self.assertEqual(report['bytes'], len(self.server.body))
        self.assertEqual([verb for verb, _ in self.server.requests], ['GET','POST','GET'])

    def test_missing_dependencies_never_reach_endpoint(self):
        for name in ('retention_recovery', 'retention', 'retention_timestamp_guards'):
            with self.subTest(name=name):
                broken = self.root/(name+'.pyz')
                with ZipFile(BUNDLE) as original, ZipFile(broken,'w') as modified:
                    for member in original.namelist():
                        if member != name+'.py':
                            modified.writestr(member, original.read(member))
                status, report = self.run_probe(bundle=broken)
                self.assertEqual((status,report['result'],report['attempts']), (1,'BLOCKED',0))
                self.assertEqual(report['reason'],f'missing bundled dependency: {name}')
                self.assertEqual(self.server.requests, [])

    def test_mismatches_never_reach_endpoint(self):
        for group, field, value, reason in (
            ('config','SUPABASE_URL','https://other.invalid','runtime project mismatch'),
            ('config','SUPABASE_RAW_BUCKET','other','runtime bucket mismatch'),
            ('identity','uid',456,'archive runtime identity mismatch'),
            ('identity','command',['wrong'],'archive runtime identity mismatch'),
        ):
            with self.subTest(field=field):
                fixture = copy.deepcopy(self.fixture)
                fixture[group][field] = value
                status, report = self.run_probe(fixture)
                self.assertEqual((status,report['result'],report['attempts']), (1,'BLOCKED',0))
                self.assertEqual(report['reason'], reason)
                self.assertEqual(self.server.requests, [])

    def test_corrupt_readback_stops_after_one_upload(self):
        self.server.corrupt = True
        status, report = self.run_probe()
        self.assertEqual((status,report['result'],report['attempts']), (1,'FAIL',3))
        self.assertEqual(report['reason'],'RecoveryError')

    def test_existing_object_stops_before_upload(self):
        self.server.body = b'existing'
        status, report = self.run_probe()
        self.assertEqual((status,report['result'],report['attempts']), (1,'FAIL',1))
        self.assertEqual(self.server.requests[0][0], 'GET')
        self.assertEqual(self.server.body, b'existing')


if __name__ == '__main__':
    unittest.main()
