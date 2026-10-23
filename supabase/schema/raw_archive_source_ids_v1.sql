-- Phase 1.75: source-ID ranges make verified raw archives safe to resume and later purge locally.
alter table public.raw_archives
  add column if not exists first_source_id bigint,
  add column if not exists last_source_id bigint;

create index if not exists raw_archives_source_id_range_idx
  on public.raw_archives(source, last_source_id)
  where last_source_id is not null;
