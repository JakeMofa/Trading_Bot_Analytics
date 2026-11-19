# Structured exact readback: reuse already verified canonical bytes

November 19, 2026. Source qualification only. No PP/prod operation, cloud DDL,
grant, runtime flag, image deployment, lifecycle acknowledgement or retirement
authority was changed. Binary results remain a separate experiment; this source
change keeps text results and existing connection/index selections.

## Change and preserved proof

Retirement readback used to serialize its expected list once for validation and
discard those bytes, serialize expected and recovered lists again for equality,
then serialize the recovered list again for size accounting. Each recovered
envelope also passed canonical re-encoding before being encoded again for its
receipt envelope hash.

The candidate returns validation's existing canonical expected bytes. The
unchanged revision query/decode path retains each original `bytea` **only after**
the original JSON/canonical-byte equality, stream scope/schema and receipt checks
pass. Receipt envelope SHA256 is computed from those same canonical-checked
bytes; payload SHA256 and every receipt identity/hash comparison remain checked.
Joining canonical envelopes with exactly `[`/`,`/`]` produces the same canonical
array as the prior encoder. Comparison remains **full byte equality**, not a hash
substitute. The exact compared byte length remains the original A size charge.
Temporary expected, joined and individual raw-byte references are released before
latest/projection reads. No cross-page cache or mutable record cache is introduced.

The verifier still independently reads current latest receipts, rejects ties/
conflicting identities, checks every newer-generation checkpoint, authenticates
newer envelopes, verifies ordering/immutability and matches current projections.
Its four-second cap, read-only repeatable-read snapshot, PP origin/database/role,
index ABI and whole-audit/HOLD policies are unchanged. Original public list return
values and newer-replacement size charges are unchanged.

## Matched generated proof

Native PG **17.2**, psycopg **3.2.13**, libpq **170006**, warm/analyzed disposable
local database. Exact `0219819` baseline and current source run alternately in
the same fixture, **eight full readbacks per arm per G scenario (32 successes)**.
Both arms use fresh connections, text results, `indexed_latest=True` with the
exact reviewed supporting index, and four-second requests. This is not PP,
TLS/Supavisor, a CPU-quota benchmark, or a production percentile claim.

The page has **500 records / K=500**: 499 rich candles plus one mutable current
price. Original canonical bytes **1,975,325**, SHA256
`9616f63207fa5d24ad130da39568ccd7f606e53ea3a45f70cc7cb66554dc9242`.
G=1 adds one independently checkpointed newer-generation price revision; returned
records remain exact original A while the current B projection is authenticated.

| Complete structured read | Baseline mean | Candidate mean | Observed reduction |
|---|---:|---:|---:|
| G=0 | 292.919 ms | 218.404 ms | 25.44% |
| G=1 | 290.744 ms | 219.630 ms | 24.46% |

All **22 matched negative checks** pass: each arm rejects suppressed oversized
envelopes, wrong generation, wrong role, cross-origin expected input, exact
canonical expected-page mismatch, corrupt payload/envelope/content receipt
hashes, noncanonical stored bytes, corrupt newer current projection and corrupt
newer envelope receipt. Network-free regressions additionally check canonical
array equivalence with Unicode, escaped strings, null/bool and exact decimals,
all receipt identity/hash fields, origin/generation scope and result ordering.

[All samples, phase spans, exact source digest and negative checks](evidence/readback-canonical-byte-reuse-generated-2026-11-19.json)
and [native regression result](evidence/readback-canonical-byte-reuse-tests-2026-11-19.json)
are sanitized generated evidence. The native regression suite includes existing
full-path session reuse, expired retained read-only audit, indexed latest ABI/
ties, immutable revision/rollback, newer-projection corruption and byte-budget
tests; its first local setup attempt lacked the reader DSN and was corrected
before the recorded final result.

Reproduce the matched source comparison from the pinned existing environment:

```sh
/tmp/tradebot-cold-reader-venv/bin/python deploy/preprod/bench_readback_canonical.py
```

`--bin-dir` can select an installed local PG17 binary directory. The benchmark
accepts no DSN, creates only its own generated local fixture, and stops its owned
server in `finally`. It writes the generated evidence JSON above. The standard
existing PostgreSQL CI fixture runs `backend.tests.test_history_v2_transport_pg`;
the new network-free tests are discovered with the backend suite.

## Decision and remaining qualification

This is a measured source candidate for reducing redundant CPU work. The native
means save about **71–75 ms/page**; multiplying by 63 native pages gives only
**4.48–4.69 seconds** and is not a PP forecast. A PP quarter-CPU quota, different
record mix and concurrency may change this; scaling elapsed time by quota or
claiming the required approximately 15-second full-audit margin is unsupported.

After exact-source CI/release qualification, compare one bounded matched PP
first page before considering another full audit. Preserve the four-second page
and overall operation limits. Actual full retained-audit completion with useful
reserve, current B writes, reader drainage and the original seal-window verdict
remain separate gaps. This source result cannot convert an expired trial or
prior incomplete HOLD into PASS or authorize A deletion.
