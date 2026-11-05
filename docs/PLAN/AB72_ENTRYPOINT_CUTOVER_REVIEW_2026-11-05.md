# A/B entrypoint integration and cutover review — November 5

**Review candidate, not production authority.** Source
`636166091cac236c881777d7af68382fbc4c0cd9`, continued from ec5f396.
Initial exact Linux CI: [41994499331](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41994499331).
FAILED at the generated UID-fence rehearsal; exported backend and root raw/application/runtime suites passed. Corrected successor identity-fence rehearsal requires its own exact CI. Production remains
on the held legacy layout; this work did not access or mutate production.

## Scope and entrypoints

Existing working branch `codex/phase1-75-retention-enable`; intended existing PR
base `codex/lightsail-deployment`, observed base
`78bcaf07baac8ba5f26a6c7dd827c35283511f30`. No new worktree/branch.
The branch comparison contains historical retention/operator work as well as A/B
changes. It is an integration review, not a three-file rollover deployment. The
existing application-only deployment route cannot be reused for this release.

| Path | Implemented behavior | Remaining production gate |
|---|---|---|
| `api.create_app` / `streaming.run_locked` | Explicit default-off runtime opens one collector; worker factories route REST/features; read-only API startup uses history role | Generated path/volume guards intentionally reject real production |
| API history, chart, `/system/status` | Core structured history; ack-filtered legacy/raw/protected views; active slot/generation from registry | Actual-volume query latency and complete legacy evidence audit |
| Feature/baseline and ensemble process | Worker-owned connection, no collector/raw write authority; existing independent discovery/one serial feature worker | Production freshness remains unvalidated |
| Lifecycle CLI and `LifecycleWorker` | Core-bound role; sealed token wakes incremental archive rather than waiting hourly; same complete cloud-operation deadline retained | Real manifest/checkpoint writes under lifecycle identity not newly authorized/tested live |
| Lifecycle retirement capability | Separate default-off flag; exact authenticated archive coverage, protected body preservation, durable draining, process leases and Linux FD proof | Reviewed production privilege/visibility route and separate enablement approval |

A/B alternate by maximum72-hour active age or earlier size trigger. There is no
second72-hour waiting period. New slot reuse gets a fresh UUID. Draining hides raw
from new attachments but preserves copied prediction/current input evidence in
core. Existing readers retain a shared process lease. Retirement takes an exclusive
lease, revalidates protected bodies against exact sealed rows under a core write
transaction, and requires complete descriptor visibility. Unknown visibility holds.
Only SQLite normal last-close cleanup is used; sidecars are never manually removed.

## Tests and failure coverage

Local Python3.13/macOS backend357 tests PASS/14 skips, controls120 PASS/3 skips.
Focused runtime8 PASS/1 skip. Backend final run29.843s. The final read-only API-role
change and root-only cutover timing output are additionally subject to exact CI.
Skipped Linux root/descriptor/process cases are NOT local passes; platform and
native artifact behavior are covered only by their named Linux CI steps. Existing
Starlette deprecation and legacy test connection ResourceWarnings are present.

| Requirement | Evidence / limit |
|---|---|
| Duplicate collector/lifecycle, unavailable slot, ID conflicts | Existing application/protocol cases plus new lifecycle lock regression |
| 72-hour timer, early size switch, A→B→A, restart activation clock | Existing scheduler regressions from b44f310/d1ba17e, rerun by full suite |
| Raw/core non-atomic commits and crashes | Existing process-kill transition tests; generated permission-fence cutover before/after acknowledgement (initial UID fixture failed; successor pending) |
| Durable acknowledgement visibility | Existing pending raw exclusion and exact core reconciliation cases |
| Cross-process readers, stale attachment refresh | New independent shared lease, long-lived worker drain, restart from draining tests; root FD checks in CI |
| Late/changed evidence | Exact body vs sealed-raw check before draining and under final core transaction; new changed-body fault blocks unlink |
| Archive failure | Existing SupabaseHTTP MockTransport deadline, denied, corrupt, conflict, duplicate and ambiguous-write reconciliation cases; default retirement hold tested through real CLI builder |
| Full disk/WAL/unknown sidecars | Existing simulated quota/I/O and allocated-file guard cases; not real filesystem exhaustion or production worst-case WAL proof |
| Market boundary/health | Existing independent186s feature/discovery, freshness, identity/replay/publication rejection tests; no new live venue validation |
| Physical power loss | NOT PROVEN; process exits cannot establish storage hardware guarantees |

No new live cloud mutation was used. Reuse the passing byte-verified live probe and
throughput evidence in ec5f396. It proves its exact objects/runtime access, not an
unexecuted production migration or all cloud failure cases.

## Capacity and performance evidence

Reuse the already-authorized normal/outage VM sample (2 MiB trigger), not an
unchanged retry. Normal A1710 rows, B13 acknowledgements; sampled peak7,895,974B,
seal→retirement0.42154s, close/removal0.12845s. Outage B1667 rows, simulated runway
61.395s, sampled peak9,764,856B; A unchanged, no pending intents, safe full-slot STOP.
Measured main RSS41,590,784B; operation including preparation/cleanup74.197s.
The139,807B exported bundle outside case roots makes the maximum observed combined
workspace9,904,663B. These are sampled file lengths, not physical allocation highwater;
child RSS, burst WAL, sustained reader time and full-scale core remain unproven.

The separate4000-event exact-export CI qualification measures real collector,
feature/forecast/history/ensemble paths with one serial worker and a separate
lifecycle process under2GiB workspace,512MiB/process,170s work/180s total limits.
Its artifact supplies exact metrics; do not substitute previous candidate metrics.

