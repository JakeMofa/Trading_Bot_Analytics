# Final fresh-A archive-only drain

Source-only candidate on `0c86b47` (the existing #190 merge). This candidate does
not modify preprod HEAD, release profiles, controller code, cloud policy or any
migration. The old `pp_historical_drain` command remains restricted to historic
`pp-live-pp` B. It cannot safely perform this final trial-A operation and is
unchanged here.

## Exact final-tail seal

New module `postgres.pp_final_trial_drain` seals only the current final fresh A
of `pp-live-pp-trial-20261119-01`, after durable OFF. It requires:

- Explicit execute flag, separate `TRADEBOT_PP_FINAL_TAIL_DRAIN=true` opt-in,
  exact preprod/live trial origin and original cycle anchor/policy environment,
  the fixed lifecycle credential mount, and persistent collection/cloud/
  retirement/AI flags OFF. The local command reads no cloud credential or ticket.
- Actual `tradebot_pp` foundation identity and `tradebot_lifecycle` login, checked
  inside the bounded transaction. All PP writer rows are locked and must be OFF
  with NULL session/lease; no database collector flag may remain ON.
- Exact current final-A UUID, writer epoch, positive raw count under the existing
  64,000-row/128-manifest archive ceiling, fresh operation UUID, offline source
  SHA and separately pinned original trial/retirement source SHA.
- Exactly the original A → B → final A UUIDs in the original trial namespace,
  with matching switch seal/start timestamps. Both predecessors must be retired
  with absent physical raw children, verified seals and retirement times within
  their original 30-minute windows and original finite session expiry. Initial A
  must have retired before the B→fresh-A switch.
- The original anchored admission receipt and both existing retirement receipts
  must match the source, successor UUIDs, seal hashes/counts, nonzero concurrent
  successor writes, transaction ID and policy/history-proof hashes. The seal
  records hashes of these receipts. The caller must supply independently
  reviewed canonical SHA-256 digests for all three receipts; any byte drift
  rejects the first operation as well as a retry. Admission/retirement rows stay share-locked
  during the local transaction. This validates the recorded retirement chain;
  it is not a new cloud proof or a full application/history trial verdict.

The command uses the existing 20-second operation budget, raw/structured worker
locks, global PP admission lock and writer barrier. It seals only final A,
increments its writer epoch and records `trial-tail:seal-only-v1`. Its writer
pointer stays on final A. It allocates no successor and grants no retirement
capability. The retained final partition, shared core, deduplication, both
previous retirement records and source outbox bodies remain intact. The receipt
always says `retirement_authorized=false` and `trial_completion_claimed=false`.

An identical operation retry returns the same seal timestamp, including after
archive verification. Any changed anchor, generation, source, epoch, count or
receipt fails closed. Journal failure rolls the seal and epoch back together.
Normal collector enable rejects the resulting sealed final writer.

## Bounded operator invocation

Run only after the release operator independently proves real processes stopped,
durable OFF/session NULL/lease NULL for every PP writer, original anchor and both
completed retirements, and exact source/image/module byte bindings. A source
argument alone does not prove which executable ran. Capture current final-A
UUID, writer epoch and raw count immediately before execution.

In the separately bound disposable local maintenance candidate, with only the
existing restricted lifecycle secret mounted and all persistent flags OFF:

```text
TRADEBOT_ENVIRONMENT=preprod
TRADEBOT_DATA_MODE=pp_live
TRADEBOT_ORIGIN_ID=pp-live-pp-trial-20261119-01
TRADEBOT_PP_WINDOW_POLICY=two-official-markets-cycle
TRADEBOT_PP_CYCLE_INITIAL_A=<original-initial-A-UUID>
TRADEBOT_DATABASE_DSN_FILE=/run/secrets/lifecycle_dsn
TRADEBOT_PP_FINAL_TAIL_DRAIN=true

python -m postgres.pp_final_trial_drain --execute \
  --origin pp-live-pp-trial-20261119-01 \
  --anchor <original-initial-A-UUID> --retired-b <retired-B-UUID> \
  --generation <current-final-A-UUID> --writer-epoch <reviewed-epoch> \
  --raw-count <reviewed-count> --operation <fresh-operation-UUID> \
  --source <reviewed-offline-candidate-SHA> \
  --trial-source <exact-source-recorded-in-both-retirement-receipts> \
  --admission-sha256 <reviewed-admission-cursor-digest> \
  --retirement-a-sha256 <reviewed-initial-A-retirement-cursor-digest> \
  --retirement-b-sha256 <reviewed-B-retirement-cursor-digest>
```

Compute each reviewed digest as `sha256(encoded(cursor))` using the existing
`postgres.archive_codec` canonical encoder, from independently read full cursor
objects. Do not derive them inside an unreviewed execution wrapper.

Independently reconcile the committed seal/checkpoint and unchanged pointer/OFF
state. Reconcile ambiguity with exactly the same operation; never rewrite the
seal time or substitute a different target.

Use the already qualified **trial-scoped** structured writer and raw Storage
identity, never the historic origin's credentials. Existing bounded page calls
are sufficient; no worker or limit is widened by this candidate:

```python
drain_bounded(repository, trial_transport_factory, execute=True,
              origin_id=TRIAL_ORIGIN,
              limits=DrainLimits(max_cycles=1, max_cycle_rows=50))

pp_sealed_archive.cycle(repository, trial_raw_transport, origin=TRIAL_ORIGIN)
```

The existing structured page requires authenticated exact remote readback before
ACK. The existing raw cycle refuses transfer while final-A structured records
are pending, and preserves its 500-row/eight-request/20-second and codec byte
bounds. Repeat pages only inside an independently bounded operator operation
with a reviewed total cycle/deadline cap derived from the exact pending/manifest
inventory, stopping on failure or complete exact verification. Both retired
predecessors are ineligible for selection, so final A is the only sealed raw
generation in this exact namespace. Source-only tests do not authorize an
unbounded worker, new credentials or policy/grant changes.

Finish with independent exact object/receipt/envelope/catalog readback and a
local retained-data fingerprint. Keep final A attached and verified, its writer
OFF, and original A/B retired history unchanged. Do not call the retirement
verifier with final A as an outgoing target: it has no collecting successor.

## Qualification

25 tests passed without skips on fresh disposable PostgreSQL 17.2 with restricted
roles and generated remote transports. The new fixture uses genuine Store
capture, both actual permit-bound privileged predecessor removals, durable OFF,
final-A seal, existing trial-scoped structured/raw ACK and archive verification,
and retained final-partition checks. Wrong scope/UUID/epoch/count/source,
changed admission/successor/boundary, missing completed-retirement state, late
retirement, enabled expired other writer and journal rollback reject safely.
Corrupt structured and unavailable raw readback retain local data and permit
exact retry. Stable replay after sealing and verification keeps its original
seal and receipt hashes. Historic B, sealed archive and structured drain suites
pass unchanged. No cloud, PP/prod, release or host action occurred.

The generated fixture does not wait through real markets or measure hosted
throughput. Existing real trial observations, cloud identity/readback and the
operator's exact deployed-candidate qualification remain separate evidence.
