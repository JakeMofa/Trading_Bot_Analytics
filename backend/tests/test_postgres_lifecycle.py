from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import gzip
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import (ArchiveIntegrityError, ArchiveLimit, ArchiveLimits,
                                    ArchiveUnavailable, CycleBudget, pack_chunk, sha256,
                                    unpack_chunk, wire)
from postgres.history import ArchiveHistory, HistoryError
from postgres.lifecycle import ArchiveWorker, LifecycleHold, RotationPolicy
from postgres.lifecycle_worker import configuration
from postgres_lifecycle_fixtures import (ImmutableMemoryTransport, MemoryRepository,
                                         generated_rows, outbox_row)


class ArchiveCodecTests(unittest.TestCase):
    def setUp(self):
        self.generation = str(uuid.uuid4())
        self.rows = generated_rows(self.generation)
        self.limits = ArchiveLimits()

    def pack(self, rows=None, limits=None):
        return pack_chunk(self.rows if rows is None else rows, origin_id='generated-lifecycle-unit',
                          generation_id=self.generation, after=None, limits=limits or self.limits)

    def test_exact_decimals_timestamps_nulls_original_wire_and_determinism(self):
        blob, manifest = self.pack()
        self.assertEqual(self.pack(), (blob, manifest))
        result = unpack_chunk(blob, manifest, self.limits)
        self.assertEqual(result, wire(self.rows))
        self.assertEqual(result[0]['price'], '12345.123456789012345678901234567890')
        self.assertEqual(result[0]['source_time'], '2026-11-12T00:00:00.123456789Z')
        self.assertIsNone(result[0]['size'])
        self.assertEqual(result[0]['raw_payload'], self.rows[0]['raw_payload'])

    def test_checksum_count_boundary_and_identity_tamper_fail(self):
        blob, manifest = self.pack()
        for key, value in [('row_count', 4), ('sha256', '0' * 64), ('byte_count', len(blob) - 1)]:
            with self.subTest(key=key), self.assertRaises(ArchiveIntegrityError):
                unpack_chunk(blob, {**manifest, key: value}, self.limits)
        for key, value in [('first', ['coinbase', 'wrong']), ('origin_id', 'other'), ('identity_sha256', '0' * 64)]:
            with self.subTest(key=key), self.assertRaises(ArchiveIntegrityError):
                unpack_chunk(blob, {**manifest, 'coverage': {**manifest['coverage'], key: value}}, self.limits)
        with self.assertRaises(ArchiveIntegrityError):
            self.pack([self.rows[0], self.rows[0]])
        with self.assertRaises(ArchiveIntegrityError):
            self.pack([{**self.rows[0], 'generation_id': str(uuid.uuid4())}])

    def test_bounded_compressed_decoded_rows_and_gzip_bomb(self):
        with self.assertRaises(ArchiveLimit):
            self.pack(limits=replace(self.limits, max_rows=2))
        small = replace(self.limits, max_object_bytes=256, max_decoded_bytes=512)
        with self.assertRaises(ArchiveLimit):
            self.pack(limits=small)
        blob, manifest = self.pack()
        bomb = gzip.compress(b'x' * (self.limits.max_decoded_bytes + 1), mtime=0)
        with self.assertRaises(ArchiveLimit):
            unpack_chunk(bomb, {**manifest, 'sha256': sha256(bomb), 'byte_count': len(bomb)}, self.limits)

    def test_cycle_limits_before_extra_request(self):
        limits = replace(self.limits, max_requests=1)
        budget = CycleBudget(limits)
        budget.request()
        with self.assertRaises(ArchiveLimit):
            budget.request()
        budget = CycleBudget(limits)
        with self.assertRaises(ArchiveLimit):
            budget.request(limits.max_cycle_bytes + 1)
        clock = [1.0]
        budget = CycleBudget(limits, clock=lambda: clock[0])
        clock[0] += limits.max_seconds
        with self.assertRaises(ArchiveLimit):
            budget.request()


