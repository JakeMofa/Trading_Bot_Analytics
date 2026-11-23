-- Disposable local Supabase lab. Only the lab producer can modify status.
create schema lab_archive_notices;
revoke all on schema lab_archive_notices from public, anon, authenticated;
create table lab_archive_notices.status (
    subscriber uuid not null,
    generation uuid not null,
    phase text not null check (phase in ('sealed','verified','held')),
    primary key (subscriber, generation)
);
create function lab_archive_notices.broadcast_status() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if TG_OP = 'INSERT' or new.phase is distinct from old.phase then
        perform realtime.send(
            jsonb_build_object('generation', new.generation, 'phase', new.phase),
            'archive_status', 'archive-status:' || new.subscriber::text, true
        );
    end if;
    return null;
end
$$;
create trigger archive_status_changed after insert or update of phase
on lab_archive_notices.status for each row
execute function lab_archive_notices.broadcast_status();
create policy lab_read_own_archive_notice on realtime.messages
for select to authenticated using (
    extension = 'broadcast' and
    (select realtime.topic()) = 'archive-status:' || (select auth.uid())::text
);
