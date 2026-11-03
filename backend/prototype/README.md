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

## Generated application compatibility adapter

`application_store.ApplicationStore(root, legacy, routing=False, retirement=False)`
is a separate generated qualification layout. Both gates default disabled; there
is no production path or environment bypass. It namespaces registry tables under
`ab_`, retains legacy raw read-only and migrates structured rows/protected evidence
into the real application schema in core. Original observation/snapshot/prediction
IDs and cloud cursors remain unchanged. New global IDs reserve all legacy IDs;
legacy composite stream identities have durable sequence mappings. Existing
un-namespaced prototype fixture cores are not an in-place migration source.

`connection()` belongs to its caller; `reader_connection()` is query-only. Raw
saves use durable intent routing, not inserts into UNION views. REST and WS saves
serialize under the existing Store lock, with no new thread/service/queue and a
bounded0.5s contention hold; SQLite still uses5s busy timeout without retries.
Readers pin generation handles until close. A critical raw failure latches a
runtime hold; full slots stop the supervisor without automatic save retries.
Actual collector/streaming/feature/forecast/ensemble/history/lifecycle functions
have explicit optional adapter seams; their default monolithic path remains.
The AB layout has a marker and write guards requiring an adapter connection;
older direct SQLite writers fail. Recovery after committed new writes is forward.

Migration tests are deliberately bounded to10000total legacy rows,128MiB audited
row encodings and1MiB/row. They stream the audit and copy structured rows only;
no database copy, raw A->B transfer or production migration is provided. The
known external-content news FTS index is rebuilt from preserved news rows.
Unknown evidence schemas, missing raw references and unknown virtual tables hold.
These generated limits cannot qualify the existing production legacy volume.

`compatible_cloud.CompatibleCloud` exercises existing SupabaseHTTP wire/schema
and checkpoint functions with original phase deadlines. Private GETs retry at
most3times; conditional uploads never overwrite, and ambiguous writes reconcile
remote identity without another POST. Raw manifest/checkpoint evidence is committed
locally only after object readback and remote confirmation. Real RLS/authentication
is NOT certified by MockTransport fixtures. `HardArchiveReads` encloses the whole
logical request/body/backoff in a child, kills and reaps on deadline, bounds output
and rejects multithreaded callers. It requires a separate single-thread lifecycle
process (the existing lifecycle process model); it is not a collector GET helper.
Kernel child-reaping time and physical power-loss behavior are not hard-real-time
or hardware qualifications.

Focused application/migration/cloud/deadline cases:

```
.venv/bin/python -m unittest discover -s backend/tests -p 'test_ab_*.py' -v
```

Linux root CI additionally exercises actual retirement after application handles
drain. No fixture test supplies production authority or clears capacity STOP.
