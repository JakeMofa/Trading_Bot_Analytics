# I7 maintenance continuation — prepared, not executed

This is a one-time operational procedure for the I7 STOP recorded in
`docs/PLAN/I7_RELEASE_ATTEMPT_2026-10-30.md`. The official execution roadmap
remains `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md`.

The normal GitHub CD workflow and root-owned forced-command helper remain
unchanged. This alternative is **not installed or invoked by either**. It needs
separate operator approval for a bounded collection gap and a one-time operator
release path. Do not dispatch normal CD again to repeat the failed live scan.

## Exact scope

- Expected runtime: `a7c098900f8310367fc262a1b837c369bb63dc56`.
- Application release: `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`, the I7-only worker containment, excluding unqualified retention changes.
- Prepared helper: `deploy/lightsail/i7_maintenance.py`. It is plan-only by default.
- Existing VM, repository and branches only; no AWS resources or SSH/firewall edits.
- No `.env`, unit, dependency, schema/index, retention, VACUUM or manual WAL changes.
- Retention and paid OpenAI stay OFF; application guard stays 4096 MiB.
- Working budget: 20 minutes, plus five minutes reserved for recovery. These are
  bounds, not a promise that full verification will finish or that service
  restoration is guaranteed after a kernel/systemd failure.
- Complete quick check and complete foreign-key verification each have a maximum
  420-second allocation, further shortened by the shared budget. No extension or
  weakened check on timeout. Read-only check children are killed/reaped by their
  parent deadline; they open only an immutable recovery copy.

## Before requesting/using the maintenance window

1. Review the helper and its tests; require passing CI on the exact helper commit.
2. Freshly verify on the operator Mac that the existing deployment branch still
   points to the application release above and that its exact-SHA push CI passed.
   The helper accepts the trusted operator's SHA/run acknowledgment; **it does not
   authenticate to GitHub or independently verify that assertion**. Never give
   the VM GitHub credentials.
3. Refresh only the existing local deployment branch (no checkout/new branch or
   Git worktree) and make a tracked-only Git bundle containing exactly
   `refs/heads/codex/lightsail-deployment` at the release SHA. Inspect bundle heads.
4. Export the helper from its exact CI-passed commit. Record SHA-256 locally,
   transfer over the existing pinned operator SSH route, and verify the same hash
   on the VM. Put it in a root-owned private directory. Do not run an uncommitted
   or subsequently edited helper.
5. Put the source bundle in a root-owned directory readable by the `tradebot`
   user (directory 0755, tracked-only bundle 0644), as in normal CD. The helper
   validates ref, SHA, ancestry, clean checkout and the narrow changed-file
   allowlist before stopping any service.
6. Approve the intentional collection interruption. Live ticks/books missed
   during the window are a data gap, not complete history that can be invented or
   assumed backfillable. This step does not approve retention or Phase 2.

Example read-only GitHub checks on the operator Mac:

```sh
gh api repos/JakeMofa/Trading_Bot_Analytics/git/ref/heads/codex/lightsail-deployment --jq .object.sha
gh run view 41138048640 --repo JakeMofa/Trading_Bot_Analytics --json headSha,status,conclusion,url
```

The example run ID is historical evidence for the fixed release; recheck that it
still reports success for the exact release and inspect any changed branch state.
The separately published helper revision must also have successful CI.

## Execution, only after approval

Keep a trusted operator session connected to supervise the entire operation and
recovery. Acquire the same `/run/lock/tradebot-deploy.lock` used by ordinary CD;
the helper refuses concurrent deployment. The approved outer supervisor must
send TERM after 20 minutes, allowing at most five additional minutes for recovery:

```sh
sudo timeout --signal=TERM --kill-after=300 1200 \
  /usr/bin/python3 /root/tradebot-i7-maintenance/i7_maintenance.py \
  --execute --confirm-collection-gap \
  --bundle /var/tmp/tradebot-i7-maintenance/source.bundle \
  --ci-verified-sha d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a \
  --ci-run-id 41138048640
```

Paths are the reviewed root-owned staging locations, not a request to create a
replacement VM. Retain a bounded operator/transport supervisor as well. A hard
watchdog termination or lost control channel requires immediate manual state
inspection; never assume automatic restoration completed from timeout alone.

The helper:

1. Validates old revision, tracked cleanliness, enabled/active required units,
   actual process OFF flags, API guard, protected configuration, fresh literal
   restart configuration, private binding, sole collector and free disk reserve.
   Inherited operator environment cannot mask unsafe file settings. It never
   prints configuration values or arbitrary command output.
2. Stops the existing monitor timer and any active read-only monitor. Waits up to
   180 seconds for a responsive API window. If that window never arrives, it
   restores the monitor and stops before taking down the collector.
3. Requests API stop immediately in that window, then stops lifecycle/ensemble
   through existing systemd configuration. Existing unit stop deadlines/policies
   still apply. Non-success shutdown results trigger restoration, not a claim of
   graceful success; no extra application kill command is introduced.
4. Checks all process file-descriptor identities for remaining DB/WAL/SHM owners,
   including aliases. Refuses unexpected owners or a nonempty remaining WAL.
   Normal last-connection cleanup is permitted; forced checkpoint/truncate or
   manual WAL deletion is not.
5. Creates a root-private recovery copy on the same VM, with 120-second copy and
   120-second independent readback limits inside the shared budget. Requires
   byte size and SHA-256 agreement, then complete SQLite quick/FK checks on that
   immutable copy. The source remains quiescent and its file identity, size and
   modification time must remain unchanged. No multi-GB Mac copy is made.
6. Only after every check passes, checks out the fixed I7-only revision, starts
   API/lifecycle/ensemble, runs existing protected smoke checks, restores the
   monitor timer, and checks stable PIDs/restarts, OFF flags, guard, protected
   configuration, sole collector and private binding.

## Failure and evidence

Before checkout, a failure restores only previously active units that this
attempt stopped; it does not change application code. After a partial checkout
or material validation failure, it stops new application processes and restores
the old revision before restarting the required units. **It never overwrites the
production DB with the backup**, so evidence collected after restart is not
discarded by code rollback.

Failure to stop or restore safely is `MANUAL_ACTION_REQUIRED`, not PASS. Old-code
service restoration is explicitly separate from API health: the original stall
can remain present. Do not repeat a failed operation or increase its budget.

Root-private `data/deployments/i7-maintenance-*/` holds phase timestamps, sanitized
reports, backup and checksum. Do not publish the DB or secrets. Preserve a
recovery copy until separately reviewed cleanup; do not call it R7 approval for
retention. Record the collection gap from the phase evidence and actual resumed
feed timestamps; do not claim full interval capture.

## After a successful maintenance release

Success is `deployed_pending_I7_validation`, not I7 complete. Independently verify
the actual revision, private endpoints/SSE/dashboard, new feed timestamps and
persisted evidence, and observe several complete feature cycles. Measure feature
age, cycle duration, API latency, collector/writer coexistence, disk I/O and WAL
growth. The worker fix does not shorten scans. If features remain too old, that
requires a separately evidenced query/performance fix with identical as-of,
staleness, decimal and provenance behavior.

Retention R5/R6 stays STOP and Phase 2 stays deferred until their own gates pass.
