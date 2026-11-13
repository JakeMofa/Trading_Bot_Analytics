# Resume here

Read AGENTS.md, then the active checkpoint in
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). That is the only
authoritative roadmap; this file is an entry point, not a second checklist.

Current work: Phase 1.75 / I7, CP5. CP0–1 foundation and CP2–4 generated
source qualification passed. PRs #17/#22 merged into preprod `d59cd1e`, exact
CI 43353905598 PASS. Actual PP controller/SSH/roles are qualified.

Candidate v0.2.0-pp.1 published, but CD 43354829263 failed at the Mac runner's
Python installer before invoking the host controller. PP application/migrations
were NOT executed. Unused root authority revoked; ephemeral runner 27 removed.
The tested fix `e4b28bb` uses existing Python 3.12. Continue its small PR, require
exact successor CI, then publish a new immutable PP candidate and prepare fresh
one-use authority for the corrected generated-only attempt. Preserve the failed
attempt. Do not reinstall qualified roles/helpers unnecessarily. Read the latest
CP5 master entry and procedure before dispatch. Production remains untouched.

The original working checkout is dirty on codex/phase1-75-retention-enable.
Preserve its AGENTS.md, roadmap additions and every unrelated edit. Do not merge
the superseded SQLite A/B branch wholesale. Current foundation changes are based
on reviewed main/preprod, isolated from that checkout. Do not expose credentials.

Implement small PRs targeting preprod. Production remains unchanged until CP9's
explicit approval. CP2 schema, CP3 app, CP4 lifecycle/history, CP5 CD, CP6 cloud,
CP7 live/capacity, CP8 exact release, CP9 cutover and CP10 acceptance are distinct.
No production/Supabase mutation, real collector, paid AI or retention is enabled
by the foundation milestone. The selected A/B contract is 72-hour-or-qualified-
size rotation inside PostgreSQL, with verified archive before local retirement.
