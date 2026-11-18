# Resume here

Latest CP6 permission checkpoint (November 18 UTC): PR #98 merged to
`preprod` as `2c6ffd2` and its exact PP-only NOLOGIN `history_v2` role was
applied to Supabase as migration `20261118021900`. Catalog readback passed.
This does **not** enable PP cloud writes, raw Storage access, local retirement,
or a production change. Draft PRs #92/#97 still need runtime/cloud
qualification. CP7 Coinbase reconnect and generated leave fixes are merged
in source but undeployed to PP; its last observed collector state was
generated/OFF after the failed diagnostic trial. Follow the opening master
roadmap section for exact evidence and next gates.

The November 17 opening section of the master roadmap now distinguishes the
**selected** PP modes from what is deployed. PP normally should preview the
production API, switch temporarily to its own live collector/PostgreSQL for a
bounded test, then return to preview; no production pause is needed. Today PP
has one `tradebot_pp` database and generated-only dashboard, not the separate
experiment database or production-preview route. PP cloud sync/retirement are
OFF. Audit actual production/Supabase coverage before claiming recent data is
complete; the last recorded production collector state was storage-held.

CP7 policy correction (November 17): PP and production may independently read
the read-only market feeds into their separate databases. Do not stop or change
production for a PP live trial. Qualify one leased collector per **PP database**,
the private ON/OFF host process control, bounded request cadence and truthful
source health first. The master roadmap's opening section supersedes older
cross-VM sole-collector language below. Production cutover still requires its
own old-writer fence. PP remains live-collector OFF as of the pp.7 release.

Current CP7 runtime (November 17): `preprod` source `4eea47b` passed exact
CI 44166604082 and was deployed as `v0.2.0-pp.7` in manual CD 44167381155.
Migration 0002 and generated-only acceptance passed. PP has five running
services; collector, cloud sync, retirement and paid AI remain OFF. The one-use
authority was consumed and the ephemeral runner unregistered. The pp.6 package
mentioned below is historical and was never deployed. Next qualify the host
ON/OFF path and cross-VM production fence before any bounded PP live run.
The master roadmap and sanitized deployment artifact have exact evidence.

Current CP7 checkpoint (November 17): PR #60 merged at `e849794`; exact CI
passed. Generated-only `v0.2.0-pp.6` is published but **not deployed**. PP still
runs `v0.2.0-pp.5` and has no lease migration 0002. The installed controller
matches the candidate, but the approved ephemeral private GitHub runner is
absent; no one-use host authority was created. Restore that runner, then run
the exact manual PP release and bounded acceptance. Do not activate PP live
collection until the host ON/OFF path and cross-VM production fence pass.
The master roadmap has the exact SHA, run links and remaining gates.

Read `AGENTS.md` and the active section of
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). The master roadmap is
authoritative; this handoff only points to the current checkpoint. Preserve the
dirty original checkout on `codex/phase1-75-retention-enable`, including all
unrelated edits and secrets. Small reviewed PRs target `preprod`.

PR #52 merged a separate loopback-bound PP operator status/OFF service; merged
source `a11d922` passed exact CI 44022560772. The first explicit token
preparation stopped before writing because the existing PP marker correctly
said `application_installed=true`. PR #53 fixed that narrow preflight and
merged as `989f461`; exact preprod CI
44024202007 passed. The explicit token preparation and controller installation
passed on PP, followed by dedicated identity run 44024832718 PASS. The
operator service was not deployed at that binding checkpoint. See the sanitized binding in
`docs/PLAN/evidence/pp-operator-controller-binding-2026-11-17.json`.

PP release `v0.2.0-pp.4` in CD 44026013400 **failed** at the GitHub-side
acceptance check after the host controller passed and started the operator
container. PP now has five running containers. Authenticated operator status
reports collection OFF; unauthenticated access is denied. Do not call this
release PASS. The authority was consumed. A PP-only acceptance-check
correction was required; production remained unchanged.

That correction merged as `e907022`, exact CI 44026918955 PASS. Version
`v0.2.0-pp.5` passed manual CD 44027443677 in generated-only scope. PP now
runs five services; private API and authenticated operator status respond,
but collection, cloud sync, retirement and paid AI remain OFF. The one-use
authority and temporary runner are gone. See
`docs/PLAN/evidence/pp-operator-release-2026-11-17.json`. Continue CP7 with
the cross-VM sole-collector fence and bounded ON/OFF session control before
any live PP feed run. Production is unchanged.

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
