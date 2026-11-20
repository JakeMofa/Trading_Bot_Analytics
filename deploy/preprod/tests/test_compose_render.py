"""Real local child/grandchild faults; no Docker engine or network required."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from compose_render import ComposeRenderError, render_config, _compose_version


class ComposeRenderTests(unittest.TestCase):
    def test_success_preserves_exact_command_environment_and_work_timeout(self):
        command = ['docker', 'compose', 'config', '--format', 'json']
        env = {'PP_APP_IMAGE': 'exact-image'}
        with patch('compose_render._run', return_value=(0, b'{"services":{}}', b'', False)) as run, \
             patch('compose_render._compose_version') as version:
            self.assertEqual(render_config(command, env=env, timeout=5), {'services': {}})
        run.assert_called_once_with(command, env, 5)
        version.assert_not_called()

    def test_failure_has_sanitized_version_elapsed_exit_without_payload_or_retry(self):
        command = [sys.executable, '-c', "import sys;print('PRIVATE_CONFIG');sys.stderr.write('PRIVATE_SECRET');sys.exit(7)"]
        with patch('compose_render._compose_version', return_value='v5.6.1'):
            with self.assertRaises(ComposeRenderError) as caught:
                render_config(command, env=os.environ.copy(), timeout=10)
        text = str(caught.exception)
        self.assertNotIn('PRIVATE', text)
        details = json.loads(text.split(' ', 1)[1])
        self.assertEqual(details['failure'], 'exit_failed')
        self.assertEqual(details['exit_code'], 7)
        self.assertEqual(details['compose_version'], 'v5.6.1')
        self.assertEqual(details['timeout_seconds'], 10)
        self.assertGreaterEqual(details['elapsed_seconds'], 0)

    def test_invalid_config_and_spawn_failure_are_sanitized(self):
        for result, expected in [((0, b'PRIVATE_INVALID', b'', False), 'invalid_config_json'),
                                 ((0, b'[]', b'', False), 'invalid_config_json')]:
            with self.subTest(expected=expected), patch('compose_render._run', return_value=result), \
                 patch('compose_render._compose_version', return_value='unavailable'):
                with self.assertRaises(ComposeRenderError) as caught:
                    render_config(['unused'], env={}, timeout=5)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn('PRIVATE', str(caught.exception))
        with patch('compose_render._run', side_effect=FileNotFoundError('PRIVATE_PATH')), \
             patch('compose_render._compose_version', return_value='unavailable'):
            with self.assertRaisesRegex(ComposeRenderError, 'spawn_failed') as caught:
                render_config(['unused'], env={}, timeout=5)
            self.assertNotIn('PRIVATE', str(caught.exception))

    def test_version_probe_is_separately_bounded_and_never_echoes_unknown_text(self):
        for raw, want in [(b'Docker Compose version v5.6.1\n', 'v5.6.1'),
                          (b'PRIVATE_UNRECOGNIZED', 'unrecognized')]:
            with self.subTest(raw=raw), patch('compose_render._run', return_value=(0, raw, b'', False)) as run:
                self.assertEqual(_compose_version({}), want)
                run.assert_called_once_with(['docker', 'compose', 'version'], {}, 1)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups required')
    def test_timeout_kills_and_reaps_child_and_stubborn_grandchild(self):
        # The command spawns a child, which spawns a grandchild. Both descendants
        # ignore TERM. Test both inherited and closed pipes: leader exit alone
        # must not be mistaken for complete cleanup.
        for close_pipes in (False, True):
            with self.subTest(close_pipes=close_pipes), tempfile.TemporaryDirectory() as td:
                path = Path(td) / 'pids.json'
                grandchild = "import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(120)"
                child = (
                    "import json,os,signal,subprocess,sys,time;"
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                    "p=subprocess.Popen([sys.executable,'-c',sys.argv[2]]);"
                    "open(sys.argv[1],'w').write(json.dumps([os.getpid(),p.pid]));"
                    "time.sleep(120)"
                )
                leader = (
                    "import subprocess,sys,time;"
                    "subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1],sys.argv[3]],"
                    + ("stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if close_pipes else "stdout=None,stderr=None")
                    + ");time.sleep(120)"
                )
                command = [sys.executable, '-c', leader, str(path), child, grandchild]
                processes = []
                original_popen = subprocess.Popen
                def start(*args, **kwargs):
                    self.assertIs(kwargs.get('start_new_session'), True)
                    process = original_popen(*args, **kwargs)
                    processes.append(process)
                    return process
                with patch('compose_render._compose_version', return_value='fixture'), \
                     patch('compose_render.subprocess.Popen', side_effect=start):
                    with self.assertRaisesRegex(ComposeRenderError, 'timeout'):
                        render_config(command, env=os.environ.copy(), timeout=1)
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].returncode)
                with self.assertRaises(ChildProcessError):
                    os.waitpid(processes[0].pid, os.WNOHANG)
                pids = json.loads(path.read_text())
                def alive(pid):
                    try:
                        proc = Path('/proc') / str(pid) / 'stat'
                        if proc.exists() and proc.read_text().split(') ', 1)[1].startswith('Z '):
                            return False  # Reparented dead descendant awaiting init reap.
                        os.kill(pid, 0)
                        return True
                    except ProcessLookupError:
                        return False
                deadline = time.monotonic() + 2
                while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(any(alive(pid) for pid in pids), pids)


if __name__ == '__main__':
    unittest.main()
