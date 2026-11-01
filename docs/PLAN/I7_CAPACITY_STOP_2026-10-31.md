# I7 capacity STOP and revised next plan — October 31, 2026

**Current checkpoint: I7 OPEN; production collection stopped at storage guard.**
This supersedes the earlier healthy production samples. The single authoritative
roadmap remains `INTELLIGENCE_REBUILD_PLAN.md`.

## Fresh observations

Read-only evidence captured **2026-11-01T00:32:04.840498+00:00 UTC / 2026-10-31T19:32:04.840498-05:00 America/Chicago**:

| Item | Observed result |
|---|---|
| Production revision | `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a` |
| Tracked checkout | Clean |
| API / ensemble / lifecycle PIDs | 10915 /849 /843, active, zero automatic restarts |
| Collector | **Not running** |
| Coinbase last data | 2026-10-31T09:24:21.972807+00:00; feed stopped |
| Polymarket last data | 2026-10-31T09:24:21.719857+00:00; feed stopped |
| Storage guard state | `limit_reached`, configured4096MiB |
| DB file | 4,278,059,008bytes |
| WAL file | 17,431,752bytes |
| Combined guard usage | 4096.499214MiB |
| Guard headroom | -523,464bytes (negative) |
| Filesystem free | 48.038GiB |
| SQLite page size / count | 4096 /1044448 |
| SQLite free pages | 0 |
| auto_vacuum | 0 (NONE) |
| Flags | OpenAI/retention OFF, paid credentials absent, guard unchanged |
| Deployment controls | Original helper restored, one-use authorization absent |

Existing production journal confirmed:

> Storage cap 4096 MiB reached (4096.3 MiB used); collection stopped without deleting data

Both feeds last advanced around **04:24AM October31 Chicago time**. The API and
SSE/dashboard still respond but serve retained state; they are not evidence of
live collection. The current `/health` reports `status=ok` despite
`collector_running=false` and stopped feeds. This is a reporting defect, not
proof of a healthy engine. No fresh full integrity/FK check was run.

The VM is not out of disk: the bot's configured DB+WAL limit has been reached.
With auto_vacuum NONE, deleting rows generally leaves reusable pages inside the
allocated file, rather than shrinking it. Retention must not be described as an
instant reduction in this file-size guard. [SQLite documentation](https://www.sqlite.org/lang_vacuum.html).
No retention or reclamation operation was attempted.

## Plan now, in order

1. **Completed:** refresh production revision, feeds, masked flags, allocation and
   disk headroom with bounded reads. Geometry child deadline5s; no history scan.
2. **Implemented locally:** read-only `i7_readiness.py` assesses a saved sanitized
   projection. Reject stopped/stale feeds, guard reach/latch, missing/unsafe flags,
   changed revision, stale evidence and unqualified/insufficient build budgets.
   Filesystem free space does not override the guard. It has no execute mode;
   even a positive result means only `READY_FOR_OPERATOR_REVIEW`.
3. **Implemented locally:** health is degraded when an enabled collector exits
   cleanly, or storage guard is limit_reached, even with populated cached RAM.
   Explicit collector-disabled read-only app behavior is preserved. No new API
   fields/status codes/routes. This reporting correction is NOT DEPLOYED.
4. **STOP / recovery decision required:** review a concrete capacity recovery
   operation consistent with data integrity and user constraints. Current
   authorization does not permit retention, compaction, guard bypass/increase,
   manual WAL action, database replacement/copies or a restart to force progress.
   R5/R6 retention qualification remains STOP. Do not silently repurpose the
   unused filesystem capacity or change guard accounting to resume collection.
5. After approved recovery and a fresh readiness PASS, qualify index/WAL/temp
   storage and writer interruption on the VM; prepare the bounded schema/release
   operation. The synthetic index measurements are not production qualification.
6. Install/release only after those gates; then validate >=20minutes, >=3cycles,
   current market rollover, <=30s snapshot age, feeds, persistence and stable API.
7. Complete remaining Phase1.75 gates, including full quick/FK audit before
   retention, R5/R6 and subsequent R7–R17. Stop before Phase2.

## Completed local validation

**191 backend tests +40 deployment/control tests PASS**, compile/diff PASS.
New tests cover the cleanly exited collector false-positive, guard-limited cached
RAM, guard vs physical disk reserve, stale evidence/feeds, missing/unsafe flags,
unqualified budgets, positive assessment never authorizing execution, and a CLI
that neither modifies its input nor accepts `--execute`.

No production service restart, DB/index write, deletion, retention, VACUUM,
checkpoint/truncate, guard/config change, DB copy/snapshot, SSH/firewall change,
AWS resource or Phase2 action occurred. Existing services stayed running; source
collection remained stopped. The freshness implementation remains undeployed.
Local evidence: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/i7-capacity-stop-20261031/` (runtime, geometry, readiness, tests and exact CI).
