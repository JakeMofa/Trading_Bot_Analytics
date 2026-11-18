# PP cloud binding preflight — November 17, 2026

Status: **offline default-OFF STOP**. This preflight is preparation only. It
does not install files, mount a Compose service, connect to Supabase, start a
worker, enable cloud sync or authorize raw retirement.

`python -m postgres.pp_cloud_preflight` accepts only `preprod`, `pp_live`,
exact origin `pp-live-pp`, and OFF values for Supabase sync, retirement and
paid AI. It requires six separate fixed `/run/secrets/` paths: one publishable
Storage API key; the dedicated Auth email, password and UUID from PR #102's
operator stage; an independent structured `tradebot_pp_history` DSN; and the
local lifecycle DSN. It checks regular, private, single-link, distinct files
by metadata only. It never reads their contents, emits their paths or values,
or sends a network request. Successful validation still exits 1 with STOP and
the unresolved gates in a sanitized JSON result.

The structured role is currently NOLOGIN, and PR #92's
`history_v2.structured_receipts` migration and narrow grants are absent from
preprod/cloud. PR #97's bounded worker remains draft and has no PP service
wiring. PR #103 provides `SupabaseStorageTransport.from_machine_files`, but
this preflight does not instantiate it. PR #104's exact UID Storage policy
candidate, live Storage denial/readback, host file installation and permission
checks, direct PostgreSQL network/TLS/deadline qualification, sustained backlog
drain, and privileged mutation authority remain separate gates. A private file
check alone proves neither the file content nor the remote principal.

Five offline focused tests cover exact identity and OFF flags, path separation,
private file metadata, invalid binding STOP, and valid synthetic files still
returning STOP. No real secret, cloud write, deployment, or production change
was involved. Runtime cloud sync and local retirement remain OFF.
