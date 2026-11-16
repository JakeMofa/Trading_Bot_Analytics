# Preprod merge CI smoke failure — November 15, 2026

The merge commit `90d24c4` failed [CI 43805761893](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43805761893).
PostgreSQL foundation, schema/application tests, runtime image build and the
first generated API acceptance passed. The generated deployment controller then
returned `child_failed` during its smoke stage and preserved the database through
its forward recovery. `CI Preprod` run 43806026192 failed downstream because
the required source CI was not PASS. Production and PP were not deployed by
either CI run.

The prior smoke seeded generated data near the 04:45 UTC market boundary. It
required the same price and market to remain current after an API restart.
Boundary expiry is a plausible explanation, but the original child error was
not captured, so the historical failure's exact substage remains unknown.

The successor adds fixed, sanitized smoke-phase reporting. It also refreshes
generated acceptance after the restart, validates previous price acknowledgement
against immutable raw storage and previous prediction against core, and allows
one new generated seed only when a probe explicitly reports that the market
expired. Unknown probe failures still stop. The check continues to require
current-market identity, fresh feeds/features, a disabled collector, schema,
API-only restart and unchanged PostgreSQL process. This is a generated CI
boundary correction, not permission to mask stale PP or production feeds.

Focused local controls pass; exact Linux CI and a fresh merge-branch result are
required before calling the issue resolved. The additive Supabase migration
candidate is held locally until the CI gate passes.
