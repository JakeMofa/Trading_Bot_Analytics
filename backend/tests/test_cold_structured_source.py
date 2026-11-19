"""Cold reader source tests; optional native DSNs must be disposable local PG17."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from postgres.cold_structured_source import ReadOnlyStructuredSource, READER_ROLE, configured_cold_history
from postgres.cold_structured_history import ColdStructuredHistory, ORIGIN, MAX_BYTES
from test_cold_structured_history import envelope, GENERATION


def fixture():
    record = envelope(1)
    receipt = dict(outbox_id=1, total=len(encoded(record)), envelope=encoded(record),
                   entity_type=record['entity_type'], entity_id=record['entity_id'],
                   content_hash=record['content_hash'],
                   payload_hash=sha256(encoded(record['payload'])),
                   envelope_hash=sha256(encoded(record)))
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.transaction.return_value = nullcontext()
    guard = dict.fromkeys(('direct_login', 'read_only', 'restricted_role', 'schema_read',
                          'no_schema_write', 'can_read', 'no_table_write'), True)

    def execute(statement, values=None):
        assert connection.read_only is True
        assert connection.prepare_threshold is None
        if 'current_database()' in statement:
            return Mock(fetchone=lambda: dict(database='postgres', role=READER_ROLE))
        if 'current_user=session_user' in statement:
            return Mock(fetchone=lambda: guard)
        if 'WITH sizes' in statement:
            return Mock(fetchall=lambda: [receipt])
        return Mock()

    connection.execute.side_effect = execute
    factory = Mock(return_value=connection)
    source = ReadOnlyStructuredSource(factory, origin_id=ORIGIN, generation_id=GENERATION)
    return source, connection, factory, receipt, guard, record


class ColdSourceTests(unittest.TestCase):
    def test_verified_source_to_manifest_page_preserves_exact_original(self):
        source, connection, factory, receipt, guard, record = fixture()
        reader = ColdStructuredHistory(source, origin_id=ORIGIN, generation_id=GENERATION)
        result = reader.read_page([dict(id=1, envelope_sha256=sha256(encoded(record)))],
                                  entity_type='core.predictions', market_id='market')
        self.assertEqual(result['rows'], [record])
        self.assertTrue(result['provenance']['historical_only'])
        self.assertFalse(result['provenance']['retirement_authority'])
        statements = [call.args[0].strip() for call in connection.execute.call_args_list]
        self.assertEqual(len(statements), 4)
        self.assertTrue(all(s.startswith(('SELECT', 'WITH')) for s in statements))
        factory.assert_called_once_with(timeout_seconds=4)

    def test_effective_write_or_privileged_or_wrong_identity_denied_before_payload(self):
        for field in ('direct_login', 'read_only', 'restricted_role', 'schema_read',
                      'no_schema_write', 'can_read', 'no_table_write'):
            source, connection, factory, receipt, guard, record = fixture()
            guard[field] = False
            with self.subTest(field=field), self.assertRaises(ArchiveIntegrityError):
                source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)
            self.assertFalse(any('WITH sizes' in c.args[0] for c in connection.execute.call_args_list))
        source, connection, factory, receipt, guard, record = fixture()
        original = connection.execute.side_effect
        connection.execute.side_effect = lambda s, v=None: (
            Mock(fetchone=lambda: dict(database='postgres', role='tradebot_pp_history'))
            if 'current_database()' in s else original(s, v))
        with self.assertRaises(ArchiveIntegrityError):
            source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)

    def test_receipt_and_canonical_byte_corruption_fail_closed(self):
        for mutate in (lambda r: r.update(payload_hash='b'*64),
                       lambda r: r.update(envelope=r['envelope']+b' '),
                       lambda r: r.update(envelope=None),
                       lambda r: r.update(outbox_id=2)):
            source, connection, factory, receipt, guard, record = fixture()
            mutate(receipt)
            with self.assertRaises((ArchiveIntegrityError, ArchiveLimit)):
                source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)

    def test_invalid_bounds_never_connect_and_network_details_are_redacted(self):
        source, connection, factory, receipt, guard, record = fixture()
        for ids, size, seconds in (([1]*2, 1, 4), (list(range(1, 52)), 1, 4),
                                  ([True], 1, 4), ([1], MAX_BYTES+1, 4),
                                  ([1], 1, float('nan')), ([1], 1, True), ([1], 1, 5)):
            with self.assertRaises(ArchiveLimit):
                source.read_revisions(ids, max_bytes=size, timeout_seconds=seconds)
        factory.assert_not_called()
        factory.side_effect = OSError('secret-password')
        with self.assertRaisesRegex(ArchiveUnavailable, '^cold structured source unavailable$'):
            source.read_revisions([1], max_bytes=1, timeout_seconds=4)

    def test_connection_time_consumes_page_deadline(self):
        source, connection, factory, receipt, guard, record = fixture()
        ticks = iter([0, 4])
        source.clock = lambda: next(ticks)
        with self.assertRaises(ArchiveLimit):
            source.read_revisions([1], max_bytes=MAX_BYTES, timeout_seconds=4)
        connection.execute.assert_not_called()

    def test_default_off_and_exact_pp_configuration_without_eager_network(self):
        settings = SimpleNamespace(environment='preprod', data_mode='pp_live', origin_id=ORIGIN)
        factory = Mock()
        self.assertIsNone(configured_cold_history(settings, {}, generation_id='bad', connection_factory=factory))
        for flag in ('TRUE', '', '1'):
            with self.assertRaises(ValueError):
                configured_cold_history(settings, {'TRADEBOT_PP_COLD_STRUCTURED_HISTORY': flag},
                                        generation_id=GENERATION, connection_factory=factory)
        settings.environment = 'production'
        with self.assertRaises(ValueError):
            configured_cold_history(settings, {'TRADEBOT_PP_COLD_STRUCTURED_HISTORY': 'true'},
                                    generation_id=GENERATION, connection_factory=factory)
        settings.environment = 'preprod'
        self.assertIsInstance(configured_cold_history(settings,
            {'TRADEBOT_PP_COLD_STRUCTURED_HISTORY': 'true'}, generation_id=GENERATION,
            connection_factory=factory), ColdStructuredHistory)
        factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
