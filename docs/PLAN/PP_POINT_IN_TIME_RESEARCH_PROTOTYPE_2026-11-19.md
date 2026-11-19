# Point-in-time research parity prototype

Source only, isolated generated qualification. No API registration, cloud/host
operations, collection, permissions, retention authority, or runtime activation.

`backend/postgres/research_window.py` composes one explicit 900-second market
window from existing verified `ArchiveHistory` raw reads and an injected
receipt-verifying `read_revisions` source. The reviewed scope binds origin,
generation UUID, market, UTC interval, predictor cutoff, independent label
cutoff, and immutable envelope hashes. It returns captured Polymarket metadata
and quote/book payloads plus saved features, forecasts, and evidence links.
Exchange values remain saved reference inputs. No features are recalculated.

A snapshot's `as_of` is not proof of its publication availability. Every returned
snapshot therefore requires its reviewed `core.snapshot_evidence` edge to a
protected `calculation_inputs/feature_inputs` record. That record must identify
the snapshot, reproduce its exact saved calculation inputs, and have arrived by
the requested cutoff. Saved price/candle inputs and market first-seen times
cannot exceed the snapshot time. Missing publication/link proof fails explicitly.
Forecasts must link to the same snapshot and time and have been created by the
cutoff. Official outcomes require separate Polymarket US protected evidence and
are returned only in the label collection under the independent label cutoff.

The existing cold structured page reader supports snapshots, predictions, and
outcomes, but not protected evidence or evidence edges. This composition uses
the existing revision-source interface directly to include those records;
receipt verification remains the supplied source's responsibility, with exact
reviewed envelope hashes additionally checked here. It does not duplicate a
cloud connection/query adapter or register a second historical endpoint.

## Qualification

Seven new generated tests passed, including one native PostgreSQL 17.2 test with
an actual transactional raw partition DROP through the existing generated
retirement gates. The PG test writes and independently reads actual local
`history_v2` projections, receipts, and immutable envelopes through the existing
`HistoryV2PostgresTransport`. Raw archive objects use the existing immutable
network-free generated transport. Application scope, captured input IDs and
bytes, feature IDs/values, forecast IDs/links, and labels remain equal while
collecting, sealed, and after retirement. The retired raw read uses authenticated
archive verification rather than the dropped local partition.

Other cases reject delayed delivery/publication, future calculation inputs,
missing/foreign/corrupt/duplicate records, broken feature/forecast links, invalid
intervals/cutoffs and deadline overruns. Existing cold structured history tests
(9) and archive/lifecycle tests (20) also pass.

## Explicit limitations and next gates

- At most 50 reviewed structured revisions, four 500-row raw pages, 256 KiB
  structured data, 2 MiB response, and 20 seconds total composition; remote requests stay capped at four seconds. Excess
  data fails rather than returning an apparently complete empty window.
- One generation only. A market spanning generations requires a separately
  qualified multi-generation merge; generation UUID is never replaced by slot.
- Coverage is the reviewed manifest only; whole-market completeness is not
  established. The raw scan is generation-bounded and currently lacks an indexed
  market/time query, so larger real generations can exceed this prototype.
- Request/availability cutoffs support explicit offsets at microsecond precision;
  source epochs and original captured decimal strings remain exact. Finer cutoff
  precision is rejected rather than silently truncated.
- No later full historical inventory, recalculation/reproduction of model results,
  similarity/RAG/AI integration, runtime parity or PP cloud qualification is claimed.
- Origin/UUID/market scope is enforced, but production transport/grant qualification
  and a real captured bounded-window application comparison remain open.

Reproduce the PG case only with a disposable Unix-socket `tradebot_pp` database
initialized with the current business/history_v2 schemas and test administrator
role: set `TRADEBOT_TEST_RESEARCH_DSN`, make psycopg available, and run
`python3 -m unittest discover -s backend/tests -p test_research_window.py`.
Without that explicit DSN, the native case skips rather than reporting a pass.
