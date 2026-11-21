"""Offline public-input rendering; no database, network, identity or policy changes."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bind_fourth_trial_cloud_policy as renderer

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = 'pp-live-pp-trial-20261119-04'
PREFIX = sha256(ORIGIN.encode()).hexdigest()
VALUES = dict(writer_uid='00000000-0000-4000-8000-000000000022',
              writer_email='archive04@example.invalid',
              reader_uid='00000000-0000-4000-8000-000000000033',
              reader_email='history-reader04@example.invalid', policy_sha256='ab' * 32)


class FourthTrialPolicyTests(unittest.TestCase):
    def test_policies_are_only_exact_scope_substitutions_of_reviewed_third(self):
        old_prefix = sha256(b'pp-live-pp-trial-20261119-03').hexdigest()
        for suffix in ('structured.sql', 'storage.sql.in'):
            old = (ROOT / ('supabase/review/pp_trial_20261119_03_' + suffix)).read_text()
            new = (ROOT / ('supabase/review/pp_trial_20261119_04_' + suffix)).read_text()
            restored = new.replace('20261119_04', '20261119_03').replace(
                '20261119-04', '20261119-03').replace('fourth trial', 'third trial').replace(PREFIX, old_prefix)
            self.assertEqual(restored, old)

    def test_render_binds_public_inputs_and_only_fourth_raw_prefix(self):
        rendered = renderer.render(**VALUES)
        self.assertNotRegex(rendered, r'__[A-Z_]+__')
        for value in VALUES.values():
            self.assertIn(value, rendered)
        patterns = re.findall(r"name ~ '([^']+)'", rendered)
        self.assertEqual(len(patterns), 4)
        generation = '00000000-0000-4000-8000-000000000001'
        key = 'raw-v1/' + PREFIX + '/' + generation + '/' + 'a' * 64 + '.jsonl.gz'
        for pattern in patterns:
            self.assertRegex(key, pattern)
            for origin in ('pp-live-pp', *(f'pp-live-pp-trial-20261119-0{i}' for i in (1, 2, 3)), 'production'):
                foreign = key.replace(PREFIX, sha256(origin.encode()).hexdigest())
                self.assertNotRegex(foreign, pattern)
            self.assertNotRegex(key + '/extra', pattern)
        self.assertIn("storage.allow_only_operation('storage.object.upload')", rendered)
        self.assertIn('AS RESTRICTIVE FOR UPDATE', rendered)
        self.assertIn('AS RESTRICTIVE FOR DELETE', rendered)

    def test_malformed_duplicate_or_injectable_bindings_are_rejected(self):
        for changes in ({'writer_uid': 'not-a-uuid'}, {'reader_uid': VALUES['writer_uid']},
                        {'writer_uid': '00000000-0000-4000-8000-0000000000AA'},
                        {'reader_email': VALUES['writer_email']},
                        {'writer_email': "x' OR true--@example.invalid"},
                        {'reader_email': 'x@example.invalid\n'}, {'policy_sha256': 'NOT_REVIEWED'},
                        {'policy_sha256': 'AB' * 32}, {'policy_sha256': 'a' * 63}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                renderer.render(**(VALUES | changes))

    def test_unknown_template_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'template.sql.in'
            path.write_text('__UNREVIEWED_MARKER__')
            with patch.object(renderer, 'TEMPLATE', path), self.assertRaises(ValueError):
                renderer.render(**VALUES)

    def test_cli_output_is_create_only_and_invalid_input_creates_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'review.sql'
            args = [part for key, value in VALUES.items() for part in ('--' + key.replace('_', '-'), value)]
            renderer.main(args + ['--output', str(path)])
            before = path.read_bytes()
            self.assertEqual(before.decode(), renderer.render(**VALUES))
            with self.assertRaises(FileExistsError):
                renderer.main(args + ['--output', str(path)])
            self.assertEqual(path.read_bytes(), before)
            other = Path(td) / 'invalid.sql'
            invalid = [part for key, value in (VALUES | {'policy_sha256': 'bad'}).items()
                       for part in ('--' + key.replace('_', '-'), value)]
            with self.assertRaises(ValueError):
                renderer.main(invalid + ['--output', str(other)])
            self.assertFalse(other.exists())

    def test_import_never_calls_process_or_network(self):
        spec = importlib.util.spec_from_file_location('offline_fourth_policy', renderer.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch('subprocess.run', side_effect=AssertionError('no process')), \
             patch('subprocess.check_output', side_effect=AssertionError('no process')), \
             patch('socket.socket', side_effect=AssertionError('no network')):
            spec.loader.exec_module(module)
        self.assertEqual(module.TEMPLATE, ROOT / 'supabase/review/pp_trial_20261119_04_storage.sql.in')


if __name__ == '__main__':
    unittest.main()
