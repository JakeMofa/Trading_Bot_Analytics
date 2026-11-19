import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.preprod import measure_storage_transfer as probe


class TransferTests(unittest.TestCase):
    def test_fixture_matches_measured_sizes_and_synthetic_content(self):
        items = probe.objects()
        self.assertEqual(sum(len(blob) for _, blob in items), 620549)
        self.assertEqual(tuple(len(blob) for _, blob in items), probe.SIZES)
        for index, (key, blob) in enumerate(items, 1):
            self.assertEqual(key, probe.PREFIX + hashlib.sha256(blob).hexdigest() + '.jsonl.gz')
            body = json.loads(gzip.decompress(blob))
            self.assertEqual((body['fixture'], body['part']), ('synthetic_pp_transfer_v1', index))
        self.assertEqual(len(set(key for key, _ in items)), 10)

    def test_only_fixed_create_and_two_reads_per_object_are_allowed(self):
        items = probe.objects()
        bounds = probe.RequestBounds(items)
        key = items[0][0]
        write = f'{probe.PROJECT_URL}/storage/v1/object/{probe.BUCKET}/{key}'
        read = f'{probe.PROJECT_URL}/storage/v1/object/authenticated/{probe.BUCKET}/{key}'
        for req in (httpx.Request('DELETE', write), httpx.Request('POST', write),
                    httpx.Request('GET', read + 'extra')):
            with self.assertRaises(probe.TransferHold):
                bounds.request(req)
        request = httpx.Request('POST', write, headers={'x-upsert': 'false'})
        bounds.request(request)
        with self.assertRaises(probe.TransferHold):
            bounds.request(request)
        bounds.request(httpx.Request('GET', read))
        bounds.request(httpx.Request('GET', read))
        with self.assertRaises(probe.TransferHold):
            bounds.request(httpx.Request('GET', read))
        with self.assertRaises(probe.TransferHold):
            bounds.response(httpx.Response(409))

    def test_scoped_auth_and_storage_transport_on_exact_31_mock_requests(self):
        items = probe.objects()
        bounds = probe.RequestBounds(items)
        uid = '4c67486d-08fa-47f6-9521-61d1d5451f32'
        data = {}
        def handle(request):
            if request.url.path == '/auth/v1/token':
                claims = dict(sub=uid, role='authenticated', aud='authenticated', exp=int(time.time())+1800,
                              iss=probe.PROJECT_URL + '/auth/v1', app_metadata={'tradebot_role':'pp_storage_archive'})
                encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
                return httpx.Response(200, json=dict(access_token='header.' + encoded + '.signature',
                    refresh_token='generated-refresh', token_type='bearer', expires_in=1800, user={'id': uid}))
            key = request.url.path.split('/' + probe.BUCKET + '/')[1]
            if request.method == 'POST':
                data[key] = request.content
                return httpx.Response(201)
            return httpx.Response(200, content=data[key])
        with tempfile.TemporaryDirectory() as folder:
            secrets = Path(folder)
            names = ('api', 'email', 'password', 'uid')
            for name, value in zip(names, ('sb_publishable_synthetic_' + 'a'*24, 'pp@example.invalid',
                                          'generated-long-password-value', uid)):
                path = secrets / name
                path.write_text(value)
                path.chmod(0o600)
            with httpx.Client(transport=httpx.MockTransport(handle),
                    event_hooks={'request':[bounds.request], 'response':[bounds.response]}) as client:
                storage = probe.SupabaseStorageTransport.from_machine_files(
                    *(secrets/name for name in names), client=client)
                report = probe.measure(storage, items, bounds)
        self.assertEqual(sum(v['bytes'] for v in report['uploads']), 620549)
        self.assertEqual(bounds.count, 31)
        self.assertFalse(any(bounds.allowed.values()))

    def test_two_read_passes_are_exact_and_corruption_holds(self):
        items = probe.objects()
        storage = Mock()
        lookup = dict(items)
        storage.read_authenticated.side_effect = lambda key, **kw: lookup[key]
        report = probe.measure(storage, items, probe.RequestBounds(items))
        self.assertEqual(len(report['uploads']), 10)
        self.assertEqual(len(report['first_reads']), 10)
        self.assertEqual(len(report['final_reads']), 10)
        self.assertEqual(storage.read_authenticated.call_count, 20)
        storage.reset_mock()
        storage.read_authenticated.side_effect = [blob for _, blob in items] + [b'wrong']
        with self.assertRaisesRegex(probe.TransferHold, 'exact_readback'):
            probe.measure(storage, items, probe.RequestBounds(items))
        self.assertEqual(storage.put_if_absent.call_count, 10)
