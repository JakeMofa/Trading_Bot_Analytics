# PP retirement phase accounting and opt-in session reuse

Source-only successor qualification, November 19 UTC. This change does not retry
PP18 retirement, deploy, issue a permit, alter the clock or reset a seal.

## Observed PP18 result

PP18 completed the A to B handoff and remote raw archive. Its final fresh proof
returned HOLD `archive_limit` under the unchanged 240-second operation cap;
sealed A retained 28,411 raw rows. The final operator evidence measures
247.855136 seconds from ticket issuance to container termination, including
startup/finalization; verifier-exclusive elapsed, exhausted dimension and
dominant phase are unproven. The required 30-minute B run separately failed
after 20m32.235895s; subsequent cleanup did not make it a continuity PASS.
[Final combined observation](PP18_COMBINED_OBSERVATION_2026-11-19.md) preserves
those actual times and limits.
Standalone final inventory measured 20.009 seconds, 63 structured pages / 31,162
rows, 57 raw objects, 121 minimum logical requests, and 53,696,972 minimum logical
bytes. The conservative newer-revision upper bound was 267,864,233 bytes, so
runtime accounting remains necessary. None of those observations proves a later
operation can fit. The original seal plus 30 minutes remains the original trial
boundary and cannot be satisfied retroactively.

Offline inputs: `/private/tmp/tradebot-pp18-ops/final-inventory.json`,
`final-retire-hold.json`, `retirement-issued-attempt.json`, and `retire.log`.

## Accounting

`verify` adds a bounded `phase_accounting` result on success and the CLI includes
it on operation HOLD. Phase names and SQLSTATE are allowlisted; no SQL, DSN,
payload, identifiers, error messages or permit values enter the summary. Counters
are the existing **logical** requests/bytes, including additional newer revision
charges; they are not protocol/wire traffic. Nested phase totals overlap and
must not be added. The operation total includes local generation entry and final
transaction finish; startup environment/schema/credential validation precedes
this existing operation budget and is not silently charged or moved by this
change. Startup failures report no operation summary.

Spans distinguish local inventory, authenticated raw read/decode (including a
nested Auth token span), local raw comparison, local structured page/encoding,
structured readback/comparison, private connection setup/release, per-page
transaction, identity/checkpoint, exact revisions, latest receipts, newer B
revisions, projection verification, and permitted DROP. The first failed phase
and safe SQLSTATE survive error sanitization. Budget exhaustion is labeled
seconds, requests or logical bytes only when the existing CycleBudget itself
rejects work; a separate page limit is not guessed to be a cycle limit.
Diagnostic failure preserves the original operation exception/outcome.

## Connection behavior

Only exact `TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION=true` opts this one-shot
command into the existing PP-only reusable factory. Missing/false remains cold;
malformed values HOLD. The recurring worker flag cannot enable retirement reuse.
No deploy/controller environment changes are included: operator binding of this
new flag requires a separately reviewed release. Shutdown closes the session.

Each page still revalidates private file/TLS binding, enters a separate short
REPEATABLE READ READ ONLY transaction, reapplies remaining transaction/statement
limits, and checks database/login identity, checkpoint, exact sealed envelopes,
latest receipts/newer envelopes and projections. A physical connection can be
shared, never a transaction or snapshot. Any failure discards it; there is no
hidden retry, partial-proof continuation, ACK/cursor write or authority change.
An explicit later invocation must reread everything and satisfy its own gates.

The original 240-second / 128-MiB / 192-request cycle limits, four-second page
limits, 500-row/4-MiB decoded page limits and original seal-bound deadline remain
unchanged. The binary transport experiment from PR #167 is not incorporated.

## Matched isolated qualification

`test_retirement_readback_reuses_session_with_fresh_snapshots_and_failure_discard`
uses real disposable PostgreSQL 17 and the actual fresh retirement worker + rich
history path, with generated in-memory raw Storage and local raw comparison.
The identical sealed workload has 500 raw rows, 1,000 immutable A envelopes
(999 distinct candles and one price) across two full pages, and one newer B
price envelope/projection. Preparation writes and ANALYZE occur outside timed
readback. Preparation is not evidence of a four-second write budget. Timed
readback uses the unchanged profile and page limit.

Three alternating cold/reused pairs include a deliberate 200ms delay per
physical open. Each mode reads the same exact raw/A/B bytes, charges three
logical requests and 1,245,824 logical bytes, and finishes two distinct committed
read-only transactions. Cold uses two connections; retained uses one.

| Pair/order | Cold seconds | Retained seconds |
| --- | ---: | ---: |
| 1 cold first | 0.688522 | 0.478427 |
| 2 retained first | 0.709623 | 0.483636 |
| 3 cold first | 0.713221 | 0.496516 |

These are setup-sensitive generated measurements, **not hosted latency or proof
that PP18's full inventory fits 240 seconds**. A later representative read-only
hosted qualification needs independent authorization/binding and phase evidence.
The fixture excludes real Storage/Auth/network, local generation locks, concurrent
B ingestion and permit/DROP/commit authority; existing lifecycle integration
coverage remains necessary for those controls.

Negative qualification corrupts a projection between reused transactions (fresh
snapshot observes and rejects it), disconnects during a real projection read
(no automatic reopen/retry), and injects identity failure. Every failed borrow
discards the connection. A later explicit full run rereads raw plus all A pages;
no local row is retired. Fixed-cap, original-seal deadline, sanitized SQLSTATE,
rollback/suppression, diagnostic-failure and separate default-off opt-in tests
cover the remaining source controls.

Psycopg's [transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
explains transaction contexts and rollback/connection-close behavior; this
implementation keeps those boundaries. Supabase's
[changelog](https://supabase.com/changelog.md) was checked for relevant changes;
this PR changes no Supabase API, policy, migration or pooler configuration.

Validation at this milestone: 379 backend tests run, 332 passed and 47 explicit
external/isolated DSN skips; all 14 history transport tests passed against a disposable local PG17
cluster, including the matched comparison and negative tests. `git diff --check`
passed. The PG cluster was stopped and removed after the run; no user database,
host runtime or hosted project was accessed.
