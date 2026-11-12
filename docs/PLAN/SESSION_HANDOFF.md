# Tradebot continuation — November 12, 2026

Read AGENTS.md and the current execution checkpoint in
INTELLIGENCE_REBUILD_PLAN.md first. That document is authoritative.

The active branch/PR is codex/pr9-release-controls / #14, independently based
on main; despite the historical branch name, its new tree contains no SQLite
A/B implementation. PRs #11–#13 are closed/superseded, branches retained. Their
work must not be merged into this pipeline change. The old PR14 source is
preserved by archive/pr14-stacked-2026-11-12. The original local checkout stays
codex/phase1-75-retention-enable at 0204901; unrelated AGENTS/roadmap/local data
edits are intentionally uncommitted. Never reset or overwrite them.

User will merge PR14 after exact CI; do not merge or deploy production on their
behalf. New pipelines are definitions and fail-closed controls, not evidence of
PP installation. GitHub has no registered private runner or environment deploy
keys at the latest bounded inventory. Runtime profiles are unqualified. No
released package/version has been published by this checkpoint. CI on the new
independent source remains required; inspect once, do not poll.

PP: tradebot-preprod-01, us-east-2a, 2 GiB / 60 GB, last known public IP
18.119.253.233 (not static), private 172.26.11.9. Host baseline passed earlier;
PostgreSQL and app are not installed/qualified. Production remains the separate
tradebot-analytics-01 at 3.13.133.25, last recorded deployed d56b4a7, legacy
storage guard 5120 MiB, feeds held, retention/paid AI OFF. These are recorded VM
findings, not fresh measurements from the PR rewrite. AWS help preference HIGH.

Next application work: small PostgreSQL PP PRs with isolated test data, exact
decimals/source timestamps/provenance, one real collector, explicit structured
Supabase sync and verified raw archives. No production data sharing for writable
migration tests. New PostgreSQL migrations must add real isolated compatibility,
forward recovery and application contract tests; the baseline SQLite CI does
not certify PostgreSQL or live Supabase.

Guide: .github/ci/ENVIRONMENTS.md. Releases/packages publish manually from main
controls, including preprod candidates. Source bundle is a scratch registry
carrier, not a runnable app image; Docker is used on hosted CI, not installed on
VMs by this PR. Main promotion requires exact main source to pass PP again.
Rollback candidates remain in the registry/Releases, but applying old code
requires reviewed schema compatibility and current acceptance. Database contents
are never restored by code rollback. Production migration/legacy retirement,
retention, paid AI and Phase2 remain separately gated.
