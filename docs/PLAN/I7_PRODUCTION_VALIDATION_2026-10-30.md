# I7 production release and observation — October 30, 2026

I7 remains **OPEN** in Phase 1.75. The worker fix is now deployed. Sampled API stall containment passed; feature freshness and rollover remain unresolved. The official roadmap remains `INTELLIGENCE_REBUILD_PLAN.md`.

## Release and controls

- Application: `a7c098900f8310367fc262a1b837c369bb63dc56` -> `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`; existing deployment branch only.
- Temporary protected helper: feature-branch commit `c2304eb3ec7e266a692696f246d438bf73c2313f`, SHA256 `d3681a5861c59e9ac2ebe97cd9864825aacf192a5fe4042060b7e6f2c882db65`.
- Exact application [CI41138048640](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41138048640) and helper [CI41159551744](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41159551744) passed. Current helper checkout: **182 backend +33 deployment/control tests PASS**; isolated application previously 159 backend +6 deployment checks and exact CI PASS.
- [Manual deployment41159675569](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41159675569) succeeded once. Metadata readiness PASS, all 12 existing endpoint/SSE/dashboard smoke checks PASS. No baseline full-smoke requirement for the known stalled old API; its two-second health probe timed out.
- User-authorized exact-release exception: full quick/FK audit **`NOT_PERFORMED_SCOPED_I7_EXCEPTION`**. Five-second read-only metadata checks are not an integrity certificate. Full audit remains outstanding before retention.
- Only API restarted: PID 2273 ->10915. Ensemble 849 / lifecycle 843 and monitor timer retained; automatic restart counts stayed 0. No application config, schema/index, dependency or unit changes.
- Original protected helper restored and hash-verified as `e633c7dbba7d3aa62bc105a60d3353d735da2954d5b707c639a091621206f5ae`; consumed authorization absent. One-job runner unregistered, credentials removed and its directory deleted; repository runner count 0.

## Restart and collection gap

API restart requested at **2026-10-31T02:22:21.427021+00:00**. The stalled old process exceeded the existing 60-second systemd stop policy; systemd issued SIGKILL at 02:23:21 UTC. No additional application kill command was issued. The new process completed startup at 02:24:47.252675 UTC; listener started02:24:47.389772 UTC. First healthy five-second observation was 02:24:50.983911 UTC.

The stop-request-to-listener interval was approximately 146 seconds, including 60 seconds old-process shutdown and 85 seconds startup/hydration. This is the measured service interruption window, not an exact accounting of missed market events. The old process was already stalled; there is no reliable last-tick-before-stop boundary in this observation. Missed ticks/books are not assumed backfilled. Normal SQLite crash recovery may occur after systemd termination; no operator WAL action or database repair was performed.

## Multi-cycle observation

Observation after release success: **2026-10-31T02:25:15.983937+00:00 to 2026-10-31T02:46:05.944991+00:00**, 20.85 minutes after release success. Five-second samples; two-second HTTP request limits. 11 completed feature cycles, 251 post-release samples, 498 probes.

| Check | Result |
|---|---|
| API sampled responsiveness | 0 failed probes; 0 timeouts; p95 0.0281s; max 0.0750s |
| Monitoring gaps | 2 extension samples lacked HTTP probes because journal had no matches; not counted as successes |
| Feature-cycle duration | 83.576–86.720s |
| Newly calculated snapshot age | 84.084–204.277s; target 30 s **FAIL** |
| All observed snapshot ages | 84.084–380.247s, including hydrated pre-release snapshot |
| Market rollover | 2 market identities observed; see transitions below |
| Non-live feed samples | 8; details preserved in local JSON |
| Collector/LiveState | New stream timestamps, market changes and persisted feature snapshot IDs advance; see final runtime projection |
| Flags | OpenAI/retention OFF; guard 4096 MiB; paid-AI credentials absent |
| API CPU | 8.523% of one core averaged over observations |
| Host I/O wait | 34.442% aggregate CPU time; not individually attributed SQL |
| API physical reads | 16760.848MiB, process including worker threads |
| API cgroup memory maximum | 777.633MiB, includes charged cache; not RSS |
| Host available memory minimum | 1348.711MiB |
| Final sampled DB / WAL | 4037951488 / 13451832 bytes |
| Sampled guard headroom | 232.281MiB; no guard increase |

Observed rollover transitions (five-second detection precision):

- Market `1974291` first seen 2026-10-31T02:30:50.983928+00:00, 50.984s after its start.

Snapshot input price quality remains measured relative to each historical `as_of`; a price marked fresh there does not mean the published snapshot is current now. Price staleness threshold remains 30 seconds. Market-scoped features can be missing after rollover until the next slow cycle completes. API containment success does not establish current trade intelligence.

## Remaining cause and next milestone

A five-second-bounded **EXPLAIN-only** production inspection confirmed: stream lookup searches `(source,event_id)` by source then uses a temporary ORDER BY B-tree; reference-price lookup scans its table and uses another temporary sort. No historical SELECT was executed for this inspection; no production index was built.

Synthetic `:memory:` feasibility testing preserved actual `_price` outputs for five cutoff cases with mixed timestamp formats, late receipts, missing and stale results; matching expression indexes removed the stream sorter in that fixture. This is not qualification for a production index build: tie behavior, malformed timestamp coverage, write overhead, build I/O/lock budget and production-scale performance remain unqualified.

**Next:** separately review and implement the smallest source-time query/performance fix, preserving no-lookahead, exact decimals, provenance and stale/missing behavior; include rollover/discovery latency in acceptance. Do not silently build a production index or extend this exception. I7 remains OPEN. Retention R5/R6 remains STOP; full quick/FK audit outstanding; Phase 2 deferred.

## Evidence and limits

Local evidence: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/i7-scoped-release-20261030/`: exact-CI qualification and test logs, release record, restart journal, helper install/restoration, runner cleanup, five-second monitor/extension, final runtime projection, observation summary, query plans and synthetic feasibility result.

Five-second probes cannot prove continuous absence of sub-sample latency spikes. No new full integrity/FK or invasive lock audit was run. Persisted feature IDs are returned after committed capture; collector live updates follow successful save paths. No additional historical scan was introduced for monitoring. Existing monitor/lifecycle/ensemble behavior was left running. No DB copy/snapshot, retention, VACUUM, manual WAL action, guard increase, infrastructure/firewall/SSH change or Phase 2 work occurred.

## Final runtime follow-up

At02:46:17 UTC, the API still displayed the ended 02:30–02:45 market and Polymarket was stale, while HTTP/dashboard/SSE and Coinbase remained responsive. This end-window projection is preserved separately. At02:46:49 UTC the 02:45–03:00 market was present and both streams were live. `/health` was HTTP 200 but **degraded** with no new market feature snapshot yet. This recovery sample does not erase rollover delay or certify fresh analysis. The normal REST loop still awaits feature completion before its pause/discovery. Current expected service PIDs and zero automatic restarts were confirmed.
