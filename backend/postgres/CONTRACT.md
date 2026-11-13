# CP2 shared PostgreSQL contract (local only)

Status: implementation contract; generated qualification pending. Python imports use
`postgres.connection`, `postgres.contract`, `postgres.migrate` with `PYTHONPATH=backend`.
Runtime startup validates only; explicit `python -m postgres.migrate` applies SQL.
`connect(dsn, environment='preprod', readonly=False)` returns a psycopg 3 connection
(dict_row; autocommit=False); validates database identity. `validate_schema(conn,
environment)` is read-only. `apply_migrations(conn, environment)` is explicit.
Dependencies: psycopg[binary]==3.2.13 (parent owns requirements).
Prerequisite: parent/admin provisions restricted tradebot_lifecycle with no owner membership; CP1 role upgrade is separate from business DDL.

All identities are strings. origin_id is durable collector/import namespace,
generation_id is a unique UUID **string**, never slot A/B; event_id is source
identity scoped by origin + source. All monetary values use unconstrained NUMERIC
(no rounding), exact decimal strings in JSON. `source_time` keeps original source
text, `source_epoch` NUMERIC preserves exact fractional epoch seconds;
`received_at` and `available_at` TIMESTAMPTZ are receipt/as-of availability.
`postgres.contract.source_timestamp(text)` returns `(original, Decimal epoch)`;
`canonical_json(value)` returns stable JSON text; `content_hash(value)` SHA256 hex.
JSON payload columns are JSONB; store original encoded wire text separately in
`raw_payload` where original byte representation matters. Content hashes include
provenance and immutable event content, excluding locally repeated receipt times.

## Tables and columns

All PK/FK deletes use RESTRICT/no cascade. Every protected relationship stays in
core. `payload` is a JSONB evidence/provenance envelope, not an unknown zero.

- `core.markets`: PK(origin_id, market_id), source, slug, duration (900/3600),
  start_time/end_time TEXT, start_epoch/end_epoch NUMERIC, target/final NUMERIC,
  result nullable UP/DOWN, status, index_symbol/rules TEXT nullable,
  first_seen/last_seen TIMESTAMPTZ, payload JSONB, content_hash TEXT.
  Mutable market projection; outcomes and raw observations preserve revisions.
- `core.candles`: PK(origin_id,source,symbol,granularity,time), time BIGINT epoch
  seconds; low/high/open/close/volume NUMERIC nullable, first_seen TIMESTAMPTZ,
  payload JSONB, content_hash TEXT. Mutable source candle revisions must be
  explicitly distinguished from immutable event conflicts.
- `core.current_prices`: PK(origin_id,source,symbol), event_id, generation_id,
  source_time TEXT, source_epoch NUMERIC, received_at/available_at TIMESTAMPTZ,
  price/size NUMERIC, payload JSONB, content_hash TEXT. No FK to disposable raw.
- `raw.events`: LIST partition on generation_id TEXT; PK(generation_id,origin_id,
  source,event_id), kind, market_id nullable, symbol nullable, source_time nullable,
  source_epoch nullable, received_at/available_at TIMESTAMPTZ, price/size NUMERIC
  nullable, payload JSONB, raw_payload TEXT nullable, content_hash TEXT.
  FK(origin_id,generation_id) -> archive.generations; nullable market FK -> core.
- `core.protected_evidence`: PK(origin_id,evidence_id), generation_id nullable,
  source/event_id/kind, market_id nullable, source_time/source_epoch nullable,
  received_at/available_at TIMESTAMPTZ, payload JSONB, raw_payload TEXT nullable,
  content_hash TEXT. No raw or generation FK, so archive remains independent.
- `core.feature_snapshots`: PK(origin_id,snapshot_id), market_id, as_of TIMESTAMPTZ,
  version INTEGER, values_json/quality_json/evidence_json JSONB, content_hash,
  UNIQUE(origin_id,market_id,as_of,version); UNIQUE(origin_id,snapshot_id,market_id).
- `core.snapshot_evidence`: PK(origin_id,snapshot_id,evidence_id), FKs to
  feature_snapshots/protected_evidence. Worker protects every referenced raw input
  atomically before acknowledging a snapshot. JSON references alone are not FKs.
