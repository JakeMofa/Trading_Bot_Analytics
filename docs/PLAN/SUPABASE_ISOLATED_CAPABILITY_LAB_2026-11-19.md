# Supabase capability tests for PP and research

November 19, 2026. The browser audit inventoried the project and the 31-card
integration catalog. This lab exercises the features relevant to PP archive
reads, secondary jobs and deterministic history. It used generated data in an
unlinked local Supabase CLI 2.65.5 stack (Supabase PostgreSQL 17.6.1.059) and
separate disposable PostgreSQL 17.2 clusters, with fictional PP and production
identities. PP, production and the hosted Supabase project were outside the lab.

## What passed

| Feature | Isolated evidence | Application to PP |
| --- | --- | --- |
| Data API, REST RPC and RLS | A scoped invoker function returned the first 500 exact, ordered rows and the next 25. SQL returned the same IDs, decimal text and hashes. Anonymous execution and authenticated mutation were denied, the other identity only saw its own row, and a request for 501 returned no rows. | If phase measurements identify repeated network trips, compare one narrow archive lookup with today's verified PostgreSQL reader. Keep the existing receipt, revision, origin and byte-bound checks. |
| Native SQL RPC with archive query shape | Twelve matched 500-row reads returned identical canonical data for A after the current projection advanced to B. Eleven negative checks passed. With no added RTT, three statements took 40.87 ms versus 44.32 ms through the invoker function. With 50 ms of delay injected per statement, the comparison was 202.14 ms versus 101.92 ms. | A measured network-bound operation could benefit from two fewer sequential SQL requests. The isolated timing excludes HTTP and PP. |
| GraphQL | Both signed-in identities fetched their own row for the same generation. A value of `0.500000000000000001` arrived as an exact string. | An alternative for scoped structured reads. The test does not identify a new archive benefit over the existing reader. |
| Private Storage | The writer put a generated object. The owning reader got byte-identical content. The other tenant and anonymous role were denied, and the reader's upload was denied. | Matches the existing split between compressed raw archive files and SQL-queryable structured history. |
| Cron and Queues | pg_cron 1.6.4 ran two one-second observations and the job was unscheduled. PGMQ 1.5.1 hid an unacknowledged message until its visibility timeout, redelivered the same ID, then removed it from delivery after archive acknowledgement. | Suitable candidates for secondary freshness checks or retryable research jobs. Durable VM outbox acknowledgements remain the source for archive progress. |
| Edge Functions and webhook transport | A local Edge Function forwarded the caller's token to RPC and returned the same 500 rows. No token returned 401. The second identity retained its own scope. pg_net posted a generated request inside the local stack and got the expected exact response. | Useful for a small status summary or notification. No full verifier or retention operation was delegated to Edge. |
| pgvector and deterministic research | pgvector 0.8.0 returned the expected ordering for three generated vectors. A separate generated A/B fixture restored 3,240 gzip ticks from 36 markets. The point-in-time query excluded 36 late arrivals and matched an independent exact-decimal oracle for retained and restored features and nearest-five ranking. | Exact SQL inputs remain appropriate for deterministic forecasts. The vector test is basic functionality. An embedding-quality use case, such as searching notes, needs its own evaluation. |
| Realtime | Two signed-in clients subscribed to the same generated table and each received its own committed notice, with no cross-scope notice observed in the bounded test. | Can deliver dashboard archive status updates. The fixture did not compare it with the VM’s existing SSE or test reconnection recovery. |
| PostgreSQL telemetry | Local `pg_stat_statements` recorded the generated RPC statements. | Pair statement counters with VM archive phase timings and oldest pending age. A live Grafana scrape and combined dashboard have separate acceptance. |

## Combined archive status prototype

The [isolated scheduler probe](../../deploy/preprod/probe_archive_health_scheduler.py)
combines Cron with PGMQ and the application's existing telemetry summarizer.
On a fresh local Supabase stack at database port 57322, run the probe with
`PYTHONPATH=backend`, psycopg installed, the disposable database password in
`TRADEBOT_HEALTH_LAB_PASSWORD`, and the checked-in
[PP21 historical audit JSON](evidence/pp21-canonical-retained-audit-2026-11-19.json)
as its sole argument. The probe creates fixture tables and a queue in that
isolated database.

