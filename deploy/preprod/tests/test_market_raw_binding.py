"""Offline policy binding and fault tests; no Supabase access."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest

from deploy.preprod.bind_market_raw_policy import (BUCKET, PROJECT_REF, TEMPLATE,
                                                    READBACK_PATCH, render,
                                                    render_readback_patch,
                                                    render_rollback, write_new)


UID = '00000000-0000-4000-8000-0000000000aa'
EMAIL = 'pp-storage-archive@example.invalid'


class PolicyBindingTests(unittest.TestCase):
    def test_exact_binding_and_private_nonoverwriting_output(self):
        sql = render(UID, EMAIL, project_ref=PROJECT_REF, bucket=BUCKET)
        self.assertEqual(sql.count(UID.encode()), 4)
        self.assertIn(b"raw_app_meta_data->>'tradebot_origin'='pp-live-pp'", sql)
        self.assertNotIn(b'__PP_STORAGE_', sql)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'candidate.sql'
            self.assertEqual(write_new(output, sql), hashlib.sha256(sql).hexdigest())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_new(output, sql)

    def test_wrong_project_bucket_uid_email_and_changed_template_fail(self):
        cases = [dict(project_ref='wrong'), dict(bucket='knowledge'),
                 dict(uid='__PP_STORAGE_AUTH_UID__'), dict(uid=UID.upper()),
                 dict(email="person'@example.com"),
                 dict(template=TEMPLATE.read_bytes() + b'-- changed\n')]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                render(**(dict(uid=UID, email=EMAIL, project_ref=PROJECT_REF,
                               bucket=BUCKET) | changes))

    def test_rollback_revokes_only_reviewed_policy_grants(self):
        sql = render_rollback(UID, EMAIL, project_ref=PROJECT_REF, bucket=BUCKET)
        self.assertIn(b'DROP POLICY tradebot_pp_raw_upload', sql)
        self.assertIn(b'DROP POLICY tradebot_pp_raw_readback', sql)
        self.assertIn(b'policy set changed; manual review required', sql)
        self.assertNotIn(b'DELETE FROM', sql)
        self.assertNotIn(b'DROP TABLE', sql)
        self.assertNotIn(b'DELETE USER', sql)
        with self.assertRaises(ValueError):
            render_rollback(UID, EMAIL, project_ref='wrong', bucket=BUCKET)

    def test_legacy_readback_patch_is_exact_and_preserves_upload(self):
        sql = render_readback_patch(UID, EMAIL, project_ref=PROJECT_REF,
                                    bucket=BUCKET, expected_policy_sha256='a' * 64)
        self.assertIn(b"'object.get_authenticated_info'", sql)
        self.assertIn(b"'storage.object.get_authenticated'", sql)
        self.assertIn(b'ALTER POLICY tradebot_pp_raw_readback', sql)
        self.assertNotIn(b'ALTER POLICY tradebot_pp_raw_upload', sql)
        self.assertNotIn(b'DROP POLICY', sql)
        self.assertNotIn(b'DELETE FROM', sql)
        self.assertNotIn(b'__EXPECTED_POLICY_SHA256__', sql)
        for changes in ({'expected_policy_sha256': '0' * 64},
                        {'expected_policy_sha256': 'wrong'},
                        {'project_ref': 'wrong'},
                        {'bucket': 'knowledge'},
                        {'template': READBACK_PATCH.read_bytes() + b'-- changed\n'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                render_readback_patch(**(dict(uid=UID, email=EMAIL,
                                              project_ref=PROJECT_REF,
                                              bucket=BUCKET,
                                              expected_policy_sha256='a' * 64) | changes))


if __name__ == '__main__':
    unittest.main()
