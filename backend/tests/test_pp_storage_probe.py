"""Offline synthetic Storage HTTP probe fault tests; no live network."""
from __future__ import annotations

import unittest
import httpx

from deploy.preprod.probe_market_raw_storage import ProbeFailure, run_probe

UID = '00000000-0000-4000-8000-0000000000aa'
EMAIL = 'pp-storage-archive@example.invalid'


class ProbeTests(unittest.TestCase):
    def probe(self, *, upload='success', read='exact', public=403, auth='correct'):
        state = {'calls': [], 'data': None, 'key': None}

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


if __name__ == '__main__':
    unittest.main()
