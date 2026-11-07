"""Record a command gate without storing command output or environment values."""
import argparse
import subprocess
import time
from run_tests import write_evidence

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('category')
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
started = time.monotonic()
try:
    code = subprocess.run(args.command, check=False).returncode
    write_evidence(args.category, {'gate': 'PASS' if code == 0 else 'FAIL', 'exit_code': code}, started)
except OSError:
    write_evidence(args.category, {'gate': 'BLOCKED', 'reason': 'command unavailable'}, started)
    raise
raise SystemExit(code)