Cron delivered the job. A deliberately rolled-back status write and queue
acknowledgement left no status row. PGMQ redelivered the same message ID, and
the retry committed one completed status. A duplicate job left one status
row, and an input with missing evidence showed `unknown`. The displayed
2.163305 seconds came from the historical audit. This probe reads no live VM
state and its output carries no retirement authority.

The probe now also runs an example of the VM's existing read-only resource
sample contract through the status consumer. It keeps the age of an observation
separate from the collector's lease and on/off state. A fresh stopped collector
is `off`; a stale or missing sample leaves the collector `unknown`. Separate
unit checks reject the wrong origin, future timestamps and timezone-free
timestamps, and identify an expired lease. The two-minute freshness threshold
is a fixture setting. Archive lag, pending rows and transport downtime require
their own live measurements.

A periodic scoped VM sample can supply this information. Realtime is optional
delivery for dashboard updates after a sample exists. The app's deployed
cloud-status endpoint does not provide the VM archive observations today.
Publishing fresh reports needs a scoped bridge and identity. Existing release
and retention jobs remain owned by the VM.

## Same-tick delivery timing

Three isolated runs published the same generated tick ID and exact price text
to both branches of a test program. The first branch used the app's actual
`event_stream` implementation over loopback HTTP, with its 250 ms snapshot
interval. The second inserted the same record into local Supabase PostgreSQL
and read it through an authenticated Realtime Postgres Changes subscription.
Tick production and both consumers used the same monotonic clock. Generated
ticks were spaced 290–470 ms apart to exercise different points within the SSE
interval without saturating its latest-state delivery. All 180 IDs and exact
price strings matched. Times end at the subscriber, before browser rendering.

| Run | Matched | SSE median / p95 | Realtime median / p95 | Paired Realtime minus SSE median / p95 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 60 | 121.542 / 233.160 ms | 90.090 / 120.052 ms | -37.443 / +88.704 ms |
| 2 | 60 | 137.474 / 233.902 ms | 66.246 / 121.098 ms | -49.494 / +87.669 ms |
| 3 | 60 | 128.536 / 231.542 ms | 66.330 / 110.429 ms | -55.063 / +72.293 ms |

Realtime arrived later for 52 of 180 pairs. This local comparison includes a
loopback database insert and Realtime propagation, plus the separate SSE frame
timer. Hosted network time, actual VM persistence cadence, batch contention
and browser rendering remain unmeasured. No collector or dashboard routing
change was needed.

A separate passive mirror was prepared for the PP rehearsal. It accepts one
operator-authorized loopback SSE connection during a generation, requires the
correct origin and collector ON, and mirrors at most 30 distinct observed
tick IDs and exact prices at one per second into a disposable local database.
Its elapsed metric starts when the observer receives a VM SSE tick and ends
when local Realtime delivers the same tick. A generated PP-shaped SSE endpoint
proved the mirror on 30 exact pairs at 68.893 ms median and 133.221 ms p95
after SSE receipt. The release owner supplies the actual collector ON receipt
and access window. Hosted TokenBot stays outside the experiment.

## PP22 live rehearsal observation

The PP22 release owner confirmed collector ON and approved a single passive SSE
subscriber for up to 30 seconds or 30 distinct IDs during each steady
generation. On November 19 just after 22:15 UTC, one 29.5-second observation
matched 16 exact Coinbase tick IDs and prices in initial A
(`94107d29-626f-480a-b61a-ce6a10f44301`, origin
`pp-live-pp-trial-20261119-01`). The mirror rate limit was one sample per
second. Repeated or rate-limited frames were excluded.

| Leg | Matched IDs | Added median | Added p95 | Range |
| --- | ---: | ---: | ---: | ---: |
| Initial A | 16 | 71.867 ms | 103.014 ms | 37.023–103.014 ms |

The elapsed time starts at actual VM SSE receipt on the observation
workstation and ends when the isolated local Supabase Realtime client receives
the same tick. This measures added local mirror delivery, with no hosted
network comparison or browser rendering measurement. The observer closed
after the bounded sample. Dashboard routing, collector, and hosted Supabase
settings were unchanged. The release owner stopped the trial in initial A
after structured sync failed to keep up. Durable OFF was confirmed at 22:21:36
UTC with 5,241 A raw rows retained. A 50-row page committed to Supabase
before its local ACK deadline and was reconciled by exact readback. The 25-row
fallback acknowledged 250 rows in 66 seconds while the input rate was about
14 rows per second. B and fresh A were unobserved, and the optional 500-row
read under live load was held to avoid adding load during recovery.
[PP22 deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44624765516)

