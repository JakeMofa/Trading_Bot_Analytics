"""Finite diagnostic scope never enables the expired destructive path."""
import unittest
from unittest.mock import patch
import uuid

from postgres.lifecycle import LifecycleHold
from postgres.pp_retained_archive_audit import AuditTarget, check_environment, LOCAL_DSN


class RetainedAuditTests(unittest.TestCase):
    def test_exact_off_identity_and_no_ticket_required(self):
        env=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
            TRADEBOT_ORIGIN_ID='pp-live-pp',TRADEBOT_PP_RETAINED_ARCHIVE_AUDIT='true',
            TRADEBOT_DATABASE_DSN_FILE=LOCAL_DSN)
        with patch('postgres.pp_retained_archive_audit.os.path.exists',return_value=False):
            check_environment(env)
            for changed in ({'TRADEBOT_PP_EXACT_RETIREMENT':'true'},
                    {'TRADEBOT_COLLECTOR_ENABLED':'true'},
                    {'TRADEBOT_DATABASE_DSN_FILE':'/run/secrets/lifecycle_dsn'},
                    {'TRADEBOT_PP_RETAINED_ARCHIVE_AUDIT':'TRUE'}):
                with self.assertRaises(LifecycleHold): check_environment({**env,**changed})
        with patch('postgres.pp_retained_archive_audit.os.path.exists',return_value=True):
            with self.assertRaises(LifecycleHold): check_environment(env)

    def test_scope_requires_positive_exact_counts_and_finite_request_fit(self):
        base=dict(sealed=str(uuid.uuid4()),collecting=str(uuid.uuid4()),seal_hash='a'*64,
            count=28411,structured_rows=31162,raw_objects=57,structured_pages=63,original_deadline_utc='2026-11-19T09:00:04.617214+00:00')
        AuditTarget(**base).validate()
        for changed in ({'raw_objects':129},{'structured_rows':0},{'structured_pages':True}):
            with self.assertRaises(LifecycleHold): AuditTarget(**{**base,**changed}).validate()

    def test_historical_off_scope_requires_exact_same_writer_and_seal(self):
        generation = str(uuid.uuid4())
        arguments = dict(sealed=generation, collecting=generation, seal_hash='a'*64,
            count=9784, structured_rows=10971, raw_objects=20, structured_pages=22,
            historical_off=True, original_deadline_utc='2026-11-19T21:00:00+00:00')
        AuditTarget(**arguments).validate()
        for change in ({'collecting': str(uuid.uuid4())}, {'historical_off': False},
                       {'count': False}, {'seal_hash': 'unbound'}):
            with self.subTest(change=change), self.assertRaises((ValueError, LifecycleHold)):
                AuditTarget(**(arguments | change)).validate()

    def test_trial_03_requires_stopped_mode_and_never_accepts_ticket(self):
        from postgres.pp_retained_archive_audit import STOPPED_TRIAL
        env = dict(TRADEBOT_ENVIRONMENT='preprod', TRADEBOT_DATA_MODE='pp_live',
                   TRADEBOT_ORIGIN_ID=STOPPED_TRIAL, TRADEBOT_PP_RETAINED_ARCHIVE_AUDIT='true',
                   TRADEBOT_DATABASE_DSN_FILE=LOCAL_DSN)
        with patch('postgres.pp_retained_archive_audit.os.path.lexists', return_value=False):
            check_environment(env, origin=STOPPED_TRIAL)
            for key in ('TRADEBOT_COLLECTOR_ENABLED', 'TRADEBOT_RETIREMENT_ENABLED'):
                with self.assertRaises(LifecycleHold):
                    check_environment({**env, key: 'true'}, origin=STOPPED_TRIAL)
        with patch('postgres.pp_retained_archive_audit.os.path.lexists', return_value=True):
            with self.assertRaises(LifecycleHold):
                check_environment(env, origin=STOPPED_TRIAL)

    def test_stopped_trial_rejects_running_writer_before_cloud_readback(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock
        from postgres.cloud_origin_binding import cloud_binding
        from postgres.pp_retained_archive_audit import STOPPED_TRIAL, audit

        target = AuditTarget(str(uuid.uuid4()), str(uuid.uuid4()), 'a'*64, 1, 1, 1, 1,
                             '2026-11-20T18:45:07+00:00')
        transport = SimpleNamespace(origin_id=STOPPED_TRIAL, generation_id=target.sealed,
            structured=SimpleNamespace(expected_role=cloud_binding(STOPPED_TRIAL).reader_role),
            raw=SimpleNamespace(_reader=True, _origin_binding=SimpleNamespace(origin_id=STOPPED_TRIAL)))
        db = Mock()
        db.execute.return_value.fetchone.side_effect = (
            dict(slot='A', seal_count=1, seal_hash=target.seal_hash, sealed_at='seal'),
            dict(generation_id=target.collecting, collector_enabled=True),
            dict(running=True),
            dict(slot='B', state='verified', retired_at=None, started_at='seal'),
        )
        module = 'postgres.pp_retained_archive_audit'
        with patch(module+'.local_snapshot', return_value=nullcontext(db)), \
                patch(module+'.LifecycleRepository._manifests', return_value=[{}]), \
                patch(module+'.bound_catalog', return_value=True), \
                patch(module+'.remote_preflight') as preflight:
            with self.assertRaisesRegex(LifecycleHold, 'all writers OFF'):
                audit(None, transport, target, origin=STOPPED_TRIAL)
            preflight.assert_not_called()

    def test_stopped_trial_b_requires_its_verified_a_before_cloud_readback(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock
        from postgres.cloud_origin_binding import cloud_binding
        from postgres.pp_retained_archive_audit import STOPPED_TRIAL, audit

        generation = str(uuid.uuid4())
        target = AuditTarget(generation, generation, 'a'*64, 1, 1, 1, 1,
                             '2026-11-20T19:30:04+00:00', historical_off=True)
        transport = SimpleNamespace(origin_id=STOPPED_TRIAL, generation_id=generation,
            structured=SimpleNamespace(expected_role=cloud_binding(STOPPED_TRIAL).reader_role),
            raw=SimpleNamespace(_reader=True, _origin_binding=SimpleNamespace(origin_id=STOPPED_TRIAL)))
        db = Mock()
        db.execute.return_value.fetchone.side_effect = (
            dict(slot='B', seal_count=1, seal_hash=target.seal_hash, started_at='seal'),
            dict(generation_id=generation, collector_enabled=False,
                 collector_session_id=None, collector_lease_expires_at=None),
            dict(running=False),
        )
        db.execute.return_value.fetchall.return_value = []
        module = 'postgres.pp_retained_archive_audit'
        with patch(module+'.local_snapshot', return_value=nullcontext(db)), \
                patch(module+'.LifecycleRepository._manifests', return_value=[{}]), \
                patch(module+'.bound_catalog', return_value=True), \
                patch(module+'.remote_preflight') as preflight:
            with self.assertRaisesRegex(LifecycleHold, 'verified A predecessor'):
                audit(None, transport, target, origin=STOPPED_TRIAL)
            preflight.assert_not_called()

    def test_trial06_b_requires_both_attachments_and_acknowledgement_before_cloud(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock

        from postgres.cloud_origin_binding import SIXTH_TRIAL_ORIGIN, cloud_binding
        from postgres.pp_retained_archive_audit import audit

        target = AuditTarget(str(uuid.uuid4()), str(uuid.uuid4()), 'a' * 64, 24896, 27528,
                             50, 56, '2026-11-23T23:30:29.987862+00:00')
        origin = SIXTH_TRIAL_ORIGIN
        transport = SimpleNamespace(origin_id=origin,generation_id=target.sealed,
            structured=SimpleNamespace(expected_role=cloud_binding(origin).reader_role),
            raw=SimpleNamespace(_reader=True,_origin_binding=SimpleNamespace(origin_id=origin)))
        module = 'postgres.pp_retained_archive_audit'
        for attached, pending, reason in ((False,False,'attachments changed'),
                                          (True,True,'not fully acknowledged')):
            db = Mock()
            db.execute.return_value.fetchone.side_effect = [
                dict(slot='B', seal_count=target.count, seal_hash=target.seal_hash),
                dict(generation_id=target.collecting, collector_enabled=False),
                dict(running=False), dict(pending=pending),
            ]
            db.execute.return_value.fetchall.return_value = [
                dict(slot='A', state='retired', present=False, attached=False,
                     retired_at='later', sealed_at='seal-a'),
                dict(slot='B', state='verified', present=True, attached=attached,
                     retired_at=None, generation_id=target.sealed, started_at='seal-a', sealed_at='seal-b'),
                dict(slot='A', state='collecting', present=True, attached=True,
                     generation_id=target.collecting, started_at='seal-b'),
            ]
            with self.subTest(attached=attached,pending=pending), \
                    patch(module+'.local_snapshot',return_value=nullcontext(db)), \
                    patch(module+'.LifecycleRepository._manifests',return_value=[{}] * 50), \
                    patch(module+'.bound_catalog',return_value=True), \
                    patch(module+'.remote_preflight') as preflight:
                with self.assertRaisesRegex(LifecycleHold, reason):
                    audit(None,transport,target,origin=origin)
                preflight.assert_not_called()
