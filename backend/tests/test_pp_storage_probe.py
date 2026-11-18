"""Offline synthetic Storage HTTP probe fault tests; no live network."""
from __future__ import annotations

import unittest
import httpx
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

from deploy.preprod.probe_market_raw_storage import ProbeFailure, run_probe
from deploy.preprod.probe_market_raw_storage import ORIGIN_HASH

UID = '00000000-0000-4000-8000-0000000000aa'
EMAIL = 'pp-storage-archive@example.invalid'
LIVE_GENERATION = uuid.UUID('500b0871-6f59-46de-a17c-537f6b0aee5d')
LIVE_DIGEST = '5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf'
LIVE_KEY = f'raw-v1/{ORIGIN_HASH}/{LIVE_GENERATION}/{LIVE_DIGEST}.jsonl.gz'
LIVE_RECORDS = [{'probe': 'pp-storage-v1', 'origin': 'pp-live-pp',
                 'generation': str(LIVE_GENERATION), 'sequence': i} for i in (1, 2)]
LIVE_BLOB = gzip.compress((''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n'
                              for row in LIVE_RECORDS)).encode(), mtime=0)


class ProbeTests(unittest.TestCase):
    def probe(self, *, upload='success', read='exact', public=403, auth='correct',
              stored_data=None):
        state = {'calls': [], 'data': stored_data, 'key': None}

        def handler(request):
            state['calls'].append((request.method, str(request.url)))
            if request.url.path == '/auth/v1/user':
                detail = {'id': UID, 'email': EMAIL, 'role': 'authenticated',
                          'app_metadata': {'tradebot_role': 'pp_storage_archive',
                                           'tradebot_origin': 'pp-live-pp'}}
                if auth == 'wrong_uid':
                    detail['id'] = '00000000-0000-4000-8000-0000000000bb'
                return httpx.Response(200, json=detail)
            if request.method == 'POST':
                state['data'] = request.content
                state['key'] = request.url.path
                if upload == 'timeout':
                    raise httpx.ReadTimeout('ambiguous write')
                if upload == 'duplicate':
                    return httpx.Response(409, json={'code': 'Duplicate'})
                return httpx.Response(201)
            if '/authenticated/' in request.url.path:
                body = state['data'] if read == 'exact' else b'corrupt'
                return httpx.Response(200, content=body)
            return httpx.Response(public)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        operation = lambda: run_probe('sb_publishable_test', 'bearer', UID, EMAIL,
                                      client=client)
        return operation, state, client

    def test_success_and_public_denial(self):
        operation, state, _ = self.probe()
        result = operation()
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(result['http_attempts'], 4)
        self.assertTrue(result['object_retained'])
        self.assertEqual(sum(method == 'POST' for method, _ in state['calls']), 1)
        self.assertEqual(result['bytes'], len(state['data']))

    def test_duplicate_and_ambiguous_timeout_reconcile_exact_bytes(self):
        for outcome in ('duplicate', 'timeout'):
            with self.subTest(outcome=outcome):
                operation, state, _ = self.probe(upload=outcome)
                self.assertTrue(operation()['ambiguous_upload_reconciled'])
                self.assertEqual(sum(method == 'POST' for method, _ in state['calls']), 1)

    def test_mismatch_and_denial_fail_closed(self):
        for variant in ({'auth': 'wrong_uid'}, {'read': 'corrupt'},
                        {'public': 200}, {'public': 500}):
            with self.subTest(variant=variant):
                operation, state, _ = self.probe(**variant)
                with self.assertRaises(ProbeFailure):
                    operation()
                if variant.get('auth'):
                    self.assertEqual(len(state['calls']), 1)

    def test_deadline_and_wrong_uid_refuse_before_network(self):
        operation, state, client = self.probe()
        with self.assertRaises(ProbeFailure):
            run_probe('sb_publishable_test', 'bearer', 'wrong', EMAIL, client=client)
        with self.assertRaises(ProbeFailure):
            run_probe('sb_publishable_test', 'bearer', UID, EMAIL, client=client,
                      deadline_seconds=181)
        with self.assertRaises(ProbeFailure):
            run_probe('sb_secret_test', 'bearer', UID, EMAIL, client=client)
        self.assertEqual(state['calls'], [])

    def test_reconcile_only_retained_object_has_zero_post(self):
        self.assertEqual(len(LIVE_BLOB), 126)
        self.assertEqual(hashlib.sha256(LIVE_BLOB).hexdigest(), LIVE_DIGEST)
        _, state, client = self.probe(stored_data=LIVE_BLOB)
        result = run_probe('sb_publishable_test', 'bearer', UID, EMAIL,
                           client=client, reconcile_key=LIVE_KEY,
                           expected_bytes=126, expected_sha256=LIVE_DIGEST)
        self.assertEqual(result['mode'], 'reconcile-only')
        self.assertEqual(result['http_attempts'], 3)
        self.assertEqual([method for method, _ in state['calls']], ['GET'] * 3)

    def test_reconcile_only_wrong_key_digest_size_and_corruption_fail_closed(self):
        _, state, client = self.probe(stored_data=LIVE_BLOB)
        for key, size, digest in (
            (LIVE_KEY.replace(ORIGIN_HASH, 'f' * 64), 126, LIVE_DIGEST),
            (LIVE_KEY, 127, LIVE_DIGEST),
            (LIVE_KEY, 126, 'f' * 64),
        ):
            with self.subTest(key=key, size=size, digest=digest):
                with self.assertRaises(ProbeFailure):
                    run_probe('sb_publishable_test', 'bearer', UID, EMAIL,
                              client=client, reconcile_key=key,
                              expected_bytes=size, expected_sha256=digest)
        self.assertEqual(state['calls'], [])
        _, state, client = self.probe(stored_data=LIVE_BLOB, read='corrupt')
        with self.assertRaises(ProbeFailure):
            run_probe('sb_publishable_test', 'bearer', UID, EMAIL,
                      client=client, reconcile_key=LIVE_KEY,
                      expected_bytes=126, expected_sha256=LIVE_DIGEST)
        self.assertEqual(sum(method == 'POST' for method, _ in state['calls']), 0)

    def test_module_cli_loads_from_repository_root(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, '-m',
                                 'deploy.preprod.probe_market_raw_storage', '--help'],
                                cwd=root, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--reconcile-key', result.stdout)


if __name__ == '__main__':
    unittest.main()
