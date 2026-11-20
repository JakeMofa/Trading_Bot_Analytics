"""Bounded, test-only Compose rendering with process-group cleanup and diagnostics."""
import json
import os
import re
import signal
import subprocess
import time


class ComposeRenderError(RuntimeError):
    pass


def _signal_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _stop_group(process):
    # The CLI leader may already have exited while its plugin/descendants retain
    # the output pipes. Signal the original group even in that case.
    _signal_group(process, signal.SIGTERM)
    try:
        output = process.communicate(timeout=0.25)
    except subprocess.TimeoutExpired:
        output = None
    # Also kill descendants that closed their pipes: leader exit/reap alone does
    # not prove the owned process group is gone.
    _signal_group(process, signal.SIGKILL)
    return process.communicate(timeout=1) if output is None else output


def _run(command, env, timeout):
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        stdout, stderr = _stop_group(process)
        return process.returncode, stdout, stderr, True
    except BaseException:
        _stop_group(process)
        raise


def _compose_version(env):
    try:
        code, stdout, _, timed_out = _run(['docker', 'compose', 'version'], env, 1)
    except (OSError, subprocess.TimeoutExpired):
        return 'unavailable'
    if timed_out:
        return 'probe_timeout'
    if code != 0:
        return 'probe_failed'
    text = stdout.decode('ascii', errors='replace').strip()
    match = re.fullmatch(r'Docker Compose version (v?[0-9][0-9A-Za-z.+_-]{0,63})', text)
    return match.group(1) if match else 'unrecognized'


def render_config(command, *, env, timeout):
    """Keep the caller's exact config command and its 5/10-second work limit.

    No retry occurs. On failure only, a separate one-second version probe helps
    identify a runner/plugin problem. Never report command arguments, environment,
    rendered configuration, or child stdout/stderr contents in an error.
    """
    started = time.monotonic()
    try:
        code, stdout, stderr, timed_out = _run(command, env, timeout)
    except OSError:
        code, stdout, stderr, timed_out = None, b'', b'', False
        failure = 'spawn_failed'
    except subprocess.TimeoutExpired:
        code, stdout, stderr, timed_out = None, b'', b'', True
        failure = 'cleanup_unproven'
    else:
        failure = 'timeout' if timed_out else 'exit_failed' if code else None
    elapsed = round(time.monotonic() - started, 3)
    if failure is None:
        try:
            config = json.loads(stdout)
            if isinstance(config, dict):
                return config
        except (ValueError, UnicodeError):
            pass
        failure = 'invalid_config_json'
    diagnostics = dict(failure=failure, timeout_seconds=timeout,
                       elapsed_seconds=elapsed, exit_code=code,
                       stdout_bytes=len(stdout), stderr_bytes=len(stderr),
                       compose_version=_compose_version(env))
    raise ComposeRenderError('compose_config_failed ' + json.dumps(diagnostics, sort_keys=True)) from None
