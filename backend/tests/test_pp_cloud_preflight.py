"""Offline PP cloud binding checks; no credential content or network access."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from postgres.pp_cloud_preflight import (EXPECTED_FILES, FILE_ENV, OFF_FLAGS,
                                         PPCloudBinding, main)


def environment():
    result = {'TRADEBOT_ENVIRONMENT': 'preprod', 'TRADEBOT_DATA_MODE': 'pp_live',
              'TRADEBOT_ORIGIN_ID': 'pp-live-pp'}
    result.update({FILE_ENV[name]: path for name, path in EXPECTED_FILES.items()})
    return result


class PPCloudPreflightTests(unittest.TestCase):
    def test_exact_binding_stays_off(self):
        binding = PPCloudBinding.from_environment(environment())
        self.assertEqual(set(binding.files), set(EXPECTED_FILES))
        self.assertTrue(all(isinstance(path, Path) for path in binding.files.values()))
        for key, value in [('TRADEBOT_ENVIRONMENT', 'production'),
                           ('TRADEBOT_DATA_MODE', 'generated'),
                           ('TRADEBOT_ORIGIN_ID', 'pp-live-other')]:
            modified = environment()
            modified[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                PPCloudBinding.from_environment(modified)
        for flag in OFF_FLAGS:
            modified = environment()
            modified[flag] = 'true'
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                PPCloudBinding.from_environment(modified)

    def test_no_alias_or_missing_binding(self):
        for purpose, key in FILE_ENV.items():
            modified = environment()
            modified[key] = EXPECTED_FILES['storage_api_key'] if purpose != 'storage_api_key' else ''
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                PPCloudBinding.from_environment(modified)

    def test_file_metadata_checks_without_reading_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            for name in EXPECTED_FILES:
                path = Path(temporary) / name
                path.write_bytes(b'x')
                path.chmod(0o400)
                paths[name] = path
            binding = PPCloudBinding(paths)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('read')):
                binding.check_file_metadata()
            paths['structured_dsn'].unlink()
            os.link(paths['local_lifecycle_dsn'], paths['structured_dsn'])
            with self.assertRaises(ValueError):
                binding.check_file_metadata()
            paths['structured_dsn'].unlink()
            paths['structured_dsn'].symlink_to(paths['local_lifecycle_dsn'])
            with self.assertRaises(ValueError):
                binding.check_file_metadata()

    def test_entrypoint_fails_closed_without_file_or_cloud_activity(self):
        with patch.dict(os.environ, environment(), clear=True), patch('builtins.print') as output:
            self.assertEqual(main(), 1)
        self.assertIn('pp_cloud_binding_invalid', output.call_args.args[0])

    def test_entrypoint_still_stops_with_synthetic_private_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = {}
            for name in EXPECTED_FILES:
                path = Path(temporary) / name
                path.write_bytes(b'x')
                path.chmod(0o400)
                expected[name] = str(path)
            configured = environment()
            configured.update({FILE_ENV[name]: path for name, path in expected.items()})
            with patch('postgres.pp_cloud_preflight.EXPECTED_FILES', expected), \
                    patch.dict(os.environ, configured, clear=True), \
                    patch('builtins.print') as output:
                self.assertEqual(main(), 1)
            status = output.call_args.args[0]
            self.assertIn('structured_role_login_unqualified', status)
            self.assertIn('structured_receipts_grants_unqualified', status)
            self.assertNotIn(temporary, status)


if __name__ == '__main__':
    unittest.main()
