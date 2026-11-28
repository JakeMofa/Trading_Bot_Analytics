# Ownership timeout: diagnosis, repair and sustained acceptance

Current status: `.14` resumed at 13:12:39 UTC and failed again at
14:30:04.056 UTC with `ownership.timeout`. Four-hour acceptance did not pass.
New phase diagnostics and resource evidence are in the
[latest master checkpoint](INTELLIGENCE_REBUILD_PLAN.md#november-28-2026--benchmark-14-sustained-check-failed).
The query phase was 85.105 ms; the cumulative check consumed 2,003.143 ms
across admission, connection, retries and worker/future/event-loop phases.
A completed callback does not prove its boolean result. Lease authority
remained valid; CPU scheduling pressure under the 0.25-core operator quota
was observed, with no swap/OOM or container restart. Do not increase the
ownership deadline or restart blindly. Retained A/B and production remain
unchanged; qualification resumes from this incident.

## Persistent private reader candidate — November 28

The implemented candidate keeps **one physical reader connection open** inside
the operator. Ownership, status and feed-preference reads borrow it one at a
time, each in a fresh read-only transaction. Waiting ownership checks get
priority over at most two waiting ordinary reads. The existing two-second
ownership deadline, native worker admission ticket and physical reader budget
remain unchanged; lifecycle/writer credentials and write paths stay separate.

The runtime performs full schema checks with its original reader budget while
OFF, before opening the retained connection. Producer stores and the private
status repository then share the same broker. Each borrow commits or closes
before release and ends idle. A failed transaction is discarded. A failed
physical close quarantines the broker; cancellation cannot free a connection
still owned by a native worker. Process/thread checks reject escaped handles.
Process shutdown closes the retained reader after requesting collector stop;
ordinary collector OFF leaves status available for a later explicit ON.

There is one reconnect attempt for a broken reused socket, only during internal
transaction setup before any caller SQL has been sent. The replacement gets
fresh role/environment checks. Caller SQL is never replayed after failure.
Ordinary reads use local 200 ms statement / 75 ms lock / 500 ms transaction
bounds. These bound server work, not arbitrary Python code holding a borrow;
only the short fixed operator callbacks belong here, not history or audits.
Ownership has its own bounded transaction within the unchanged async deadline.

The desired-feed SELECT alone retries exact SQLSTATE 57014 or 25P04 with the
existing finite three-attempt/backoff policy, using a fresh transaction each
time. Native tests prove a preference and OFF changed during backoff are seen.
It never returns cached preferences. Persistent failures, permission/identity
errors and other failures retain their previous refusal behavior. This retry
does not apply to ownership, status endpoints or state-changing commands.

Diagnostics now retain each native attempt's true/false/capacity/error category,
native duration and worker-to-loop resume delay. This avoids treating the old
cumulative `worker_complete` phase as proof of the final callback's outcome.
Late results still cannot authorize collection, even when the native result
was true. Records include neither exception text nor credential values.

- [x] Implement shared reader, startup/shutdown wiring and bounded diagnostics.
- [x] Pass native PostgreSQL 17 tests for fresh UUID/expiry/OFF, priority across
  real status/preferences, reconnect-before-caller-SQL, SQL failure without
  replay, transaction timeout, cancellation, close failure and handle affinity.
- [x] Pass actual runtime native wiring: one reader backend across status and
  producer reads, IDLE between transactions, closed on process shutdown.
- [x] Independently review physical accounting and the preference retry boundary.
- [x] Run final backend discovery: 754 tests / 67 expected skips / no failures;
  all 14 new native shared-reader/preferences/runtime cases ran without skips.
- [ ] Qualify exact merged source, current retained-data recovery/adoption and
  fresh Benchmark observation. This candidate has not been deployed.
- [ ] Repeat four hours and 24 hours; if delivery latency remains problematic,
  compare the operator CPU allowance separately on the same VM.

[Actual implementation benchmark](evidence/benchmark-shared-private-reader-local-2026-11-28.json):
80 identical synchronous callbacks per reader on disposable PG17 / local Unix
socket. Fresh login median **2.739 ms**, p95 **5.374 ms**; shared reader median
**0.163 ms**, p95 **0.244 ms** (one backend PID; fresh OFF observed). The first
shared call includes initialization. This excludes VM/network/CPU-quota/executor
and event-loop contention; it is not a predicted Benchmark latency or long-run
acceptance. No container CPU allowance or live data was changed for this test.

Official guidance checked for this design:
[psycopg concurrent operations](https://www.psycopg.org/psycopg3/docs/advanced/async.html),
[transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
[PostgreSQL 17 transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html),
and [transaction/statement timeout semantics](https://www.postgresql.org/docs/17/runtime-config-client.html).
Connection reuse is compatible with fresh reads; serialization must cover the
whole transaction because cursors on one psycopg connection share transaction
and error state. No long-lived read transaction is kept between borrows.

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

- [x] Add bounded monotonic timings for scheduling, reader admission,
  connection/environment validation, ownership SQL and physical close.
- [x] Distinguish the outer async deadline from native SQLSTATE57014, reader
  admission failure, connection failure and a false ownership result.
- [ ] Correlate failures with event-loop delay, executor queue delay and
  per-container CPU throttling/pressure. Do not attribute an interval's entire
  throttling total to a single request.
- [x] Record late worker completion after cancellation. A timed-out
  `asyncio.to_thread` call can continue holding a physical database connection.
  It must neither release its budget early nor grant authority on late success.

Current code puts all of those phases inside a two-second outer deadline while
libpq connection establishment alone permits five seconds. Private reads share
one reader slot and ownership uses the default thread executor. These are
design risks, not a demonstrated cause of the 09:51 stop.

Deliverable: a regression that reproduces each delay class and a diagnostic
record naming its phase without keys, DSNs, payloads or unbounded logging.

## 2. Qualify the smallest control-path repair

The first implemented candidate is smaller than the retained-reader proposal:
it isolates ownership from the default ingestion executor with one lazy,
process-wide worker and at most one outstanding native call. Cancellation does
not return its ticket until the native future really finishes. It keeps the
existing fresh physical database connections, private reader allowance and
two-second check. Native fixtures reproduce default-pool starvation, but do
not establish it as the cause of the real 09:51 failure. A reused private
connection remains a follow-up if measured admission/connect phases justify it.

The candidate also checks the monotonic deadline after receiving a result.
A delayed event loop can otherwise deliver ready True before processing an
overdue timer. That result is rejected, even though its SQL itself was fast.
Structured diagnostics separate this deadline from native SQLSTATE57014 and
callback timeouts; late native completion never reinstates authority.

All ten focused scheduling/phase/deadline/import tests passed locally using
native disposable PostgreSQL 17 where required. Independent review found and
verified fixes for late event-loop delivery and migration-only import isolation.
The pre-existing controller suite passed 332 cases (nine skips), and CI-control
tests passed 58 cases. Full backend discovery passed 735 cases (67 environment
skips). PR #263 merged as `ca2e082` after its exact head source and PR CI passed.
The final combined release still needs exact-source CI and live acceptance.
The isolated executor applies to continuous ownership checks; activation and
durable-OFF callbacks retain their existing default-executor paths.

Retained-reader alternative, only if phase evidence justifies it: replace repeated physical
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

The 12:05–12:09 UTC complete read-only inventory from #265 passed preservation
but took 271.275 seconds. Its actual timing report projects 904.378 seconds of
inventory work alone in normal CD and 542.549 seconds for two recovery scans.
Both exceed the unchanged 600/180-second budgets. Do not dispatch CD from this
result. Raw metadata comparison round trips dominate, followed by repeated
per-origin descriptor scans and full-row outbox hashing. Qualify a single
native ordered metadata cursor and one complete all-origin outbox descriptor
snapshot, keep exact original full-row/page digests and consistent read-only
snapshots, and re-measure before adoption. This is a maintenance-cost finding,
not evidence that those scans caused the earlier ownership deadline.
[Measured costs and unchanged writer state](evidence/benchmark-full-inventory-cost-2026-11-28.json).

The complete-inventory follow-up at 11:25 UTC found that the existing
`raw.events` identity-hash sort also exceeds the unchanged 64 MiB temporary
file cap at the current size. PostgreSQL's bounded log confirms a temp-file
error, not role capacity, RAM exhaustion or the 19-second query deadline.
This occurred before the newly qualified outbox cursor ran. #264 and its
exact Linux CI are complete, but no new live outbox timing or deployment can
be claimed. The generic metadata-hash repair is now part of this adoption
gate, alongside the raw table's actual 437,064 rows and `en_US.utf8` collation.

An actual read-only preflight at 10:48 UTC found another admission blocker:
the existing complete-origin outbox digest on A's 235,755 rows reached
19,000.576 ms and was canceled with SQLSTATE57014. A stayed OFF at epoch 9,
235,755 ACKs, zero pending, and the same last outbox ID. No CD was dispatched;
the preflight stopped before scanning the remaining origins. A separate
controller repair must bound each digest statement while preserving complete
coverage, canonical full-row hashes and a consistent snapshot. The old
98,058-row acceptance does not qualify this larger inventory.

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
