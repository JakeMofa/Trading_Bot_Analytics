# I7 exact-release exception — no database copies or snapshots

User authorized implementation and execution on October 30, 2026. This is an
operational runbook; `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md` remains the roadmap.
The prior copy-based maintenance plan is withdrawn and its execute CLI disabled.

## Fixed release and gates

Old application: `a7c098900f8310367fc262a1b837c369bb63dc56`.
Candidate: `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a` on the existing deployment
branch. Only the worker containment plus its tests/documentation are included.
No migration, index, dependency, unit, configuration or retention change.

The temporary protected deployment helper requires that exact old/candidate pair,
bundle ref, ancestry and six-file changed scope. A root-owned mode-0600 one-use
authorization file `/run/tradebot-i7-authorization.json` records `old`, `release`,
`application_ci_run`, `helper_ci_run`, `helper_sha256` and `expires_at` (Unix time,
no more than one hour away). The trusted operator verifies both exact-commit CI
runs and current deployment branch before writing it. The VM receives no GitHub
credentials. The existing Actions workflow independently verifies application CI.

Retain OFF flags, absent paid-AI credentials, guard4096, protected config, disk
reserve, clean checkout, expected schema, private listener and single collector.
Read only SQLite metadata in a child with a five-second deadline. Record full
quick/FK checks as `NOT_PERFORMED_SCOPED_I7_EXCEPTION`, never integrity PASS.
Normal non-I7 releases retain their original full-check path.

## Execution and recovery

1. Refresh the runtime, storage and services. Abort on mismatch or reached guard.
2. Export the exact CI-passed helper; transfer through existing pinned operator
   SSH, verify SHA-256, preserve the original protected **helper code only**, and
   install the reviewed root-owned helper. No database file is copied.
3. Write the bounded one-use authorization after fresh GitHub checks. Use the
   existing one-job private runner and manual deployment workflow with the fixed
   candidate SHA. Keep the existing deployment flock and unchanged forced key.
4. The helper records baseline health (known timeout allowed), consumes the
   authorization, checks out the candidate, restarts only API and requires bounded
   smoke checks. It retains before/after PID/restart evidence and phase times.
5. Work budget600 seconds plus recovery180, each command bounded. Supervise the
   operation inside the Actions900-second limit. Only API may restart; rollback
   restores old application code, never database data. Failed old-code health is
   not certified; failure to restore is `MANUAL_ACTION_REQUIRED`. No auto retry.
6. After the attempt restore the original protected helper code, verify its hash,
   remove any unused authorization, and clean up/unregister the ephemeral runner.
   The release result remains failed even after successful recovery.

## Observation and closure

Observe >=20 minutes and >=3 completed feature cycles, max30 minutes. Sample
lightweight API/feed state every5 seconds with two-second request limits; use
existing journal cycle timestamps. Record revision, automatic restarts, feed and
LiveState progress, feature/input age, rollover, disk I/O, RAM, CPU, DB/WAL sizes
and guard headroom. Do not introduce historical scans for monitoring.

Containment requires no two-second API timeouts during observed cycles, advancing
feeds/LiveState, stable services, dashboard/SSE and persisted collection. Snapshot
age target30 seconds; existing price freshness threshold30 seconds. Freshness
failure keeps I7 OPEN even if containment passes. Complete quick/FK verification
remains outstanding before retention. No Phase2 work.
