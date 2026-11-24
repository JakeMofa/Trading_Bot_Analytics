"""Keep retained-B attribution precise and free of SQL text or payloads."""
from contextlib import nullcontext
from datetime import datetime
import json
import unittest
from unittest.mock import Mock, patch

from psycopg.errors import QueryCanceled
from postgres import pp_retained_b_local_diagnostic as diagnostic


class RetainedBLocalTests(unittest.TestCase):
    def fixture(self, failure=None):
        generation = dict(slot='B', state='verified', hold_reason=None, retired_at=None,
                          seal_count=24896, seal_hash=diagnostic.SEAL_HASH,
                          sealed_at=datetime.fromisoformat(diagnostic.SEALED_AT),
                          partition_name='kept')
        rows = [dict(id=index, origin_id=diagnostic.SIXTH_TRIAL_ORIGIN,
                     generation_id=diagnostic.SEALED, entity_type='generated',
                     entity_id=str(index), content_hash='a' * 64,
                     payload={'value': 'private fixture value'}) for index in range(1, 501)]
        stages = (
            ('transaction', None), ('transaction_timeout', None),
            ('statement_timeout', None), ('lock_timeout', None),
            ('identity', dict(role='tradebot_reader', database='tradebot_pp', read_only='on')),
            ('off', None), ('writer', dict(generation_id=diagnostic.SUCCESSOR, epoch=5)),
            ('generation', generation), ('attachment', dict(present=True)),
            ('manifests', [{}] * 50), ('coverage', dict(rows=27528, pending=0)),
            ('first_id', dict(id=1)),
            ('sizes', [dict(id=index, bytes=200) for index in range(1, 501)]),
            ('payloads', rows),
        )
        db = Mock()
        db.transaction.side_effect = nullcontext
        responses = iter(stages)

        def execute(query, params=None):
            stage, reply = next(responses)
            cursor = Mock()
            if stage == failure:
                cursor.fetchone.side_effect = cursor.fetchall.side_effect = QueryCanceled('private SQL and DSN')
            else:
                cursor.fetchone.return_value = cursor.fetchall.return_value = reply
            return cursor

        db.execute.side_effect = execute
        return lambda: nullcontext(db)

    def test_reports_local_page_hashes_and_each_query_timing(self):
        with patch.object(diagnostic, 'bound_catalog', return_value=True):
            result = diagnostic.diagnostic_report(self.fixture())
        self.assertEqual((result['status'], result['rows']), ('local_page_verified', 500))
        self.assertEqual(result['hosted_requests'], 0)
        self.assertIs(result['retirement_authorized'], False)
        self.assertRegex(result['canonical_sha256'], r'^[a-f0-9]{64}$')
        for name in ('retained_manifest_query', 'retained_outbox_coverage',
                     'structured_page_size_query', 'structured_page_payload_query',
                     'retained_page_canonicalize'):
            self.assertEqual(result['phase_accounting']['phases'][name]['calls'], 1)
        self.assertNotIn('private fixture', json.dumps(result))

    def test_cancellation_identifies_statement_even_during_fetch(self):
        for failure, expected in (
            ('coverage', 'retained_outbox_coverage'),
            ('first_id', 'structured_page_size_query'),
            ('sizes', 'structured_page_size_query'),
            ('payloads', 'structured_page_payload_query'),
        ):
            with self.subTest(failure=failure), patch.object(diagnostic, 'bound_catalog', return_value=True):
                result = diagnostic.diagnostic_report(self.fixture(failure))
                self.assertEqual(result['status'], 'HOLD')
                self.assertEqual(result['phase_accounting']['failed_phase'], expected)
                self.assertEqual(result['phase_accounting']['sqlstate'], '57014')
                self.assertNotIn('private SQL', json.dumps(result))
                self.assertEqual(result['hosted_requests'], 0)
                self.assertIs(result['retirement_authorized'], False)
