# Exact third PP trial scope — offline candidate

This candidate admits only `pp-live-pp-trial-20261119-03` in the existing
`tradebot_pp` database. It creates no infrastructure, credentials or hosted
resources and performs no deployment. Trial 01 and the failed trial 02 retain
their original data, source evidence, partitions, writer pointers and deadlines.
No old initial-A preparation or lease is recycled.

## Admission and retained data

Backend 01 and 02 cloud bindings remain unchanged. New 03 has the exact additional
writer/reader roles `tradebot_pp_trial_20261119_03_writer` and
`tradebot_pp_trial_20261119_03_reader`, plus a distinct raw object prefix derived
from its exact origin. Unknown origins, including04, remain rejected.

Fresh 03 preparation requires all database collectors durably OFF, with null
sessions/leases for every PP writer, under the existing global admission lock.
It additionally requires the exact retained 02 initial A
`41c82044-0fb8-4900-bea0-7c43ba079ff0` to be the sole02 generation, verified,
without a hold, with all manifest totals matching its seal count, every manifest
verified, all outbox rows acknowledged, its physical partition attached to
`raw.events` with the exact original generation bound,
and its OFF writer pointer unchanged. These local checks do not claim independent
remote readback: the new root writer proof separately requires
`trial_02_independent_archive_verified=pass`, based on the actual separate-reader
audit performed before fresh 03 admission.

The host permits fresh enter/ON only for 03. Exact retained 01 and 02 profiles
continue to support OFF/leave recovery and reject fresh enter/ON. A new 03 anchor,
one-use authority, source/image proof, controller installation/identity and
existing root qualification are required. Normal lease ceiling 4560, exact cycle
lease 6600, final-minute admission alignment, two full official markets per
outgoing generation, both original 30-minute seal deadlines, queue cap 10000,
4-second requests, 20-second worker cycles and resource/headroom gates are unchanged.

## Additive policy and local SQL

The repository's local PP migration 0007 adds only 03 capture triggers and extends
the existing exact retirement function to 03 with identical predicates. Existing
migration bytes remain untouched. Its original live-successor, separate fresh
readback, permit, source, policy epoch, reader/reference and physical-partition
checks remain. The issuer accepts03 only under the two-market window. It grants
no authority to retire failed 02, whose original handoff/deadline requirements
remain unmet.

New review-only `pp_trial_20261119_03_structured.sql` and
`pp_trial_20261119_03_storage.sql.in` files add distinct 03 principals/policies.
Existing public/history schemas, migrations,01/02 role grants and policies are
not rewritten. The new fixed03 renderer is create-only and checks exact new
machine UIDs and the independently reviewed current policy-catalog hash. Actual
hosted application requires a separate fresh review; no hosted migration filename
or application is generated here.

Storage uses exact authenticated object GET/upload operation guards, with no
list/sign/public/update/delete authority. This matches current
[Supabase Storage access-control guidance](https://supabase.com/docs/guides/storage/security/access-control).
The current [Supabase changelog](https://supabase.com/changelog) was reviewed;
no relevant SDK/CLI change is needed for these offline SQL templates.

## Credential and proof contract

Container secret targets remain generic; only exact host sources change to
`/etc/tradebot/cloud/trial_20261119_03_*`. Required files are the SQL
`history_writer_dsn` and `history_reader_dsn`, writer Auth
`archive_{api_key,email,password,uid}`, and reader Auth
`history_reader_{api_key,email,password,uid}`. The existing pinned CA is shared.
The API mounts only the four reader Auth files staged separately as
`/etc/tradebot/pp-runtime/trial_20261119_03_history_reader_*`; it receives no SQL
or writer credential.

Root proof files are separately named
`trial_20261119_03_writer_{authority,proof}.json` and
`trial_20261119_03_history_reader_{authority,proof}.json`. Old proof files remain.
Writer verdicts retain the prior actual SQL/Storage scope and add explicit
`sql_trial_01_denied`, `storage_trial_01_denied`, `sql_trial_02_denied`,
`storage_trial_02_denied`, plus the actual02 independent archive audit verdict.
Reader hosted denials explicitly name `retained_trial_01_origin` and
`retained_trial_02_origin`, alongside the existing legacy/list/upload/sign/public
checks. Reader identity, source/image/anchor authority and proof hashing remain
strict. No synthetic result is substituted for a hosted qualification.

## Completion and failure boundaries

The failed 02 seal/audit helper remains pinned02. Final successful-cycle sealing
uses the existing terminal helper with an explicit `--origin
pp-live-pp-trial-20261119-03` and matching environment. Its original 02 default
remains; omission of the explicit 03 selector is rejected before secret access.
Both scopes require the same complete A→B→freshA chain, actual timely previous
retirements, exact final counts/epoch, durable OFF and independent read-only audit.
It creates no fourth generation and grants no deletion of final A.

A hypothetical failed 03 run has no pre-authorized initial-A maintenance shortcut.
Its actual failed identity/source/counts would require a separate exact review.
Network retry changes and diagnosis belong to the preceding recovery milestone;
this patch preserves that source snapshot without changing its behavior.

## Offline qualification

Owned native PG17 tests exercise03 preparation after verified02 archive, refusal
before archive or with missing acknowledgements, no reset of retained 02 or occupied03,
the actual two-leg cycle, both real SQL retirement directions, complete terminal03
archive/readback, and byte-equivalent retained01/02 snapshots. Additive cloud policy
tests verify both prior catalogs/grants/roles, least privilege, cross-prefix denials
and old identity usability. Host/CI tests retain legacy negative checks and verify
retained01/02 recovery. Final test counts are recorded in the operator handoff;
there is no live03 PASS claim.

### Reviewed bounds correction

Trial03 terminal maintenance permits at most 64,000 total acknowledged outbox
rows, using the existing bounded maintenance ceiling. Trial02 keeps its original
10,000 total-row default. Neither pending queue capacity 10,000 nor the requirement
of zero pending rows before sealing/audit changes. Raw/object/request/byte/time
budgets remain unchanged; inventories that do not fit still hold. Native tests
actually ACK 10,001 structured revisions, reject an unacknowledged row, replay it
through fresh readback/ACK, seal, archive and independently verify within the
existing 64MiB audit budget. Separate detached-table and wrong-partition-bound
faults must reject fresh 03 preparation.

The separate scratch operational terminal launcher preserves an explicit
`sys.path.insert(0,'/app/backend')` before imports because its container invokes
Python with `-I`. Offline isolated-Python positive/negative import tests and local
create-only target preparation cover that launcher; no remote execution is claimed.
