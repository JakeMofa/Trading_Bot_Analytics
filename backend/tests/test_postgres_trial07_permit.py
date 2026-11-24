"""Trial07 admits exact size-bound retirement permits on disposable PostgreSQL."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_pp_initial_trial_drain as pg17
import test_postgres_lifecycle_integration as lifecycle_fixture
from postgres.cloud_origin_binding import SEVENTH_TRIAL_ORIGIN
from postgres.connection import connect
from postgres.lifecycle import LifecycleRepository
from postgres.rehearsal_profile import CYCLE_POLICY, SIZE_CYCLE_MAX_BYTES, SIZE_CYCLE_POLICY


class Trial07Permit(unittest.TestCase):
    admin = pg17.InitialSealNative.__dict__['admin']
    tearDownClass = pg17.InitialSealNative.__dict__['tearDownClass']

    @classmethod
    def setUpClass(cls):
        pg17.InitialSealNative.setUpClass.__func__(cls)

    def test_exact_size_admission_is_required_before_issuing(self):
        origin = SEVENTH_TRIAL_ORIGIN
        repository = LifecycleRepository(lambda: connect(self.lifecycle_dsn))
        initial = repository.bootstrap(origin)
        first_id = initial['generation_id']
        self.origin = origin
        self.app_factory = lambda: connect(self.app_dsn)
        lifecycle_fixture.PostgreSQLLifecycleIntegration.insert(self, 1)
        session = str(uuid.uuid4())
        seal_hash = 'a' * 64
        now = datetime.now(timezone.utc)
        # Seed a sealed pair to test the issuer independently of the controller.
        with repository.transaction() as db:
            successor = repository._create(db, origin, 'B', now)['generation_id']
            db.execute("""UPDATE archive.generations SET state='verified',
                sealed_at=%s,verified_at=%s,seal_hash=%s,seal_count=1
                WHERE generation_id=%s""", (now, now, seal_hash, first_id))
            db.execute("""UPDATE archive.generations SET state='collecting',started_at=%s
                WHERE generation_id=%s""", (now, successor))
            db.execute("""UPDATE ops.writer_state SET generation_id=%s,
                collector_enabled=true,collector_session_id=%s,
                collector_lease_expires_at=now()+interval '10 minutes'
                WHERE origin_id=%s""", (successor, session, origin))
        end = now + timedelta(seconds=60)
        variables = dict(
            sealed=first_id, collecting=successor, row_count=1, seal_hash=seal_hash,
            release_sha='a' * 40, policy_epoch_hash='b' * 64, history_reader_proof='c' * 64,
            freeze_started_at=(now - timedelta(seconds=5)).isoformat(), freeze_ends_at=end.isoformat(),
        )
        issuer = Path(__file__).resolve().parents[2] / 'deploy/preprod/issue_pp_retirement.sql'

        def issue(profile):
            args = [str(self.bin / 'psql'), '-X', '-qAt', '-h', str(self.socket),
                    '-U', 'tradebot_migrator', '-d', 'tradebot_pp', '-f', str(issuer)]
            for key, value in dict(variables, window_profile=profile).items():
                args.extend(('-v', f'{key}={value}'))
            return subprocess.run(args, env=self.env, capture_output=True, text=True, timeout=6)

        def bind(**override):
            cursor = dict(initial_a=first_id, session_id=session, profile=SIZE_CYCLE_POLICY,
                          threshold_bytes=SIZE_CYCLE_MAX_BYTES)
            with repository.transaction() as db:
                repository._checkpoint(db, initial, 'rehearsal:two-leg-session', cursor | override)

        self.assertNotEqual(issue(SIZE_CYCLE_POLICY).returncode, 0)
        bind(threshold_bytes=SIZE_CYCLE_MAX_BYTES + 1)
        self.assertNotEqual(issue(SIZE_CYCLE_POLICY).returncode, 0)
        bind(session_id=str(uuid.uuid4()))
        self.assertNotEqual(issue(SIZE_CYCLE_POLICY).returncode, 0)
        bind()
        self.assertNotEqual(issue('two_markets').returncode, 0)
        self.assertNotEqual(issue('standard').returncode, 0)
        issued = issue(SIZE_CYCLE_POLICY)
        self.assertEqual(issued.returncode, 0, 'trial07 permit issuance rejected')
        ticket = str(uuid.UUID(issued.stdout.strip()))
        from psycopg.errors import NoDataFound
        with self.assertRaises(NoDataFound), repository.transaction() as db:
            # An issuer ticket alone cannot remove a partition without same-xact proof.
            db.execute('SELECT archive.retire_pp_generation(%s,%s,%s,%s,%s,%s)',
                       (ticket, first_id, successor, 'a' * 40, 'b' * 64, 'c' * 64))
        with self.admin() as db:
            permit = db.execute('''SELECT sealed_id,collecting_id,expires_at,used_at
                FROM archive.pp_retirement_permits WHERE ticket=%s''', (ticket,)).fetchone()
            self.assertEqual((permit['sealed_id'], permit['collecting_id']), (first_id, successor))
            self.assertEqual(permit['expires_at'], end)
            self.assertIsNone(permit['used_at'])
            self.assertIsNotNone(db.execute('SELECT to_regclass(%s) AS child',
                ('raw.' + initial['partition_name'],)).fetchone()['child'])


class Trial07TerminalControl(unittest.TestCase):
    def test_terminal_drain_refuses_wrong_profile_before_reading_secret(self):
        from postgres.pp_final_trial_drain import main

        initial, final, operation = (str(uuid.uuid4()) for _ in range(3))
        args = ['--execute', '--origin', SEVENTH_TRIAL_ORIGIN, '--initial-a', initial,
                '--generation', final, '--writer-epoch', '4', '--raw-count', '2',
                '--outbox-count', '1', '--trial-source', 'a' * 40, '--source', 'b' * 40,
                '--operation', operation]
        environment = dict(TRADEBOT_PP_FINAL_TRIAL_DRAIN='true', TRADEBOT_ENVIRONMENT='preprod',
                           TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID=SEVENTH_TRIAL_ORIGIN,
                           TRADEBOT_PP_WINDOW_POLICY=CYCLE_POLICY, TRADEBOT_PP_CYCLE_INITIAL_A=initial,
                           TRADEBOT_DATABASE_DSN_FILE='/run/secrets/lifecycle_dsn')
        with patch.dict(os.environ, environment, clear=True), \
             patch('postgres.pp_final_trial_drain.private_dsn') as credential:
            self.assertEqual(main(args), 1)
            credential.assert_not_called()
