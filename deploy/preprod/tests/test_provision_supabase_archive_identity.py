import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "provision_supabase_archive_identity.py"
spec = importlib.util.spec_from_file_location("provision_supabase_archive_identity", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

UID = "f429a64e-6aa0-48b2-8268-1d5581764296"
EMAIL = "tradebot-pp-archive@example.invalid"
KEY = b"test-admin-key-never-print"


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.key_file = self.root / "admin-key"
        self.key_file.write_bytes(KEY + b"\n")
        os.chmod(self.key_file, 0o400)
        self.stage = self.root / "stage"
        self.calls = 0

    def invoke(self, requester, **changes):
        options = dict(project_ref=module.PROJECT_REF, email=EMAIL,
                       admin_key_file=self.key_file, output_dir=self.stage,
                       execute=True, request_fn=requester)
        options.update(changes)
        return module.provision(**options)

    def success(self, payload, key):
        self.calls += 1
        self.assertEqual(key, KEY)
        body = json.loads(payload)
        self.assertEqual(body["email"], EMAIL)
        self.assertTrue(body["email_confirm"])
        self.assertEqual(body["app_metadata"], {
            "tradebot_role": "pp_storage_archive", "tradebot_origin": "pp-live-pp"})
        self.assertEqual(len(body["password"]), 64)
        self.assertEqual(body["password"], (self.stage / "supabase_auth_password").read_text().strip())
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")
        return 201, json.dumps({"id": UID, "email": EMAIL,
                                "app_metadata": body["app_metadata"]}).encode()

    def test_create_stages_private_files_and_returns_only_uid(self):
        uid = self.invoke(self.success)
        self.assertEqual(uid, UID)
        self.assertEqual(self.calls, 1)
        self.assertEqual(stat.S_IMODE(self.stage.stat().st_mode), 0o700)
        self.assertEqual({p.name for p in self.stage.iterdir()},
                         {"supabase_auth_email", "supabase_auth_password", "supabase_auth_uid", "status"})
        for path in self.stage.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        self.assertEqual((self.stage / "supabase_auth_uid").read_text().strip(), UID)
        self.assertEqual((self.stage / "status").read_text().strip(), "CREATED_VERIFIED_RESPONSE")
        with self.assertRaises(module.ProvisionError):
            self.invoke(self.success)
        self.assertEqual(self.calls, 1)

    def test_private_history_reader_stages_distinct_files_and_verifies_role(self):
        def create(payload, key):
            body = json.loads(payload)
            self.assertEqual(body["app_metadata"], {
                "tradebot_role": "pp_storage_history_reader", "tradebot_origin": "pp-live-pp"})
            self.assertEqual(body["password"], (self.stage / "history_reader_password").read_text().strip())
            return 201, json.dumps(dict(id=UID, email=EMAIL, app_metadata=body["app_metadata"])).encode()
        self.assertEqual(self.invoke(create, purpose="history-reader"), UID)
        self.assertEqual({p.name for p in self.stage.iterdir()},
                         {"history_reader_email", "history_reader_password", "history_reader_uid", "status"})
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o400 for p in self.stage.iterdir()))

    def test_history_reader_rejects_writer_metadata_and_preserves_uncertain_stage(self):
        def wrong(payload, key):
            return 201, json.dumps(dict(id=UID, email=EMAIL, app_metadata={
                "tradebot_role": "pp_storage_archive", "tradebot_origin": "pp-live-pp"})).encode()
        with self.assertRaises(module.ProvisionError):
            self.invoke(wrong, purpose="history-reader")
        self.assertFalse((self.stage / "history_reader_uid").exists())
        self.assertTrue((self.stage / "history_reader_password").exists())
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")

    def test_definite_duplicate_rejection_cleans_private_stage(self):
        def duplicate(payload, key):
            self.calls += 1
            return 422, b'{"message":"already exists"}'
        with self.assertRaisesRegex(module.ProvisionError, "rejected") as caught:
            self.invoke(duplicate)
        self.assertEqual(self.calls, 1)
        self.assertFalse(self.stage.exists())
        self.assertNotIn(EMAIL, str(caught.exception))
        self.assertNotIn(KEY.decode(), str(caught.exception))

    def test_timeout_keeps_stage_and_forbids_blind_retry(self):
        def timeout(payload, key):
            self.calls += 1
            raise TimeoutError("secret body and admin key")
        with self.assertRaisesRegex(module.ProvisionError, "uncertain") as caught:
            self.invoke(timeout)
        self.assertEqual(self.calls, 1)
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")
        self.assertTrue((self.stage / "supabase_auth_password").exists())
        self.assertFalse((self.stage / "supabase_auth_uid").exists())
        self.assertNotIn("secret body", str(caught.exception))
        with self.assertRaises(module.ProvisionError):
            self.invoke(timeout)
        self.assertEqual(self.calls, 1)

    def test_ambiguous_http_and_mismatched_binding_keep_stage(self):
        responses = [(503, b""), (201, b"not-json"),
                     (201, json.dumps({"id": UID, "email": "wrong@example.invalid",
                                      "app_metadata": {"tradebot_role": "pp_storage_archive",
                                                       "tradebot_origin": "pp-live-pp"}}).encode())]
        for status, body in responses:
            with self.subTest(status=status, body=body[:8]):
                with self.assertRaises(module.ProvisionError):
                    self.invoke(lambda _payload, _key: (status, body))
                self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")
                self.assertFalse((self.stage / "supabase_auth_uid").exists())
                module._discard_stage(self.stage)

    def test_wrong_scope_unsafe_key_and_implicit_run_never_request(self):
        def forbidden(*_args):
            self.fail("request must not be sent")
        for change in ({"project_ref": "another-project"}, {"execute": False},
                       {"email": "User@Example.com"}):
            with self.subTest(change=change), self.assertRaises(module.ProvisionError):
                self.invoke(forbidden, **change)
            self.assertFalse(self.stage.exists())
        os.chmod(self.key_file, 0o644)
        with self.assertRaises(module.ProvisionError):
            self.invoke(forbidden)
        self.assertFalse(self.stage.exists())

    def test_key_symlink_rejected_before_stage(self):
        link = self.root / "key-link"
        link.symlink_to(self.key_file)
        with self.assertRaises(OSError):
            self.invoke(lambda *_: self.fail("request must not be sent"), admin_key_file=link)
        self.assertFalse(self.stage.exists())

    def test_partial_staging_failure_removes_credentials_before_http(self):
        original = module._write_private
        def fail_second(directory, name, content):
            if name == "supabase_auth_password":
                raise OSError("test-only failure with secret")
            return original(directory, name, content)
        with patch.object(module, "_write_private", side_effect=fail_second):
            with self.assertRaises(module.ProvisionError) as caught:
                self.invoke(lambda *_: self.fail("request must not be sent"))
        self.assertFalse(self.stage.exists())
        self.assertNotIn("test-only failure", str(caught.exception))

    def test_short_file_writes_complete_or_remove_partial_file(self):
        private = self.root / "private"
        private.mkdir(mode=0o700)
        original = os.write
        def short_write(descriptor, content):
            return original(descriptor, content[:3])
        with patch.object(module.os, "write", side_effect=short_write):
            module._write_private(private, "complete", b"abcdefghi")
        self.assertEqual((private / "complete").read_bytes(), b"abcdefghi")

        calls = 0
        def stall_write(descriptor, content):
            nonlocal calls
            calls += 1
            return original(descriptor, content[:3]) if calls == 1 else 0
        with patch.object(module.os, "write", side_effect=stall_write):
            with self.assertRaises(OSError):
                module._write_private(private, "incomplete", b"abcdefghi")
        self.assertFalse((private / "incomplete").exists())

    def test_post_success_uid_write_failure_keeps_uncertain_stage(self):
        original = module._write_private
        def fail_uid(directory, name, content):
            if name == "supabase_auth_uid":
                raise OSError("test-only UID write failure")
            return original(directory, name, content)
        with patch.object(module, "_write_private", side_effect=fail_uid):
            with self.assertRaises(module.ProvisionError) as caught:
                self.invoke(self.success)
        self.assertEqual(self.calls, 1)
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")
        self.assertFalse((self.stage / "supabase_auth_uid").exists())
        self.assertNotIn("test-only UID", str(caught.exception))

    def test_post_success_status_write_failure_keeps_uncertain_stage(self):
        original = module._replace_status
        def fail_created(directory, value):
            if value == "CREATED_VERIFIED_RESPONSE":
                raise OSError("test-only status failure")
            return original(directory, value)
        with patch.object(module, "_replace_status", side_effect=fail_created):
            with self.assertRaises(module.ProvisionError) as caught:
                self.invoke(self.success)
        self.assertEqual(self.calls, 1)
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")
        self.assertEqual((self.stage / "supabase_auth_uid").read_text().strip(), UID)
        self.assertNotIn("test-only status", str(caught.exception))

    def test_post_success_status_sync_failure_restores_uncertain_stage(self):
        original = module._replace_status
        def fail_after_replace(directory, value):
            original(directory, value)
            if value == "CREATED_VERIFIED_RESPONSE":
                raise OSError("test-only post-rename sync failure")
        with patch.object(module, "_replace_status", side_effect=fail_after_replace):
            with self.assertRaises(module.ProvisionError):
                self.invoke(self.success)
        self.assertEqual(self.calls, 1)
        self.assertEqual((self.stage / "status").read_text().strip(), "UNCONFIRMED_CREATE")

    def test_request_never_redirects_or_uses_proxy(self):
        class Response:
            status = 201
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, length):
                self.length = length
                return b"{}"
        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()
        opener = Opener()
        with patch.object(module.urllib.request, "build_opener", return_value=opener) as build:
            result = module._default_request(b"{}", KEY)
        self.assertEqual(result, (201, b"{}"))
        self.assertEqual(opener.request.full_url, module.ADMIN_URL)
        self.assertEqual(opener.request.get_method(), "POST")
        self.assertEqual(opener.request.data, b"{}")
        self.assertEqual(opener.timeout, 10)
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer " + KEY.decode())
        self.assertEqual(opener.request.get_header("Apikey"), KEY.decode())
        self.assertIsInstance(build.call_args.args[0], module.urllib.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], module.NoRedirect)


if __name__ == "__main__":
    unittest.main()
