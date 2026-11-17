# PP archive and retirement flow — November 17, 2026

## Requested functional result

The user wants a bounded PP test of the complete sequence: A collects; a
qualified size trigger switches durable writes and dashboard state to B; sealed
A's required structured history reaches private `history_v2`; its raw chunks
reach private Supabase Storage; authenticated readback proves exact identity,
coverage, checksums, decimals, timestamps and provenance; protected references
and readers clear; then only A's local PostgreSQL partition is retired. B must
continue acknowledging writes during A's archive work. There is no additional
72-hour wait after A seals. This is a **separate checkpoint** from the first
at-most-30-minute PP live collector/query/market-boundary session. A and B do
not each receive a 30-minute timer. The 72-hour-or-qualified-size policy stays.

## Read-only cloud and code inventory

On November 17, the connected target project `xttdqeimdujweijxcuro` reported
ten private `history_v2` tables, zero `history_v2` RLS policies, only `postgres`
table grants, no `tradebot*` database role and zero `storage.objects` policies.
The `market-raw` bucket is private. No cloud records or objects were read or
written during this inventory. These findings agree with the schema-only CP6
installation report, and show that a narrow PP runtime identity is **not yet
authorized** to import structured history or upload raw objects.

`SupabaseStorageTransport` has bounded create-only raw upload and authenticated
download but rejects structured writes/readback. The deployed lifecycle command
keeps cloud and retirement OFF. `archive.retire_generation_partition` currently
permits only generated qualification origins. Existing `ArchiveWorker` can
perform small generated archives with a mock transport, but its generated-only
retirement proof does not authorize deleting a PP-live partition.

The proposed `ScopedArchiveTransport` composes raw and structured clients while
binding both to one exact origin/generation. It explicitly claims no retirement
authority. Generated HTTP and isolated PostgreSQL tests are required before its
PR is described as passing; they do not prove live Supabase permissions or
throughput. Any malformed cross-origin object key or structured envelope must
stop before I/O. A corrupted readback must preserve local A.

## Gates for the later bounded PP full-flow trial

1. Review and qualify a dedicated PP identity, private namespace, narrow
   `history_v2` grants, and Storage create/read policies. Test that overwrite,
   move and delete are denied to ordinary runtime identities. Keep privileged
   service-key/admin mutation paths inventoried; Supabase states service keys
   bypass Storage RLS.
2. Implement and qualify structured import with immutable conflict checks,
   ordered mutable market/current-price revisions, exact authenticated
   readback and generation-specific acknowledgements. Preserve the existing
   public history and keep PP origin distinct from production.
3. Measure PP live growth, then qualify a size trigger that switches A→B within
   a bounded window without violating the 72-hour-or-size rule. Verify B writes,
   API/SSE/dashboard and query continuity while A's archive runs. Failure or
   outage keeps A local and reports backlog.
4. Separately review mutation protection through final verification and local
   removal, protected-reference preservation, reader drainage, exact scope and
   recovery. Retire A only after fresh authenticated readback and every gate
   passes. Never infer permission continuity from a cached proof alone.

The first <=30-minute live session keeps cloud sync and retirement OFF. The
later full-flow test is not enabled by a passing generated fixture, by the
schema's presence, or by the published PP code alone. Production and paid AI
remain unchanged.

Documentation checked: [Storage access control](https://supabase.com/docs/guides/storage/security/access-control),
[Postgres roles](https://supabase.com/docs/guides/database/postgres/roles), and
the [Supabase changelog](https://supabase.com/changelog.md). The November 4
CLI v3 breaking change affects future CLI commands; this review used the
connected read-only SQL tool and did not invoke the CLI.