## Structured write sizing after the live hold

Two disposable PostgreSQL 17 checks used the current structured writer and
fresh authenticated readback. Three generated pages per size were rotated.
Matching canonical bytes and receipt and revision counts were required.

The wider fixture fit 25 and 50 rows at up to 99,201 and 198,401 bytes.
All generated 75-row pages exceeded the existing 256 KiB limit at
295,657–297,601 bytes. A narrower fixture fit all sizes at up to 67,201,
134,401 and 201,601 bytes. In that narrower run, generated put-plus-readback
medians were 567 ms, 545 ms and 1,306 ms for 25, 50 and 75 rows respectively.
The wider run's 25- and 50-row medians were 245 ms and 359 ms. These small
fixture runs omit the network, TLS, pooler and local ACK. Their timing varies
between runs. At roughly 14 incoming rows/sec the observed live worker would
need a sustained complete turn in about 1.79 seconds for 25 rows or 3.57
seconds for 50, including handoff. The existing reviewed row ceiling is 50.
Next measurement should use actual host page bytes and separate cloud commit,
authenticated readback and local ACK timings.

## Full structured write, verify, and ACK qualification

A disposable PostgreSQL 17 cluster ran the real active worker, installed
schema and trial writer role, durable local outbox, and exact hosted-side
receipt/revision checks. It applied no PP or hosted changes. Every successful
page had 50 equal canonical envelopes and 50 persisted local ACKs. The first
comparison used two pages per arm at each injected wait. With 50 ms per
counted database wait, batching (`69af6ef`) cut 25 waits to 15 and the median
complete page went from 1.489 s to 0.950 s. With zero injection it went from
99 ms to 98 ms.

For the revision query rewrite (`d9ab8d4`), each arm processed eight consecutive
50-row pages in two runs with reversed order, 50 ms of simulated wait and a
100 ms handoff. Both versions persisted all 400 exact ACKs per run. The revised
source measured 48.61–49.02 records/sec compared with 25.92–25.99 records/sec
for the previous batching code. Median write, fresh readback and local ACK
for the revision fix were approximately 640–652, 238–240, and 17–19 ms.
The result exercises sustained work against a generated backlog in the lab.
Network, TLS, hosted contention, and PP CPU limits require separate evidence.

On the actual stopped PP backlog, the original batching candidate held on
the first 50-row write. The release trace put about 3.14 s in its final writer
batch and recorded a transaction timeout during the revision SELECT before
ACK. The estimated old plan rescanned the selected generation through
repeated joins. The replacement selects scoped rows once and applies the same
byte and exactness checks. A hosted read-only test on the same 25 IDs took
1.591 ms of database execution with the new query, and the old query hit
its 3.5 s timeout.

Exact-CI `a9e51dd` passed the entire real PP backlog with the collector off.
All 4,888 pending rows completed durable write, fresh authenticated readback
and local acknowledgement across 98 contiguous pages in 126.358883 seconds,
or 38.68347 rows/sec. No errors or retries occurred. The retained generation
had 5,241 raw rows, 5,651 total structured ACKs, and zero pending.

| PP stage | Median | p95 |
| --- | ---: | ---: |
| Supabase write | 678 ms | 835 ms |
| Fresh verified readback | 245 ms | 331 ms |
| Local ACK | 96 ms | 145 ms |
| Entire page | 1,153 ms | 1,395 ms |

The longest page took 2.501 seconds. The real stopped backlog exceeds the
14 rows/sec target. Sustained concurrent intake and the A/B/fresh-A trial
remain separate. The release owner will archive and audit the stopped A
before another live start. A remains attached.
[Hosted query diagnosis in d9ab8d4](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d9ab8d4/docs/PLAN/evidence/pp22-sync-query-diagnosis-2026-11-19.json)

## Independent PP23 release checks

A disposable checkout of PR #192 head `ecba5f4` ran 49 focused tests with
zero skips in 12.440 seconds. Coverage included the actual worker readiness
output accepted by the controller, native generated PostgreSQL rotations
and preservation of the earlier archived A, final-A sealing and audit,
scoped cloud policies, revision query guards, and HTTP/SSE and browser
reference-price behavior during market discovery. The merge `f964c93`
matches the tested backend, deployment, and Supabase trees. This check ran
without a PP connection or hosted writes. Live release acceptance remains
separate. [Release PR](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/192)

