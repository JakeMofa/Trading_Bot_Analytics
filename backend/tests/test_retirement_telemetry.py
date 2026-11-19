"""Offline summaries distinguish completed coverage from failed-span attempts."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from postgres.retirement_telemetry import compare, load_evidence, main, summarize


def completed(elapsed=200):
    return {'status': 'retained_archive_audit_verified', 'sealed': 'reviewed-generation',
        'manifest_digest': 'a' * 64, 'objects_read': 2, 'structured_count': 500,
        'inventory': {'raw_objects': 2, 'structured_rows': 500, 'structured_pages_examined': 1},
        'retirement_authorized': False, 'original_trial_satisfied': False,
        'operation_deadline_met': True,
        'phase_accounting': {'elapsed_seconds': elapsed, 'remaining_seconds': 240-elapsed,
            'diagnostics_unavailable': False, 'requests': 4, 'logical_bytes': 12345,
            'nested_phase_totals_overlap': True, 'failed_phase': None, 'exhausted_limit': None,
            'phases': {'raw_read_decode': {'calls': 2, 'seconds': 4, 'max_seconds': 2},
                'structured_readback': {'calls': 1, 'seconds': 6, 'max_seconds': 6},
                'history_transaction': {'calls': 1, 'seconds': 5, 'max_seconds': 5},
                'history_exact_revisions': {'calls': 1, 'seconds': 3, 'max_seconds': 3},
                'history_connect': {'calls': 1, 'seconds': 1, 'max_seconds': 1}}}}


class TelemetryTests(unittest.TestCase):
    def test_actual_pp19_hold_keeps_partial_counts_and_remaining_time_honest(self):
        evidence_path = Path(__file__).resolve().parents[2] / 'docs/PLAN/evidence/pp19-retained-a-readback-2026-11-19.json'
        result = summarize(load_evidence(evidence_path))
        self.assertEqual(result['outcome'], 'held')
        self.assertFalse(result['readback_completed'])
        self.assertEqual(result['elapsed_seconds'], 67.51035)
        self.assertEqual(result['reported_remaining_seconds'], 172.489744)
        self.assertEqual(result['requests'], 60)
        self.assertEqual(result['logical_bytes'], 4428956)
        self.assertEqual(result['counts']['raw_read_decode_attempts'], 57)
        self.assertEqual(result['counts']['structured_readback_attempts'], 1)
        self.assertIsNone(result['counts']['reported_structured_rows'])
        self.assertIsNone(result['counts']['reported_objects_read'])
        self.assertEqual(result['failed_phase'], 'history_projections')
        self.assertEqual(result['workload_bottlenecks'][0]['phase'], 'raw_read_decode')
        self.assertEqual(result['history_bottlenecks'][0]['phase'], 'history_latest_receipts')
        self.assertFalse(result['retirement_authorized'])

    def test_nested_spans_rank_separately_and_never_replace_elapsed_with_sum(self):
        result = summarize(completed(10))
        self.assertEqual(result['elapsed_seconds'], 10)
        self.assertEqual([r['phase'] for r in result['workload_bottlenecks']],
                         ['structured_readback', 'raw_read_decode'])
        self.assertEqual([r['phase'] for r in result['history_bottlenecks']],
                         ['history_exact_revisions', 'history_connect'])
        self.assertTrue(result['phase_totals_must_not_be_summed'])
        self.assertNotIn('total_phase_seconds', result)
        self.assertEqual(result['byte_semantics'], 'logical_budget_charges_not_wire_bytes')
        self.assertEqual(result['phases']['raw_read_decode']['attempt_mean_seconds'], 2)

    def test_zero_and_missing_attempt_counts_have_no_invented_average(self):
        evidence = completed()
        evidence['phase_accounting']['phases']['history_connect']['calls'] = 0
        del evidence['phase_accounting']['phases']['raw_read_decode']['calls']
        result = summarize(evidence)
        self.assertIsNone(result['phases']['history_connect']['attempt_mean_seconds'])
        self.assertIsNone(result['phases']['raw_read_decode']['attempt_mean_seconds'])

    def test_indexed_pp20_explicit_completed_counts_are_not_the_63_attempts(self):
        # Exact trusted summary excerpt from PR #178, head 73da26e0d4a4d54.
        evidence = {'status': 'HOLD', 'reason': 'archive_limit',
            'first_page_rows': 500, 'first_page_succeeded': True,
            'first_page_seconds': 2.729234, 'first_page_latest_receipts_seconds': 0.133765,
            'completed': {'structured_pages': 62, 'structured_pages_required': 63, 'raw_objects': 57},
            'limits': {'seconds': 240, 'per_page_seconds': 4, 'requests': 192, 'logical_bytes': 134217728},
            'phase_accounting': {'diagnostics_unavailable': False, 'elapsed_seconds': 239.607621,
                'remaining_seconds': 0.392458, 'requests': 122, 'logical_bytes': 53777944,
                'failed_phase': 'history_checkout', 'phases': {
                    'structured_readback': {'calls': 63, 'seconds': 149.945141},
                    'history_exact_revisions': {'calls': 62, 'seconds': 71.051815}}}}
        result = summarize(evidence)
        self.assertEqual(result['outcome'], 'held')
        self.assertEqual(result['counts']['structured_readback_attempts'], 63)
        self.assertEqual(result['counts']['explicit_completed_structured_pages'], 62)
        self.assertEqual(result['counts']['explicit_required_structured_pages'], 63)
        self.assertEqual(result['counts']['explicit_completed_raw_objects'], 57)
        self.assertIsNone(result['counts']['reported_structured_rows'])
        self.assertEqual(result['reported_remaining_seconds'], 0.392458)
        self.assertEqual(result['limits']['seconds'], 240)
        self.assertEqual(result['first_page']['seconds'], 2.729234)
        self.assertTrue(result['first_page']['succeeded'])
        self.assertFalse(result['readback_completed'])
        self.assertFalse(compare(completed(), evidence)['comparison']['performance_comparable'])

    def test_completed_same_scope_can_compare_but_faster_hold_cannot_claim_speedup(self):
        baseline, candidate = completed(), completed(100)
        result = compare(baseline, candidate)['comparison']
        self.assertTrue(result['performance_comparable'])
        self.assertEqual(result['elapsed_reduction_percent'], 50)
        self.assertEqual(result['elapsed_seconds_delta'], -100)
        candidate['status'] = 'HOLD'
        candidate['phase_accounting']['failed_phase'] = 'history_projections'
        result = compare(baseline, candidate)['comparison']
        self.assertFalse(result['performance_comparable'])
        self.assertIsNone(result['elapsed_reduction_percent'])
        self.assertEqual(result['elapsed_seconds_delta'], -100)

    def test_scope_missing_mismatch_partial_coverage_and_late_runs_are_not_comparable(self):
        variants = []
        candidate = completed(100); candidate.pop('manifest_digest'); variants.append(candidate)
        candidate = completed(100); candidate['sealed'] = 'another'; variants.append(candidate)
        candidate = completed(100); candidate['structured_count'] = 499; variants.append(candidate)
        candidate = completed(100); candidate['operation_deadline_met'] = False; variants.append(candidate)
        candidate = completed(100); candidate['phase_accounting']['diagnostics_unavailable'] = True; variants.append(candidate)
        for candidate in variants:
            with self.subTest(candidate=candidate):
                result = compare(completed(), candidate)['comparison']
                self.assertFalse(result['performance_comparable'])
                self.assertIsNone(result['elapsed_reduction_percent'])

    def test_missing_invalid_metrics_remain_null_unknown_secrets_are_not_copied(self):
        evidence = {'status': ['password=secret'], 'reason': 'password=secret',
            'phase_accounting': {'elapsed_seconds': float('nan'), 'requests': True,
                'logical_bytes': -1, 'remaining_seconds': 10**1000,
                'failed_phase': 'password=secret', 'phases': {'password=secret': {'seconds': 2}}}}
        result = summarize(evidence)
        for key in ('elapsed_seconds', 'requests', 'logical_bytes', 'reported_remaining_seconds'):
            self.assertIsNone(result[key])
        self.assertEqual(result['outcome'], 'unknown')
        self.assertTrue(result['diagnostics_unavailable'])
        self.assertNotIn('secret', json.dumps(result, allow_nan=False))
        self.assertIsNone(compare({}, {})['comparison']['elapsed_seconds_delta'])

    def test_unknown_or_missing_failure_metadata_cannot_convert_failure_to_completion(self):
        candidate = completed()
        candidate['phase_accounting']['failed_phase'] = 'unrecognized_phase'
        self.assertFalse(summarize(candidate)['readback_completed'])
        candidate = completed()
        candidate['phase_accounting']['exhausted_limit'] = 'unrecognized_limit'
        self.assertFalse(summarize(candidate)['readback_completed'])

    def test_missing_phase_delta_is_null_not_implied_zero(self):
        candidate = completed(100)
        del candidate['phase_accounting']['phases']['history_connect']
        result = compare(completed(), candidate)
        self.assertIsNone(result['comparison']['phase_seconds_delta']['history_connect'])
        self.assertNotIn('history_connect', result['candidate']['phases'])

    def test_cli_reads_bounded_files_and_redacts_parse_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'password=never-echo'
            path.write_text(json.dumps(completed()))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([str(path), '--candidate', str(path)]), 0)
            self.assertTrue(json.loads(output.getvalue())['comparison']['performance_comparable'])
            path.write_text('{password=never-echo')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([str(path)]), 1)
            self.assertNotIn('never-echo', output.getvalue())
            path.write_text(json.dumps(completed()))
            with patch('postgres.retirement_telemetry.MAX_EVIDENCE_BYTES', 10):
                with self.assertRaises(ValueError):
                    load_evidence(path)


if __name__ == '__main__':
    unittest.main()
