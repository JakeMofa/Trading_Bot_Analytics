"""Independent native-cursor limits, EOF, deadline and role checks; no host/DB."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Budget, DeploymentHold
import linux_actions
import metadata_inventory as inventory


class Exchange:
    def __init__(self, hashes, *, manifest=None, after_fetch=None):
        self.hashes = hashes
        self.expected = len(hashes) if manifest is None else manifest
        self.position = 0
        self.after_fetch = after_fetch
        self.commands = []
        self.max_reply = 0

    def __call__(self, query):
        self.commands.append(query)
        if query.startswith('SELECT to_json(count(*)'):
            return [self.expected]
        if query.startswith('FETCH '):
            rows = self.hashes[self.position:self.position + inventory.FETCH_ROWS]
            self.position += len(rows)
            self.max_reply = max(self.max_reply, sum(len(json.dumps(row)) + 1 for row in rows))
            if self.after_fetch:
                self.after_fetch()
            return rows
        if query.startswith(('BEGIN ', 'DECLARE ', 'CLOSE ')):
            return []
        raise AssertionError('unexpected SQL/fallback')


class MetadataInventoryResources(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())

    def digest(self, exchange, budget=None):
        return inventory.metadata_digest(exchange, 'core.markets',
            'origin_id,market_id,content_hash', budget or Budget(180), self.directory)

    def test_fetch_and_wire_bounds_without_host_scratch_or_adjacent_queries(self):
        exchange = Exchange(['a' * 64] * 1025)
        with patch('tempfile.TemporaryFile', side_effect=AssertionError('scratch forbidden')):
            result = self.digest(exchange)
        self.assertEqual(result['count'], 1025)
        self.assertLess(exchange.max_reply, 65536)
        self.assertTrue(all(len(q.encode()) < 4096 for q in exchange.commands))
        self.assertEqual(sum(q.startswith('DECLARE ') for q in exchange.commands), 1)
        self.assertEqual(sum(q.startswith('FETCH ') for q in exchange.commands), 4)
        self.assertFalse(any('WITH ORDINALITY' in q or 'GROUP BY' in q or 'row_number' in q
                             for q in exchange.commands))
        self.assertEqual(list(Path(self.directory).iterdir()), [])

    def test_retains_native_text_sort_and_projection_boundary(self):
        exchange = Exchange([])
        self.digest(exchange)
        declaration = next(q for q in exchange.commands if q.startswith('DECLARE '))
        self.assertIn('NO SCROLL CURSOR', declaration)
        self.assertIn('ORDER BY fingerprint OFFSET 0', declaration)
        self.assertIn('SELECT to_json(fingerprint) FROM (', declaration)
        self.assertNotIn('COLLATE', declaration)
        self.assertNotIn('::bytea', declaration)

    def test_unchanged_qualification_cardinality_limit_precedes_cursor(self):
        self.assertEqual(inventory.MAX_ROWS, 64 * 1024**2 // 32)
        self.assertEqual(inventory.FETCH_ROWS, 512)
        exchange = Exchange([], manifest=inventory.MAX_ROWS + 1)
        with self.assertRaisesRegex(DeploymentHold, 'metadata_inventory_limit'):
            self.digest(exchange)
        self.assertFalse(any(q.startswith('DECLARE ') for q in exchange.commands))

    def test_bad_manifest_types_and_counts_are_rejected(self):
        for value in (-1, True, '1', 1.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DeploymentHold, 'metadata_snapshot_invalid'):
                    self.digest(Exchange([], manifest=value))

    def test_extra_row_beyond_snapshot_count_is_rejected(self):
        with self.assertRaisesRegex(DeploymentHold, 'metadata_snapshot_invalid'):
            self.digest(Exchange(['a' * 64] * 2, manifest=1))

    def test_premature_eof_is_rejected(self):
        with self.assertRaisesRegex(DeploymentHold, 'metadata_snapshot_invalid'):
            self.digest(Exchange(['a' * 64], manifest=2))

    def test_oversized_fetch_response_is_rejected(self):
        exchange = Exchange(['a' * 64])
        def oversized(query):
            if query.startswith('FETCH '):
                return ['a' * 64] * 513
            return exchange(query)
        with self.assertRaisesRegex(DeploymentHold, 'metadata_snapshot_invalid'):
            self.digest(oversized)

    def test_wire_hash_shape_is_strict(self):
        for value in ('a' * 63, 'A' * 64, 'z' * 64, 123):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DeploymentHold, 'metadata_invalid_hash'):
                    self.digest(Exchange([value]))

    def test_deadline_after_fetch_never_commits_or_continues(self):
        class Deadline:
            expired = False
            def timeout(self):
                return 0 if self.expired else 180
        budget = Deadline()
        def expire():
            budget.expired = True
        exchange = Exchange(['a' * 64] * inventory.FETCH_ROWS, after_fetch=expire)
        with self.assertRaisesRegex(DeploymentHold, 'deadline_exceeded'):
            self.digest(exchange, budget)
        self.assertFalse(any(q.startswith('CLOSE ') for q in exchange.commands))

    def test_server_sort_refusal_has_no_other_algorithm_or_deadline_fallback(self):
        exchange = Exchange(['a' * 64])
        def refused(query):
            if query.startswith('FETCH '):
                raise DeploymentHold('outbox_psql_failed')
            return exchange(query)
        with self.assertRaisesRegex(DeploymentHold, 'outbox_psql_failed'):
            self.digest(refused)
        self.assertEqual(sum(q.startswith('DECLARE ') for q in exchange.commands), 1)
        self.assertFalse(any(q.startswith('CLOSE ') for q in exchange.commands))

    def test_empty_evidence_and_snapshot_statement_limits(self):
        exchange = Exchange([])
        self.assertEqual(self.digest(exchange), {'count':0, 'digest':hashlib.sha256(b'').hexdigest()})
        self.assertIn('REPEATABLE READ READ ONLY', exchange.commands[0])
        self.assertIn("statement_timeout='19s'", exchange.commands[0])
        self.assertFalse(any('work_mem=' in q or 'temp_file_limit=' in q for q in exchange.commands))
        self.assertEqual(exchange.commands[-1], 'CLOSE metadata_hashes; COMMIT;')

    def test_archive_metadata_uses_reader_even_outside_watch_mode(self):
        actions = linux_actions.LinuxActions()
        actions.pg_id = 'generated-fixture-postgres'
        actions.watch_diagnostics = False
        captured = []
        @contextmanager
        def channel(args, _budget, _env, _cleanup):
            captured.append(args)
            yield lambda _: []
        with patch.object(linux_actions, 'psql_channel', channel):
            with actions._outbox_channel(Budget(180), require_reader=True):
                pass
            with actions._outbox_channel(Budget(180)):
                pass
        self.assertEqual(captured[0][captured[0].index('-U') + 1], 'tradebot_reader')
        self.assertEqual(captured[1][captured[1].index('-U') + 1], 'tradebot_app')
