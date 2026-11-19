# Finite read-only retained A audit candidate

This command measures an existing sealed A after the original trial deadline.
It never issues/reads/consumes a permit, writes a lease/checkpoint/cursor/ACK,
changes the seal, changes a grant, or calls any retirement/DROP function. Its
result explicitly says `original_trial_satisfied=false` and
`retirement_authorized=false`. A diagnostic timing pass cannot repair PP18's
historical retirement HOLD.

## Exact intended operational scope (not executed)

- Local database `tradebot_pp`, origin `pp-live-pp`.
- Retained A `2f5ab434-14c0-4a61-8b8e-145c9a05f0e6`, exactly 28,411 raw rows,
  57 catalogued raw objects, and 31,162 structured rows across 63 real pages.
- Opposite generation `23f4ccb8-c243-4eae-bbd2-8c75aae9816a` remains bound in
  writer state. This audit does not require B to advance while the collector is
  OFF and cannot claim concurrent B persistence evidence.
- The exact original seal hash must be supplied from the reviewed retained
  generation binding; the audit rejects any mismatch before cloud I/O. The final
  read-only snapshot at 08:56:09.912353 UTC records seal hash
  `bd8e9f5da7951f0ee72a01bf26a48133d258d42da10d24190a1738bcfdc27250`.
  Original seal deadline
  from recorded inventory is `2026-11-19T09:00:04.617214+00:00`.
- All 57 authenticated raw GETs/decode/local exact row comparisons and all 63
  rich structured reads/local exact envelope comparisons run in one bounded
  invocation. No prior partial proof can be combined to pass.

Use the released source/image only after sealed coordinates the host window.
No host action has occurred for this candidate. Do not dispatch the destructive
retirement command as an audit substitute.

## Identity and permission bounds

The dedicated CLI is `python -m postgres.pp_retained_archive_audit`. It requires
exact `TRADEBOT_PP_RETAINED_ARCHIVE_AUDIT=true`, PP environment/origin/data mode,
`TRADEBOT_DATABASE_DSN_FILE=/run/secrets/pp_retained_reader_dsn`, no inline DSN,
collector/retirement/paid AI/persistent cloud flags false, and no mounted
`/run/secrets/pp_retirement_ticket`. No existing deployment profile enables it.

The staged private local DSN must log in as **tradebot_reader**, never lifecycle,
owner, migrator or admin. Existing foundation/business grants provide SELECT on
all six required tables. Startup checks identity, database, read-only status,
schema USAGE and every SELECT privilege; missing grants HOLD without trying to
add them. The proof uses one REPEATABLE READ READ ONLY local snapshot and an
ACCESS SHARE lock on `raw.events`, compatible with ordinary inserts. It opens
no generation FOR UPDATE lock and creates no persistent reader lease. Individual
queries and the total local transaction remain deadline-bounded. Existing
connection environment checks precede this archive snapshot, inside the same
operation budget.

Raw Storage uses the existing independent `history_reader_api_key`,
`history_reader_email`, `history_reader_password`, `history_reader_uid` files
and `reader=True`, which denies upload operations. The structured login remains
**tradebot_pp_history** on database `postgres`, with the existing fixed TLS/CA
binding. It has writer grants; this audit truthfully labels that role and uses
it only through fresh REPEATABLE READ READ ONLY transactions. Authenticated
preflight verifies existing SELECT/schema privileges for all projection,
checkpoint, receipt and immutable-envelope tables before any raw GET. No grant,
policy, role-limit or cloud configuration change is included or required by
default. Missing privileges HOLD for separate review.

## Timing and budget interpretation

The existing exact 240 seconds / 128MiB / 192 logical requests profile and
four-second remote operations remain. The operation clock begins before local
snapshot entry and includes permission checks, complete local inventory, all
raw and structured work, and local snapshot finish. It is an **audit operation
clock**, not a replacement seal clock. The original seal timestamp/deadline and
whether it was already expired are reported separately and never changed.
The reviewed original deadline is a required exact UTC argument; a changed local
seal timestamp HOLDs before remote I/O.

Recorded minimum proof cost: 121 requests and 53,696,972 logical bytes. This
route adds one explicitly counted zero-byte authenticated privilege preflight,
so minimum requests are **122**. Actual Auth refreshes and newer B envelopes
remain counted and capped. The previously recorded conservative newer-envelope
upper bound exceeded 128MiB; actual charges must pass at runtime. Nothing skips
an envelope or raises the cap to force a pass. Logical byte accounting excludes
PostgreSQL/HTTP protocol overhead; it is not network transfer size.

Cold and retained session modes use the separate exact retirement flag from
#169. A finite initial replay can measure the retained mode with phase evidence;
any later paired comparison must repeat the entire proof, retain its own cap,
record order and actual login, and cannot use write/ACK/cursor resets. Avoid
unplanned additional remote load or parallel audit sessions.

Required CLI scope arguments:

```
--sealed 2f5ab434-14c0-4a61-8b8e-145c9a05f0e6
--collecting 23f4ccb8-c243-4eae-bbd2-8c75aae9816a
--seal-hash bd8e9f5da7951f0ee72a01bf26a48133d258d42da10d24190a1738bcfdc27250
--original-deadline-utc 2026-11-19T09:00:04.617214+00:00
--count 28411 --structured-rows 31162 --raw-objects 57 --structured-pages 63
```

This is a candidate binding, not a runnable dispatch: sealed must bind the
released source/image, staged reader files, unchanged recorded seal and exclusive host
window before executing. The candidate adds no host controller/deploy changes.

## Native qualification

The package-invoked PostgreSQL test creates isolated A, seals it one hour before
the audit, archives its raw rows, and captures immutable structured history.
The actual audit runs under tradebot_reader with existing fixture SELECT grants,
compares local/raw/structured data, reports the expired original seal and no
authority, and leaves raw/outbox/generation unchanged. Wrong local identity,
missing local SELECT, wrong structured scope and missing remote SELECT all
reject before raw GETs. A direct mutation attempt inside the local snapshot is
rejected by PostgreSQL READ ONLY. These are correctness controls, not a hosted
57-object/63-page performance result; that exact replay remains unexecuted.

Integrated source validation on preprod `2d706a7`: **383 backend tests run,
334 passed and 49 explicit isolated/external DSN skips**. All **16 native
history transport/inventory tests passed** in a disposable official-foundation
PG17 cluster using CI-style package invocation. The reader used distinct
generated SCRAM authentication through the supplied reader DSN, not a changed
admin username/password. Missing-SELECT coverage uses an already denied
authority table without changing shared ACLs. Exact before/after catalog
equality and final migration/schema validation also passed. The cluster was
stopped and removed. No hosted data,
operator credentials or live host were accessed. The exact 57-object/63-page
hosted replay remains a separate, unexecuted qualification.
