# Resume here

Read AGENTS.md, then the active checkpoint in
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). That is the only
authoritative roadmap; this file is an entry point, not a second checklist.

Current work: Phase 1.75 / I7. PostgreSQL CP0–1 passed within foundation scope;
**CP2–5 source components PRs #18–#21 are merged into the integration branch.
Final controller source `deb8f0d` passed exact Linux CI 43351324325, including
real Docker/PostgreSQL/API recovery and root SSH permissions. PR #17 targets
preprod and needs its combined exact CI. Next is actual PP helper/identity/runner
binding and the manual generated deployment; those are not yet performed.
Read the master's current checkpoint and ownership table.** PR #15 aligned reviewed main
workflows/docs into preprod (`15475f7`); foundation source `40c2761` passed exact Linux CI 43340827516 and PP execution.
Check the newest foundation PR, exact CI and host evidence before treating that
statement as current. Docker/PostgreSQL alone do not qualify app or CD.

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
