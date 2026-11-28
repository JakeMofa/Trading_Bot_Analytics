# Ownership timeout: diagnosis, repair and sustained acceptance

Status: planned; no runtime fix or new live run has been applied for this incident.
This is the immediate workstream in the [master plan](INTELLIGENCE_REBUILD_PLAN.md).
Keep current A, retained A/B and production unchanged during offline work.

## Evidence and objective

Benchmark `.13` stopped at 09:51:04.539628 UTC with `ownership.timeout`,
although its preceding renewal granted authority until 09:53:03.485334.
At the last captured status, A was OFF with 235,755 verified ACKs and zero
pending. This is distinct from the corrected status503 renewal failure.
The narrow PostgreSQL logs do not identify a native query or capacity error.
See the [incident checkpoint](INTELLIGENCE_REBUILD_PLAN.md#november-28-2026--later-ownership-deadline-failure-benchmark-off).

Keep collection responsive under the normal three-feed, dashboard and archive
workload while preserving exact producer identity and database-enforced write
authority. A real ownership loss must still stop unauthorized writes.
No design can promise collection through arbitrary database/host failure;
record missing coverage rather than implying that live display equals saved data.

## 1. Identify which phase exceeds the deadline

- [ ] Add bounded monotonic timings for scheduling, reader admission,
  connection/environment validation, ownership SQL and physical close.
- [ ] Distinguish the outer async deadline from native SQLSTATE57014, reader
  admission failure, connection failure and a false ownership result.
- [ ] Correlate failures with event-loop delay, executor queue delay and
  per-container CPU throttling/pressure. Do not attribute an interval's entire
  throttling total to a single request.
- [ ] Record late worker completion after cancellation. A timed-out
  `asyncio.to_thread` call can continue holding a physical database connection.
  It must neither release its budget early nor grant authority on late success.

Current code puts all of those phases inside a two-second outer deadline while
libpq connection establishment alone permits five seconds. Private reads share
one reader slot and ownership uses the default thread executor. These are
design risks, not a demonstrated cause of the 09:51 stop.

Deliverable: a regression that reproduces each delay class and a diagnostic
record naming its phase without keys, DSNs, payloads or unbounded logging.

## 2. Qualify the smallest control-path repair

Preferred candidate, subject to phase evidence: replace repeated physical
connection setup with one serialized private read service using the existing
operator reader allowance. Give it a dedicated worker so feed/background work
cannot fill its executor queue. Prioritize ownership reads ahead of queued
status/preferences reads, and bound the latter; a running SQL call cannot be
preempted merely by queue priority.

- [ ] Reuse at most one private reader connection, with a fresh read-only
  transaction/snapshot for each job. Validate role/environment on connection
  establishment and every reconnect. Never share a transaction across callers.
- [ ] Preserve current exact-origin/session/expiry checks and per-write fences.
  No cached ownership, false-owner retry or deadline increase.
- [ ] Bound queue length and individual operations so status work cannot consume
  the entire ownership deadline. Refuse excess optional reads explicitly.
- [ ] On connection failure, close before replacement; reconnect only within
  the existing aggregate check allowance. If fresh proof cannot be obtained,
  retain the safe stop and report the exact reason.
- [ ] Preserve the reader-role limit of four: public API two, private operator
  one, serialized host diagnostics one. No new fifth connection or pooler is
  needed for this candidate.
- [ ] If controlled measurements identify CPU quota as the limiting phase,
  compare a reviewed quota change separately on the same workload. Extra host
  RAM alone does not change a container's CPU allowance.

Use stage 1 evidence to choose a smaller change if connection reuse or worker
isolation is unnecessary. Do not combine a quota increase with the first
control-path comparison and then claim which change fixed it.

## 3. Prove both continuity and fencing offline

- [ ] Saturate the shared executor and optional-read queue while ownership
  continues using its reserved, bounded lane.
- [ ] Delay connection/environment validation, reader admission, ownership SQL
  and close independently; prove phase attribution and total deadline behavior.
- [ ] Cancel a waiting caller while its worker continues; prove no leaked or
  prematurely returned session ticket and no overlapping replacement connection.
- [ ] Test native query cancellation, dropped connection and reconnect failure.
- [ ] Change session UUID, disable collection, expire the lease and change
  generation; stale workers must not write, renew or resurrect themselves.
- [ ] Exercise all three feed writers, dashboard/history reads, calculation,
  archive ACKs and optional Coinbase candle rejection concurrently on native
  PostgreSQL 17. Preserve saved identity/value/provenance and existing budgets.

Deliverable: focused native regressions, existing controller/runtime checks
and an independent code review. Automatic restart after an ambiguous failure
is not part of this repair; fresh admission must be qualified separately.

## 4. Prepare a safe Benchmark adoption

- [ ] Qualify exact source CI, controller/profile compatibility and recovery.
- [ ] Preflight fingerprint cost against the now larger retained A. Bounded
  fingerprint SQL still has growing total work; prove it fits current limits
  before dispatching deployment, rather than relaxing those limits blindly.
- [ ] Preserve retained fingerprints, active-generation identity, saved prefix
  and archive coverage. No deletion or old-PP/production action.
- [ ] Use a qualified preserving handoff if available. Otherwise surface the
  collection interruption of the normal maintenance route before adoption;
  the existing API-only route does not deploy collector-runtime changes.

No blind restart, deployment or guard change is authorized by the evidence
record itself. Follow current user authorization and the qualified route.

## 5. Extend acceptance beyond the previously passing short window

- [ ] Capture a before/after comparison with all three feeds, normal ACK work,
  bounded dashboard polling and repeated identical 500-row history reads.
- [ ] Observe at least four continuous hours, exceeding `.13`'s approximately
  two-hour post-admission lifetime. Keep every failure and sampling gap visible.
- [ ] Require no unexpected OFF/session change, no writes after authority loss,
  ownership checks completing within two seconds, API quote publication within
  five seconds, and the same 500-row page within four seconds under collection.
- [ ] Plot arrivals, verified ACKs, pending count and oldest pending age together;
  require lag to recover after load bursts rather than using average ACK rate
  alone. Report exact event counts and receipt-to-save/archive coverage gaps.
- [ ] Continue to a 24-hour checkpoint if healthy. These are observation gates,
  not a guarantee against every future failure or a new 72-hour rotation claim.
- [ ] Then run the current three-feed release's actual A-to-B dashboard/history
  continuity test under a qualified profile, retaining old A/B. Resume 72-hour
  retirement work only after that separate acceptance.

Grafana should distinguish source stale, private ownership slow, collector OFF,
and archive lag. A last-known-good value must not appear as current health.

## Delivery order

1. Instrumentation and native failure reproductions.
2. Evidence-selected control-path repair and independent review.
3. Qualified Benchmark adoption, four-hour comparison and 24-hour observation.
4. Current-release A/B query/collection continuity, then the deferred roadmap.

Parallel implementation can split native fault fixtures from runtime changes
and dashboard/telemetry verification. One owner retains live Benchmark access
to prevent concurrent probes or deployments from confounding measurements.
