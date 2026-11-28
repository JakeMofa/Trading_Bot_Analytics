# Private Benchmark source controls

Only `pp-live-pp-benchmark-watch` has per-source commands. Existing users of
the read-only dashboard can see the durable preferences and current worker
status. An operator opens a restricted session to see enabled action buttons
on that same Market page. Pausing one feed preserves both other preferences
and the collector lease. Resuming one feed leaves a stopped global collector OFF.

Forward the existing private FastAPI and operator listeners through the
pinned Benchmark SSH connection as 127.0.0.1:18433 → 127.0.0.1:8000 and
127.0.0.1:18434 → 127.0.0.1:8001. An authorized host operator requests
`POST /collector/feeds/session` using the existing private operator Bearer
header inside its trusted channel. Pipe that JSON directly through the SSH
connection to `python3 deploy/preprod/open_benchmark_feed_controls.py` on the
desktop. Never print the grant, copy it into a PR, or put it in query strings.
The browser receives only a 30-minute feed-control grant. It cannot start
or stop the whole collector. Closing or reloading the page locks the controls.
Minting, expiry, locking the browser and redeploying do not change preferences.

The read-only API returns desired and observed feed status in `/state/current`.
The private operator accepts one feed and an expected revision in each
`PUT /collector/feeds/{feed}`. Commands are serialized per source and the
response follows PostgreSQL commit. Existing `ops.worker_checkpoints` rows
are keyed by stable origin and feed, independent of the current A/B slot.