## PP23 first live observation

The release owner verified PP23 ON around 01:14:05 UTC on November 20,
for origin `pp-live-pp-trial-20261119-02` and initial A
`41c82044-0fb8-4900-bea0-7c43ba079ff0`. The earlier archived PP22 A
was preserved under the separate origin.

One approved 29.5-second observer window matched 27 exact tick IDs and
prices in initial A. Local Realtime added 70.557 ms median and 114.536 ms
p95 after the observer received the VM SSE tick. The range was
15.703–118.033 ms. The primary stream reported Coinbase stale during part of
the sample while the collector and storage remained available. This timing
excludes upstream delay, browser rendering and hosted Realtime.

A separate 59.945-second operator sample measured 13.863 incoming versus
13.779 acknowledged structured rows per second. Pending changed from 28 to
33 and oldest pending age fell from 1.966 to 1.755 seconds. No holds or
retries occurred. Nonempty pages measured 15.002 rows per service second,
excluding handoff; no full 50-row page was seen. The window shows sync close
to intake but leaves a sustained wall-clock rate over 14 rows/sec unproven.

The original 500-row read was skipped in this window because the existing
wrapper expected the old deployment and ran four sweeps. An offline
single-read payload was prepared. It still needs a reviewed passive host
launcher, a fresh quiet-window decision, and existing scoped credentials.

A separate browser agent verified the hosted Realtime service was already
enabled on TokenBot main, with zero tables in its Postgres Changes
publication and no separate preview branch visible. No setting was changed.
[PP23 deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44648041989)

## PP23 live stop and confirmed scope

The initial A remained collecting across the first Polymarket natural
rollover at 01:30 UTC. In the observer's market-missing samples, Coinbase event
IDs advanced and backend freshness remained within its guard. Quote, feature,
and forecast stayed absent until the new market appeared by 01:30:18.913.
The stored samples do not contain numeric browser display values. A separate
Coinbase freshness issue recurred after the boundary.

Over 01:15:53.833–01:38:35.059 UTC, observed structured ACKs averaged
13.6994/sec against 13.6877 incoming/sec. Pending fell from 30 to 14.
The saved session status marked `coinbase_stream.ws_closed_error` and
durable OFF at 01:38:52.371 UTC. The observer subsequently saw OFF at
01:38:55.464. The lease had not expired. The exact reconnect budget
branch and underlying WebSocket closure cause remain unresolved.

