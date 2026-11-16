"""CP6 Storage wire tests; all HTTP is intercepted by a generated transport."""
import os
from pathlib import Path
import tempfile
import unittest

import httpx

from postgres.archive_codec import (ArchiveIntegrityError, ArchiveLimit,
                                    ArchiveLimits, ArchiveUnavailable, CycleBudget)
from postgres.supabase_storage import (BUCKET, PROJECT_URL, SupabaseStorageTransport,
                                       read_token_file)


KEY = ('raw-v1/' + 'a' * 64 + '/00000000-0000-4000-8000-000000000001/' +
       'b' * 64 + '.jsonl.gz')
TOKEN = 'generated-secret-for-mock-only'


class SupabaseStorageTests(unittest.TestCase):
    def client(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        self.addCleanup(client.close)
        return SupabaseStorageTransport(TOKEN, client=client)

    def test_create_only_then_authenticated_exact_readback(self):
        requests = []
        def handle(request):
            requests.append(request)
            if request.method == 'POST':
                self.assertEqual(request.content, b'exact compressed bytes')
                self.assertEqual(request.headers['x-upsert'], 'false')
                return httpx.Response(200, json={'Key': KEY})
            return httpx.Response(200, content=b'exact compressed bytes')
        transport = self.client(handle)
        transport.put_if_absent(KEY, b'exact compressed bytes', timeout_seconds=2)
        self.assertEqual(transport.read_authenticated(KEY, max_bytes=128, timeout_seconds=2),
                         b'exact compressed bytes')
        self.assertEqual([request.method for request in requests], ['POST', 'GET'])
        self.assertEqual(requests[0].url.host, 'xttdqeimdujweijxcuro.supabase.co')
        self.assertEqual(requests[0].url.path, '/storage/v1/object/' + BUCKET + '/' + KEY)
        self.assertEqual(requests[1].url.path,
                         '/storage/v1/object/authenticated/' + BUCKET + '/' + KEY)
        self.assertEqual(requests[0].headers['authorization'], 'Bearer ' + TOKEN)

    def test_existing_object_requires_exact_bytes_and_accounts_second_request(self):
        calls = []
        def handle(request):
            calls.append(request.method)
            if request.method == 'POST':
                return httpx.Response(409, json={'code':'KeyAlreadyExists'})
            return httpx.Response(200, content=b'original')
        transport = self.client(handle)
        with CycleBudget(ArchiveLimits(max_requests=2)) as budget:
            budget.request(len(b'original'))
            transport.put_if_absent(KEY, b'original', timeout_seconds=2)
            self.assertEqual(budget.requests, 2)
        self.assertEqual(calls, ['POST', 'GET'])
        with self.assertRaises(ArchiveIntegrityError):
            transport.put_if_absent(KEY, b'changed', timeout_seconds=2)

    def test_ambiguous_post_and_unknown_errors_hold_without_overwrite(self):
        for response in [httpx.ReadTimeout('sensitive=' + TOKEN),
                         httpx.Response(400, json={'code':'NoSuchKey'}),
                         httpx.Response(409, json={'code':'Unrecognized'})]:
            with self.subTest(response=type(response).__name__):
                calls = []
                def handle(request):
                    calls.append(request.method)
                    if isinstance(response, Exception):
                        raise response
                    return response
                transport = self.client(handle)
                with self.assertRaises(ArchiveUnavailable) as raised:
                    transport.put_if_absent(KEY, b'original', timeout_seconds=2)
                self.assertNotIn(TOKEN, str(raised.exception))
                self.assertEqual(calls, ['POST'])

    def test_bounded_reads_key_validation_and_disabled_structured_path(self):
        calls = []
        def handle(request):
            calls.append(request.method)
            return httpx.Response(200, content=b'12345')
        transport = self.client(handle)
        for bad in ('../secret', KEY + '?upsert=true', KEY.replace('raw-v1/', 'other/')):
            with self.subTest(key=bad), self.assertRaises(ArchiveIntegrityError):
                transport.read_authenticated(bad, max_bytes=8, timeout_seconds=2)
        self.assertEqual(calls, [])
        with self.assertRaises(ArchiveLimit):
            transport.read_authenticated(KEY, max_bytes=4, timeout_seconds=2)
        with self.assertRaises(ArchiveLimit):
            transport.put_if_absent(KEY, b'x' * (2 * 1024 * 1024 + 1), timeout_seconds=2)
        with self.assertRaises(ArchiveUnavailable):
            transport.put_structured([], timeout_seconds=2)
        with self.assertRaises(ArchiveUnavailable):
            transport.read_structured_authenticated([], max_bytes=8, timeout_seconds=2)
        self.assertEqual(calls, ['GET'])

    def test_private_file_and_project_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'token'
            path.write_text(TOKEN + '\n')
            path.chmod(0o400)
            self.assertEqual(read_token_file(path), TOKEN)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_token_file(path)
            path.chmod(0o400)
            alias = Path(folder) / 'alias'
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                read_token_file(alias)
        for url, bucket in [('https://other.supabase.co', BUCKET), (PROJECT_URL, 'public')]:
            with self.assertRaises(ValueError):
                SupabaseStorageTransport(TOKEN, project_url=url, bucket=bucket)


if __name__ == '__main__':
    unittest.main()
