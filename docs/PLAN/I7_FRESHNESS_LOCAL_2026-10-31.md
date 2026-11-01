# I7 freshness and rollover — local implementation, not deployed

October 31, 2026. The authoritative roadmap remains `INTELLIGENCE_REBUILD_PLAN.md`.
Production's last verified release is the October 30 worker containment `d56b4a7`.
No production measurement or change was made for this local milestone. I7 is OPEN.

## Implemented plan

1. Make price ordering explicit and indexable, preserving `julianday` comparisons,
   received-at cutoff, exact Decimal values, input IDs and stale/missing behavior.
2. Run feature work serially in a separate loop, with a 15-second pause after each
   completed cycle. Keep REST discovery and external request cadence unchanged.
3. Publish only results <=30 seconds old for the same currently active market.
   Keep historical captures; reject expired/changed-market/future/over-age RAM
   publications. Cancellation drains the single SQLite owner even after repeated
   cancellation, and never publishes its result during shutdown.
4. Prepare explicit indexes and measure cost on generated data. Never build them
   automatically on startup or through the previous release exception.
5. Qualify a bounded production schema operation before deployment, then repeat
   multi-cycle, >=20-minute and market-boundary validation.

## Local behavior and compatibility

Feature version **2** defines equal-source-time ties: smallest `event_id` TEXT key
for stream rows, smallest numeric `id` for REST rows; stream still wins an equal
instant across sources. Version 1's SQL specified no within-source tie rule.
This intentional clarification is versioned, not presented as guaranteed identical
historical tie provenance. Existing version-1 snapshots remain intact.

The optional index preparation module is not imported by startup. It requires an
explicit caller transaction and refuses an existing same-name index with different
SQL. Both partial indexes restrict to Coinbase, with keys
`(source, julianday(source_time) DESC, input_key ASC)`. Tests with the actual stream
NOT NULL schema rejected an earlier redundant partial predicate that the local
planner did not select; current plans eliminate both temporary ORDER BY sorts.
No forced INDEXED BY or production ANALYZE was introduced.

REST and feature loops are independently supervised within the existing sole
collector. Only one feature cycle may run at a time; no task backlog or overlapping
worker is created. The 15-second pause does not promise 15-second runtime: meeting
snapshot age <=30s still requires a fast lookup and production validation.
The new `feature_supervisor` feed-health entry exposes running/error/stopped state.
No paid calls, source polling increase, trading endpoint or API route was added.

This does not clear an already-published snapshot when it later ages; its `as_of`
remains visible. It does not redesign all RAM baseline freshness checks or remove
startup hydration cost. Market discovery still has its own network/REST timing;
the change removes its wait on the feature calculation, not every possible delay.

## Synthetic cost evidence

Generated temporary fixtures only; **no database copies or snapshots** and no
production database opened. Run `backend/benchmark_feature_prices.py --rows N`;
it accepts no existing database path and cleans up its generated fixture.

| Rows per price table | Median lookup before / after | Index page growth | Build time |
|---|---|---|---|
| 100,000 | 0.07650s / 0.0000123s | 6,144,000 bytes | 0.1064s |
| 1,000,000 | 0.88939s / 0.0000126s | 63,275,008 bytes | 1.2827s |

Outputs matched with/without indexes. The concurrent writer got SQLITE_BUSY after
its ~60ms probe budget while the schema transaction was held; writing resumed
when it committed. That timeout is not a production lock-duration estimate. These
are local warm-cache numbers on generated rows, not cold VM measurements or a
production performance guarantee. The benchmark measures both indexes together.

Local evidence directory:
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/i7-freshness-local-20261031/`.

## Release gate — still unresolved

- Refresh actual VM storage/guard headroom; quantify both index growth, temporary
  build space/WAL, normal collection growth and increased feature/prediction rows
  from the faster cadence. The old ~232MiB headroom is historical, not current.
- Qualify build I/O and writer exclusion against an explicit interruption budget;
  decide rollback/abort handling before changing production. No live CREATE INDEX
  now, no generic skip-check flag and no reuse of the consumed I7 exception.
- Full quick/FK audit remains outstanding before retention; R5/R6 remains STOP.
- Do not deploy scheduler alone expecting fast features without the qualified
  indexes: slow results will be rejected by the new publication age gate.
- Retention and paid AI OFF; guard4096 unchanged. No production restart, network or
  infrastructure changes, historical live scan, VACUUM, manual WAL action or Phase2.

## Validation

189 backend tests and33 deployment/control tests PASS; compile and diff checks PASS.
Seven new regressions cover query equivalence and deterministic ties, no automatic
index creation, transaction/definition refusal, publication boundaries, independent
REST progress,15-second scheduling and repeated-cancellation draining. Existing
real WAL reader/collector-write coexistence test now exercises the feature loop.
Exact-commit CI is required before any release; current milestone is local only.
