"""Generated-only PP Auth qualification; no network or live credentials."""
import concurrent.futures
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveLimit, ArchiveUnavailable, ArchiveLimits, CycleBudget
from postgres.supabase_storage import SupabaseStorageTransport


KEY = ('raw-v1/' + 'a' * 64 + '/00000000-0000-4000-8000-000000000001/' +
       'b' * 64 + '.jsonl.gz')
UID = '00000000-0000-4000-8000-000000000123'
API_KEY = 'sb_publishable_generated-public-project-key-123456'
EMAIL = 'pp-archive@example.test'
PASSWORD = 'generated-machine-password-12345'
EXP = int(time.time()) + 3600


def token(uid=UID, *, role='authenticated', suffix='first'):
    claims = {'sub': uid, 'role': role,
              'iss': 'https://xttdqeimdujweijxcuro.supabase.co/auth/v1',
              'exp': EXP}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    return f'generated-header.{encoded}.generated-signature-{suffix}'


class SupabaseMachineAuthTests(unittest.TestCase):
    def machine(self, handler, *, uid=UID):
        client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        self.addCleanup(client.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        paths = []
        for name, value in [('key', API_KEY), ('email', EMAIL),
                            ('password', PASSWORD), ('uid', uid)]:
            path = Path(folder.name) / name
            path.write_text(value + '\n')
            path.chmod(0o400)
            paths.append(path)
        return SupabaseStorageTransport.from_machine_files(*paths, client=client), paths

    @staticmethod
    def auth_response(access=None,
                      refresh='generated-refresh-token-123456', uid=UID):
        return httpx.Response(200, json={'access_token': access or token(uid),
                                         'refresh_token': refresh,
                                         'token_type': 'bearer',
                                         'expires_in': 3600,
                                         'user': {'id': uid}})

    def test_sign_in_upload_readback_and_restart(self):
        calls = []
        def handle(request):
            calls.append((request.method, request.url.path, request.url.query))
            if request.url.path == '/auth/v1/token':
                self.assertEqual(request.url.params['grant_type'], 'password')
                self.assertEqual(request.headers['apikey'], API_KEY)
                self.assertEqual(request.headers.get('authorization'), None)
                self.assertEqual(request.content, b'{"email":"pp-archive@example.test","password":"generated-machine-password-12345"}')
                return self.auth_response()
            self.assertEqual(request.headers['authorization'], 'Bearer ' + token())
            if request.method == 'POST':
                self.assertEqual(request.headers['x-upsert'], 'false')
                return httpx.Response(201, json={'Key': KEY})
            return httpx.Response(200, content=b'archive')
        machine, paths = self.machine(handle)
        machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        self.assertEqual(machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2),
                         b'archive')
        self.assertEqual([call[0] for call in calls], ['POST', 'POST', 'GET'])
        fresh = SupabaseStorageTransport.from_machine_files(*paths,
            client=machine._client)
        self.assertEqual(fresh.read_authenticated(KEY, max_bytes=32, timeout_seconds=2),
                         b'archive')
        self.assertEqual([call[1] for call in calls].count('/auth/v1/token'), 2)

    def test_refresh_once_for_concurrent_reads(self):
        calls = []
        mutex = threading.Lock()
        def handle(request):
            with mutex:
                calls.append(request)
            if request.url.path == '/auth/v1/token':
                if request.url.params['grant_type'] == 'password':
                    return self.auth_response()
                self.assertEqual(request.url.params['grant_type'], 'refresh_token')
                self.assertIn(b'generated-refresh-token-123456', request.content)
                return self.auth_response(token(suffix='refreshed'),
                                          'generated-refresh-token-rotated')
            return httpx.Response(200, content=b'archive')
        machine, _ = self.machine(handle)
        machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2)
        machine._machine._expires = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            values = list(pool.map(lambda _: machine.read_authenticated(
                KEY, max_bytes=32, timeout_seconds=2), range(6)))
        self.assertEqual(values, [b'archive'] * 6)
        grants = [r.url.params['grant_type'] for r in calls
                  if r.url.path == '/auth/v1/token']
        self.assertEqual(grants, ['password', 'refresh_token'])
        self.assertTrue(all(r.headers['authorization'] ==
                            'Bearer ' + token(suffix='refreshed') for r in calls[-6:]))

    def test_rejected_refresh_and_storage_unauthorized_fail_closed(self):
        calls = []
        def handle(request):
            calls.append(request.url.path)
            if request.url.path == '/auth/v1/token':
                if request.url.params['grant_type'] == 'refresh_token':
                    return httpx.Response(401, json={'message': PASSWORD})
                return self.auth_response()
            return httpx.Response(200, content=b'archive')
        machine, _ = self.machine(handle)
        machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2)
        machine._machine._expires = 0
        with self.assertRaises(ArchiveUnavailable) as error:
            machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        self.assertNotIn(PASSWORD, str(error.exception))
        before = len(calls)
        with self.assertRaises(ArchiveUnavailable):
            machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2)
        self.assertEqual(len(calls), before)
        self.assertEqual(calls.count('/storage/v1/object/market-raw/' + KEY), 0)

        def forbidden(request):
            if request.url.path == '/auth/v1/token':
                return self.auth_response()
            return httpx.Response(403)
        machine, _ = self.machine(forbidden)
        with self.assertRaises(ArchiveUnavailable):
            machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        with self.assertRaises(ArchiveUnavailable):
            machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2)

    def test_identity_mismatch_bad_files_and_budget(self):
        calls = []
        def wrong_user(request):
            calls.append(request.url.path)
            return self.auth_response(uid='00000000-0000-4000-8000-000000000999')
        machine, paths = self.machine(wrong_user)
        with self.assertRaises(ArchiveUnavailable):
            machine.read_authenticated(KEY, max_bytes=32, timeout_seconds=2)
        self.assertEqual(calls, ['/auth/v1/token'])
        machine, _ = self.machine(lambda request: self.auth_response(
            access=token(role='service_role')))
        with self.assertRaises(ArchiveUnavailable):
            machine.put_if_absent(KEY, b'x', timeout_seconds=2)
        paths[2].chmod(0o644)
        with self.assertRaises(ValueError):
            SupabaseStorageTransport.from_machine_files(*paths)
        paths[2].chmod(0o400)
        with CycleBudget(ArchiveLimits(max_requests=1)) as budget:
            budget.request(1)
            machine, _ = self.machine(lambda request: self.auth_response())
            with self.assertRaises(ArchiveLimit):
                machine.put_if_absent(KEY, b'x', timeout_seconds=2)
            self.assertEqual(budget.requests, 1)

    def test_oversize_auth_response_and_expired_deadline_do_not_upload(self):
        calls = []
        def oversized(request):
            calls.append(request.url.path)
            return httpx.Response(200, content=b'x' * 9000)
        machine, _ = self.machine(oversized)
        with self.assertRaises(ArchiveUnavailable):
            machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        self.assertEqual(calls, ['/auth/v1/token'])
        with self.assertRaises(ArchiveUnavailable):
            machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        self.assertEqual(calls, ['/auth/v1/token'])

        machine, _ = self.machine(lambda request: self.fail('expired request reached network'))
        machine._machine._lock.acquire()
        try:
            with self.assertRaises(ArchiveUnavailable):
                machine.read_authenticated(KEY, max_bytes=32,
                                           timeout_seconds=0.001)
        finally:
            machine._machine._lock.release()

    def test_transient_auth_failure_stops_current_work_then_later_cycle_recovers(self):
        calls = []
        def handle(request):
            calls.append(request.url.path)
            if request.url.path == '/auth/v1/token':
                if calls.count('/auth/v1/token') == 1:
                    raise httpx.ReadTimeout('secret=' + PASSWORD)
                return self.auth_response()
            return httpx.Response(200, content=b'archive')
        machine, _ = self.machine(handle)
        with self.assertRaises(ArchiveUnavailable) as error:
            machine.put_if_absent(KEY, b'archive', timeout_seconds=2)
        self.assertNotIn(PASSWORD, str(error.exception))
        self.assertEqual(calls, ['/auth/v1/token'])
        self.assertEqual(machine.read_authenticated(KEY, max_bytes=32,
                                                     timeout_seconds=2), b'archive')
        self.assertEqual(calls.count('/auth/v1/token'), 2)


if __name__ == '__main__':
    unittest.main()
