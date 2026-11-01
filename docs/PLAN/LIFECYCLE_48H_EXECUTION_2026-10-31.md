# 48-hour lifecycle execution evidence — October31,2026

The official roadmap remains `INTELLIGENCE_REBUILD_PLAN.md`. This report records
execution evidence and gates; it does not establish completion of Phase1.75.

## Authorized bridge: PASS

- Exact helper commit`8187465a0af3965f0f1d811621710afc3358ef70`,
  [CI41263032555](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41263032555) PASS.
- Helper SHA256`d35433333d91a205d6f56169b22532679faea9c06a177e5a4cb237ed5cd2eafa` exported from that commit and verified on VM.
- Changed only the literal guard4096->5120. Configuration bytes/owner/mode preserved
  except that value; no retained configuration backup or credentials in evidence.
- Applied **2026-11-01T01:56:47.671426+00:00 UTC /2026-10-31T20:56:47.671426-05:00 Chicago**.
- API restart returned in~0.393s; no application checkout. API PID10915->17165;
  ensemble849/lifecycle843 and monitoring unchanged; zero automatic restarts.
- Passed **300.007s continuous observation**,
  114 samples total, one reset due the existing rollover
  delay. Both feeds/live timestamps, current market, private API, dashboard/SSE
  verified. Source collection resumed; previous gap is not assumed backfilled.
- Actual runtime guard5120, application`d56b4a7`, paid AI/retention OFF,
  paid credentials absent. DB4,283,228,160/WAL18,160,992 bytes at02:06:48UTC.
- Review due **2026-11-02T01:56:47.671426+00:00 UTC /2026-11-01T19:56:47.671426-06:00 Chicago**. Deadline uses UTC across
  the daylight-saving transition. This is a review deadline, not automatic limit
  reversion. Ceiling remains5120 and is not permanent until the24h soak passes.

## Retention candidate: local tests, Linux qualification pending

The candidate replaces Python manifest-envelope arrays/sorting with current SQL
range counts and bounded joins to TEMP exact approved identities. A TEMP indexed
cache holds only pure validity of exact strings, prepared outside the writer lock.
Fresh global scans of both raw tables find/validate unseen timestamp strings.
Range coverage, references, anchor and eligibility are still checked under the
same BEGIN IMMEDIATE as DELETE. No broad-range deletion or weakened archive proof.

New writer target250ms, deadline500ms, measured including commit. Interruption
before commit rolls back; a commit overrun records committed_rows and stops later
batches rather than falsely claiming those rows were rolled back. TEMP bookkeeping
and100ms handoff occur outside the main writer transaction. Qualification will use
1000-row batches; collector busy timeout remains5000ms.

Local validation: **194 backend tests PASS (one Linux-only harness self-test skipped
on Mac),51 deployment/control tests PASS**, compile/diff PASS. Existing archive,
mutation, new-identity, timestamp and late-reference tests pass. Deadline tests
cover rollback and the distinction between a completed commit and rollback.

`backend/qualify_retention_sql.py` accepts only generated fixtures, not a DB copy.
It loads actual deployed save/RAM code and verifies its SHA on production-guarded
runs. Actual last-rowid point lookups gave cardinality upper bounds578343
observations/1684881 stream events; they are not full row counts. Generated trials
use that global scale plus the previously qualified40031/196509 eligible-identity
scale. Passing this profile alone will not qualify a larger cleanup plan.

Each Linux trial:180s total (170s work +10s cleanup),512MiB address-space limit per
process,2GiB aggregate generated/TEMP disk guard, actual save every150ms and50ms
heartbeat. Production HTTP probes every5s; unexpected stopped/degraded feeds or
API timeout abort the fixture test. Stop after the first failed gate. Three full
successful trials required; warm-cache Mac benchmarks are not R5/R6 PASS.
Synthetic manifest claims are performance fixtures, not cloud verification.

## Remaining gates

R5/R6 remains STOP until actual Linux qualification passes. No production retention,
DELETE, schema/index change, full integrity/FK scan, archive recovery proof or
application release has occurred. Then follow the approved order: archive/readback
and full audit, exact raw-row recovery manifest, controlled<=1000-row first cleanup,
qualified indexes/freshness release, lifecycle-only enablement and24h soak.

No DB copies/snapshots, VACUUM, manual WAL, new resources/network changes, paid AI or
Phase2. Local evidence: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/`.
