# AB72 archive probe review

The original GET against the authenticated Storage object route returned HTTP 400
on November 4 at 9:03:50 p.m. Chicago time. The matching Storage log record is
`ba370c17-95a9-4262-9fc7-cdc003acf53e`. The original client saved the status only.
A single read-only GET against the identical key from lifecycle PID 31771
reproduced HTTP 400 with Storage code `NoSuchKey`, error `not_found`, embedded
status `404` and request ID `01a1a9b4-7728-7bfe-a791-b2116c1e8336`. Neither
request wrote an object or row. The route shape is the same as the archive
client's authenticated download route.

The candidate recognizes that exact wrapped absence response only during
preflight. Other unexpected responses stop the probe. The POST retains
`x-upsert: false`, including if the key appears after preflight. An ambiguous
POST can proceed only to the same authenticated readback and exact verification.
Eight isolated Linux loopback tests passed with external networking disabled.

[Supabase error codes](https://supabase.com/docs/guides/storage/debugging/error-codes)
and [create-only upload behavior](https://supabase.com/docs/guides/storage/uploads/standard-uploads).

One attempt for approval, from the repository root. The limit is 180 seconds,
three HTTP attempts, one object of at most 64 KiB under
`ab72-readiness/2026-11-03-v1/`, two embedded synthetic records and zero
structured row writes. Cleanup requires separate approval.

```bash
python3 - <<'PY'
import shlex
import subprocess

loader = """
import hashlib, pathlib, subprocess, sys, tempfile
payload = sys.stdin.buffer.read(262145)
expected = "3ea35c10ebec4bf47eaad305c14d13ea3581b4e6b1f0bb485e969b1d2729bbe5"
if len(payload) > 262144 or hashlib.sha256(payload).hexdigest() != expected:
    raise SystemExit("probe bundle checksum mismatch")
with tempfile.TemporaryDirectory(prefix="ab72-probe-") as folder:
    bundle = pathlib.Path(folder) / "probe.pyz"
    bundle.write_bytes(payload)
    result = subprocess.run([sys.executable, "-IS", str(bundle), "--live"],
                            cwd=folder, env={}, timeout=171)
raise SystemExit(result.returncode)
"""
remote = "sudo -n timeout 172 /usr/bin/python3 -IS -c " + shlex.quote(loader)
with open("/private/tmp/ab72-wrapped-absence-probe.pyz", "rb") as bundle:
    result = subprocess.run([
        "ssh", "-i", "data/deploy/lightsail/tradebot-20261023",
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=data/deploy/lightsail/known_hosts",
        "-o", "ConnectTimeout=7", "ubuntu@3.13.133.25", remote,
    ], stdin=bundle, timeout=180)
raise SystemExit(result.returncode)
PY
```
