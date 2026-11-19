"""Default-OFF session reuse, fresh transaction discipline and failure discard."""
import base64
import hashlib
from pathlib import Path
import ssl
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg.pq import TransactionStatus
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from postgres.pp_history_session import ReusablePPHistoryConnectionFactory, session_reuse_requested


class Connection:
    def __init__(self):
        self.closed = self.broken = False
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        self.uncommitted_discarded = False

    def close(self):
        self.uncommitted_discarded = self.info.transaction_status != TransactionStatus.IDLE
        self.closed = True


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.dsn, self.ca = folder/'dsn', folder/'ca'
        pem = '-----BEGIN CERTIFICATE-----\n' + base64.b64encode(b'generated-session-ca').decode() + '\n-----END CERTIFICATE-----\n'
        self.ca.write_text(pem)
        self.ca.chmod(0o644)
        self.secret = ('host=aws-1-us-west-2.pooler.supabase.com port=5432 dbname=postgres '
            'user=tradebot_pp_history.xttdqeimdujweijxcuro password=' + 'x'*48 +
            ' sslmode=verify-full sslrootcert=' + str(self.ca) +
            ' connect_timeout=5 application_name=tradebot_pp_history')
        self.dsn.write_text(self.secret)
        self.dsn.chmod(0o600)
        binding = patch('postgres.pp_history_connection.PP_CA_DER_SHA256',
                        hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest())
        binding.start()
        self.addCleanup(binding.stop)
        self.factory = ReusablePPHistoryConnectionFactory(self.dsn, self.ca)
        self.addCleanup(self.factory.close)

    def test_explicit_exact_opt_in_only(self):
        self.assertFalse(session_reuse_requested({}))
        self.assertFalse(session_reuse_requested({'TRADEBOT_PP_REUSE_HISTORY_SESSION':'false'}))
        self.assertTrue(session_reuse_requested({'TRADEBOT_PP_REUSE_HISTORY_SESSION':'true'}))
        for value in ('TRUE', '1', '', True):
            with self.assertRaises(ArchiveIntegrityError):
                session_reuse_requested({'TRADEBOT_PP_REUSE_HISTORY_SESSION':value})

    def test_separate_checkouts_share_one_idle_physical_connection(self):
        connection = Connection()
        with patch('psycopg.connect', return_value=connection) as opened:
            for _ in range(3):
                with self.factory(timeout_seconds=4) as db:
                    self.assertIs(db, connection)
                self.assertFalse(connection.closed)
            opened.assert_called_once()
        self.factory.close()
        self.assertTrue(connection.closed)
        with self.assertRaises(ArchiveUnavailable):
            with self.factory(timeout_seconds=4):
                self.fail('closed factory reused')

    def test_concurrent_checkout_and_close_do_not_queue_or_discard_owner(self):
        connection = Connection()
        with patch('psycopg.connect', return_value=connection):
            with self.factory(timeout_seconds=4):
                with self.assertRaises(ArchiveUnavailable):
                    with self.factory(timeout_seconds=4):
                        self.fail('concurrent checkout admitted')
                with self.assertRaises(ArchiveUnavailable):
                    self.factory.close()
                self.assertFalse(connection.closed)

    def test_unsafe_binding_discards_existing_session_without_reconnect(self):
        connection = Connection()
        with patch('psycopg.connect', return_value=connection) as opened:
            with self.factory(timeout_seconds=4):
                pass
            self.dsn.chmod(0o644)
            with self.assertRaises(ArchiveIntegrityError):
                with self.factory(timeout_seconds=4):
                    self.fail('unsafe binding accepted')
            self.assertTrue(connection.closed)
            opened.assert_called_once()

    def test_valid_password_rotation_reconnects_under_same_role_binding(self):
        first, second = Connection(), Connection()
        with patch('psycopg.connect', side_effect=[first, second]) as opened:
            with self.factory(timeout_seconds=4):
                pass
            self.dsn.write_text(self.secret.replace('x'*48, 'y'*48))
            with self.factory(timeout_seconds=4) as db:
                self.assertIs(db, second)
            self.assertTrue(first.closed)
            self.assertEqual(opened.call_count, 2)

    def test_unfinished_transaction_is_aborted_by_discard_never_committed(self):
        connection = Connection()
        with patch('psycopg.connect', return_value=connection):
            with self.assertRaises(ArchiveIntegrityError):
                with self.factory(timeout_seconds=4):
                    connection.info.transaction_status = TransactionStatus.INTRANS
        self.assertTrue(connection.closed)
        self.assertTrue(connection.uncommitted_discarded)

    def test_error_after_possible_commit_discards_and_next_request_reconnects(self):
        first, second = Connection(), Connection()
        with patch('psycopg.connect', side_effect=[first, second]) as opened:
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                with self.factory(timeout_seconds=4):
                    raise RuntimeError('ambiguous after commit')
            with self.factory(timeout_seconds=4) as db:
                self.assertIs(db, second)
            self.assertEqual(opened.call_count, 2)
        self.assertTrue(first.closed)

    def test_deadline_after_commit_discards_and_holds(self):
        connection = Connection()
        now = [100.0]
        with patch('psycopg.connect', return_value=connection), \
                patch('time.monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(ArchiveLimit):
                with self.factory(timeout_seconds=4):
                    now[0] = 104.1
        self.assertTrue(connection.closed)

    def test_idle_and_lifetime_bounds_force_reconnect(self):
        now = [100.0]
        connections = [Connection() for _ in range(4)]
        with patch('psycopg.connect', side_effect=connections) as opened, \
                patch('time.monotonic', side_effect=lambda: now[0]):
            with self.factory(timeout_seconds=4):
                pass
            now[0] = 131
            with self.factory(timeout_seconds=4):
                pass
            self.assertTrue(connections[0].closed)
            for moment in range(151, 432, 20):
                now[0] = moment
                with self.factory(timeout_seconds=4):
                    pass
            self.assertTrue(connections[1].closed)
            self.assertEqual(opened.call_count, 3)

    def test_broken_connection_is_discarded_before_next_transaction(self):
        first, second = Connection(), Connection()
        with patch('psycopg.connect', side_effect=[first, second]):
            with self.factory(timeout_seconds=4):
                pass
            first.broken = True
            with self.factory(timeout_seconds=4) as db:
                self.assertIs(db, second)
            self.assertTrue(first.closed)


if __name__ == '__main__':
    unittest.main()
