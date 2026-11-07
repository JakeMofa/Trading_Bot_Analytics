# Database checks before, during and after release

Scope: PR/offline qualification is automatic; production verification and cutover
are separate reviewed operations. No PR job reads a production database, opens a
live Supabase session or applies cloud DDL. These are coverage claims, not a
deployment approval. Production A/B/core acceptance remains BLOCKED.

## Before deployment: PR/offline

| Area | Executed coverage / evidence | Limits and remaining gate |
| --- | --- | --- |
| SQLite generated predecessor schemas | `test_ab_application`, `test_recovery_bootstrap`, `test_selected_recovery`, `test_ab_data_validation`, `test_ab_fresh_b`; backend and privileged `test` jobs | Known generated supported layouts, not arbitrary historical schemas or production bytes |
| Migration/bootstrap/restart/partial failure | Existing migration/crash/recovery suites; `ab-import-report` and bounded integrated qualification | Existing byte/RAM/deadline caps retained; full production volume/runway not certified |
| References and exact data | Direct legacy FKs, unknown/missing dependency rejection, original payload/ID/decimal tests; application store and recovery suites | Cross-file evidence needs explicit application verification; SQLite FK checks alone cannot certify it |
| Generated A/B/core and retained legacy | Existing root descriptor, writer/read-lease, rotation, cutover, joint API/SSE, fresh-B and exact-export tests | Generated qualification does not establish a production multi-file controller |
| Archive legacy/wire/checkpoints | `test_ab_cloud_compatibility`, namespace and archive/recovery suites; actual HTTP adapter with MockTransport | Real adapter code, synthetic responses; no live REST/auth/bucket permission or drift proof |
| Reviewed Postgres SQL | **Isolated Postgres schema compatibility** job applies all three unchanged `supabase/schema/*.sql` files, repeats them, upgrades generated pre-source-ID manifests and preserves checkpoints | PostgreSQL 17.6 pinned image; Supabase roles and `storage.buckets` are minimal fixtures, not Supabase Auth/Storage/PostgREST services |
| Postgres integrity/access | Exact NUMERIC value, FK/duplicate rejection, failure rollback/retry, private bucket flags, RLS enabled, anon/authenticated denied, service-role CRUD characterized | Source DDL permits service-role mutations; no immutable object/manifest fence is established; no actual deployed role identity checked |
| SQLite news migration | Existing application tests exercise application initialization; separate news SQL file is not applied to Postgres | It is SQLite application DDL, not a Supabase migration |
| Supply chain | Actual requirements pip-audit, static/workflow/source checks | Vulnerability or unavailable audit blocks readiness; no exemptions |

The new Postgres job uses a network-disabled Docker container, no published host
port or mounted host data, generated roles only, one CPU, 512 MiB container RAM,
256 MiB data tmpfs, 8 MiB socket tmpfs, 128 PIDs. Pull is capped at 120s; tests at
150s; job at five minutes. Normal and always-run cleanup remove only the job's
unique generated instance. Schema SHA-256s, source/tested SHAs, test counts,
skips and elapsed time are in `ci-postgres-<tested-sha>`; missing/failed evidence
blocks `PR readiness`. This is a small compatibility workload, not a capacity test.

## During deployment: current release controls versus missing A/B route

