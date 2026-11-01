# Authorized single quiescent maintenance attempt

Authorization: user's attached maintenance instruction, followed by continuation.
No second approval is needed for this exact scope. One attempt only, no retry.
Old runtime d56b4a7; application blobs pinned to fd90458. New candidate must have
exact CI before any installation or writer-stop. No concurrent-write proof reuse.

Budget state machine: complete verification <=1800s, all other maintenance <=600s,
verification reap <=10s, recovery reserved180s. Absolute interruption2590s from
first stop request, never reset. The50minute manual Actions job permits setup and
reporting but cannot extend controller deadlines. Commands reserve reaping inside
caller allocations. Verification reserves10s for reap inside its step allocation;
this conservatively shortens possible SQL work, never extends the30minute ceiling.

Operator preflight BEFORE helper install: exact CI/runtime, clean tracked checkout,
private binding, sole collector, flagsOFF, services active, cap5120, free disk and
cap deadline; main-file-only maximum possible headroom must still be>=128MiB.
A failure here leaves production untouched. Do not proceed if the paused physical
headroom can no longer possibly pass; do not wait for a more favorable sample.

After exact CI and preflight, preserve existing protected helper CODE in a private
root-owned directory (no configuration/database copy), recording mode/SHA256.
Install exactly deploy.py, release_verification.py, smoke.py,
maintenance_controller.py, maintenance_host.py from the qualified candidate.
Record original absent helpers as null. Create root0600 authorization at
/run/tradebot-maintenance-release.json with approval_confirmed=true, full release,
old=d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a, exact ci_run, expires_at no more than
one hour away and before the cap deadline; helpers maps the five filenames to
installed SHA256; original_helpers maps each to null or {path,sha256,mode}.
Policy must equal {verify:1800,other:600,reap:10,recovery:180,interruption:2590,
headroom_mib:128,ceiling_mib:5120}. No credential values enter reports or GitHub.

Use existing manual deploy-tradebot.yml, existing deployment branch/private runner,
revision=qualified candidate, operation=maintenance. No SSH/firewall/infra changes.
Helper checks bundle ancestry and pinned application blobs. Authorization is
consumed before monitor/writer stops. Record monitor states; pause active timer
and oneshot. Record active writer states and stop API, ensemble, lifecycle. Any
partial stop enters recovery. Refuse all unexplained DB/WAL/SHM descriptors; signal
none. Allow only SQLite's ordinary last-connection close. Measure real physical
allocation; <128MiB headroom means restore services and STOP, not another attempt.

Run complete quick/FK in one owned read-only child, reaping on timeout/interruption.
Keep all writers stopped; bind release/runtime/helper/database/schema/configuration
identities before/after checks, require no owners again, then exact checkout.
Restore active services and monitor. One bounded functional smoke uses fresh source
and current market identity, advancing RAM/persistence, full dashboard/SSE/API
routes, OFF flags, revision/service/ceiling checks. Explicit feature unavailable/
stale diagnostics are allowed; stale source data and expired market identity are
not. Startup transport readiness is bounded, not an extra observation session.

Before checkout failure: no code change, restore every active writer even if one
start fails. After partial checkout/failure: stop known writers, bounded old-code
checkout when safe, restore every active writer. Never restore DB contents.
Failure remains failed after recovery. Record helper restoration PASS/FAILED; try
all helper restorations even if one fails. Only original helper CODE is restored;
new temporary helper code absent beforehand is removed. Preserve phase records.

No20minute observation, polling soak or background monitor task. Multi-cycle and
real-boundary acceptance NOT PERFORMED. Record receipt gaps, not claimed backfill.
No retention/paidAI, deletion, copy/snapshot, VACUUM, manualWAL, index, guard increase
or Phase2. Deadline2026-11-02T01:56:47.671426Z unchanged; preflight requires enough
remaining time for the absolute interruption ceiling. Phase1.75/I7 OPEN.

User-approved amendment2026-11-01:128MiB applies only to this one-use quiescent
route and pinned rollover application. Normal/live512MiB policy unchanged;5120MiB
ceiling,physical accounting,verification/recovery/interruption limits unchanged.
Fresh capacity/deadline failures stop before installation/authority/dispatch.
