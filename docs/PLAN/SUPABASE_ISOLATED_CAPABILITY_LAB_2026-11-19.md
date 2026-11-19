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
settings were unchanged. B and fresh A await their switch receipts. A bounded
structured query under live load is a separate operator-coordinated check.
[PP22 deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44624765516)

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
