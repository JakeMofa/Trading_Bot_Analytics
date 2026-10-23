-- TradebotAnalytics Phase 1.75 private Storage buckets.
-- Supabase documents bucket creation through SQL as a supported option.
-- Objects remain private; server-side access uses the project secret/service role.

insert into storage.buckets (id, name, public)
values
  ('market-raw', 'market-raw', false),
  ('knowledge', 'knowledge', false),
  ('backups', 'backups', false)
on conflict (id) do update
set public = false;
