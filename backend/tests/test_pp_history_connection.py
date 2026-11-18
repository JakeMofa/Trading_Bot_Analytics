"""Generated-only tests of the private PP history connection binding."""
import base64
import hashlib
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from postgres.pp_history_connection import PPHistoryConnectionFactory


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class PPHistoryConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.ca_file, self.dsn_file = root / 'ca.crt', root / 'history_dsn'
        self.ca = ('-----BEGIN CERTIFICATE-----\n' +
                   base64.b64encode(b'generated-pp-test-ca').decode() +
                   '\n-----END CERTIFICATE-----\n')
        self.ca_file.write_text(self.ca)
        self.ca_file.chmod(0o644)
        self.dsn = (
            'host=aws-1-us-west-2.pooler.supabase.com port=5432 dbname=postgres '
            'user=tradebot_pp_history.xttdqeimdujweijxcuro '
            'password=' + 'x' * 48 + ' sslmode=verify-full '
            'sslrootcert=' + str(self.ca_file) +
            ' connect_timeout=5 application_name=tradebot_pp_history\n')
        self.dsn_file.write_text(self.dsn)
        self.dsn_file.chmod(0o600)
        digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.ca)).hexdigest()
        binding = patch('postgres.pp_history_connection.PP_CA_DER_SHA256', digest)
        binding.start()
        self.addCleanup(binding.stop)

    def factory(self):
        return PPHistoryConnectionFactory(self.dsn_file, self.ca_file)

    def test_exact_private_binding_and_deadline(self):
        connection = Connection()
        with patch('psycopg.connect', return_value=connection) as connect:
            self.assertIs(self.factory()(timeout_seconds=4), connection)
        self.assertFalse(connection.closed)
        self.assertGreaterEqual(connect.call_args.kwargs['connect_timeout'], 2)
        self.assertLessEqual(connect.call_args.kwargs['connect_timeout'], 4)
        self.assertEqual(connect.call_args.args[0], self.dsn.strip())

    def test_wrong_scope_and_extra_parameters_never_connect(self):
        for replacement in (
            'host=attacker.invalid',
            'user=postgres.xttdqeimdujweijxcuro',
            'sslmode=require',
            'sslrootcert=/tmp/untrusted',
            'connect_timeout=30',
            'application_name=other',
            'host=aws-1-us-west-2.pooler.supabase.com hostaddr=127.0.0.1',
        ):
            with self.subTest(replacement=replacement):
                original = self.dsn.split()
                key = replacement.split('=')[0]
                candidate = [part for part in original if not part.startswith(key + '=')]
                candidate.extend(replacement.split())
                self.dsn_file.write_text(' '.join(candidate))
                with patch('psycopg.connect') as connect, self.assertRaises(ArchiveIntegrityError):
                    self.factory()(timeout_seconds=4)
                connect.assert_not_called()

    def test_file_and_ca_mismatch_fail_closed(self):
        with patch('psycopg.connect') as connect:
            self.dsn_file.chmod(0o644)
            with self.assertRaises(ArchiveIntegrityError):
                self.factory()(timeout_seconds=4)
            self.dsn_file.chmod(0o600)
            self.ca_file.write_text(
                '-----BEGIN CERTIFICATE-----\n' +
                base64.b64encode(b'changed-ca').decode() +
                '\n-----END CERTIFICATE-----\n')
            with self.assertRaises(ArchiveIntegrityError):
                self.factory()(timeout_seconds=4)
            self.ca_file.write_text(self.ca)
            alias = self.dsn_file.parent / 'alias'
            alias.symlink_to(self.dsn_file)
            with self.assertRaises(ArchiveIntegrityError):
                PPHistoryConnectionFactory(alias, self.ca_file)(timeout_seconds=4)
            connect.assert_not_called()

    def test_low_budget_and_late_connection_never_return(self):
        with patch('psycopg.connect') as connect, self.assertRaises(ArchiveLimit):
            self.factory()(timeout_seconds=1.9)
        connect.assert_not_called()
        connection = Connection()
        with patch('psycopg.connect', return_value=connection), \
                patch('postgres.pp_history_connection.time.monotonic',
                      side_effect=(100.0, 100.1, 104.0)), \
                self.assertRaises(ArchiveLimit):
            self.factory()(timeout_seconds=3)
        self.assertTrue(connection.closed)

    def test_connect_errors_never_include_secret(self):
        with patch('psycopg.connect', side_effect=RuntimeError('password=' + 'x' * 48)):
            with self.assertRaises(ArchiveUnavailable) as error:
                self.factory()(timeout_seconds=3)
        self.assertNotIn('password=', str(error.exception))


if __name__ == '__main__':
    unittest.main()
