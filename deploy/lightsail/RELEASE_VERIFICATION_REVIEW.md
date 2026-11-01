# Proposed rollover release procedure — review required, not executed

This procedure is prepared for the fd90458 rollover/health application only.
The controls pin its three application Git blobs and the old runtime
`d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`. They cannot authorize another application
or runtime baseline. The final qualified control candidate and exact CI are
recorded in `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md` and the qualification section
below. No production approval is inferred from passing tests or this file.

## Policy submitted for one review

- Fresh, COMPLETE `quick_check` and `foreign_key_check` in one read transaction,
  supervised in a Linux child with512MiB address-space limit. No writer pause,
  database copy/snapshot, integrity omission, manual WAL operation or index.
- Verification work budget1800s, owned-child reap budget10s, recovery reserve180s;
  separate manual Actions verification job ceiling35minutes includes setup/transport.
  These are proposed budgets, not approved extensions of any earlier budget.
- Successful evidence may be consumed once, within300s of completion and before
  original review expiry (at most3600s from authorization creation). Bind release,
  runtime, CI acknowledgments, installed helper/verifier/smoke hashes, database
  path/device/inode/schema_version/catalog hash and protected configuration digest.
- Data collection continues: DML may advance after the consistent verified read
  snapshot. Evidence is NOT a content checksum, immutable DB proof or guarantee
  that subsequent writes cannot introduce corruption. Accepting this five-minute
  concurrent-write evidence-reuse policy requires explicit review; otherwise the
  route stays disabled. Identity/schema/configuration/revision changes invalidate it.
- API/source checks use independent HTTP children with2s wall deadlines, not only
  socket read timeouts. Metadata child deadline3s, persistence child2s. Owned
  command/HTTP/metadata children receive TERM then KILL with bounded reaping; an
  unreaped child is a manual-action STOP, never PASS or a prompt to retry.
- Monitor during verification at each5s child-wait boundary: collector running,
  both feeds live, current market and matching quote, source age[-5,30]s, receipt
  and persisted age[-5,30]s, both RAM and both persistence timestamps advancing
  since the preceding probe. Persistence uses latest256stream/128observation
  rowids only, not source-time history scans. Schema identity reads are metadata.
- Physical DB+WAL must remain below5120MiB minus512MiB required headroom. Retain existing
  min2GiB free disk/runtime flags/protected configuration/sole collector/private
  listener checks. No guard increase. A long read snapshot can pin WAL frames:
  abort/reap if collection or storage guards fail; never checkpoint to make room.
- Code-deploy work600s plus180s recovery within the existing15minute deploy job.
  No new full scan in that job: consume fresh complete proof instead. Restart
  only API. Every failure/interruption after checkout intent triggers bounded
  old-code checkout/API restart, never database restoration. Report recovery
  failure as MANUAL_ACTION_REQUIRED; restored code is not certified healthy.

The verification and deployment Actions invocations use the SAME existing manual
workflow, branch, private runner label, SSH key/forced command and deployment
flock. No public endpoint, infrastructure or SSH/firewall change is needed.
Legacy `deploy <SHA>` keeps its complete inline checks. Reviewed commands are
`verify <SHA>` and `deploy-verified <SHA>`; dispatch.sh permits only these phases.
The consumed I7 exception and its authorization file are not used.

## Prepared controls

`release_verification.py` requires root-owned0600 no-symlink review/evidence files.
The review must set approval_confirmed=true and match every fixed policy value.
The template below is deliberately invalid and is NOT an authorization:

```json
{
  "approval_confirmed": false,
  "review_id": "REPLACE_WITH_EXPLICIT_REVIEW_REFERENCE",
  "old": "d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a",
  "release": "REPLACE_WITH_QUALIFIED_CONTROL_CANDIDATE_SHA",
  "application_ci_run": 0,
  "controls_ci_run": 0,
  "helper_sha256": "REPLACE_WITH_INSTALLED_DEPLOY_PY_HASH",
  "verifier_sha256": "REPLACE_WITH_INSTALLED_RELEASE_VERIFICATION_PY_HASH",
  "smoke_sha256": "REPLACE_WITH_INSTALLED_SMOKE_PY_HASH",
  "expires_at": 0,
  "policy": {
    "work_seconds": 1800, "reap_seconds": 10, "recovery_seconds": 180,
    "freshness_seconds": 300, "deploy_seconds": 600,
    "storage_ceiling_mb": 5120, "storage_reserve_mb": 512
  }
}
```

