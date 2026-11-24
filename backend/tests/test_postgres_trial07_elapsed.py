"""Exact elapsed trial07 clock and quote checks on disposable PostgreSQL."""
from contextlib import ExitStack
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch
import uuid

import test_postgres_trial07_permit as fixture
from postgres.connection import connect
from postgres.lifecycle import LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.pp_retirement_report import active_sample
from postgres.pp_trial_prepare import prepare
from postgres.rehearsal_profile import (CYCLE_LEASE_CAP_SECONDS, ELAPSED_CYCLE_POLICY,
                                        ELAPSED_CYCLE_SECONDS, SEVENTH_TRIAL_ORIGIN)


class ElapsedTrial07(unittest.TestCase):
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']
    cleanup_origin = setup.cleanup_origin

    def setUp(self):
        self.origin = SEVENTH_TRIAL_ORIGIN
        with self.admin() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM archive.generations WHERE origin_id=%s LIMIT 1',
                                         (self.origin,)).fetchone())
        self.factory = lambda: connect(self.lifecycle_dsn)
        self.repo = LifecycleRepository(self.factory)
        self.anchor = str(uuid.uuid4())
        self.session = str(uuid.uuid4())
        self.ids = [self.anchor]
        self.addCleanup(self.cleanup_origin, self.origin, self.ids)
        mocked = {'space_hold': None}
        patcher = patch('postgres.lifecycle.pp_space.sample', return_value=mocked)
        self.space = patcher.start()
        self.addCleanup(patcher.stop)

    def admit(self):
        with ExitStack() as patches:
            for retained in ('third', 'fourth', 'fifth', 'sixth'):
                patches.enter_context(patch(f'postgres.pp_trial_prepare.retained_{retained}_fingerprint',
                                            return_value='c' * 64))
            prepared = prepare(self.repo, self.anchor, 'a' * 40, execute=True,
                               origin_id=self.origin, rehearsal_window_seconds=ELAPSED_CYCLE_SECONDS)
        self.assertEqual((prepared['profile'], prepared['window_seconds'], prepared['collector_enabled']),
                         (ELAPSED_CYCLE_POLICY, ELAPSED_CYCLE_SECONDS, False))
        enable = dict(session_id=self.session, expected_generation_id=self.anchor, rehearsal_anchor=self.anchor,
                      max_seconds=CYCLE_LEASE_CAP_SECONDS)
        with self.assertRaisesRegex(LifecycleHold, 'elapsed window mismatch'):
            self.repo.enable_collector(self.origin, **enable)
        with patch('postgres.lifecycle.require_cycle_alignment',
                   side_effect=AssertionError('elapsed cycle does not align to a UTC quarter')):
            self.assertTrue(self.repo.enable_collector(
                self.origin, **enable, rehearsal_window_seconds=ELAPSED_CYCLE_SECONDS)['collector_enabled'])
        with self.factory() as db:
            receipt = db.execute('''SELECT cursor FROM archive.checkpoints WHERE origin_id=%s
                AND generation_id=%s AND consumer='rehearsal:two-leg-session' ''',
                (self.origin, self.anchor)).fetchone()['cursor']
        self.assertEqual((receipt['profile'], receipt['window_seconds'], receipt['session_id']),
                         (ELAPSED_CYCLE_POLICY, ELAPSED_CYCLE_SECONDS, self.session))
        self.admitted = datetime.fromisoformat(receipt['admitted_at'])
        return enable

    def switch(self, at):
        with patch.object(LifecycleRepository, '_elapsed_cycle_clock', return_value=at), \
                patch.object(RotationPolicy, 'size_due', side_effect=AssertionError('no size trigger')):
            result = self.repo.switch_if_due(self.origin, rehearsal_anchor=self.anchor, market_pair_trial=True,
                        require_live_lease=True, rehearsal_window_seconds=ELAPSED_CYCLE_SECONDS)
        if result['status'] == 'switched':
            self.ids.append(result['generation_id'])
        return result

    def quote(self, generation, at):
        with connect(self.app_dsn) as db:
            db.execute('''INSERT INTO raw.events(generation_id,origin_id,source,kind,event_id,
                received_at,available_at,payload,content_hash)
                VALUES (%s,%s,'polymarket_us','quote',%s,%s,%s,'{}',%s)''',
                (generation, self.origin, str(uuid.uuid4()), at, at, 'a' * 64))

    def retire_fixture_a(self):
        # The independent permit test checks the destructive authorization.
        # Here simulate its completed outcome to exercise the second clock.
        from psycopg import sql

        with self.admin() as db:
            partition = sql.Identifier('raw', 'events_g_' + uuid.UUID(self.anchor).hex)
            db.execute(sql.SQL('DROP TABLE {}').format(partition))
            db.execute("""UPDATE archive.generations SET state='retired',verified_at=sealed_at,
                retired_at=sealed_at,seal_hash=%s WHERE generation_id=%s""", ('c' * 64, self.anchor))

    def test_actual_admission_then_actual_b_switch_drive_windows(self):
        self.admit()
        a_due = self.admitted + timedelta(seconds=ELAPSED_CYCLE_SECONDS)
        self.quote(self.anchor, self.admitted - timedelta(seconds=1))
        self.assertEqual(self.switch(a_due - timedelta(microseconds=1))['generation_id'], self.anchor)
        self.assertEqual(self.switch(a_due)['reason'], 'elapsed_window_waiting_for_polymarket')
        self.quote(self.anchor, self.admitted + timedelta(seconds=1))
        delayed_a = a_due + timedelta(seconds=5)
        first = self.switch(delayed_a)
        self.assertEqual((first['slot'], first['window_elapsed_seconds']), ('B', 1805.0))
        self.assertEqual(first['window_started_at'], self.admitted.isoformat())
        self.assertEqual(first['next_generation_started_at'], delayed_a.isoformat())
        self.assertTrue(self.repo.owns_collector(self.origin, self.session))
        self.assertGreater(first['sealed_allocated_bytes'], 0)
        self.retire_fixture_a()
        b = first['generation_id']
        self.quote(b, delayed_a + timedelta(seconds=1))
        b_due = delayed_a + timedelta(seconds=ELAPSED_CYCLE_SECONDS)
        self.assertEqual(self.switch(b_due - timedelta(seconds=5))['generation_id'], b)
        second = self.switch(b_due)
        self.assertEqual((second['slot'], second['window_elapsed_seconds']), ('A', 1800.0))
        self.assertEqual(second['window_started_at'], delayed_a.isoformat())
        fresh = second['generation_id']
        after_b = b_due + timedelta(seconds=1)
        self.assertFalse(self.switch(after_b)['terminal_polymarket_seen'])
        self.quote(fresh, after_b)
        self.assertTrue(self.switch(after_b)['terminal_polymarket_seen'])
        self.assertEqual(self.switch(after_b)['generation_id'], fresh)
        self.assertTrue(self.repo.owns_collector(self.origin, self.session))
        with self.factory() as db:
            self.assertEqual(active_sample(db, self.origin, include_polymarket=True)['polymarket_quotes'], 1)
        self.repo.disable_collector(self.origin)

    def test_occupied_a_still_fences_writer_at_second_deadline(self):
        self.admit()
        a_due = self.admitted + timedelta(seconds=ELAPSED_CYCLE_SECONDS)
        self.quote(self.anchor, self.admitted)
        first = self.switch(a_due)
        self.quote(first['generation_id'], a_due)
        held = self.switch(a_due + timedelta(seconds=ELAPSED_CYCLE_SECONDS))
        self.assertEqual((held['reason'], held['collector_enabled']), ('other_slot_not_retired', False))
        self.assertFalse(self.repo.owns_collector(self.origin, self.session))
        self.assertEqual(self.repo.generation(self.anchor)['state'], 'sealed')
