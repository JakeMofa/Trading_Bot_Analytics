-- Disposable, unlinked local Supabase project only.
begin;
create table public.lab_archive_rows (
    owner_id uuid not null,
    generation text not null,
    outbox_id bigint not null,
    decimal_text text not null,
    primary key (owner_id, outbox_id)
);
alter table public.lab_archive_rows enable row level security;
revoke all on public.lab_archive_rows from public, anon, authenticated;
grant select on public.lab_archive_rows to authenticated;
create policy own_archive_read on public.lab_archive_rows for select to authenticated
    using (owner_id = (select auth.uid()));

create function public.lab_archive_page(after_id bigint)
returns table (generation text, outbox_id bigint, decimal_text text)
language sql stable security invoker set search_path = ''
as $$
    select a.generation, a.outbox_id, a.decimal_text
    from public.lab_archive_rows a
    where a.owner_id = (select auth.uid()) and a.outbox_id > after_id
    order by a.outbox_id limit 500
$$;
revoke all on function public.lab_archive_page(bigint) from public, anon;
grant execute on function public.lab_archive_page(bigint) to authenticated;
commit;
