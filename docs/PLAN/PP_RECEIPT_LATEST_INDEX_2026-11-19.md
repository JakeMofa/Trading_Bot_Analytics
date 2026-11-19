# PP latest receipt lookup: guarded source candidate

No live DDL, flag activation, authentication/cap change or audit retry is part
of this source candidate. The normal rank query remains default. The opt-in is
available only through the explicitly gated PP retained-archive audit CLI;
recurring service and destructive verifier profiles do not wire the flag.

## Observed problem and evidence scopes

The actual PP19 audit verified all 57 raw objects but held on its first rich
500-row structured page. It charged 60 logical requests and 4,428,956 logical
bytes in 67.510s, with 172.490s of the 240s cycle remaining. The structured page
lasted 4.711504s; phase measurements included exact revisions 1.142899s, latest
receipts 2.050960s, newer revisions 0.101279s, and projections 0.261247s. This
was a page/transport failure, not exhaustion of the whole cycle. No data retired.

The independent hosted connector-role plan for the actual 73 keys scanned
42,133 PP receipts, joined 37,412 revisions, and spilled sorts (1,137 temp
blocks read / 1,141 written). That snapshot's execution was 150.532ms. Separate
actual runtime-role cumulative statement statistics had 46 calls, mean 178.624ms
and max 1950.347ms, with 18,025/18,110 temp reads/writes. A server-side tail near
the observed phase is therefore supported, but statistics cannot identify the
individual audit call. Connector, runtime-role cumulative statistics and full
phase timings remain distinct; none promises exactly 2s saved after an index.

The existing PK is (origin_id,generation_id,outbox_id). Indexing just those
receipt stream fields does not support latest-by-entity lookup. Rank must
consume and sort historical revisions for each requested key, including a hot
current-price identity with 37,340 historical receipts.

## Candidate and fail-closed behavior

`TRADEBOT_PP_INDEXED_LATEST_RECEIPTS=true` is an exact, separate default-OFF
selection. Malformed values HOLD. The candidate seeks one ordered group per
key using LATERAL with `FETCH FIRST 1 ROW WITH TIES`; it retains every equal-max
outbox ID across generations. Missing keys and ambiguous maxima keep the
existing cardinality/integrity checks. Plain LIMIT 1/DISTINCT ON are not used.

The index keys are `(origin_id,entity_type,md5(entity_id),outbox_id DESC)`, with
no INCLUDE. **Full `entity_id` equality is always a residual predicate.** Hash
comparison never authenticates identity and hash collision cannot merge keys.
Hashing avoids adding a B-tree tuple-size restriction to schema-unbounded
entity_id text; actual hosted maximum was 148 bytes, but that observation does
not establish a future bound. The existing importer already restricts entity
types to its eight table identifiers and PP origin is fixed. No new write-length
constraint or role grant is added.

Before the first raw GET, the existing authenticated permission preflight also
verifies the supporting index's exact ABI. Every structured page rechecks the
ABI in its existing authenticated A checkpoint query, inside that page's fresh
REPEATABLE READ READ ONLY transaction. The existing timeout-setting query also
sets a transaction-local catalog-only search path so an identically named user
function cannot masquerade as builtin md5 in deparsed index definition.

ABI validation requires the exact full PG17 index definition, target table,
btree access method, nonunique/nonpartial/no-INCLUDE layout, deterministic
identity collation and valid/ready/live flags. Wrong, absent or failed-build
indexes HOLD before indexed lookup. A connection-bound token stays local to
one page invocation; it is not reused across transactions or physical sessions.
The full transport adds **no SQL statement or application wait**: the ABI is a
scalar part of the existing checkpoint SELECT. Default rank takes its original
single latest-receipt query and has no index probe/search-path setting.

Concurrent DDL after a successful ABI check can make the planner lose the
index. The query still enforces exact identity, max ties and the remaining
four-second transaction/page cap; it may HOLD on a slower scan. Index presence
never authorizes deletion. No partial proof or cached ABI grants later authority.
All original 240s/128MiB/192-request bounds and the historical seal deadline stay
unchanged. Preflight's physical connection may expire after the 44.75s raw
phase under the existing 30s idle rule; lifetime/idle settings are unchanged.

## Generated PG17 plans and costs

The disposable native fixture matches observed cardinalities (not private keys
or hardware): 42,133 receipts / 73 requested keys / 37,412 joined revisions, then
250,000 receipts with 221,550 hot-key revisions. The same driver, immutable rows,
keys and three alternating read pairs are used before/after. work_mem 4MB;
prepare_threshold None; no forced index/plan setting. Plain covering index was
explored separately and rejected as the candidate because identity text is
unbounded. Lateral without a supporting index was slower (269ms and 1825ms),
which is why the runtime gate refuses it rather than falling back.

