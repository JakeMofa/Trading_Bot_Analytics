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
