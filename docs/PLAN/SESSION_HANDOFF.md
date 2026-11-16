# Resume here

Read `AGENTS.md` and the active section of
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). The master roadmap is
authoritative; this handoff only points to the current checkpoint. Preserve the
dirty original checkout on `codex/phase1-75-retention-enable`, including all
unrelated edits and secrets. Small reviewed PRs target `preprod`.

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

## Next work

Continue the approved Phase 1.75 plan through small PRs. CP6 is the separately
reviewed additive private Supabase `history_v2` compatibility and bounded
readback qualification. CP7 implements actual read-only Coinbase/Polymarket US
15-minute feeds into PP PostgreSQL, persisted operator mode control, truthful
dashboard labels and the bounded sole-collector PP live run. Do not infer a live
connector from the merged offline translators. Production collector fencing,
production cutover and retirement require their later explicit gates.

CP6's read-only Supabase inventory found ten existing public history tables and
no `history_v2`; two migration ledger entries were counted by catalog query.
The generated private-contract check passed exact CI at `bc3db42` (PR #33),
but actual cloud migration, scoped grants, isolated writes/readback and
mutation-authority qualification remain open. See
[the CP6 review](CP6_SUPABASE_CONTRACT_REVIEW_2026-11-15.md).

Update: the schema-only migration from PR #35 was applied to Supabase as
`history_v2_private_20261116` after exact preprod CI passed. Ten empty private
RLS tables exist; public tables and disabled runtime flags are unchanged.
Scoped grants, runtime writes/readback and Storage authority remain CP6 work.
The historical preprod merge CI failure was addressed by PR #34; its merge CI
passed. Read the [sanitized schema result](evidence/cp6-history-v2-schema-2026-11-16.json).

The default-off private Storage transport candidate is tested with intercepted
HTTP only. It has no PP runtime wiring or retirement authority. Cloud access
and structured sync still require separate qualification.

Keep the selected 72-hour-or-qualified-size A/B generation policy inside
PostgreSQL. Archive verification precedes local retirement. Current PP access
success does not close I7 or Phase 1.75; both remain OPEN. The old SQLite A/B
branch is historical and must not be bulk-merged.
