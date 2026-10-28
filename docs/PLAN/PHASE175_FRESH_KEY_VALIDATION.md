# Phase 1.75: bound fresh key reconstruction

The previous apply path rebuilt and sorted keys for both complete raw tables in
every transaction. The captured qualification state contained 247,446
observations and 1,004,317 streams. A disposable-copy collector failed after
5.204 seconds while that reconstruction held the writer lock for 5.352 seconds.
No production apply is authorized by this change.

## Static preparation

Before BEGIN IMMEDIATE, prepare only the fixed cutoff, copied verified manifest
metadata, original manifest boundaries, approved identity sets, and a hint for an
already-existing covering index. Timestamp validity may be cached only as a pure
fact about the exact string. No current row existence, reference, coverage count,
or eligibility fact is reused across transactions.

Filter original manifests to those containing at least one approved identity.
A manifest containing no approved identity cannot authorize any delete. Retain
its full original bounds when it does intersect scope; never clip the bounds to
the approved identities, since an unapproved late row elsewhere in the original
range can invalidate coverage.

## Fresh transaction

Each BEGIN IMMEDIATE still performs these checks before its exact-identity DELETE:

1. Scan current received_at values in BOTH raw tables through a connection-local
   timestamp guard. Cached exact strings avoid repeated parsing; every new value
   is strictly checked. This global guard remains necessary to reject malformed
   rows even outside the active dataset or candidate range. It materializes no
   unrelated identities or payloads, and its callback is removed after the scan.
2. Fetch current keys only for the active dataset inside the envelope of relevant
   original manifests. Normalize and sort those keys. Observations reuse the
   existing observations_market_kind_received covering index when available;
   streams use the existing received_at/source/event_id cursor index. No index
   or durable schema change is made.
3. Count ALL current identities in each relevant original manifest range, including
   unapproved, late, and newer rows. Excess rows invalidate the whole manifest.
4. Re-read the sequence anchor and prediction references. Apply the fixed cutoff
   and approved/pending identity intersection to current rows.
5. Delete only selected exact identities and commit the bounded batch. Hand the
   writer lock back outside the transaction; repeat fresh checks for the next batch.

Raw timestamps remain limited to exact seconds or six fractional digits in UTC.
At zero microseconds, the 25-character form sorts before the 32-character form;
the stream lower boundary includes both forms. Canonical tuple checks still
handle source/event-id ties and precise microsecond bounds.

The invariant remains: final delete set = approved set intersect currently safe
set. Scope may shrink and cannot expand. Unverified archives authorize nothing.

## Validation and limits

Retention 44/44, backend 179/179, streaming 12/12, collector 10/10, historical 3/3,
operations 5/5, deployment controls 6/6. Focused regressions cover bounded active
materialization, malformed unrelated rows, full-original-range late invalidation,
both UTC widths, precise same-second bounds, and reuse of existing indexes.
Existing stale-plan/reference/coverage/cutoff/batch/idempotence tests remain.

A generated in-memory key-scale profile (not a production database) measured the
old exact constructor at 2.020 seconds and new active constructors at 0.574
seconds for observations / 0.644 seconds for streams, including fresh global
timestamp guards. These measurements are not R5/R6 PASS, a full apply timing, or
a safe production budget. Three comparable production-sized trials with the
actual collector default 5,000 ms timeout are still required on isolated compute.

R0-R4 evidence is preserved. R5/R6 remain stopped pending access to the existing
verified AWS snapshot and full qualification. The approved temporary SSH /32 did
not restore connectivity and was removed; the original cloud firewall state was
verified exactly. No test VM was created while its source snapshot was inaccessible.
No large database was copied to the Mac. No merge, deployment, production delete,
retention enablement, guard change, historical rewrite, or Phase 2 is included.
