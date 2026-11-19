# Exact local PP trial-origin source slice

Source-only addition: `pp-live-pp-trial-20261119-01` is the single new trial
origin in the existing `tradebot_pp` database. It joins the legacy `pp-live-pp`
origin in an exact cycle-profile allowlist. No arbitrary trial suffix, pattern,
new database, alternate collector fence, partition deletion or historical seal
change is introduced.

The trial origin requires `two-official-markets-cycle`, its canonical initial-A
UUID and explicit 6600-second finite admission. Missing/ordinary profiles and
ordinary short lease admission are rejected. The existing final-minute UTC
quarter gate, exact session/expiry checkpoint, two official market pairs,
filesystem floor, occupied-slot OFF behavior and terminal fresh A still apply.
Legacy origin behavior and ordinary 4560-second cap remain unchanged.

Both scopes use the unchanged environment-wide advisory admission lock and the
same `pp-live-%` active-lease exclusion inside `tradebot_pp`. The new trial does
not revive or reassign either retained historical generation. Its initial A
must belong to the exact trial origin and have a free opposite slot.

## Generated evidence

Seven profile tests passed, including rejection of adjacent/unknown trial
origins and trial requests without the exact cycle policy. Three disposable
native PostgreSQL 17.2 tests passed with restricted app/lifecycle/migrator roles.
The added test seeds legacy A/B with exact Coinbase reference inputs, then
exercises generated trial A → B → fresh A. It compares the retained legacy
metadata and raw rows exactly before/after and proves active-lease exclusion in
both origin directions. The cycle fixture simulates completed trial-A
retirement through its owner-only fixture; it does not establish trial permit,
archive, real-time continuity or actual deletion qualification.

## Integration dependencies before activation

The host controller must bind this exact origin consistently across API,
calculation, lifecycle and operator configuration, profile validation, transition
state and one-use session authority. Existing cloud transports, principal
policies and archive/readback routes require separately reviewed exact-origin
bindings. Existing migration 0003 retirement-capture triggers and
`retire_pp_generation` are pinned to the legacy origin; equivalent exact trial
safeguards are a separate schema/retirement dependency, not bypassed here.
No host, cloud, deployment or live data action was performed for this slice.
