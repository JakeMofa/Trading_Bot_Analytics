"""Bounded tracked-source syntax, shell syntax and high-confidence credential signatures.

This is a signature gate, not a claim that all secret formats are detectable.
Only tracked files are inspected; matching values are never printed.
"""
import ast
import re
import subprocess
from pathlib import Path

SIGNATURES = [re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
              re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
              re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{36,255}\b'),
              re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{50,255}\b')]


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    failures = []
    python_count = shell_count = scanned = 0
    for name in filter(None, names):
        path = Path(name)
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > 4 * 1024**2:
            failures.append((name, 'exceeds 4MiB scan limit; explicit review required'))
            continue
        body = path.read_bytes()
        scanned += 1
        if any(pattern.search(body) for pattern in SIGNATURES):
            failures.append((name, 'credential signature; value redacted'))
        if path.suffix == '.py':
            python_count += 1
            try:
                ast.parse(body, filename=name)
            except SyntaxError:
                failures.append((name, 'Python syntax invalid'))
        if path.suffix == '.sh':
            shell_count += 1
            if subprocess.run(['bash', '-n', name], capture_output=True).returncode:
                failures.append((name, 'shell syntax invalid'))
    for name, reason in failures:
        print(f'{name}: {reason}')
    print(f'Tracked files={scanned}; Python syntax={python_count}; shell syntax={shell_count}')
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
