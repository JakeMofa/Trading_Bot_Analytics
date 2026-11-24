"""Exercise a size-triggered cycle on owned PG17 and generated archive data."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_pp_initial_trial_drain as cluster
import test_postgres_lifecycle_integration as lifecycle_fixture
from postgres.archive_codec import ArchiveLimits
from postgres.connection import connect
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, RotationPolicy
from postgres.lifecycle_worker import configuration
from postgres.rehearsal_profile import (ELAPSED_CYCLE_POLICY, ELAPSED_CYCLE_SECONDS, GeneratedSizeCycle,
                                        SEVENTH_TRIAL_ORIGIN, SIZE_CYCLE_MAX_BYTES, SIZE_CYCLE_POLICY, cycle_anchor)
from postgres_lifecycle_fixtures import ImmutableMemoryTransport


class SizeCycleScope(unittest.TestCase):
    def test_profile_is_bounded_and_wrong_operator_or_worker_env_is_rejected(self):
        initial = str(uuid.uuid4())
        for invalid in (0, True, 1.5, SIZE_CYCLE_MAX_BYTES + 1):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                GeneratedSizeCycle(initial, invalid)
        with self.assertRaises(ValueError):
            GeneratedSizeCycle('A', 123)
        for origin in ('generated-cycle', 'pp-live-pp', 'pp-live-pp-trial-20261119-07'):
            env = {'TRADEBOT_ENVIRONMENT': 'preprod', 'TRADEBOT_ORIGIN_ID': origin,
                   'TRADEBOT_DATA_MODE': 'generated' if origin.startswith('generated-') else 'pp_live',
                   'TRADEBOT_PP_LIVE_LIFECYCLE': 'true', 'TRADEBOT_PP_WINDOW_POLICY': SIZE_CYCLE_POLICY,
                   'TRADEBOT_PP_CYCLE_INITIAL_A': initial, 'TRADEBOT_QUALIFIED_GENERATION_BYTES': '32768'}
            for check in (cycle_anchor, configuration):
                with self.subTest(origin=origin, check=check.__name__), self.assertRaises(ValueError):
                    check(env)

    def test_live_elapsed_profile_requires_exact_scope_and_no_size_override(self):
        anchor = str(uuid.uuid4())
        env = dict(TRADEBOT_ENVIRONMENT='preprod', TRADEBOT_DATA_MODE='pp_live',
                   TRADEBOT_ORIGIN_ID=SEVENTH_TRIAL_ORIGIN,
                   TRADEBOT_PP_WINDOW_POLICY=ELAPSED_CYCLE_POLICY,
                   TRADEBOT_PP_CYCLE_INITIAL_A=anchor, TRADEBOT_PP_LIVE_LIFECYCLE='true',
                   TRADEBOT_PP_ELAPSED_CYCLE_SECONDS=str(ELAPSED_CYCLE_SECONDS))
        self.assertEqual(cycle_anchor(env), anchor)
        self.assertEqual(configuration(env)['rehearsal_window_seconds'], ELAPSED_CYCLE_SECONDS)
        for change in (dict(TRADEBOT_ENVIRONMENT='production'),
                       dict(TRADEBOT_PP_ELAPSED_CYCLE_SECONDS='01800'),
                       dict(TRADEBOT_PP_SIZE_CYCLE_BYTES='33554432'),
                       dict(TRADEBOT_ORIGIN_ID='pp-live-pp-trial-20261119-06'),
                       dict(TRADEBOT_PP_WINDOW_POLICY='two-official-markets-cycle'),
                       dict(TRADEBOT_QUALIFIED_GENERATION_BYTES='1')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                configuration(env | change)

    def test_live_and_other_policy_refuse_to_open_a_database(self):
        profile = GeneratedSizeCycle(str(uuid.uuid4()), 32768)
        repo = LifecycleRepository(lambda: self.fail('opened database'))
        for origin in ('generated-', 'pp-live-pp', SEVENTH_TRIAL_ORIGIN):
            with self.subTest(origin=origin), self.assertRaises(LifecycleHold):
                repo.switch_if_due(origin, generated_size_cycle=profile)
        with self.assertRaises(LifecycleHold):
            repo.switch_if_due('generated-size', RotationPolicy(32768), generated_size_cycle=profile)
        production = LifecycleRepository(lambda: self.fail('opened database'), environment='production')
        with self.assertRaises(LifecycleHold):
            production.prepare_generated_size_cycle('generated-size', profile)


class GeneratedSizeNative(unittest.TestCase):
    admin = cluster.InitialSealNative.__dict__['admin']
    tearDownClass = cluster.InitialSealNative.__dict__['tearDownClass']
    insert = lifecycle_fixture.PostgreSQLLifecycleIntegration.insert

    @classmethod
    def setUpClass(cls):
        cluster.InitialSealNative.setUpClass.__func__(cls)

    def setUp(self):
        self.factory = lambda: connect(self.lifecycle_dsn)
        self.app_factory = lambda: connect(self.app_dsn)
        self.repo = LifecycleRepository(self.factory)
        self.origin = 'generated-size-' + uuid.uuid4().hex
        self.started = datetime.now(timezone.utc)
        self.initial = self.repo.bootstrap(self.origin, self.started)
        self.profile = GeneratedSizeCycle(self.initial['generation_id'], self.allocation(self.initial) + 1)
        space = patch('postgres.lifecycle.pp_space.sample', return_value={'space_hold': None})
        self.space = space.start()
        self.addCleanup(space.stop)

    def allocation(self, generation):
        with self.factory() as db:
            row = db.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS bytes',
                             ('raw.' + generation['partition_name'],)).fetchone()
            return row['bytes']

    def switch(self, minute=0, *, profile=None):
        return self.repo.switch_if_due(self.origin, now=self.started + timedelta(minutes=minute),
                                       generated_size_cycle=self.profile if profile is None else profile)

    def retire(self, generation):
        predecessor = self.repo.generation(generation)
        transport = ImmutableMemoryTransport()
        worker = ArchiveWorker(self.repo, transport, ArchiveLimits())
        self.assertEqual(worker.archive_cycle(generation)['status'], 'archived')
        transport.calls.clear()
        retired = worker.retire_generated(generation, qualification_enabled=True)
        self.assertEqual(retired['status'], 'retired_generated')
        self.assertIn(('structured_authenticated_get', 1), transport.calls)
        self.assertIsNone(self.allocation(predecessor))

    def write_fixture(self, index):
        event = self.insert(index)
        with self.app_factory() as db:
            db.execute('''INSERT INTO ops.outbox
                (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                VALUES (%s,%s,'fixture',%s,%s,jsonb_build_object('id',%s::integer),now())''',
                (self.origin, event['generation_id'], event['event_id'], event['content_hash'], index))

    def test_two_real_size_switches_after_verified_retirement_and_no_third_switch(self):
        self.repo.prepare_generated_size_cycle(self.origin, self.profile)
        self.repo.prepare_generated_size_cycle(self.origin, self.profile)
        initial = self.initial['generation_id']
        self.assertEqual(self.switch(4400)['generation_id'], initial)
        self.write_fixture(1)
        a = self.switch(1)
        self.assertEqual((a['reason'], a['slot'], a['seal_count']), ('qualified_size', 'B', 1))
        self.assertGreaterEqual(a['sealed_allocated_bytes'], a['threshold_bytes'])
        self.write_fixture(2)
        self.assertEqual(self.switch(2)['reason'], 'other_slot_not_retired')
        self.assertEqual(self.repo.generation(initial)['state'], 'sealed')
        self.retire(initial)
        self.repo = LifecycleRepository(self.factory)
        self.profile = GeneratedSizeCycle(initial, self.profile.threshold_bytes)
        b = self.switch(3)
        self.assertEqual((b['reason'], b['slot'], b['seal_count']), ('qualified_size', 'A', 1))
        self.assertNotEqual(b['generation_id'], initial)
        self.write_fixture(3)
        self.retire(a['generation_id'])
        self.assertEqual(self.switch(4)['reason'], 'two_leg_rehearsal_complete')
        self.assertEqual(self.switch(5)['generation_id'], b['generation_id'])

    def test_binding_changes_and_storage_hold_fail_closed(self):
        with self.assertRaisesRegex(LifecycleHold, 'binding missing'):
            self.switch()
        self.repo.prepare_generated_size_cycle(self.origin, self.profile)
        changed = replace(self.profile, threshold_bytes=self.profile.threshold_bytes + 1)
        with self.assertRaisesRegex(LifecycleHold, 'binding changed'):
            self.repo.prepare_generated_size_cycle(self.origin, changed)
        with self.assertRaisesRegex(LifecycleHold, 'binding missing or changed'):
            self.switch(profile=changed)
        self.insert(1)
        self.space.return_value = {'space_hold': 'pp_filesystem_reserve'}
        self.assertEqual(self.switch(1)['reason'], 'pp_filesystem_reserve')
        self.assertEqual(self.repo.generation(self.initial['generation_id'])['state'], 'collecting')

    def test_prepare_rejects_already_populated_initial_a(self):
        self.insert(1)
        with self.assertRaisesRegex(LifecycleHold, 'empty initial A'):
            self.repo.prepare_generated_size_cycle(self.origin, self.profile)
