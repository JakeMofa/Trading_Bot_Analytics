"""Partition existing unittest suites and emit sanitized, machine-readable evidence."""
import argparse
import json
import os
from pathlib import Path
import time
import unittest

APPLICATION = {'test_api.py', 'test_dashboard.py', 'test_dashboard_api.py',
               'test_live_state.py', 'test_streaming.py', 'test_rollover_publication.py',
               'test_rollover_health.py', 'test_feature_freshness.py'}
ROOT = ['test_raw_generations.py', 'test_ab_application.py', 'test_ab_runtime.py',
        'test_incremental_retirement.py', 'test_ab_cutover.py', 'test_archive_history.py']


REQUIRED_ROOT = 'test_archive_history.Tests.test_actual_retirement_then_archive_history_calculations_and_dashboard'


class ExecutionEvidence(unittest.TextTestResult):
    """Record successful execution, rather than discovery or a skipped test."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successful_ids = set()

    def addSuccess(self, test):
        self.successful_ids.add(test.id())
        super().addSuccess(test)


def required_execution(category, result):
    return category != 'root' or REQUIRED_ROOT in result.successful_ids


def write_evidence(category, result, started):
    evidence = {'category': category, 'source_sha': os.environ.get('CI_SOURCE_SHA'),
                'tested_sha': os.environ.get('GITHUB_SHA'),
                'event': os.environ.get('GITHUB_EVENT_NAME'),
                'scope': 'synthetic offline CI; no production acceptance or capacity claim',
                'elapsed_seconds': round(time.monotonic() - started, 3), **result}
    directory = Path(os.environ['CI_EVIDENCE_DIR'])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (category + '.json')).write_text(json.dumps(evidence, indent=2) + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f"### {category}: {evidence['gate']}\n\n"
                          f"Source `{evidence['source_sha']}`; tested `{evidence['tested_sha']}`.\n\n"
                          f"Tests: {evidence.get('tests', 'NOT PERFORMED')}; skips: "
                          f"{evidence.get('skips', 'NOT PERFORMED')}; elapsed: {evidence['elapsed_seconds']}s.\n\n"
                          "Generated/offline scope only. Production acceptance and full capacity: NOT PERFORMED.\n\n")
    return evidence


def suite(category):
    loader = unittest.TestLoader()
    if category == 'controls':
        return loader.discover('deploy/lightsail', pattern='test_*.py')
    if category == 'ci-controls':
        return loader.discover('.github/ci', pattern='test_*.py')
    paths = sorted(Path('backend/tests').glob('test_*.py'))
    if category == 'root':
        paths = [Path('backend/tests') / name for name in ROOT]
    elif category == 'application':
        paths = [p for p in paths if p.name in APPLICATION]
    elif category == 'backend':
        paths = [p for p in paths if p.name not in APPLICATION]
    else:
        raise ValueError('unknown category')
    return unittest.TestSuite(loader.discover('backend/tests', pattern=p.name) for p in paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('category', choices=['backend', 'application', 'root', 'controls', 'ci-controls'])
    args = parser.parse_args()
    started = time.monotonic()
    try:
        result = unittest.TextTestRunner(verbosity=2, resultclass=ExecutionEvidence).run(suite(args.category))
        passed = result.wasSuccessful() and result.testsRun > len(result.skipped) and required_execution(args.category, result)
        write_evidence(args.category, {'gate': 'PASS' if passed else 'FAIL',
                       'tests': result.testsRun, 'skips': len(result.skipped),
                       'required_checkpoint4_executed': REQUIRED_ROOT in result.successful_ids,
                       'failures': len(result.failures), 'errors': len(result.errors)}, started)
    except Exception:
        write_evidence(args.category, {'gate': 'BLOCKED', 'reason': 'test runner could not complete'}, started)
        raise
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
