-- TradebotAnalytics Phase 1.75: permanent structured history + archive manifests.
-- Applied to hosted Supabase through the project migration API.
-- Public-schema tables are RLS-enabled with no anon/authenticated policies.
-- The server-side secret/service role is the only intended writer.

begin;

create table if not exists public.markets (
  id text primary key,
  slug text not null unique,
  duration integer not null,
  start timestamptz not null,
  "end" timestamptz not null,
  target numeric,
  final numeric,
  result text check (result is null or result in ('UP','DOWN')),
  status text,
  index_symbol text,
  rules text,
  first_seen timestamptz not null,
  last_seen timestamptz not null,
  raw_json jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now()
);

create index if not exists markets_window_idx on public.markets(start, "end");
create index if not exists markets_result_idx on public.markets(result, "end");

create table if not exists public.candles (
  source text not null,
  symbol text not null,
  granularity integer not null,
  time bigint not null,
  low numeric,
  high numeric,
  open numeric,
  close numeric,
  volume numeric,
  first_seen timestamptz,
  synced_at timestamptz not null default now(),
  primary key (source, symbol, granularity, time)
);

create table if not exists public.feature_snapshots (
  source_id bigint primary key,
  market_id text not null references public.markets(id) on delete cascade,
  as_of timestamptz not null,
  version integer not null,
  values_json jsonb not null,
  quality_json jsonb not null,
  evidence_json jsonb not null,
  synced_at timestamptz not null default now(),
  unique (market_id, as_of, version)
);

create index if not exists feature_snapshots_market_time_idx
  on public.feature_snapshots(market_id, as_of);

create table if not exists public.predictions (
  source_id bigint primary key,
  snapshot_source_id bigint not null references public.feature_snapshots(source_id) on delete cascade,
  market_id text not null references public.markets(id) on delete cascade,
  model_version text not null,
  as_of timestamptz not null,
  created_at timestamptz not null,
  seconds_remaining double precision not null,
  probability_up double precision,
  probability_down double precision,
  abstain_reason text,
  assumptions_json jsonb not null default '{}'::jsonb,
  extra_json jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now(),
  unique (snapshot_source_id, model_version)
);

create index if not exists predictions_market_time_idx
  on public.predictions(market_id, as_of);
create index if not exists predictions_model_time_idx
  on public.predictions(model_version, as_of);

create table if not exists public.official_outcomes (
  market_id text primary key references public.markets(id) on delete cascade,
  final numeric not null,
  result text not null check (result in ('UP','DOWN')),
  confirmed_at timestamptz not null,
  source_json jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now()
);

create table if not exists public.news_events (
  source_id bigint primary key,
  source text not null,
  source_guid text not null,
  url text not null,
  title text not null,
  published_at timestamptz,
  first_seen timestamptz not null,
  last_seen timestamptz not null,
  categories_json jsonb not null default '[]'::jsonb,
  asset_tag text not null,
  synced_at timestamptz not null default now(),
  unique (source, source_guid)
);

create index if not exists news_events_available_idx
  on public.news_events(published_at, first_seen);

create table if not exists public.model_outputs (
  id uuid primary key default gen_random_uuid(),
  market_id text not null references public.markets(id) on delete cascade,
  model_version text not null,
  as_of timestamptz not null,
  probability_up double precision,
  probability_down double precision,
  confidence double precision,
  fresh boolean not null default true,
  output_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (market_id, model_version, as_of)
);

create table if not exists public.evaluation_metrics (
  id bigint generated always as identity primary key,
  model_version text not null,
  checkpoint text not null,
  evaluated_at timestamptz not null default now(),
  metrics_json jsonb not null,
  unique (model_version, checkpoint, evaluated_at)
);

create table if not exists public.sync_checkpoints (
  dataset text primary key,
  last_source_id bigint,
  last_source_time timestamptz,
  last_source_key text,
  rows_synced bigint not null default 0,
  status text not null default 'idle',
  detail text,
  updated_at timestamptz not null default now()
);

create table if not exists public.raw_archives (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  market_id text,
  started_at timestamptz not null,
  ended_at timestamptz not null,
  bucket text not null,
  object_path text not null,
  compression text not null,
  content_type text not null,
  sha256 text not null,
  event_count bigint not null,
  uncompressed_bytes bigint not null,
  compressed_bytes bigint not null,
  verified_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (bucket, object_path)
);

create index if not exists raw_archives_source_time_idx
  on public.raw_archives(source, started_at, ended_at);

alter table public.markets enable row level security;
alter table public.candles enable row level security;
alter table public.feature_snapshots enable row level security;
alter table public.predictions enable row level security;
alter table public.official_outcomes enable row level security;
alter table public.news_events enable row level security;
alter table public.model_outputs enable row level security;
alter table public.evaluation_metrics enable row level security;
alter table public.sync_checkpoints enable row level security;
alter table public.raw_archives enable row level security;

revoke all on table
  public.markets,
  public.candles,
  public.feature_snapshots,
  public.predictions,
  public.official_outcomes,
  public.news_events,
  public.model_outputs,
  public.evaluation_metrics,
  public.sync_checkpoints,
  public.raw_archives
from anon, authenticated;

grant usage on schema public to service_role;
grant select, insert, update, delete on table
  public.markets,
  public.candles,
  public.feature_snapshots,
  public.predictions,
  public.official_outcomes,
  public.news_events,
  public.model_outputs,
  public.evaluation_metrics,
  public.sync_checkpoints,
  public.raw_archives
to service_role;

grant usage, select on all sequences in schema public to service_role;

commit;