Root permissions are the trust boundary: a trusted operator independently verifies
exact GitHub push CI and installs review data only after user approval. No GitHub
credentials go to the VM. Each manual workflow invocation also independently
requires current deployment-branch HEAD and exact successful push CI.

## Production steps, only after that review

1. Recheck the existing deployment branch equals the qualified control candidate;
   verify its exact application/control CI run(s), helper hashes and clean deployed
   d56b4a7. Refresh actual flags/cap/services/storage/private listener without heavy
   queries. Keep retention/paidAI OFF and the storage-cap review deadline unchanged.
   Check enough time remains for verification, deployment and bounded functional smoke;
   reaching the cap deadline is an operator review, not an extension.
2. Export only the CI-passed `deploy.py`, `release_verification.py`, `smoke.py`.
   Through existing pinned operator SSH verify their SHA256 and install as reviewed
   root-owned helpers under `/usr/local/lib/tradebot-cd/`. Preserve original helper
   CODE/hash for restoration; never copy the database or configuration. Do not
   overwrite an unexpected helper. Keep the existing forced key and sudo scope.
3. Inspect any prior /run review/claimed/evidence/consumed files; a prior failure
   or unreaped child requires manual review, not deletion to trigger another try.
   After explicit approval create `/run/tradebot-release-review.json` root0600,
   no symlink, from the template with exact SHAs/hashes/CI IDs and reviewed policy.
   Do not generate this production authority during preparation.
4. Use the existing operator/private runner arrangement and manually dispatch
   `deploy-tradebot.yml` on `codex/lightsail-deployment`, inputs revision=qualified
   control candidate and operation=verify. The helper holds the existing flock,
   checks bundle/application scope/runtime, consumes the review before a heavy
   child starts (`.claimed.json`), and emits verification evidence ONLY after
   both full checks and final identity/health/runtime checks pass.
5. On any scan, source/venue, API, storage or reaping failure: STOP. No checkout or
   service restart occurs in this phase. Record partial completed checks and the
   failure; do not dispatch deployment or retry automatically. The old rollover
   bug may itself make this live-verification gate fail at a boundary. This
   procedure does not waive that gate or promise a safe successful scan.
6. On PASS, confirm `/run/tradebot-release-verification.json` and current branch CI.
   Immediately dispatch the SAME workflow/ref/revision with operation=deploy-verified.
   Queuing can exhaust the300s freshness window; expired evidence is a STOP, not
   a reason to extend TTL, reuse old proof or automatically rerun verification.
   All identity/config/runtime/hash/freshness checks repeat immediately before
   evidence is renamed `.consumed.json` and code checkout begins.
7. Only API restarts. Bounded collection probes plus existing full smoke routes
   (dashboard/SSE/history/system/models/cloud and secret-leak checks) remain.
   The reviewed smoke permits degraded ONLY with feature_snapshot_missing and/or
   feature_as_of_stale; current-market/source collection checks remain mandatory.
   Legacy smoke defaults still require ok. A failure records code-only rollback;
   no data, config, unit, WAL or index restoration is performed.
8. After deployment, run one bounded functional smoke sequence: API/current market,
   source freshness, advancing RAM/persistence, dashboard/SSE and stable services.
   Existing controls use two samples separated by5s for progress/stability; no
   repeated observation session, background soak or automatic retry. Report results
   and yield. Multi-cycle and real-boundary acceptance are NOT PERFORMED unless
   separately evidenced. I7 and Phase1.75 remain OPEN. Slow feature freshness and
   retention remain separate unfinished work.
9. Preserve private review/verification/deployment and observation evidence.
   Retire unused authority and restore helper CODE only if separately required by
   the approved procedure, with exact hash checks; never replace database contents.
   Update the authoritative roadmap with measurements and any rollback outcome.

Preparation does not approve or execute these steps. Phase1.75 stays OPEN.
Retention qualification remains paused until rollover/health production acceptance
passes; feature-speed and retention-commit work remain separate. No paidAI,
production deletion, backup/snapshot, manual WAL, index, guard increase or Phase2.

## Preparation evidence (no production action)

Local working-tree backend246tests PASS(two Linux-only skips); deployment controls
88tests PASS(three Linux-only skips), including18new review/evidence/deadline,
complete-check, bounded-persistence and rollback tests. Compile and shell syntax
checks PASS. Exact Linux CI must exercise platform-specific controls before this
procedure is qualified. Candidate must also pass its own isolated-tree suites.

