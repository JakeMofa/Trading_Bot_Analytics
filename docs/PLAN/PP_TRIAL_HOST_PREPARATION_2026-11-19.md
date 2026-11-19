# Exact trial host preparation, source only

This slice extends the existing root one-use enter authority with an optional
exact `trial_origin=pp-live-pp-trial-20261119-01` plus the already required
canonical initial-A UUID. It cannot select another trial suffix or origin. The
same release SHA, artifact/controller hashes, image ID, host, transition nonce,
expiry and durable one-use permit consumption remain required.

The explicit enter transition validates generated runtime and profiles, stops
all generated app services, then executes one bounded local lifecycle oneoff.
`postgres.pp_trial_prepare` allocates that exact initial-A UUID and partition in
`tradebot_pp`. Under the existing global PP admission lock it locks all PP writer
rows and requires stored enabled/session/expiry fields to be durably OFF, even
for expired leases. It never changes old A/B generation states, timestamps,
writer pointers or raw records. Initial A remains OFF. An exact unused same-source
preparation is idempotent; changed UUID/source, evidence, prior admission epoch,
missing partition or conflicting existing trial fails. The host then starts all
four app services on the trial origin and proves actual host API/operator OFF.

Permit-free leave and emergency OFF use the active transition's exact origin
and never invoke preparation. Recovery proves trial OFF before restoring the
generated runtime. Regular legacy entry/ON/profile behavior remains unchanged.
The outbox preservation allowlist adds only the one exact trial origin and uses
a four-origin probe to continue detecting unknown namespaces.

## Explicit activation hold

**This slice qualifies preparation and OFF only.** Trial ON authorization and
dispatch both reject with `pp_trial_archive_readiness_unqualified`, before an ON
permit can be consumed. Legacy recurring cloud sidecars are also refused on the
trial active scope. API trial mounts include no legacy history reader and no
writer credentials. A separate exact trial cloud-worker/reader credential and
positive/negative proof integration must replace those holds before activation.
No marker, default or caller flag bypasses the hold.

The future cloud targets are defined separately by `cloud_runtime_profile`:
trial SQL writer/reader DSNs, trial archive Auth writer, and independent trial
history Auth reader. Existing legacy identity/proof cannot qualify that scope.

## Generated evidence

Four trial host contract tests pass: full-service origin/profile binding,
command/session rejection, prepare-after-stop and leave ordering, no legacy
reader inspection/mounts, and both root/dispatch ON holds preserving authority.
A disposable native PostgreSQL 17.2 test executes actual restricted lifecycle
initial-A allocation, checks exact idempotency, stale-enabled lease rejection,
changed identity/source rejection, unchanged historic A/B metadata and refusal
to reuse a previously admitted epoch. Its default-off CLI control also passes.
Existing transition, Linux profile, installer, bundle, workflow and recurring
worker tests remain part of the focused verification.

No host operation, deployment, live collector, cloud credential read/provisioning
or Supabase grant was performed for this source milestone.
