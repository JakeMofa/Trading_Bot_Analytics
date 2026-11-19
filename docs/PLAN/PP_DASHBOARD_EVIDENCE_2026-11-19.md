# Independent dashboard evidence audit

The existing live observer proves API identity, basic feed/feature freshness,
advancing IDs and limited endpoint reachability. It does not inspect forecast
probability, abstention, model input age or prediction-to-market/snapshot binding.
A nonempty historical list can consist entirely of prior-market or abstaining
records. A prediction ID is a durable output identity, not proof of a number.

`deploy/preprod/dashboard_evidence.py` is an independent **offline** JSONL
processor. It never connects to the network or database, changes a worker, starts
collection or supplies retirement authority. Do not replace the existing observer,
controller, archive/reconciliation or browser acceptance gates with this result.

## Capture contract

Each existing `/state/current` or `/events` response is represented as:

```json
{"at":"2026-11-19T10:00:05+00:00","endpoint":"/state/current","source_sha":"exact deployed source SHA","latency_ms":1,"monotonic_seconds":5,"state":{"environment":"preprod","data_mode":"pp_live","origin_id":"pp-live-pp","generated_at":"2026-11-19T10:00:05+00:00"}}
```

The real `state` must include market start/end/id/active; Coinbase event/source
and generation timestamps; feature snapshot id/market/as-of and price/candle
quality; saved prediction id/snapshot id/market/as-of/UP/DOWN/reason; and RAM
estimate market/as-of/snapshot-as-of/UP/DOWN/reason. Use `capture()` to select
these fields without headers, cookies, keys or unrelated payloads. Original
probability strings remain strings. Its history selection is limited to five
items and never treats those historical items as current numerical evidence.

For the separately authorized local pp17 conductor, `RecordedAPI` wraps exactly
the existing `PrivateAPI.get()` responses and appends `live-payloads.jsonl` after
receipt, including UTC completion time, monotonic time, latency and source SHA.
There are no extra API calls. Existing observer samples/contracts and generation
observations remain independent. The temporary conductor itself is not committed,
executed or deployed by this source change.

## Process a run

```sh
python3 deploy/preprod/dashboard_evidence.py \
  --input /absolute/run/live-payloads.jsonl \
  --generations /absolute/run/live-generations.jsonl \
  --output /absolute/run/dashboard-evidence-result.json
```

Both inputs are local JSONL, capped at 64 MiB each; output is create-only.
Generation rows use the existing sampler's `writer.at_utc` and
`writer.generation_id`. The helper brackets each observed writer change between
two DB observations, selects the nearest state at/before and at/after that
bracket, and retains both classifications and source/input timestamps. It does
not invent an exact switch timestamp or equate a Coinbase event's generation
with the currently active writer. Market rollover and raw-generation rotation
are separate events.

`integrity_result` fails on stale/unbound/invalid published forecast content or
wrong state identity/time. Missing richer evidence or switch sides stays
INCOMPLETE. `numeric_forecast_result` additionally requires three distinct
currently bound saved numerical predictions and numerical saved/live output on
both sides of each observed switch. A truthful nonempty abstention reason with
null probability remains an abstention: integrity may pass, numerical acceptance
remains incomplete. Missing probability without reason stays unavailable.

Saved forecasts require current active market, fresh as-of/feature (0–30 seconds),
exact snapshot identity/time and a source price that was fresh at calculation.
Live numerical estimates additionally require the UI's 0–10-second source tick,
matching volatility snapshot and completed-candle age below 120 seconds. The
report retains current input ages separately from calculation-time freshness.
Probabilities must be finite, within [0,1] and complementary. Stale historical
numbers do not become current because an endpoint returns successfully.

The report does not prove rendered browser content, continuous SSE coverage,
collector ownership, archive verification, safe retirement or predictive skill.
It is sampled evidence, not a guarantee between observations. Existing old
ID-only evidence remains insufficient; do not fill in missing fields by inference.

## Local validation

```sh
python3 -m unittest discover -s deploy/preprod/tests -p 'test_dashboard_evidence.py' -v
```

Fixtures exercise honest abstention versus numerical acceptance, old-market IDs,
stale/future times, snapshot mismatch, stale saved/live inputs, missing switch
sides, malformed probabilities, secret-field omission, decimal preservation and
the executable create-only CLI. No release/host/runner configuration changes,
no merge during the pp17 freeze, and no runtime acceptance claimed here.

## Server comparison clock and cross-host uncertainty

Run evidence exposed a 22–65 ms negative operator-minus-generated delta. The
operator and API run on different hosts; that delta combines clock offset and
response delivery and cannot by itself establish a stale server forecast.
The audit compares server feature/forecast/source timestamps against the API's
`generated_at`, and places API states against database writer switch brackets
using that server timestamp. Original operator acquisition time remains intact.

A separate per-observation delta and aggregate min/max disclose the difference.
The existing observer's -2-second tolerance and the audit's 10-second upper
state-delivery band are reported explicitly; exceeding that band adds missing
clock/delivery qualification, rather than blaming forecast content. Missing
server time fails; stale/future model inputs relative to server time still fail.
No synchronized-clock, network-freshness or exact switch-time claim is made.
The actual switch gate remains INCOMPLETE until evidence brackets a real switch.
This offline reporting correction does not change the deployed API or trial.
