import json
from pathlib import Path
import tempfile
import unittest
from readiness import CATEGORIES, REQUIRED, JOBS, validate
from run_tests import APPLICATION


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
            for state in ['failure', 'skipped', 'cancelled']:
                self.assertTrue(validate(root, dict(dict.fromkeys(JOBS, 'success'), test=state), 'b'*40, 'a'*40))
            (root / 'integrated-report.json').unlink()
            self.assertTrue(validate(root, dict.fromkeys(JOBS, 'success'), 'b'*40, 'a'*40))

    def test_application_partition_names_exist(self):
        self.assertTrue(APPLICATION)
        for name in APPLICATION:
            self.assertTrue((Path('backend/tests') / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
