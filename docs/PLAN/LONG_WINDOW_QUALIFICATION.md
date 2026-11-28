# Long-window verification and local retention

A full 72-hour slot exceeds the short rehearsal's 192 requests, 128 MiB and
240 seconds. The current raw archive catalog also caps a generation at 128
objects. At 4.57 million structured records a 500-row readback needs at least
9,140 structured pages before reading raw objects.

## Offline qualification

The generated PostgreSQL 17 test uses two databases and an independently
authenticated archive reader. It compiled a raw object plus 194 structured
pages from a sealed A. Verification advanced to pages 54, 118, 182 and 195
in four invocations. A fresh Python process resumed after page 54 using the
durable journal and the same fixture signing key. The destination received 195 page reads plus one fresh
terminal read during that sequence. A subsequent invocation checked the
terminal page again.

- Each new page uses a fresh read-only transaction on each database. The source
  lease binds the caller's exact origin and generation before a row lock and
  expires after six seconds. A successor committed and another client acquired
  the sealed generation row lock during a destination read.
- A signed durable cursor binds the source seal, certificate expiry, archive
  identity, reader role, permission epoch, version numbers, page count and
  ordered inventory digest. A simulated crash after staging the checkpoint
  rolled it back and the next invocation resumed at the same page.
- The fixture rejects changed source rows, a replaced early destination page,
  changed inventory metadata, a forged cursor, an expired certificate,
  revoked reader access and unexpected write privileges. It checks the final
  digest and authenticates the last page again before taking a short local
  lock. Both source partitions remain attached.

Run from the repository root with the backend dependencies and native
PostgreSQL 17 binaries installed.

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_long_window_shadow.py
```

## Requirements before any hosted retirement

1. The test uses a fixture compiler and explicit version invalidation on two
   local databases. A hosted implementation needs a trustworthy, durable
   inventory that binds the complete source manifest chain, every structured
   revision, current projection dependency, exact Storage object version,
   reader identity and applicable policies. A catalog claiming a version is
   insufficient if a privileged actor can change data without invalidating it.
2. A constant-time terminal sample is meaningful only under that immutable
   inventory contract. Reconcile a real restored cold history and deterministic
   decision across a handoff, then qualify protection from the final authenticated
   check through any local removal. A revoked grant or storage replacement must
   keep local data recoverable. The prototype contains no removal API.
3. Raw partition removal leaves ACKed outbox payloads, protected inputs,
   snapshot links, predictions and deduplication records local. The present
   cold prediction reader still depends on the local outbox for expected
   coverage. Qualify compact immutable coverage and conflict detection before
   pruning records with foreign-key dependencies. The 30-day dedup expiry
   needs an executor and an explicit policy for older replays.