Retained legacy physical DB+WAL5,369,085,952B plus SHM98,304B is independently
additional to a new layout. Reusable pages are not physical free-space credit.
Last VM reading46.38GiB free/~1.257GiB available RAM does not meet the older proposed
40GiB fixture+10GiB free floor/2GiB RAM: short approximately3.62GiB disk/0.743GiB RAM.
No larger fixture was launched or limit raised. The current2GiB fixture allowance
cannot contain the retained legacy allocation alone.16/21GiB ceilings remain
unapproved and unsupported. There is no qualified production ceiling or expiry.

Small live measured slower upload846,958B/s, download721,984B/s; the recorded2MiB
fixture compresses to781,446B. Extrapolated upload+verified readback+final recheck+
observed close is3.34s; B growth68–111KB at assumed20/32.5KiB/s.72-hour extrapolation
is~135.6min and159–258MiB added B raw/index demand, excluding unmeasured core/WAL,
manifest work and worst readers. These are not measured full-window guarantees.
Outage runway must be min(active size remaining / measured conservative growth,
active age remaining), less measured burst/WAL/recovery allowance; it cannot be
specified for production until those terms and a reviewed ceiling exist.

## Cutover procedure and recovery — currently STOP before step1

This is the concrete sequence to qualify and bind, not an executable approval
request. Missing numeric/path/volume controls below prevent safe dispatch.

1. Freeze exact source/export manifest and passing Linux CI; bind reviewed helpers,
   host, database main/WAL device/inode/allocation/mtime/schema, configuration hash,
   lifecycle project/private bucket/runtime identity, expiry and single-attempt ID.
   Require freshly measured disk/RAM and approved aggregate normal/migration limits.
2. Stop API collector and other legacy writers once. Verify PIDs/FDs are quiescent.
   Install the reviewed OS ownership/mode fence while preserving original metadata;
   prove the old service identity cannot write or replace legacy. The corrected generated
   test separates the fenced unprivileged old UID from the root new-operator UID,
   with a sticky root-owned parent. It does not qualify running the production
   application as root or silently change the adapter ownership requirement.
3. Run complete required quick/FK/source-reference verification under one absolute
   verification budget, child reaping and recovery reserve. Do not repeat the old
   1790.105s timeout unchanged. Its exact active check and a sufficient complete
   verification/import budget are still missing. Existing1800s verification,
   600s other,10s reaping,180s recovery/2590s absolute interruption are NOT qualified
   for this migration and must not be silently enlarged or bypassed.
4. Import structured core plus exact legacy identity/protected-input/cursor maps
   into a fresh layout using a qualified bounded production-volume importer.
   Current10000-row/128MiB audit rejects the actual known structured counts alone
   (18289snapshots/27743predictions), so current code must STOP here. Complete
   coverage/equality/foreign-key audit is required before exposing routed reads.
5. Start one new collector on the exact release, retirementOFF, paidAI/legacy
   retentionOFF. Keep the old writer fenced. Capture the first durable new core
   acknowledgement and prove current slot identity, source freshness and persistence.
6. Run one bounded functional smoke: two-second API probes, correct current market,
   advancing Coinbase/current-market Polymarket persistence, dashboard/SSE and stable
   services. No soak/repeated restarts. Missing venue evidence is incomplete acceptance.
7. Before new acknowledgements, failed migration can restore prior code/permissions
   only after proving no new durable writes and original compatibility. Preserve
   incomplete core for diagnosis. After any new durable acknowledgement, keep the
   legacy fence, stop new writes if unsafe, and recover forward using exact core
   intents/raw identities. Never restore database contents or resume the old writer.
8. Retirement remainsOFF until its separate recorded gate: exact cloud coverage,
   protected evidence, root-equivalent complete FD visibility, capacity and recovery
   proof. One subsequent reviewed enablement; no inherited live probe authority.

Required remaining implementation/measurement: production path allowlist and
streamed legacy importer under reviewed volume/resource bounds; aggregate guard
write/WAL reservation highwater and horizon; complete verification budget; privileged
retirement visibility route; successor manual workflow binding the full application
scope. The old application-only pins are not a general bypass. No executable command
is supplied that disables those holds. All production migration/ceiling/retirement
approvals remain separate. I7 and Phase1.75 remain open.


## Review disposition

Checkpoint1 scope/entrypoint inventory: PASS. Checkpoint2 generated routing:
implemented; Linux raw/application/runtime suites passed on6361660, production
path/volume integration BLOCKED. Checkpoint3 generated safeguards: substantial
passing regression coverage, full Linux successor result pending; production
capacity/power-loss proof NOT PROVEN. Checkpoint4: initial Linux UID fixture FAIL;
corrected separate-identity rehearsal pending. Checkpoint5: BLOCKED at representative
capacity requirements, with scaled evidence above reused. Checkpoint6: draft PR
review only, exact successor CI pending. Checkpoint7: BLOCKED, no merge/cutover
approval request. Missing volume/capacity/control qualification prevents an honest
execution-ready procedure. Continue independent code/CI review; do not dispatch.

Full deployment-branch diff includes historical retention diagnostics, native
qualification tools, control amendments and reports. They remain default-off and
must be explicitly reviewed as branch history; a claim that this PR contains only
the latest entrypoint files would be false. No approval is requested for historical
exceptions or production indexes. Review found and fixed the reader check/unlink
race and protected body revalidation gap; the generated old/new UID conflict was
not resolved by relaxing ownership guards. Full deployment-scope security and
production-volume review remains a merge gate rather than an asserted PASS.
