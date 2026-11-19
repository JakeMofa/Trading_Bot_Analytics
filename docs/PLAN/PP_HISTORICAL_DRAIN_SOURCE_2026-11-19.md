# Historic PP B seal and bounded archive candidate

Source-only qualification from `e00bd2c`. The user requested preservation and
Supabase archival of old A/B before a separately scoped fresh trial. No hosted
execution, cloud transfer, release, schema or grant change occurred here.

The existing PP21 A is already sealed/verified. B is still `collecting` despite
its durable writer being OFF, so the sealed raw worker correctly does not select
B. Restarting that writer or rotating into occupied A is unnecessary. The narrow
candidate seals exact B for historical archival, without creating a successor,
switching its writer pointer, retiring anything or changing A's original seal.

## Local admission and mutation

`postgres.pp_historical_drain` accepts one canonical B generation UUID, exact
reviewed writer epoch and positive raw count, canonical operation UUID, and the
40-character reviewed source SHA. Execution requires an explicit flag, exact
old `pp-live-pp` environment, the fixed lifecycle secret mount, and collector,
cloud-service, retirement and AI flags OFF. It reads no cloud secret or ticket.
The separate release/operator binding establishes which immutable candidate
image actually runs; the receipt's source argument alone is not that proof.

A 20-second operation acquires the existing raw/structured origin worker locks,
the global PP collector-admission lock, then the writer row lock. It requires
all PP collectors OFF and the target writer's session/lease NULL. The exact
current B must be unsealed, have no archive manifests and still match the
reviewed count, under the unchanged 128×500 sealed-worker row/catalog ceiling.
The physical child must remain attached with the exact UUID partition bound.

One transaction sets B's real seal time and count, increments its writer epoch
and writes `historical-drain:seal-only-v1`. It leaves the writer pointer, raw
rows, A, shared core, deduplication and structured source bodies intact. A
checkpoint failure rolls back the seal and epoch together. An identical replay
acknowledges the same committed operation and seal timestamp; a different
operation/epoch/source/count cannot reseal or replace it. Normal enable and
Store ingestion reject the resulting non-collecting old writer.

This checkpoint is not `retirement:pp-fresh-readback`, issues no ticket and
explicitly records `retirement_authorized=false` and
`original_trial_satisfied=false`. It does not turn old observations into a
successful fresh two-market trial. The writer has no collecting successor in
its origin, so normal PP retirement admission also remains unsatisfied.

## Finite operator sequence after exact release qualification

1. Independently capture A/B/core/outbox/dedup fingerprints and the exact old B
   UUID, current epoch and count. Prove the real old collector stopped and the
   durable flag OFF/session NULL/lease NULL. Keep every other PP collector OFF
   during the local seal. Do not infer OFF from an expired lease alone.
2. In the independently bound candidate with only the reviewed lifecycle mount,
   use the existing preprod/live old-origin environment, all persistent flags
   OFF and the additional exact opt-in `TRADEBOT_PP_HISTORICAL_DRAIN=true`:

   ```text
   python -m postgres.pp_historical_drain --execute \
     --generation <reviewed-old-B-UUID> --writer-epoch <reviewed-epoch> \
     --raw-count <reviewed-count> --operation <fresh-operation-UUID> \
     --source <exact-reviewed-release-SHA>
   ```

3. Independently read the committed checkpoint, same writer pointer and OFF
   state, new B seal and unchanged A/raw/core/dedup/source-body fingerprints.
   After an ambiguous command result, reconcile or repeat exactly the same
   operation. Never substitute a new operation or rewrite a seal timestamp.
4. Use the already reviewed old-origin structured worker/drain. Each bounded
   page needs authenticated exact remote readback before ACK. Then use the
   existing `pp_sealed_archive` worker; it selects sealed B and refuses raw
   upload while B has pending structured records. Each existing cycle keeps its
   500-row page, eight-request, 20-second and codec byte bounds. Its catalog
   remains capped at 128 manifests. No limits were enlarged here.
5. Stop those operator-owned workers after the finite reviewed drain. Prove B's
   exact verified catalog and authenticated remote rows/objects, plus unchanged
   local retained data. An idle worker or a local `verified` state alone is not
   an independent full-history readback. Reuse the existing bounded read-only
   audit/restore paths as separately reviewed evidence. Original expired A
   authority remains expired. Neither generation is detached or deleted.
6. Admit the separately qualified fresh trial origin only after its own release,
   cloud identities, environment, capacity and ownership checks. This module
   provides no new-origin admission or runtime profile.

## Qualification and limits

Twenty tests passed without skips on disposable local PostgreSQL 17.2 with
restricted app/lifecycle/migrator roles, and generated archive transports:

- Genuine Store capture, A→B, durable OFF, exact B seal and stable replay.
- Wrong UUID/count/epoch, expired-but-enabled writer and another PP collector
  rejected; journal failure rolled back seal/epoch atomically.
- An in-flight Store write drained before OFF/seal; the changed reviewed count
  rejected archival admission and preserved both committed B rows.
- Existing sealed structured/raw workers reject corrupt structured readback
  before ACK and unavailable raw readback before verification; retry succeeds.
- Exact retained A metadata/catalog, both raw inputs, shared price/core evidence,
  deduplication and structured source bodies match before/after. Only genuine
  ACK and new B seal/catalog/checkpoint metadata change.
- Existing archive/drain bounds, no-secret default OFF and failure retention
  controls pass. No partition is removed and no collecting successor is made.

The local fixture has two tiny generations. It establishes code/transaction
and existing-worker compatibility, not hosted capacity, actual Supabase
permissions/availability, full PP21 transfer time, or a real fresh trial pass.
