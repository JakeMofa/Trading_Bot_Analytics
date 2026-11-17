# Resume here

Read `AGENTS.md` and the active section of
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). The master roadmap is
authoritative; this handoff only points to the current checkpoint. Preserve the
dirty original checkout on `codex/phase1-75-retention-enable`, including all
unrelated edits and secrets. Small reviewed PRs target `preprod`.

PR #52 merged a separate loopback-bound PP operator status/OFF service; merged
source `a11d922` passed exact CI 44022560772. An explicit PP token-preparation
attempt stopped before writing because the existing application's host marker
is correctly `application_installed=true`. The narrowly scoped runtime
preflight correction is under review. No operator process or token is installed,
and PP collection remains OFF.

## Current PP checkpoint — November 15, 2026

The private PP API route is **PASS in generated-only scope**. Source `b50861d`
passed [exact CI 43765914993](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43765914993),
published as `v0.2.0-pp.3`, and passed
[CD 43766281486](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43766281486).
The installed controller hash is `d66518ce...`; its dedicated-key identity run
43765449362 passed. An approved operator SSH tunnel to PP host
`127.0.0.1:8000` returned HTTP 200 for dashboard, state, health, local history
and SSE. The prior dynamic-container-IP tunnel is historical. Read the
[sanitized acceptance result](evidence/pp-loopback-acceptance-2026-11-15.json).

PP runs four Compose services and local PostgreSQL. Its application remains in
generated mode; live collector, cloud archival/retirement, paid AI and trading
are OFF. The temporary runner deregistered and one-use authority is gone.
Production was not changed or freshly audited by this release.

## Current work — November 15 CST / November 16 UTC

CP6's additive private `history_v2` schema was applied as
`history_v2_private_20261116`; see the
[sanitized schema result](evidence/cp6-history-v2-schema-2026-11-16.json).
PRs #37 and #38 added default-off bounded private Storage requests and strict
structured-outbox envelope validation. PR #41 separated the Storage project
key from its bearer token after confirming that privileged service keys bypass
Storage RLS. No cloud runtime is connected. A read-only catalog check found no
`history_v2` runtime grants and no `storage.objects` policies. Scoped identity,
reviewed allow/deny tests, actual isolated write/readback, mutable projection
ordering and privileged mutation protection remain CP6 gates.

CP7 PR #39 added default-off bounded Coinbase ticker and Polymarket US 15-minute
market source clients. PR #40 requires the durable collector-enabled flag for
any future `pp_live` ingest. PR #42 added an idempotent stop transaction and a
generated PostgreSQL lock-handoff test. All five PRs merged into `preprod`;
latest source `a0e2678` passed
[preprod CI 43813105666](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43813105666).
These changes were not deployed to PP. They do not enable collection.

**Continue with:** the restricted authenticated PP operator control, real
source/market-boundary integration and cross-VM
sole-collector fence. CP6 cloud identity/grants and actual readback must pass
before archival/retirement is enabled. Keep PP generated-only, production
legacy SQLite held, and retirement/paid AI OFF until their separate gates.

November 16 CP7 progress: PRs #45-#49 merged into `preprod`. The default-off
source bridge, generated PostgreSQL write/read/stop qualification, unstarted
authenticated status/OFF operator surface, and prepared-OFF `pp_live` origin
configuration and bounded closed Coinbase candles passed their PR CI and
preprod merge CI. PR #50 added a supervised, bounded coordinator with
independent source tasks, one-second durable-flag/owner checks and a required
durable-OFF callback; its exact preprod CI 44018709047 passed. None was
deployed to PP or enables a live collector. The next candidate makes the
status/OFF operator API a separate process with file-mounted credentials, but
it has no Compose binding or ON route. Qualify host-bound operator control and
the cross-VM fence before any bounded live run. PP remains generated-only and
production is unchanged.

Keep the selected 72-hour-or-qualified-size A/B generation policy inside
PostgreSQL. Archive verification precedes local retirement. Current PP access
success does not close I7 or Phase 1.75; both remain OPEN. The old SQLite A/B
branch is historical and must not be bulk-merged.
