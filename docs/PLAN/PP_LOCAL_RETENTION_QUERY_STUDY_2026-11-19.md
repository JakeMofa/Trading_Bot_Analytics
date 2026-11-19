# PP local archive page lookup study

The indexed hosted replay held near its deadline after verifying all 57 raw
objects and 62 structured pages. Its local inventory took about 15.8 seconds and
raw comparison about 16.1 seconds. This study isolates the PostgreSQL page read
used by raw comparison and the outbox page read used by structured inventory.
The PP release chat retains its separate runtime qualification.
[Indexed PP replay evidence](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/178)

## Generated measurements

An isolated native PostgreSQL 17 cluster used partitioned raw events and an
acknowledged outbox with the current primary keys and pending-outbox index.
Generated A had 28,411 raw rows and 31,162 outbox rows. B had 9,784 raw rows and
10,971 outbox rows. Synthetic candidate rows included JSON and exact decimals.
The benchmark called the existing `LifecycleRepository._page` and
`LifecycleRepository._pending` methods at 500 rows with their current byte
limits. Each arm warmed once and ran three full sequential sweeps. Time includes
local SQL, row fetch, and the same ordered canonical hashes in both arms.
It excludes cloud operations and live concurrent collection.

| PostgreSQL locale | Query path | Current median | Candidate median | Rows / pages |
| --- | --- | ---: | ---: | ---: |
| en_US.UTF-8 | Raw event cursor | 4.416 s | 0.740 s | 28,411 / 57 |
| C | Raw event cursor | 4.317 s | 0.723 s | 28,411 / 57 |
| en_US.UTF-8 | Acknowledged outbox cursor | 0.721 s | 0.714 s | 31,162 / 63 |
| C | Acknowledged outbox cursor | 0.770 s | 0.738 s | 31,162 / 63 |

The raw page count, event order and combined digest across all 57 canonical
pages matched exactly in all runs
(`007866e48bd7bc23b96c26c240af250aa197c51bb337550b0ffd41f45a966050`).
The same checks matched for the 63 outbox pages
(`5c5df4ed5c5cbe20531cdf82f9d93f9116244a2eba0bb24d372673d97b340d02`).
These are generated fixture digests.

The raw cursor uses explicit `COLLATE "C"` on both keys. The baseline read
scanned A and sorted the qualifying rows before choosing its page. For a
representative middle cursor in the en_US.UTF-8 fixture, the size query visited
1,672 shared buffers and took about 88 ms. The new cursor index let the same
query stop after 501 rows, using 68 buffers and taking about 2 ms. The generated
index definitions were:

```sql
CREATE INDEX test_raw_generation_cursor
    ON raw.events (generation_id, source COLLATE "C", event_id COLLATE "C");
CREATE INDEX test_outbox_generation_id ON ops.outbox (generation_id, id);
```

The outbox query still chose its primary-key index in the shown middle-page
plan. The small sweep difference does not establish a useful outbox index.
Generated outbox IDs were contiguous by generation, and the sweep excludes
preflight count, structured record conversion, and full inventory work.
Measure those phases separately on representative PP evidence.

## Full-schema PostgreSQL 17 qualification

A second disposable cluster applied all local PostgreSQL migrations and used
generated data from two origins. Three warmed reads kept the same production
page function and 500-row limit. Five 5,000-row inserts per arm used fresh
partitions and alternated which arm ran first.

| Measurement | Current | Cursor index |
| --- | ---: | ---: |
| Median 28,411-row sweep, 57 pages | 4.613 s | 0.761 s |
| Median 5,000-row bulk insert | 0.242 s | 0.253 s |
| Median WAL per 5,000 inserted rows | 5,603,688 bytes | 6,421,672 bytes |

The extra bulk-insert time was about 4% and additional WAL about 15% in this
fixture. All six sweeps matched on row count, page count and ordered canonical
page digest
(`ecc3a6fdc7f41a005ee585b0c0f60599f4040641a702cfa8919e3c6d8f9474dc`).
A concurrent build on the quiet 28,411-row child took 64 ms, generated about
2.23 MB of WAL and produced a valid, ready 2.47 MB index. Under a held
`ROW EXCLUSIVE` lock, a regular child build hit the configured 250 ms lock
timeout. PostgreSQL refused a concurrent build on the partitioned parent
with SQLSTATE `0A000`. Bulk inserts and a quiet build do not establish live
collector latency, concurrent build duration or rollover behavior.

## Remaining qualification

1. Ask the release operator for the exact retained A mid-page size and payload
   query plans under the existing scoped reader. Start with plain `EXPLAIN`.
   Any timed read should keep the current bounds and stay outside a critical
   retention operation. Record the actual relation, collation, scan, sorting,
   Buffers when measured, and phase timings.
2. If PP shows the same repeated raw scan, qualify an index on a sealed
   generation child before considering any index on active generations.
   Look up the relation through the registered generation UUID. Test that a
   failed or retried build cannot advance archive or retirement state, the
   successor continues writing, and its own archived hashes still match.
   Account for build and lock time separately from the verification sweep.
3. Keep the live gates intact. A faster local scan reduces time spent inside
   exact verification. It does not authorize retirement or remove any raw,
   receipt, structured projection, reader, or permit check. The full audit
   still needs PP timing. The fixture indexes were removed with the disposable
   cluster, and no application code, schema migration, or hosted index changed.

This is a separate lever from the hosted latest-receipt index already deployed
and the canonical byte-reuse candidate in
[#180](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/180).