Read-only permission metadata confirmed the existing restricted deployment sudo
rule already accepts a wildcard argument to the same forced helper. Only booleans
were retained; no sudo/SSH rule, credentials or configuration were changed. No
production DB was opened for this metadata check. Root review and protected helper
installation remain separate manual actions after procedure approval.

Service PID/restart identities and the protected configuration digest are checked
before/after verification and again before deployment. Evidence does not survive
an intervening service restart, configuration change or database/schema replacement.

Startup readiness is distinct from collection recovery: after API restart, allow
up to180s within the existing600s code budget for transport to become available.
Only connection/transport failures are polled. Once health responds, run collection
validation once; expired identity, stale source data or unexpected degradation is
a failure, not a new recovery/retry window. Startup timing/failure counts are
recorded separately and are not counted as the functional smoke results.
The final control qualification includes this readiness regression (19new controls;
89total working-tree controls, including three platform-specific skips locally).

## Final qualified control candidate — awaiting production review

Candidate **2c24ddef0b746945caa228c5c7954b6755ebfe70** is on the existing
`codex/lightsail-deployment` branch, retaining fd90458's exact application tree.
Working source **bde20f5197222ddd376ef2d6a703d6fe0ba783a6** passed
[CI41331790634](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41331790634).
Candidate [Python CI41331916958](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41331916958)
passed169backend/25control tests on Linux, including the real bounded verification
child. Its [manual-workflow validation41331917043](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41331917043)
was a **push** event: validate PASS; verify/deploy SKIPPED. No production phase ran.
Local candidate169backend/25controls PASS(one Linux-only skip); working246backend/
89controls PASS(two/three Linux-only skips). No source-time/index/dependency or
application change was introduced by the control candidate.

Exact helper SHA256 values for operator readback after the procedure is approved:

| Installed helper | SHA256 |
|---|---|
| deploy.py | 41db48d22d945f03e65892ac18c5314bc9dd326f56b1debcb50ff6e322334321 |
| release_verification.py | 1160b97691909362bfae97dc0dd3c32bcb2e0f24d83e2e1c18a34fbccaec830b |
| smoke.py | 59ace5e05a961512590f4932caa1403f4eb84bd9d657b04feb35db64383d7780 |

After review, the operator's review document would use release=the full2c24dde SHA,
application_ci_run=41331916958 and controls_ci_run=41331917043, independently
rechecked against GitHub. Keep approval_confirmed=false until approval; expires_at
must be computed at actual authorization creation, never extended automatically.

These are the future manual commands for steps4/6, **not executed during prep**:

```sh
gh workflow run deploy-tradebot.yml --ref codex/lightsail-deployment -f revision=2c24ddef0b746945caa228c5c7954b6755ebfe70 -f operation=verify
# Only after a fresh complete PASS, within TTL and with unchanged identities:
gh workflow run deploy-tradebot.yml --ref codex/lightsail-deployment -f revision=2c24ddef0b746945caa228c5c7954b6755ebfe70 -f operation=deploy-verified
```

Production procedure review is still pending. There is no installed review file,
new helper install, heavy scan, application restart or production acceptance result
from this milestone. Retention/paidAI stay OFF; original data/ceiling/deadline and
unrelated working edits are preserved.

## Revised gate — November1 17:41:57UTC

The former64MiB storage reserve was inconsistent with the required512MiB headroom.
The revised control enforces512MiB; candidate2c24dde and its helper hashes are
superseded for this revised procedure and must not be installed/dispatched.
New exact-candidate CI/review bindings are required before execution.

Fresh DB+WAL4846731328bytes leaves497.796814MiB, below512MiB: STORAGE STOP.
Ceiling5120MiB and deadline2026-11-02T01:56:47.671426Z remain unchanged.
No cleanup, capacity increase, helper installation, authority, heavy scan or
production dispatch is authorized by this revision. Storage needs a separately
reviewed resolution; procedure approval alone does not override this STOP.

The sequence is now verify -> deploy -> bounded functional smoke -> report/yield.
All earlier20-30minute observation instructions in historical qualification text
are superseded. No repeated monitoring or automatic background soak. Multi-cycle
and real-boundary acceptance: NOT PERFORMED. Production approval is pending the
revised request; the user's revision is not installation/verification/deploy authority.
