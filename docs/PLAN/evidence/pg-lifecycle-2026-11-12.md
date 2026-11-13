# CP4 PostgreSQL lifecycle and history — implementation evidence

Scope: generated, isolated qualification code on `codex/pg-lifecycle`, based on
`3031554`, for integration through `codex/feature-postgres-pp`. This note does not
close CP4 or establish PostgreSQL integration, PP, cloud, or capacity acceptance.
The master roadmap remains parent-owned and authoritative.

## Implemented contract

- Explicit bootstrap creates unique UUID generation A through CP2's narrow
  lifecycle SQL helper. The application never performs DDL. Writer-state row
  `FOR SHARE` protects acknowledged ingestion; lifecycle `FOR UPDATE` atomically
  seals/switches to a new UUID in the other slot. Late source events go to the
  current generation. Rotation is 72 hours or an explicitly configured size
  fixture. There is no extra 72-hour sealed wait. The other slot must be retired
  before reuse; registry constraints cap nonretired slots at two per origin.
- Raw archive pages have deterministic gzip JSONL bytes, bounded encoded/decoded
  sizes, exact decimals as strings, original source timestamp strings, raw wire
  text, NULLs, origin/generation/dataset identity, row count, SHA-256 and identity
  boundaries. No replacement/delete/upsert operation exists on the transport.
- Structured outbox sync performs authenticated exact-content readback before
  acknowledging immutable versions. Checkpoints are generation/dataset scoped.
  Manifests/checkpoints and duplicate-identical object writes allow restart after
  ambiguous upload or between pages. The calculation branch tags newly produced
  structured output with the current generation, while protected raw input keeps
  its original generation identity.
- Explicit generated retirement acquires the generation lock, checks reader
  leases and independently acknowledged protected evidence, re-reads every
  object and structured record, verifies the live sealed local data against the
  archive, and writes a transaction-ID-bound gate before CP2's exact partition
  drop helper. A committed/cached verification does not authorize a later drop.
  This path requires a `generated-` origin, preprod identity, an injected immutable
  generated transport, and explicit qualification enablement. Runtime cloud
  mutation authority remains unqualified and retirement is OFF.
- `ArchiveHistory.read_generation()` is the route-neutral supported historical
  interface used by CP3's explicit `/history/archive/{generation_id}` endpoint.
  It queries local data under the generation read lock, or, after retirement,
  resolves the catalog and authenticates/validates archived bytes. Opaque cursors
  include generation and source/event identity. `price_inputs()` exposes exact
  Decimal values and full provenance for offline calculations. Missing/failed
  retrieval is an explicit error; there is no cloud fallback for current price.
- Runtime entrypoint: `python -m postgres.lifecycle_worker --once --bootstrap`
  prepares A explicitly; later invocations omit `--bootstrap`. The worker reads
  dedicated lifecycle `DSN_FILE`, `TRADEBOT_DATA_MODE` (generated/replay),
  `TRADEBOT_ORIGIN_ID`, optional `TRADEBOT_QUALIFIED_GENERATION_BYTES`, and
  `TRADEBOT_OUTBOX_MAX_PENDING` (default 10,000 pending records). Runtime cloud and
  retirement flags must remain false. Without a qualified transport it rotates
  and reports an archive hold. No live source or cloud client is installed here.

## Bounded qualification, not capacity evidence

Default archive limits are 500 rows/page, 2 MiB compressed/object, 4 MiB decoded,
16 MiB transfer/cycle, 24 transport requests/cycle, 20 seconds/cycle, 4 seconds/I/O,
and 128 manifests/generation. SQL statements receive remaining cycle deadlines;
new connections require their five-second reserve. Exceeding a bound preserves
local data. Final readback must fit one bounded cycle; no prior proof is reused.
The raw partition allocation threshold excludes core, outbox, WAL, temporary
files, logs and images and is not a production sizing statement. Pending outbox
admission is bounded by CP3; lifecycle independently holds if its bound is passed.

## Local verification

- `python3 -m unittest discover -s backend/tests -p 'test_postgres_lifecycle*.py' -v`:
  14 focused tests passed; five PostgreSQL integration tests skipped because no
  isolated DSNs/running local daemon were supplied.
- `/Users/jake/Documents/Trading_bot_Analytics/.venv/bin/python -m unittest discover -s backend/tests -q`:
  86 tests discovered, 81 passed, five database integration tests skipped.
  The existing virtual environment was used without modification. The system
  Python broad-suite attempt lacked the pre-existing websockets dependency.
- `python3 -m compileall -q backend/postgres`: passed.
- `git diff --check`: passed before commit.

Unit coverage includes decimal/source/wire preservation, chunk corruption and
identity mismatch, gzip expansion bound, request/time/data limits, upload outage,
ambiguous upload, cancellation, manifest restart, fresh final readback, missing
objects, changed local evidence, reader/protection holds, runtime refusal,
structured corruption/retry, historical pagination, and empty generations.

The authored PostgreSQL tests require `TRADEBOT_TEST_LIFECYCLE_DSN` and
`TRADEBOT_TEST_APP_DSN`, the CP2 migrated isolated preprod schema, and CP3 API
modules. They perform actual A→B→A→B partition cycles, concurrent write/switch
locking, B ingestion while A archives, late event routing, persistent checkpoints,
actual partition absence plus supported HTTP history and Decimal calculation
retrieval, reader drain, protected evidence survival, missing/corrupt objects,
and rejection of a committed old-transaction retirement checkpoint. They remain
unverified until the parent runs the integrated Linux/Docker suite.

## Remaining gates and limits

No production/PP database, Supabase bucket/table, AWS resource, real collector,
service, paid AI, database copy, WAL setting or manual VACUUM was touched.
CP6 must qualify the actual private history_v2 adapter, credentials/grants,
exact readback, compatibility, and effective mutation authority. Current mock
transport cannot authorize real cloud-backed retirement. CP7 must measure
capacity/latency and aggregate storage growth; retained acknowledged outbox,
core/catalog and dedup identities have no production compaction policy here.
There is no claim that these small fixtures meet production response targets.

Official Supabase references checked for the transport contract on 2026-11-12:
[changelog](https://supabase.com/changelog.md),
[private storage access](https://supabase.com/docs/guides/storage/buckets/fundamentals),
[authenticated downloads](https://supabase.com/docs/guides/storage/serving/downloads),
and [standard upload conflicts](https://supabase.com/docs/guides/storage/uploads/standard-uploads).
Private downloads require authenticated access. Duplicate upload conflicts are
not evidence of equality; replacement is deliberately absent from this contract.