Initial A remained attached and unsealed with 18,930 raw records, 20,362
structured ACKs, zero pending, and no archive manifests at that snapshot.
The trial never switched to B. B and fresh A therefore had no timing
samples, and the scoped live 500-row comparison was not performed.
The previously archived PP22 A was preserved.
[Deployed retry behavior](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/f964c93/backend/postgres/live_ingest.py#L115)

## Independent Coinbase reconnect and local ingest checks

The exact PP23 source passed 16 existing reconnect and supervisor tests. A
generated replay saved a valid fixture tick before each of 13 WebSocket
closures, spaced more than 60 seconds apart. The lifetime cap allowed 12
reconnects and then raised `coinbase_stream.ws_closed_error` despite the
successful intervening saves. The actual live stop identifies the same error
class but does not identify which retry limit or underlying closure caused it.

A separate native PostgreSQL 17.2 fixture exercised the real store and
restricted app role for 400 generated ticks. Two 100-tick blocks per arm
alternated new checked connections with one validated dedicated local
connection. Each event kept its own transaction and its existing durable
writer/lease checks. Independent SQL matched committed event identities and
hashes, and an attempted write on a reused session after durable OFF failed
before persisting anything. On a Unix socket without concurrent load:

| Local save path | Median | p95 |
| --- | ---: | ---: |
| Fresh connection per event | 7.186 ms | 8.199 ms |
| Dedicated reused connection | 0.891 ms | 1.396 ms |

The live stale tick was already about 41.1 seconds old when dequeued. Host
measurements must locate the delay before assigning it to checkout or DB
work. Capture source-to-parser, parser-to-dequeue, worker queue, checkout
and committed save time with the bounded diagnostics. Compare the current
fresh connection path with one dedicated serial writer whose thread opens,
uses and closes its own restricted connection. The current `asyncio.to_thread`
calls can use different threads. Benchmark one transaction per event before
considering multiple events per transaction.

| Next fixture case | Required observation |
| --- | --- |
| Constrained serial owner and backlog | Assert one thread owns its connection, no idle transaction persists, the handoff is bounded, and multiple callers cannot share the connection. Compare throughput, queue age, checkout and commit p95 at identical input cadence including a burst. |
| Commit, rollback and duplicate | Confirm raw event, projection, dedup and outbox changes appear together. A rolled-back write yields no ACK. A replay of the same event remains idempotent and retains the original hash, while a conflicting identity holds. |
| Generation switch and stop | Verify one event per committed generation across a real switch with unchanged writer-lock order. Reject a write after durable OFF or lease expiry, including lease expiry between admission and the final check. Verify no pending writes cross an acknowledged stop. |
| Broken connection or ambiguous commit | Discard the session and revalidate environment and role on replacement. Reconcile the same immutable event via existing dedup before any ACK after lost commit response. Fail closed for invalid identity or storage errors. |
| Backpressure attribution | Separate source-to-parser age from time queued to dequeue and time spent in the local writer. Retain unknown when frame pairing is lost. Include matching dashboard freshness/abstention and another source's continuity during transient reconnects. |

No runtime or PP settings changed. The probe source and its rerun output
are preserved as local research artifacts for the release owner.

## Independent recovery candidate and connection safety tests

The PP recovery candidate at PR #193 head `5fb9fa3` passed 49 focused
tests with zero skips in a disposable checkout using native PostgreSQL
where applicable. The run covered rate-limited reconnects, timing
diagnostics, supervisor and fatal failure handling, a generated market
boundary, the stopped-A archive-only path, and trial host controls.
This run validates candidate behavior independently. Exact release CI
and live PP acceptance remain separate.
[Recovery PR](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/193)

A combined native fixture used the actual supervisor, retry, Polymarket
normalization and store paths. With 16 generated Coinbase connection
attempts and virtual backoff, it held the three-reconnect-starts-per-60s
limit while Polymarket market and quote writes persisted on both sides of a
size-triggered fixture A → B switch. The current estimate abstained with
`reference_price_not_fresh`. Explicit stop and a fatal injected storage
rejection both committed durable OFF. Real feed availability and the
two-official-market live schedule were outside this fixture. The portable
regression was handed to the release owner as a test-only patch. It passed
both generated checks with native PostgreSQL and again through the isolated
restricted-DSN harness on `64b213c`. The continuity test reproduced the old
`coinbase_stream.ws_closed_error` behavior on deployed `f964c93`.

A separate exact deployed-source fixture used one restricted PostgreSQL
connection opened, used and closed by a dedicated writer thread. Independent
SQL confirmed exact raw, dedup and outbox state after a successful event,
idempotent duplicate, and conflicting replay refusal. An injected exception
before commit left no persisted evidence or ACK. An injected lost ACK after
an actual commit recovered the original exact event on a new validated
connection. A size-triggered generated A → B switch routed the next new
event to B using the reused connection and kept the old duplicate in A.
Lease expiry inside a write and durable OFF both rejected new writes.
A different thread was refused. This controlled test did not implement
reuse in the release or measure the PP network or provider.

At this checkpoint PP is OFF. The failed PP23 A remains attached with 18,930
raw rows and no pending structured records. It still needs exact-source
archive-only sealing and independent readback before a fresh one-use trial
is admitted. A retry on the same VM requires the qualified release, a fresh
origin and permissions, a healthy memory/readiness check, and a new ON
receipt. No new run or deletion occurred in this work.

## Stopped PP23 A independent audit

PR #193 exact head `62d54e2` passed the required push and PR checks and
merged as `6a09ed4`. The release owner separately sealed the stopped PP23
A with collection OFF. The independent reader authenticated and compared
all 38 raw objects covering 18,930 records, and verified 20,362 structured
records across 41 pages. The audit used 81 requests and 35,230,341 logical
bytes within its bound. Before/after archive fingerprints, existing older
data and writer records matched. The verified A remained locally attached,
with no pending records or retirement. These are archive-only results.
The fresh trial still needs two complete 30-minute windows with committed
Polymarket collection, scoped archive verification and both live switches.
[Recovery PR](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/193)

## PP24 operator startup and Coinbase candle isolation

The first PP24 deployment stopped during smoke testing before live
admission. The private API answered at 02:59:10.542 UTC and the operator
finished starting 0.326 seconds later. The smoke check had a single operator
attempt. Recovery stopped the candidate with PostgreSQL still healthy.
The independently verified PP23 A remained attached.
[PP24 deployment run](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44664385511)

The readiness candidate passed 46 isolated action tests, including delayed
operator binding and immediate rejection of reachable invalid state. Its
candle handling passed six focused tests. An independent PostgreSQL 17
fixture injected repeated Coinbase WebSocket closures plus a candle fetch
timeout and checked real restricted Polymarket market and quote commits
before and after a generated A → B switch. The previous release `d5615a3`
stopped with `coinbase_candles.timeout`. Candidate `fc9413b` passed, with
stale reference-price abstention and durable OFF verified. Live proof still
requires observed quotes and actual switch times on the PP VM.
[Readiness and candle PR](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/196)

## PP25 live-entry memory check

PP25 passed deployment acceptance on the same VM. Two attempts to enter
the live-ready profile held before any collector start. In a read-only
reproduction, the host had 1,072,451,584 bytes of available memory against
the required 1,073,741,824 bytes. The other entry prechecks passed. The
original failures returned a generic reason, so the exact cause for each
attempt remains unproven. The release chat recovered to generated mode with
collection OFF and PostgreSQL preserved.
[PP25 deployment run](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44668724097)

PR #198 checks the existing headroom requirement after stopping the owned
application containers and before startup. The independent 13-case suite
passed, including read-only preflight failures issuing no application stop
or recovery, and a partial stop attempt receiving one bounded recovery.
These checks qualify the control flow. The live A → B → fresh A trial and
the duration of Polymarket collection on each leg are still open.
[Transition sequencing PR](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/198)

## PP26 live A and parallel isolated Supabase checks

PP26 admitted collection at 17:44:08.840017 UTC on November 20. The PP21
and PP23 retained archives were outside the current trial. The first full
official 15-minute market had 180 API observations, 133 distinct quote
receipt times and zero API errors. Its first observed quote was 22.252
seconds after the market boundary. The second market's first observed quote
was 10.292 seconds after the next boundary. The collector session stayed
live. Polymarket receipts advanced while Coinbase was stale, and the release
observer verified forecast abstention with `reference_price_not_fresh`.
[PP26 deployment run](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44783463740)

A single coordinated 4-second-budget GET returned 500 active-A raw
records (768,232 bytes, exact origin and generation) in 0.816234 seconds,
with `local_postgres` provenance. The hosted structured-history route had
no deployed service binding. The earlier 2.163305-second hosted structured
page used a different dataset and transport. Through 17:53:36 UTC, live
API p95 was 127.516 ms for state and 101.980 ms for health. The first SSE
frame p95 was 84.407 ms across ten checks. First-frame time does not measure
individual quote delivery latency.

In a disposable local stack, the app SSE path and Supabase Realtime
delivered the same 60 saved PP26 Polymarket receipt metadata records with
exact timestamp and market identity. Replay-start median/p95 was
118.294/241.804 ms for SSE and 89.409/121.005 ms for Realtime. Realtime
arrived later in 19 of 60 pairs. Cross-tenant isolation passed, and a scoped
Data API RPC returned identical rows in 15 reads. A second fixture checked
private Storage byte restoration and access control, Cron-to-Queue retry
and duplicate behavior, and scoped Edge, GraphQL, webhook and vector paths.
These isolated tests used saved receipt metadata. Hosted Realtime latency,
Pipelines delivery and Analytics Bucket performance remain unmeasured.

## PP26 live A → B outcome

One session collected through the actual A → B switch at 18:15:07.207508
UTC. A ran for 30 minutes 58 seconds and covered official markets
`2730625` and `2730561`. A verified 24,649 raw records across 50 hosted
objects at 18:17:00.381174 UTC while B continued accepting new records.
The controller reported 26,480 structured acknowledgements for A.
Historical raw-quote retrieval and deterministic prediction replay passed
while A was attached. Final retirement exited nonzero after roughly 249
seconds. The launcher lost the native verifier reason, leaving the exact
failed phase unproven. No local partition was deleted.

Explicit OFF was observed at 18:31:15 UTC. B had collected for about 16
minutes with 12,301 raw records and 13,210 structured acknowledgements.
The writer session and lease cleared, both partitions stayed attached, and
the pending queue drained. B did not finish its official market pair and
fresh A did not start. The old PP21 and PP23 archives were outside this
retirement attempt.

The passive observer recorded zero API errors across 371 A and 194 B
samples. A/B p95 was 130.067/129.046 ms for state, 170.469/268.408 ms for
five-record prediction history and 87.513/96.415 ms for the first SSE frame.
The observer saw 276/140 distinct fresh Polymarket quote receipts, 98/54
while Coinbase was stale. Mean structured acknowledgement rates were
14.295/13.692 rows per second. Some rolling intervals were below 14, while
sampled queues peaked at 75/45 and drained to zero. These counts use the
existing read-only API and database observer outputs.

### Supabase logs for the failed retirement readback

The read-only Logs Explorer window was November 20, 2026, 18:26:00–18:30:10
UTC. The aggregates below used the exact new A generation or the exact
trial03 reader role. No database query, Storage download, access change,
record payload, object path, or credential was needed to collect them.

- `edge_logs`, filtered by the new A generation in `request.path` and
  grouped by request method and response status, showed 50 GETs for 50
  distinct paths. All were HTTP 200, from 18:26:29.910 to 18:27:19.290 UTC.
  Gateway `response.origin_time` median/p95 was 327/502 ms. The underlying
  `storage_logs` stream contained 36 matching events and all were HTTP 200.
- `supavisor_logs`, filtered on the exact trial03 reader in its `user`
  attribute, contained 162 events from 18:27:21.402769 to 18:30:07.758111
  UTC. A text-category aggregation found 68 disconnect-like and 94 other
  entries, with zero timeout/error matches. Events can repeat across pool
  components and cannot establish the number of connections or completed SQL pages.
- `postgres_logs` contained two `LOG` entries with SQLSTATE `00000` in
  the window and no attributable per-query durations. The child exited
  nonzero at about 18:30:09 UTC. The final raw GET response preceded the
  exit by about 170 seconds. Gateway success establishes object delivery
  from Supabase. Client decode, exact local comparison, structured page
  completion, and the verifier's failed phase are still unproven.

PP26's retirement wrapper left `TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION`
at its default `false`. The recurring structured-sync worker's reuse flag
controls a separate path. The reader activity supports investigating the
structured and connection phases using the new diagnostics before trying
any retirement change.

### B archive recovery with collection OFF

The review reproduced a statement timeout in the original protected-
evidence lookup using the trial's actual row counts. The successor used
the existing outbox unique key and kept full typed payload equality. Its
fixed-scope helper passed exact Linux CI, then sealed B at 19:00:04 UTC on
November 20. The existing worker verified all 12,301 B raw records across
25 Supabase Storage objects at 19:01:07 UTC, 63.36 seconds after the seal.
All 13,210 structured records were acknowledged. The final snapshot
confirmed A and B verified and attached, the collector and archive worker
OFF, and no fresh A. The original final retirement error remains unidentified.
[Exact recovery CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44797052857)
· [Release recovery evidence](https://github.com/JakeMofa/Trading_Bot_Analytics/commit/1b1098b)

## Product scope and decisions

Managed Pipelines and Analytics Buckets require hosted capabilities. The
parallel local proxy was PostgreSQL logical WAL decoding plus DuckDB/Parquet.
It observed 2,002 row changes and demonstrated replay duplication if the same
unconsumed batch is applied twice. After a mutable row was removed, 999 current
rows remained and all 1,000 immutable revision envelopes were still available.
The Parquet round trip preserved every canonical envelope and hash, numeric
precision, original decimal spelling and 200 missing outcomes. A PP-origin
and availability query returned 150 eligible rows with zero future labels.
This qualifies the local mechanism and export format. Managed delivery,
hosted destinations, and Iceberg catalog behavior remain unverified.
[Managed Pipelines requirements](https://supabase.com/docs/guides/database/replication/pipelines)
· [Analytics Buckets](https://supabase.com/docs/guides/storage/analytics/introduction)

The release accepted the hosted receipt/index lookup and the canonical
byte-reuse improvement. With those changes, the PP21 read-only diagnostic
verified 63 structured pages and 57 raw objects, with the first 500 rows at
2.163305 seconds and identical retained fingerprints. Keep the current reader
for that milestone. Match any future alternative against the same inputs,
scope, exact outputs, request count and elapsed budget. Qualify the active
50-row write configuration and any larger write batch separately.
[PP21 retained-A evidence](PP21_CANONICAL_RETAINED_AUDIT_2026-11-19.md)

Third-party catalog entries for unrelated workflows remain catalog research.
The lab adds no application dependency, credentials, paid service, lifecycle
authorization, or hosted configuration.