class RotationConfigurationTests(unittest.TestCase):
    def test_72_hours_or_qualified_size_without_second_wait(self):
        now = datetime.now(timezone.utc)
        policy = RotationPolicy(1024)
        self.assertIsNone(policy.due(now, now + timedelta(hours=71), 1023))
        self.assertEqual(policy.due(now, now + timedelta(hours=72), 0), 'age_72h')
        self.assertEqual(policy.due(now, now + timedelta(seconds=1), 1024), 'qualified_size')
        self.assertIsNone(RotationPolicy().due(now, now, 10**12))
        with self.assertRaises(ValueError):
            RotationPolicy(0)

    def test_runtime_cannot_enable_cloud_or_retirement(self):
        self.assertEqual(configuration({})['origin_id'], 'generated-pp')
        for values in [{'TRADEBOT_RETIREMENT_ENABLED': 'true'}, {'TRADEBOT_CLOUD_ENABLED': 'true'},
                       {'TRADEBOT_DATA_MODE': 'live'}, {'TRADEBOT_ORIGIN_ID': 'production'}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                configuration(values)


class ArchiveLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository()
        self.transport = ImmutableMemoryTransport()
        self.limits = ArchiveLimits(max_rows=2)
        self.worker = ArchiveWorker(self.repository, self.transport, self.limits)
        self.generation = self.repository.generation_id

    def archive_all(self):
        for _ in range(5):
            result = self.worker.archive_cycle(self.generation)
            if result['status'] == 'archived':
                return
        self.fail('did not finish bounded pages')

    def test_restart_chunks_and_history_after_retirement(self):
        original = wire(self.repository.rows)
        self.worker.archive_cycle(self.generation)
        self.assertEqual(self.repository.record['state'], 'sealed')
        self.worker = ArchiveWorker(self.repository, self.transport, self.limits)
        self.archive_all()
        self.assertEqual(len(self.repository.catalog), 3)
        before = len(self.transport.calls)
        self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(len(self.repository.rows), 0)
        self.assertEqual(len(self.transport.calls) - before, 3)  # fresh, not cached
        history = ArchiveHistory(self.repository, self.transport, self.limits)
        result = history.read_generation(self.generation, limit=2)
        all_rows = result['rows']
        self.assertEqual(result['provenance']['tier'], 'authenticated_archive')
        while result['next_cursor']:
            result = history.read_generation(self.generation, limit=2, after_event_id=result['next_cursor'])
            all_rows.extend(result['rows'])
        self.assertEqual(all_rows, original)
        price = history.price_inputs(self.generation, limit=1)['inputs'][0]
        self.assertEqual(price['price'], Decimal('12345.123456789012345678901234567890'))
        self.assertEqual(price['source_time'], original[0]['source_time'])
        self.assertIsNone(price['size'])

    def test_upload_outage_ambiguity_and_cancellation_preserve_local(self):
        for failure, error in [('fail_put', ArchiveUnavailable), ('ambiguous_put', ArchiveUnavailable),
                               ('cancel_put', KeyboardInterrupt)]:
            with self.subTest(failure=failure):
                setattr(self.transport, failure, True)
                with self.assertRaises(error):
                    self.worker.archive_cycle(self.generation)
                self.assertEqual(len(self.repository.rows), 5)
                self.assertEqual(len(self.repository.catalog), 0)
                setattr(self.transport, failure, False)
        self.archive_all()
        self.assertEqual(len(self.transport.objects), 3)

    def test_corrupt_missing_object_or_changed_local_blocks_final_retirement(self):
        self.archive_all()
        key = self.repository.catalog[0]['object_key']
        original = self.transport.objects[key]
        self.transport.objects[key] = original[:-1] + b'x'
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        del self.transport.objects[key]
        with self.assertRaises(ArchiveUnavailable):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.transport.objects[key] = original
        self.repository.rows[0]['raw_payload'] = 'changed local raw'
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(self.repository.retire_calls, 0)
        self.assertEqual(len(self.repository.rows), 5)

    def test_reader_protected_evidence_and_runtime_gate_hold(self):
        self.archive_all()
        with self.assertRaises(LifecycleHold):
            self.worker.retire_generated(self.generation)
        for attribute in ['reader', 'protected_hold']:
            setattr(self.repository, attribute, True)
            before = len(self.transport.calls)
            with self.assertRaises(LifecycleHold):
                self.worker.retire_generated(self.generation, qualification_enabled=True)
            self.assertEqual(before, len(self.transport.calls))
            setattr(self.repository, attribute, False)
        self.transport.authority_scope = 'supabase-unqualified'
        with self.assertRaises(LifecycleHold):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(self.repository.retire_calls, 0)

    def test_structured_exact_readback_and_restart(self):
        self.repository.outbox_rows = [outbox_row(self.repository)]
        self.transport.corrupt_structured = True
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.archive_cycle(self.generation)
        self.assertIsNone(self.repository.outbox_rows[0]['acknowledged_at'])
        self.transport.corrupt_structured = False
        self.archive_all()
        self.assertIsNotNone(self.repository.outbox_rows[0]['acknowledged_at'])
        self.transport.corrupt_structured = True
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(self.repository.retire_calls, 0)
        self.transport.corrupt_structured = False
        self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(self.repository.retire_calls, 1)

    def test_final_readback_budget_does_not_authorize_partial_proof(self):
        self.archive_all()
        worker = ArchiveWorker(self.repository, self.transport, replace(self.limits, max_requests=2))
        before = len(self.transport.calls)
        with self.assertRaises(ArchiveLimit):
            worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(before, len(self.transport.calls))
        self.assertEqual(self.repository.retire_calls, 0)

    def test_local_history_never_calls_remote_and_errors_are_explicit(self):
        history = ArchiveHistory(self.repository, self.transport, self.limits)
        result = history.read_generation(self.generation, limit=2)
        self.assertEqual(result['provenance']['tier'], 'local_postgres')
        self.assertEqual(self.transport.calls, [])
        with self.assertRaises(HistoryError):
            history.read_generation(self.generation, after_event_id='wrong')
        with self.assertRaises(HistoryError):
            history.read_generation(str(uuid.uuid4()), after_event_id=result['next_cursor'])
        with self.assertRaises(HistoryError):
            history.read_generation(self.generation, dataset='future_unknown')
        self.archive_all()
        self.worker.retire_generated(self.generation, qualification_enabled=True)
        with self.assertRaisesRegex(HistoryError, 'not configured'):
            ArchiveHistory(self.repository).read_generation(self.generation)
        self.transport.fail_get = True
        with self.assertRaises(HistoryError) as caught:
            history.read_generation(self.generation)
        self.assertEqual(caught.exception.code, 'archive_unavailable')

    def test_empty_generation_is_archiveable(self):
        repository = MemoryRepository(rows=[])
        worker = ArchiveWorker(repository, self.transport)
        worker.archive_cycle(repository.generation_id)
        worker.retire_generated(repository.generation_id, qualification_enabled=True)
        result = ArchiveHistory(repository, self.transport).read_generation(repository.generation_id)
        self.assertEqual(result['rows'], [])
        self.assertTrue(result['complete'])


if __name__ == '__main__':
    unittest.main()
