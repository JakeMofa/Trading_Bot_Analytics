# Independent pipeline checkpoint — November 12, 2026

PR #14 is extracted onto main, excluding the entire unmerged A/B implementation.
PRs #11–#13 are closed/superseded at the user's direction; branches retained.
The preserved original PR14 source is tagged archive/pr14-stacked-2026-11-12.
No merge, production/PP deployment or package publication occurred.

Four named environment workflows, shared CI and manual candidate publication
are prepared. Release assets and a linked GHCR scratch carrier retain source
versions, checksums and provenance for later reviewed code recovery. They do
not contain a DB, install Docker on the VM, implement a PostgreSQL engine, or
certify one-click old-version rollback. Actions evidence expires after 90 days;
published Releases/packages are not automatically pruned by this configuration.

Local results: 67 backend tests, 29 release/transport control tests, dependency
audit and actionlint PASS. The local Docker daemon is unavailable, so the
scratch-carrier build/extract proof is required in exact Linux CI, not claimed
locally. New-source GitHub CI remains pending until push/inspection.

Live GitHub read-only inventory found zero private runners and no environment
deployment secrets; production's owner approval/branch restriction exists.
Targets remain runtime_qualified=false. Actual PP host/controller/PostgreSQL
readiness must be delivered in the next application/runtime milestone. See
[operation and exact binding requirements](../../.github/ci/ENVIRONMENTS.md).

The master roadmap remains authoritative. Production remains at the recorded
legacy SQLite storage hold; no fresh VM inspection or data operation occurred.
I7 and Phase 1.75 remain OPEN. No paid AI, retention, snapshots, manual WAL or
infrastructure changes were made.
