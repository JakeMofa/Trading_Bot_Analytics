# Generated A/B/core prototype

Not a production adapter; no live module imports this directory. `Store` accepts
only an owned0700`generated-ab-*` directory outside production. One serial raw
writer uses FULL WAL connections. Core intents recover individual durable file
commits; there is no claim of atomic multi-file WAL commits.

Run tests with the project's environment:

```
.venv/bin/python -m unittest discover -s backend/tests -p test_raw_generations.py
.venv/bin/python -m unittest discover -s backend/tests -p test_ab_capacity.py
.venv/bin/python backend/prototype/qualify_ab.py
```

The fixed profile creates4000generated records,A/B/core and generated archive
objects. It retains fixtures at the reported private path; do not commit them.
It uses simulated72h timestamps, not72h elapsed observation. A bounded RAM projection selects the exact indexed price/metadata candidates
and17candle rows, then reuses unmodified features.calculate/forecasts.baseline.
It persists generated snapshots,predictions,model/abstention details and generation
evidence references in core. This is not a live API/lifecycle adapter.
Linux CLI preserves512MiB address-space and170s work/180s whole-workload limits;
all fixture files,archive objects and sidecars count against2GiB. Other platforms
report RSS and elapsed; they do not establish Linux virtual-memory qualification.

Complete OS descriptor proof and actual retirement require Linux root. CI adds
an isolated sudo generated-test step only; no secrets/network/production DBs.
An unsupported or incompletely visible descriptor namespace is NOT PROVEN, never
permission to unlink. Ordinary metadata connection close handles empty sidecars;
there is no checkpoint pragma, WAL truncation or separate WAL/SHM deletion.

Registry states:preparing->active->sealed->retiring->retired. Onlyoneactive and
onelivegeneration/slot are enforced by unique indexes. Immutable UUID filenames
prevent A/B role reuse from overwriting history. Pending raw intents are bounded
by the single caller; current raw commits precede acknowledgment. Durable event
IDs prevent local-key reuse and duplicates across retirement. The identity ledger
is part of core growth and cannot be omitted from production capacity planning.

Lifecycle workers use worker_session() for worker-owned core connections; reads
open their own SQLite connections. Only collector thread may route/write/handoff.
No unbounded queue:occupied slots or quotas produce explicitSTOP. History queries
are limited10000rows, archive batches1000rows, manifest lists10000perdataset/gen.
These are prototype controls, not proof of real workload coverage or a license
to silently truncate. A production adapter must report unsupported lookbacks.

Archive bytes preserve JSON number text; existing retention_recovery.verify_archive
and build_manifest validate size/SHA/count/full identity boundaries/exact decimals.
Retirement rereads objects freshly,checks exactlocalcoverage,corepinned evidence,
strictnewestreceipt>72h and draines handles before removing onlygeneratedmain DB.
Core ledger/protected records/markets/predictions/outcomes/manifests persist.
Full slots,archive failure,reference failure or an unknown reader retain files.

The proposed16GiB normal/21GiB migration budget is preliminary arithmetic under
explicit caps/empirical allowances, not a representative capacity qualification.
No runtime configuration or production migration command is supplied by this
module. See the authoritative roadmap and the consolidated qualification report.

`feature_inputs.py` selects at most one price/metadata candidate per generation,
plus the durable metadata pin, core REST price candidate and17completed candles.
It uses the unchanged feature SQL and matching expression indexes on generated
files; the RAM projection is query-only before calculation. Core capture is a
single worker-owned transaction containing the real snapshot,baseline/model/
abstention details and copied generation-qualified evidence. There is no global
read transaction across files and no claim that old live SQL is already routed.
A generated flat-history comparison proves feature/quality/evidence equivalence,
including future-source exclusion and a source-late event. Existing discovery/
serial-worker/publication tests still exercise the preserved application code.

Normal production collector/API/lifecycle adapters, legacy structured-table and
ID/reference migration, existing Supabase structured sync and full-scale shape
qualification remain explicit promotion gates. Do not load this prototype into
production merely because its scaled Linux test passes.
