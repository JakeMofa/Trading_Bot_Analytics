# Resume here

Read AGENTS.md, then the active checkpoint in
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). That is the only
authoritative roadmap; this file is an entry point, not a second checklist.

Current work: Phase 1.75 / I7. CP0–5 PASS in generated scope; CP6 next.
Preprod source `a7f7cd0` passed exact CI 43355993076 and deployed as
v0.2.0-pp.2 in CD 43356521535. Four PP containers run, with 32 foundation rows,
21 generated events and 21 predictions preserved. Authority consumed; temporary
runner 28 removed. Live collector/cloud/retirement/paid AI remain OFF.

Operator dashboard/API/SSE access passed through pinned SSH to the dynamically
resolved private API container IP. The configured localhost:8000 publication is
UNAVAILABLE on the internal-only bridge; do not document it as working or loosen
network isolation. Read the verified README route and latest CP5 evidence.
The pp.1 Python-setup failure is preserved; it did not invoke the host controller.

Next is CP6 actual Supabase compatibility with its reviewed migration/permission
and bounded cloud-write scope. CP7 live/capacity, CP8 production candidate, CP9
approved cutover and CP10 verified retirement/acceptance remain open. No production
change or cloud activation is authorized by the generated PP deployment pass.
The master plan now specifies the requested temporary PP live rehearsal: first
qualify stable private API access and real PostgreSQL feed/query paths, explicitly
fence production, run PP as the sole collector across a market boundary and a
qualified A/B switch, then stop and fence PP collection while leaving its API
up. Production later uses its own database/collector; PP preview reads the
production API/SSE, never production's database directly.
The user also selected a visible PP mode switch: isolated test, sole-collector
live rehearsal, then read-only production preview. Implement a private
authenticated operator control with durable ownership fencing and restart-safe
OFF, and show the source/mode on the dashboard. Do not interpret the existing
generated-only deployment as a working live collector or production mirror.
Selected PP setting has three modes: `isolated`, `pp_live`, and later
`production_preview`. It selects a labelled dashboard source and, only with
operator authority and a sole-collector fence, controls PP intake. It never
points PP at the production database. Test subsets stay separately identified.

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