| Gate | Existing implementation | A/B/core + retained legacy status / owner action |
| --- | --- | --- |
| Exact release/source binding | `verify_ci.py`: full dispatch SHA equals approved deployment-branch HEAD and successful exact push `python-tests.yml`; reviewed bundle/helper hashes and one-use verification evidence | Preserve unchanged. A different branch's success or synthetic PR merge is insufficient |
| Preflight/schema identity | `preflight.py` pins `SQLITE_DB_PATH=data/btc_intelligence.db`; `release_verification.py` binds device/inode/schema version/catalog hash and rechecks identity | **Legacy single-path route.** Storage owner must bind actual retained legacy, core and both slots, sidecars and selected recovery identities after fencing |
| Complete SQLite integrity | Read-only quick_check/FK, bounded child, persisted check progress and reaping in release verification tests | Checks one legacy file. Storage owner must cover every actual retained/created file plus explicit cross-file dependencies under reviewed deadlines |
| Sole collector/service ownership | `deploy.py:services`, process/service identity checks, competing collector rejection | Existing legacy checks; qualify A/B-specific writer authority, quiescence, reader/worker drainage, post-fence identity and activation order |
| Disk and memory | Runtime preflight checks >2 GiB free; `maintenance_host.py:allocation` sums legacy main+WAL logical bytes against 5120 MiB | **Not aggregate A/B capacity.** No complete runtime RSS/memory gate here. Storage owner must bound core/A/B/legacy/WAL/SHM/work/TEMP/recovery/held descriptors together and qualify RAM/space/time margins |
| Failure/rollback | Existing code rollback, smoke failure handling, service restoration, interruption/reaping/one-use evidence tests | Legacy code rollback does not reverse A/B migration or prove multi-file crash recovery. Storage owner must supply approved whole-layout recovery/rollback policy |
| Supabase during cutover | No PR/live schema mutation added | Live catalog/grant/bucket/source/checkpoint drift and authenticated probes NOT PERFORMED. Separate reviewed read-only scope required; DDL/permission changes require their own approved scope |

`deploy-tradebot.yml` remains manual-only for production operations and restricted
to `codex/lightsail-deployment`. Its validating push trigger does not run production.
No new dispatcher, host helper, database migration or resource-policy change is
introduced by this CI work. Existing I7/scoped exception code is not a generic
A/B production acceptance route and must not silently substitute for full checks.

## After deployment: required bounded acceptance

| Gate | Existing evidence/implementation | Remaining production requirement |
| --- | --- | --- |
| Functional smoke | Existing `smoke.py` checks health/state/forecasts/models/cloud status, dashboard/history and SSE, freshness/market identity and sanitized responses; control tests are offline | Run reviewed smoke on actual accepted layout, prove source persistence advances, truthful API/history and stable sole-owner services; NOT PERFORMED here |
| Persistence/integrity/identity | Legacy release verification/persistence probes and generated A/B restart/replay tests | Actual core/A/B/retained-legacy identity, exact cross-file references, allocation and memory after activation; storage-owner gate |
| Archive-backed application history | New base `cc06c01` adds API/helper replay and privileged wrapper in `test_ab_application` | Requires fresh Linux root/source/PR evidence. Existing 42f207c results predate it. A/B-only replay does not prove eventual removed-legacy retrieval |
| First natural seal and retirement | Generated readback/corruption/drain tests only | Separate bounded first-seal verification, then separately recorded retirement enablement. Effective mutation/policy fence and fresh authority must be qualified; no enablement here |
| Sustained capacity/recovery | Existing finite synthetic profiles and timers/control tests | Representative runtime aggregate envelope, outage runway, full legacy verification/recovery and sustained real rollover remain open |

## Current source and merge sequence

Completed source `42f207c7a4ca956278d30f8a8b9fc80e7278b9a6`:
[push 42325464188](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42325464188),
[PR 42325468395](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42325468395).
Controls, quality, application, backend/root/joint and integrated jobs PASS;
dependency audit FAIL for cryptography 46.0.7; readiness BLOCKED as designed.
No independent latest joint-handoff bug was identified on that source.

Storage owner applied the reviewed 50.0.0 dependency patch in `4c673bf`, then pushed
new application/reconciliation source `cc06c01`, followed by packaging fix
`0cef90a6eb2f6fdc1784e6e2deeab431709f3578` (isolated helper uses `-I -B` to
preserve exact exports). Refresh this CI branch from that final base; require fresh exact-source push and PR checks, including the new Postgres
job and privileged application replay test. PR #10 stays a CI-only diff against
the working branch; review it there before separately considering PR #9's full
storage/release gates. Do not merge either PR based on older checks. Enable branch
requirements only after the final stable checks have passing evidence. No merge,
production dispatch or live Supabase probe is authorized/performed here.

References: [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Postgres RLS/bypass semantics](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
The current Supabase changelog was reviewed; no Supabase CLI/SDK is invoked or
upgraded by this isolated SQL-engine job.
