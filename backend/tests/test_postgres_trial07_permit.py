"""Trial07 admits exact elapsed-window retirement permits on disposable PostgreSQL."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_pp_initial_trial_drain as pg17
import test_postgres_lifecycle_integration as lifecycle_fixture
from postgres.cloud_origin_binding import SEVENTH_TRIAL_ORIGIN
from postgres.connection import connect, connect_migrator
from postgres.lifecycle import LifecycleRepository
from postgres.rehearsal_profile import CYCLE_POLICY, ELAPSED_CYCLE_SECONDS, ELAPSED_CYCLE_POLICY


class Trial07Permit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ('LIFECYCLE', 'APP', 'MIGRATOR')
        supplied = {name: os.getenv(f'TRADEBOT_TEST_{name}_DSN') for name in names}
        cls.external = any(supplied.values())
        if not cls.external:
            pg17.InitialSealNative.setUpClass.__func__(cls)
            return
        if (not all(supplied.values()) or
                (os.getenv('TRADEBOT_DATA_MODE'), os.getenv('TRADEBOT_ORIGIN_ID'))
                != ('generated', 'generated-pp')):
            raise RuntimeError('trial07 permit test requires an owned generated database')
        cls.lifecycle_dsn = supplied['LIFECYCLE']
        cls.app_dsn = supplied['APP']
        cls.migrator_dsn = supplied['MIGRATOR']
        cls.psql = shutil.which('psql')
        if not cls.psql:
            raise RuntimeError('trial07 issuer test requires psql')

    @classmethod
    def admin(cls, database='tradebot_pp'):
        if cls.external:
            if database != 'tradebot_pp':
                raise RuntimeError('exact CI database required')
            return connect_migrator(cls.migrator_dsn)
        return pg17.InitialSealNative.admin.__func__(cls, database)

    @classmethod
    def tearDownClass(cls):
        if not cls.external:
            pg17.InitialSealNative.tearDownClass.__func__(cls)

    def test_exact_elapsed_admission_is_required_before_issuing(self):
        origin = SEVENTH_TRIAL_ORIGIN
        repository = LifecycleRepository(lambda: connect(self.lifecycle_dsn))
        with self.admin() as db:
            self.assertIsNone(db.execute(
                'SELECT 1 FROM archive.generations WHERE origin_id=%s LIMIT 1', (origin,)).fetchone())
        initial = repository.bootstrap(origin)
        first_id = initial['generation_id']
        owned_generations = [first_id]
        self.addCleanup(self.cleanup_origin, origin, owned_generations)
        self.origin = origin
        self.app_factory = lambda: connect(self.app_dsn)
        lifecycle_fixture.PostgreSQLLifecycleIntegration.insert(self, 1)
        session = str(uuid.uuid4())
        seal_hash = 'a' * 64
        now = datetime.now(timezone.utc)
        # Seed a sealed pair to test the issuer independently of the controller.
        with repository.transaction() as db:
            successor = repository._create(db, origin, 'B', now)['generation_id']
            owned_generations.append(successor)
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
            if self.external:
                from psycopg.conninfo import conninfo_to_dict

                pg_vars = {'host': 'PGHOST', 'port': 'PGPORT', 'user': 'PGUSER',
                           'password': 'PGPASSWORD', 'dbname': 'PGDATABASE'}
                connection = conninfo_to_dict(self.migrator_dsn)
                env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
                env.update({variable: connection[key] for key, variable in pg_vars.items()
                            if key in connection})
                args = [self.psql, '-X', '-qAt', '-f', str(issuer)]
            else:
                env = self.env
                args = [str(self.bin / 'psql'), '-X', '-qAt', '-h', str(self.socket),
                        '-U', 'tradebot_migrator', '-d', 'tradebot_pp', '-f', str(issuer)]
            for key, value in dict(variables, window_profile=profile).items():
                args.extend(('-v', f'{key}={value}'))
            return subprocess.run(args, env=env, capture_output=True, text=True, timeout=6)

        def bind(**override):
            cursor = dict(initial_a=first_id, session_id=session, profile=ELAPSED_CYCLE_POLICY,
                          window_seconds=ELAPSED_CYCLE_SECONDS,
                          admitted_at=(now - timedelta(seconds=ELAPSED_CYCLE_SECONDS)).isoformat())
            with repository.transaction() as db:
                repository._checkpoint(db, initial, 'rehearsal:two-leg-session', cursor | override)

        self.assertNotEqual(issue(ELAPSED_CYCLE_POLICY).returncode, 0)
        bind(window_seconds=ELAPSED_CYCLE_SECONDS + 1)
        self.assertNotEqual(issue(ELAPSED_CYCLE_POLICY).returncode, 0)
        bind(session_id=str(uuid.uuid4()))
        self.assertNotEqual(issue(ELAPSED_CYCLE_POLICY).returncode, 0)
        bind(admitted_at=(now - timedelta(seconds=ELAPSED_CYCLE_SECONDS - 1)).isoformat())
        self.assertNotEqual(issue(ELAPSED_CYCLE_POLICY).returncode, 0)
        bind()
        self.assertNotEqual(issue('two_markets').returncode, 0)
        self.assertNotEqual(issue('standard').returncode, 0)
        issued = issue(ELAPSED_CYCLE_POLICY)
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


    def cleanup_origin(self, origin, generations):
        from psycopg import sql

        with self.admin() as db:
            db.execute('DELETE FROM archive.pp_retirement_permits WHERE sealed_id=ANY(%s)', (generations,))
            db.execute('DELETE FROM ops.writer_state WHERE origin_id=%s AND generation_id=ANY(%s)',
                       (origin, generations))
            db.execute('DELETE FROM archive.checkpoints WHERE origin_id=%s AND generation_id=ANY(%s)',
                       (origin, generations))
            for generation in generations:
                partition = sql.Identifier('raw', 'events_g_' + uuid.UUID(generation).hex)
                db.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(partition))
            db.execute('DELETE FROM archive.generations WHERE origin_id=%s AND generation_id=ANY(%s)',
                       (origin, generations))


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


    def test_terminal_chain_requires_both_full_windows_and_scoped_quotes(self):
        from postgres.lifecycle import LifecycleHold
        from postgres.pp_final_trial_drain import SealTarget, completed_chain

        generations = [str(uuid.uuid4()) for _ in range(3)]
        target = SealTarget(generations[2], generations[0], 4, 1, 1, 'a' * 40,
                            str(uuid.uuid4()), 'b' * 40)
        admitted = datetime(2026, 11, 23, 20, tzinfo=timezone.utc)
        cursor = dict(initial_a=target.initial_a, profile=ELAPSED_CYCLE_POLICY,
                      window_seconds=ELAPSED_CYCLE_SECONDS)
        prepared = cursor | dict(policy='trial:initial-a-prepare-v1', source_sha=target.trial_source)
        admission = cursor | dict(lease_seconds=6600, session_id=str(uuid.uuid4()),
                                  admitted_at=admitted.isoformat(),
                                  lease_expires_at=(admitted + timedelta(seconds=6600)).isoformat())

        def database(*, second_seconds=1800, handoff_quotes=1, terminal_quote=True):
            first_seal = admitted + timedelta(seconds=1800)
            second_seal = first_seal + timedelta(seconds=second_seconds)
            times = [admitted, first_seal, second_seal]
            rows = []
            results = [Mock(fetchall=Mock(return_value=rows)),
                       Mock(fetchone=Mock(return_value={'cursor': prepared})),
                       Mock(fetchone=Mock(return_value={'cursor': admission}))]
            for index, generation in enumerate(generations[:2]):
                seal = times[index + 1]
                row = dict(generation_id=generation, slot='AB'[index], state='retired',
                           sealed_at=seal, started_at=times[index],
                           verified_at=seal + timedelta(seconds=40),
                           retired_at=seal + timedelta(seconds=80),
                           seal_hash='c' * 64, seal_count=1,
                           partition_name='events_g_' + uuid.UUID(generation).hex)
                rows.append(row)
                proof = dict(enabled=True, policy='pp-exact-retirement-v1',
                             source=target.trial_source, seal_hash=row['seal_hash'], count=1,
                             active=generations[index + 1], txid=index + 1, active_new_rows=1,
                             active_new_polymarket_quotes=handoff_quotes,
                             policy_epoch='d' * 64, history_reader_proof='e' * 64)
                results.extend([Mock(fetchone=Mock(return_value={'cursor': proof})),
                                Mock(fetchone=Mock(return_value={'child': None}))])
            rows.append(dict(generation_id=generations[2], slot='A', started_at=second_seal))
            results.append(Mock(fetchone=Mock(return_value={'exists': True} if terminal_quote else None)))
            return Mock(execute=Mock(side_effect=results))

        for change, expected in (({'second_seconds': 1799}, 'admission'),
                                 ({'handoff_quotes': 0}, 'successor Polymarket'),
                                 ({'terminal_quote': False}, 'terminal A')):
            with self.subTest(change=change), self.assertRaisesRegex(LifecycleHold, expected):
                completed_chain(database(**change), target, origin_id=SEVENTH_TRIAL_ORIGIN)
        rows = completed_chain(database(), target, origin_id=SEVENTH_TRIAL_ORIGIN)
        self.assertEqual([row['generation_id'] for row in rows], generations)