| Generated receipts | Rank before index, client median | Indexed lateral, client median | Indexed server plan | Temp blocks |
| --- | ---: | ---: | ---: | ---: |
| 42,133 | 60.744ms | 0.558ms | see retained plan | 0 |
| 250,000 | 169.214ms | 0.751ms | see retained plan | 0 |

The hash index alone does not improve the unchanged rank SQL materially. It
must be paired with the guarded query selection. A full 500-key metadata page
is also qualified in the retained artifact. Both queries return identical
multisets for normal, missing and equal-max cross-generation receipts. A forced
all-hash-collision variant retains exact identity equality. An incompressible
8KiB identity inserts and reads successfully through the hash index.

The actual rich transport comparison reads 500 exact sealed A envelopes
(499 distinct candles and one price; 852,583 canonical bytes) plus the same
newer B envelope (1,786 charged bytes), checkpoint and projections. It includes
320ms cold setup and 100ms per simulated application wait, including explicit
BEGIN/COMMIT. Preparation, raw/local inventory and WAN throughput are excluded.

| Generated receipts | Rank rich-page median | Indexed rich-page median | SQL / modeled waits, both |
| --- | ---: | ---: | ---: |
| 42,133 | 1.724195s | 1.688855s | 508 / 11 |
| 250,000 | 1.873741s | 1.705615s | 508 / 11 |

The PP-sized full-page benefit is small in this local model. An initial version
with a separate per-page ABI wait was actually slower at that size (1.771s
versus 1.694s); the fused check removes that regression. These are generated
correctness/scaling measurements, not proof of a hosted four-second page or
240-second complete audit. The original PP18 trial remains failed.

Index size was 5,218,304 bytes at 42k and 30,883,840 at 250k; standalone concurrent
builds took about 0.1/0.6s on local hardware. Actual 25-row importer receipt INSERT
statements, 500 rows per rolled-back sample, measured median 22.060→21.326ms at 42k
and 19.042→21.413ms at 250k. Earlier repeated fixture runs varied; do not treat the
small 42k timing reversal as a write speedup. WAL clearly increased: baseline
about 259kB per 500 versus338–392kB indexed. This is receipt SQL/index work only,
excluding envelope/projection writes, transaction commit and remote latency.
The additional index therefore has real storage/WAL/maintenance cost.

## Migration, rollout and rollback review

The migration was created with Supabase CLI 2.65.5 `migration new`; it contains
one `CREATE INDEX CONCURRENTLY` statement. PostgreSQL forbids this in a
transaction block or pipeline. Do not run it through an unqualified CLI batch,
MCP apply_migration transaction, or a file containing BEGIN. A separately
reviewed operator must bind the source, target and standalone autocommit
executor before any hosted DDL. No such application occurred here.

There is intentionally no IF NOT EXISTS: an existing same-name wrong or invalid
index must not count as success. A failed concurrent build can leave an invalid
index which still costs writes. Inspect ready/valid/live/definition first; a
separate standalone concurrent rollback script removes only this named index.
Disable the app opt-in and stop audit borrowers before rollback. Leave receipts,
envelopes, checkpoints, policies and grants intact. Default rank still works
without the candidate index. Schema inspection/confirmation precedes any retry.

Official references: PostgreSQL17 [SELECT/LATERAL/WITH TIES](https://www.postgresql.org/docs/17/sql-select.html),
[CREATE INDEX CONCURRENTLY and failure handling](https://www.postgresql.org/docs/17/sql-createindex.html),
and [covering-index size/write tradeoffs](https://www.postgresql.org/docs/17/indexes-index-only-scans.html).

Reproduce only on a disposable local cluster:

```
/tmp/pp-revision-full-venv/bin/python deploy/preprod/bench_receipt_latest.py \
  --pg-bin /opt/homebrew/opt/postgresql@17/bin \
  --output /tmp/receipt-latest-qualified-results.json
```

The script accepts no cloud DSN and starts PG17 with listen_addresses empty
and a private Unix socket. It stops/removes the cluster. Generated plans,
raw timing samples, semantic checks, WAL and source fingerprints are retained
in [the evidence artifact](evidence/pp-receipt-latest-generated-2026-11-19.json).
Native official-foundation/SCRAM tests also qualify valid concurrent creation,
missing/wrong/invalid ABI, cross-origin exclusion, duplicate max ties, full rich
newer-B proof and corrupt-projection rejection. No live project was mutated.

Validation of the final candidate: 388 backend tests passed (50 external/isolated
DSN skips); all 17 package-invoked history/inventory tests passed on official
foundation PostgreSQL 17 with distinct generated SCRAM reader credentials,
unchanged shared catalog and final schema validation. The standalone two-size
plan/rich-page benchmark completed and cleaned its own separate cluster.
