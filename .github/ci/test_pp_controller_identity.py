import importlib.util
from pathlib import Path
import subprocess
import unittest


PATH = Path(__file__).with_name('pp_controller_identity.py')
SPEC = importlib.util.spec_from_file_location('pp_controller_identity', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = 'a' * 64


class IdentityTests(unittest.TestCase):
    def test_exact_identity_passes(self):
        def runner(command, **kwargs):
            self.assertEqual(command[-1], 'identity-v1 preprod tradebot-preprod-01 ' + SHA)
            self.assertIn('StrictHostKeyChecking=yes', command)
            return subprocess.CompletedProcess(command, 0, b'{"gate":"IDENTITY_PASS","environment":"preprod","instance":"tradebot-preprod-01","controller_sha256":"' + SHA.encode() + b'","runtime_qualified":false,"database_changed":false}', b'')
        self.assertEqual(MODULE.check(SHA, 'synthetic-key', 'synthetic-pin', runner=runner)['gate'], 'IDENTITY_PASS')

    def test_missing_binding_fails_before_ssh(self):
        with self.assertRaises(ValueError):
            MODULE.check(SHA, '', 'synthetic-pin')
        with self.assertRaises(ValueError):
            MODULE.check('bad', 'synthetic-key', 'synthetic-pin')

    def test_mismatched_response_fails_closed(self):
        for response in (b'{}', b'not json', b'{"gate":"IDENTITY_PASS"}'):
            with self.subTest(response=response), self.assertRaises(ValueError):
                MODULE.check(SHA, 'synthetic-key', 'synthetic-pin',
                             runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 0, response, b''))


if __name__ == '__main__':
    unittest.main()
