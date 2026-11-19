# Source qualification: continuous PP A → B → fresh A

This source candidate adds an explicit `two-official-markets-cycle` profile for
`preprod`, `pp_live`, `pp-live-pp` only. Both operator and lifecycle configuration
must specify `TRADEBOT_PP_CYCLE_INITIAL_A` as the exact canonical initial A UUID.
It adds no automatic activation, renewal, trading, cloud action or retirement
authority. No PP/prod host or retained data was changed during qualification.

## Admission and finite lease

Ordinary sessions retain their 4560-second ceiling. The dedicated profile
requires an explicit `max_seconds=6600` request; the usual default 900 is rejected.
Initial A must be collecting and the other slot must be free. Existing PP21
retained A/B cannot become a fresh rehearsal by changing slot labels or passing
an old generation/permit.

The actual ON UPDATE returns its database `updated_at`; before commit, admission
requires that timestamp to lie in the final 60 seconds strictly before a UTC
quarter. Rejection rolls back ON. The fixed lease budget includes at most 60
seconds to A's first full quarter, 1800 seconds of A markets, up to another 900
seconds of B alignment after a slightly late first switch, 1800 seconds of B
markets, B's original 1800-second archive window and 240 seconds of total
scheduling margin. Additional metadata or operation delays consume that finite
margin; the database expiry never moves.

An existing `archive.checkpoints` row records the initial A, actual collector
session UUID, DB admission and exact DB expiry. Every cycle tick checks the
locked writer session and expiry against that record. A normally admitted lease
or changed session cannot borrow the cycle profile. No migration is required.

## Switch behavior and original controls

The worker requires the persisted A/B/fresh-A chain, with each previous actual
`sealed_at` equal to its successor's `started_at`. Each outgoing generation still
needs its next two complete official quarter-hour markets and in-generation
quotes whose source and receipt times are inside those intervals. Missing
metadata/quotes holds the switch while the same collector continues. A new
collector task is not started at a switch.

The second switch requires the original A slot already retired. An occupied slot
still atomically commits OFF and preserves both partitions. Fresh A is terminal
for this profile, preventing an unintended third switch. Filesystem reserve,
pending outbox, one active collector per environment, strict DB lease expiry,
explicit OFF/restart fencing, raw provenance and generation UUIDs remain enforced.
Both retirement seal deadlines remain their actual seal plus 30 minutes. The
separate exact permit/readback path must qualify and retire both outgoing UUIDs;
this switch candidate cannot issue or bypass that authority.

## Evidence and limits

- 12 planner/profile tests pass, including ordinary cap isolation, exact cycle
  scope/duration, bounded task ownership, API authentication and explicit budget,
  final-minute admission arithmetic and immutable handoff chain checks.
- Existing focused operator (20), collector orchestration (6), live supervisor
  (8) and lifecycle (20) tests passed.
- Two new disposable native PostgreSQL 17.2 tests pass with restricted app,
  lifecycle and migrator logins. They exercise real lease admission rollback,
  checkpoint tamper rejection, both quote-qualified switches, three distinct
  generation UUIDs, delayed-market holds, continued successor writes, unchanged
  session/expiry, terminal fresh A, expiry write rejection, and occupied-slot OFF
  preserving the old partition.
- The native switch fixture uses generated market time and overrides only the
  alignment validator. It simulates independently completed initial-A retirement
  through its owner fixture. This is **not** the exact PP retirement permit proof,
  real-time two-market continuity, archive capacity evidence or deployment
  authorization. Those remain separate integration and operational gates.

Runtime imports changed in `collector_session`, `live_supervisor`, `operator_api`,
`operator_runtime`, `operator_session`, `lifecycle` and `lifecycle_worker`; source
packaging must include the new `postgres/rehearsal_profile.py` module.
