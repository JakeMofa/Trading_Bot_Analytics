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
its 3.5 s timeout. The full hosted write-to-ACK result is still open.
[Hosted query diagnosis in d9ab8d4](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d9ab8d4/docs/PLAN/evidence/pp22-sync-query-diagnosis-2026-11-19.json)

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
