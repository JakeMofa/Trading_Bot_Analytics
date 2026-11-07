import json
from pathlib import Path
import tempfile
import unittest
from readiness import CATEGORIES, REQUIRED, JOBS, validate
from run_tests import APPLICATION, ROOT, REQUIRED_ROOT, ExecutionEvidence, required_execution
import io
from summaries import readiness_summary


class GateTests(unittest.TestCase):
    def fixture(self, directory):
        for category in CATEGORIES:
            (directory / (category + '.json')).write_text(json.dumps(
                {'gate': 'PASS', 'source_sha': 'a'*40, 'tested_sha': 'b'*40, 'tests': 2, 'skips': 1}))
        for name in REQUIRED:
            (directory / name).write_text(json.dumps({'source_sha': 'b'*40}))

    def test_missing_failure_sha_zero_tests_and_duplicate_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            check = lambda: validate(root, dict.fromkeys(JOBS, 'success'), 'b'*40, 'a'*40)
            self.assertEqual(check(), [])
            self.assertTrue(validate(root, {}, 'b'*40, 'a'*40))
            (root / 'root.json').unlink()
            self.assertTrue(check())
            self.fixture(root)
            data = json.loads((root / 'root.json').read_text())
            for key, value in [('gate', 'FAIL'), ('tested_sha', 'c'*40), ('source_sha', 'd'*40), ('tests', 1)]:
                changed = dict(data, **{key: value})
                (root / 'root.json').write_text(json.dumps(changed))
                self.assertTrue(check(), key)
            self.fixture(root)
            (root / 'duplicate').mkdir()
            (root / 'duplicate/root.json').write_text((root / 'root.json').read_text())
            self.assertTrue(check())

    def test_failed_or_skipped_job_and_missing_generated_report_block_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            for state in ['failure', 'skipped', 'cancelled', 'queued', 'in_progress', 'pending']:
                self.assertTrue(validate(root, dict(dict.fromkeys(JOBS, 'success'), test=state), 'b'*40, 'a'*40))
            (root / 'integrated-report.json').unlink()
            self.assertTrue(validate(root, dict.fromkeys(JOBS, 'success'), 'b'*40, 'a'*40))

    def test_security_failure_is_distinct_from_sha_failure_and_summary_preserves_skips(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            data = json.loads((root / 'dependencies.json').read_text())
            data['gate'] = 'FAIL'
            (root / 'dependencies.json').write_text(json.dumps(data))
            jobs = dict(dict.fromkeys(JOBS, 'success'), security='failure')
            problems = validate(root, jobs, 'b'*40, 'a'*40)
            self.assertIn('dependencies: FAIL gate result', problems)
            self.assertFalse(any('SHA binding' in problem for problem in problems))
            text = readiness_summary(root, jobs, CATEGORIES, 'a'*40, 'b'*40,
                                     'https://github.com/example/repo/actions/runs/123', problems)
            for expected in ['| security | FAIL |', '| backend | PASS | 2 | 1 |',
                             'Source SHA: `' + 'a'*40, 'Tested SHA: `' + 'b'*40,
                             '/actions/runs/123', 'Readiness: BLOCKED', 'NOT PERFORMED']:
                self.assertIn(expected, text)

    def test_postgres_job_and_executed_schema_evidence_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            jobs = dict.fromkeys(JOBS, 'success')
            self.assertEqual(validate(root, jobs, 'b'*40, 'a'*40), [])
            jobs.pop('postgres')
            self.assertTrue(validate(root, jobs, 'b'*40, 'a'*40))
            jobs['postgres'] = 'success'
            (root / 'postgres.json').unlink()
            self.assertTrue(validate(root, jobs, 'b'*40, 'a'*40))
            self.fixture(root)
            (root / 'postgres.json').write_text(json.dumps({'gate': 'PASS',
                'tested_sha': 'b'*40, 'source_sha': 'a'*40, 'tests': 0, 'skips': 0}))
            self.assertTrue(validate(root, jobs, 'b'*40, 'a'*40))

    def test_checkpoint4_root_inclusion_and_success_not_skip_are_required(self):
        self.assertIn('test_archive_history.py', ROOT)
        class Case(unittest.TestCase):
            def runTest(self): pass
            def id(self): return REQUIRED_ROOT
        success = unittest.TextTestRunner(stream=io.StringIO(), resultclass=ExecutionEvidence).run(Case())
        self.assertTrue(required_execution('root', success))
        class Skipped(Case):
            def runTest(self): self.skipTest('missing privilege')
        skipped = unittest.TextTestRunner(stream=io.StringIO(), resultclass=ExecutionEvidence).run(Skipped())
        self.assertFalse(required_execution('root', skipped))
        empty = unittest.TextTestRunner(stream=io.StringIO(), resultclass=ExecutionEvidence).run(unittest.TestSuite())
        self.assertFalse(required_execution('root', empty))

    def test_application_partition_names_exist(self):
        self.assertTrue(APPLICATION)
        for name in APPLICATION:
            self.assertTrue((Path('backend/tests') / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