- `core.predictions`: PK(origin_id,prediction_id), snapshot_id,market_id,
  model_version, as_of/created_at TIMESTAMPTZ, seconds_remaining NUMERIC,
  probability_up/down NUMERIC nullable, abstain_reason nullable,
  assumptions_json/payload JSONB, content_hash;
  FK(origin_id,snapshot_id,market_id) -> feature_snapshots same triple;
  UNIQUE(origin_id,snapshot_id,model_version).
- `core.outcomes`: PK(origin_id,outcome_id), market_id,evidence_id,
  result UP/DOWN, final NUMERIC nullable, source_time/source_epoch nullable,
  confirmed_at/available_at TIMESTAMPTZ, payload JSONB,content_hash;
  FK market + protected evidence. Revisions are distinct immutable outcome_id.
- `ops.feed_health`: PK(origin_id,source),status,updated_at,last_data_at nullable,
  reconnects BIGINT default 0,detail JSONB default {}.
- `ops.worker_checkpoints`: PK(origin_id,worker),cursor JSONB,updated_at.
- `ops.dedup`: PK(origin_id,source,event_id),generation_id,content_hash,expires_at.
  Bounded expiry requires worker cleanup; retention must cover replay contract.
- `ops.outbox`: id BIGINT identity PK,origin_id,generation_id nullable,entity_type,
  entity_id,content_hash,payload JSONB,created_at,acknowledged_at nullable;
  UNIQUE(origin_id,entity_type,entity_id,content_hash). Immutable content versions.
- `archive.generations`: PK(origin_id,generation_id),generation_id globally UNIQUE,
  slot A/B,state ('prepared','collecting','sealed','verified','retired'),
  partition_name TEXT UNIQUE,created_at,started_at/sealed_at/verified_at/retired_at
  nullable,seal_count BIGINT nullable,seal_hash TEXT nullable,hold_reason nullable.
  Unique active generation and active slot indexes per origin (state collecting).
- `ops.writer_state`: PK(origin_id),generation_id FK generation,epoch BIGINT,
  collector_enabled BOOLEAN false,updated_at. Writer must lock this row FOR SHARE
  during raw write and lifecycle FOR UPDATE during atomic switch/seal. Writer
  checks collecting state; late source events route current generation, never seal.
- `archive.manifests`: PK(origin_id,generation_id,manifest_id),format_version,
  object_key,sha256,row_count,byte_count,coverage JSONB,created_at,
  verified_at nullable,verification JSONB nullable; FK generation.
- `archive.checkpoints`: PK(origin_id,generation_id,consumer),cursor JSONB,
  acknowledged_at; FK generation.
- `archive.reader_leases`: PK(lease_id),origin_id,generation_id,holder,expires_at;
  FK generation. Reader acquisition and retirement serialize via generation lock.

Timestamp columns (except explicit nullable values) and payload/hash columns are
NOT NULL. Optional raw price/size and current size remain NULL when unavailable.
Use `postgres.contract.partition_name(generation_id)` => `events_g_<uuidhex>`.
Lifecycle calls `archive.create_generation_partition(origin_id,generation_id)`
through its dedicated role. Narrow fixed-search-path SECURITY DEFINER helpers
create/drop only registered UUID-derived children; grant SELECT to lifecycle and
reader, SELECT/INSERT to app. Retirement helper currently restricts to generated-
origins in preprod and validates fresh transaction-bound gate evidence. No arbitrary DDL in app startup. Runtime partition changes
are validated against generation registry and inherited schema contract.

## Ownership and migration behavior

Foundation creates raw/core/ops/archive owned tradebot_owner; migrator SET ROLE
tradebot_owner. App cannot DDL or mutate ops.environment_identity/schema_migrations.
Reader SELECT only. Version/checksum/schema ledger uses ops.schema_migrations.
Each apply validates existing ledger + current catalog before executing migration;
repeat is no-op. Applied files cannot be edited. Foundation smoke, when present,
is explicitly validated/excluded from business snapshot. Existing foundation's
environment_identity remains environment-bound. Empty means empty business schema
after foundation initialization, not role/database provisioning.

history_v2 SQL is an additive private **contract artifact only**, outside local
migration discovery. It revokes PUBLIC/anon/authenticated and enables RLS without
public policies; applying or cloud writing remains CP6 and is not authorized here.
