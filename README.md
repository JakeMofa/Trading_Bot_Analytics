# Tradebot BTC Intelligence

Read-only BTC market collection, numerical forecasts and an intelligence dashboard,
focused on Polymarket US 15-minute markets. Exchange prices are reference inputs,
not official settlement. Hourly markets, trading and paid AI remain deferred.

**Current checkpoint: Phase 1.75 / I7 unfinished.** The active storage direction
is PostgreSQL tested in isolated preproduction before any production migration.
The pending SQLite A/B implementation was superseded; PRs #11–#13 are closed,
with their branches and evidence retained. PR #14 added independent CI/CD and version publication; PR #15 aligned those
controls into preprod. Checkpoint 1 is qualified on PP: Docker and PostgreSQL are installed and
generated persistence/role tests pass. The application adapter and live collector
are not installed on PP. Generated PostgreSQL schema, application and lifecycle
components are qualified together in the feature integration branch; PP
deployment-control code also passed generated Linux qualification. Actual host
bindings and manual application deployment remain open. See the master for exact
commits and CI.

Start with the authoritative [master roadmap](docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md),
then the [session handoff](docs/PLAN/SESSION_HANDOFF.md). Detailed pipeline operation
and remaining bindings are in the [environment guide](.github/ci/ENVIRONMENTS.md).

## Environments and instances

| Environment | Code policy | Lightsail instance | Last verified resources/address | Actual application/database state |
| --- | --- | --- | --- | --- |
| Local development | Your reviewed feature branch | Your computer | Isolated fixtures | Existing main-baseline application uses SQLite; tests use generated data |
| PP / preprod / PRT | Permanent `preprod` branch; main controls may also test an exact main candidate | `tradebot-preprod-01`, `us-east-2a` | 2 vCPU, 2 GiB RAM, 60 GB SSD; `18.119.253.233`, private `172.26.11.9` | Docker 29.9.3 / Compose 5.7.1 / PostgreSQL 17.12 foundation qualified; app, collector and CD controller not installed/qualified |
| Production | Intended release branch `main`, explicit manual promotion only | `tradebot-analytics-01`, `us-east-2` | 2 vCPU, 2 GiB RAM, 60 GB SSD; `3.13.133.25`, private `172.26.2.84` | Last recorded deployed revision `d56b4a7`, legacy SQLite; services active but collection held at the 5,120 MiB DB+WAL guard |

PP foundation was verified November 12 (November 13 UTC); production state is
the earlier recorded inventory, not a fresh live-health claim. PP's public address is **not static**; recheck it in Lightsail. Disk/SSD
holds database files; RAM holds caches and working state. The storage guard is
an application limit, not the VM's total SSD size.

`main` currently differs from the deployed production revision. Merging workflow
configuration does not reconcile or replace that application. Keep one real
market collector. PP may preview production through an approved read-only API;
writable schema, performance and recovery tests use its own generated/replayed
data. PP must not write to the production database or start a second collector.

## Databases and data flow

| Store | Purpose | Current versus planned |
| --- | --- | --- |
| Production local SQLite | Existing collector evidence, structured records and application history | Existing `/opt/tradebot/data/btc_intelligence.db`; do not modify or copy it during onboarding |
| PP local PostgreSQL | Intended replacement for SQLite A/B; qualify schema, queries, concurrency, retention and recovery | Installed foundation with empty raw/core/ops/archive namespaces and isolated smoke data; business schema and adapter pass generated CI but are not yet deployed |
| Supabase Postgres | Long-term structured markets, candles, features, predictions, outcomes and sync checkpoints | Existing TokenBot project, ref `xttdqeimdujweijxcuro`, `us-west-2` |
| Supabase Storage | Private raw archives and associated verification evidence | Existing `market-raw` bucket; other private buckets include `knowledge` and `backups` |

Intended flow: one collector → local working database → verified background
structured sync/raw archive → Supabase history. Local raw deletion is allowed
only after authenticated archive readback, identity/checksum reconciliation,
protected-reference checks and the approved retention gate. PostgreSQL on a VM
and Supabase Postgres are separate databases; the same engine does not sync them.
Raw archive objects are not SQL tables; archived history needs explicit retrieval.

Preserve exact decimal values, original source timestamp strings, receive times,
source/market identities, missing-data states and provenance. Review the actual
selected 72-hour-or-qualified-size A/B policy in the master roadmap. The SQLite
implementation is superseded; the lifecycle is retained using PostgreSQL
partitions. No additional 72-hour wait follows sealing, and retirement always
follows verified archival. It is not yet a deployed retention policy. Production
retention and paid AI remain OFF. Supabase schema/permissions do not change
when this CI configuration merges.

## PP PostgreSQL foundation (checkpoint 1)

The source package in `deploy/preprod/` runs only PostgreSQL, not Tradebot's
API, calculation/lifecycle workers or collector. The business schema and app
adapter are subsequent checkpoints. Use the existing approved PP SSH route.
Never point these commands at production. The helper requires the root-owned
PP host marker, exact hostname, Ubuntu 24.04, 10 GiB free disk and 1 GiB available
RAM. It rejects an already installed Tradebot service.

These commands passed on the existing PP host using source `40c2761`. From an
approved SSH session, use the installed root-owned checkout. Do not run `verify`
against a later business schema: it intentionally rejects additions until the
versioned migration contract replaces this foundation-only check.

```sh
# On PP, from the installed reviewed export:
cd /opt/tradebot-pp-foundation
sudo python3 deploy/preprod/foundation.py preflight
sudo python3 deploy/preprod/foundation.py install-docker
sudo python3 deploy/preprod/foundation.py up
sudo python3 deploy/preprod/foundation.py verify
sudo python3 deploy/preprod/foundation.py status
```

`install-docker` uses Docker's signed official Ubuntu repository, checks its
signing-key fingerprint and refuses conflicting packages. It does not add users
to the root-equivalent Docker group. `up` pins PostgreSQL 17.12/bookworm by digest
and creates only the named `tradebot_pp_pgdata` volume and private Compose
network. No port is published; no production/cloud credentials are loaded.

Secret files live only under `/etc/tradebot/pp-postgres`, mode 0700, with 0400
files owned by the pinned image's PostgreSQL UID. The helper creates them once,
preserves them on repeat runs, and never prints passwords. Credentials are not
in Compose environment variables, Git, artifacts or command arguments. Admin
access remains a privileged operator action. Keep the deployment files at a
stable root-owned location on PP for subsequent Compose operations.

Restricted roles: non-login owner, migration identity with explicit `SET ROLE`,
application without DDL, and read-only history identity. Foundation creates only
empty `raw/core/ops/archive` namespaces plus `ops.environment_identity`; future
business migrations run explicitly rather than at app startup. Role grants for
real business tables must be reviewed with those migrations.

`verify` uses 32 generated rows, checks exact decimals/source strings and role
restrictions, recreates only the PostgreSQL container, and confirms the same
volume still contains committed rows. It reports relation/data/WAL/temp usage
and memory. Smoke data is capped at 64 MiB; PostgreSQL's own cluster, image and
WAL consume additional measured space. This is persistence/correctness evidence,
not representative capacity, power-loss, application or A/B qualification.

Defaults: 512 MiB memory including no swap allowance, 128 MiB shared buffers,
20 connections, 2 MiB work memory, bounded queries/temp files and rotated logs.
Full durability, page checksums and autovacuum remain enabled. `max_wal_size` is
a soft maintenance setting, not an aggregate storage ceiling.

```sh
# PP-only status and logs (do not print secret contents):
sudo python3 deploy/preprod/foundation.py status
sudo env PP_SECRET_DIR=/etc/tradebot/pp-postgres docker compose \
  --env-file /dev/null -f deploy/preprod/compose.yaml logs --tail 50 postgres
# Stop safely; volume and credentials are retained:
sudo python3 deploy/preprod/foundation.py stop
```

Failure recovery preserves the database volume. Correct the evidenced error
before restarting; do not use `down --volumes`, replace files, or restore old
code over newly acknowledged data. The CI-only disposable-data command refuses
hosts with the PP marker. No foundation command enables collection, retention,
Supabase sync, paid AI, or the CD runtime qualification flag.

CI executes host/control regressions and the real pinned container on Linux,
including recreation, role tests and rejection of injected column drift. The
separate PostgreSQL integration job adds business-schema migration and drift
coverage from checkpoint 2. Evidence is a sanitized
`postgres-foundation-<SHA>` Actions artifact. It does not need cloud secrets.

## PostgreSQL application qualification (feature integration)

The `backend/postgres/` package contains the reviewed local schema contract,
explicit versioned migrator, generated ingestion, RAM-backed API/SSE, serial
calculation worker and A/B lifecycle/history code. Its local business migration
is separate from the unapplied private Supabase `history_v2` contract. Application
startup only validates schema; unreviewed drift stops startup.

The generated integration run on Linux executes against PostgreSQL 17, including
restricted-role migrations, repeated/upgrade checks and actual partition removal
followed by archived API/history retrieval. The built API container acknowledged
21 generated records and served dashboard/history/SSE. This proves that tested
scope; it does not establish live feeds, preview networking, representative
capacity, ensemble/news/evaluation or real cloud permissions.

CP5 supplies the separate runtime Compose overlay and restricted manual host
controller. They are not installed merely by merging application code. Do not
run the foundation-only `verify` command against the migrated business schema.
Production and runtime retirement remain unchanged/OFF. Exact verified runtime
commands will be added after the PP host deployment succeeds.

## Local developer quick start

Use Python 3.12, matching CI. From a clean clone or the intended existing checkout:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m unittest discover -s .github/ci -p 'test_*.py' -v
```

These tests use local/generated fixtures and mocked transports, without live
Supabase keys or production database access. Git ignores `data/`, `.env` and
`.venv/`; never commit a key, credentials, local database or process log.
Do not use an operator's existing production `.env` for a development run.

For a deliberately **empty, isolated SQLite dashboard preview** of the current
main-baseline application, initialize the same schemas used by its tests:

```sh
PYTHONPATH=backend/app .venv/bin/python - <<'PY'
from collector import connect
from features import initialize as features
from forecasts import initialize as forecasts
from news import initialize as news
from streaming import initialize as streaming
from knowledge import initialize as knowledge

with connect('data/dev/empty-preview.db') as db:
    for initialize in (features, forecasts, news, streaming, knowledge):
        initialize(db)
PY
.venv/bin/python backend/app/dashboard.py --db data/dev/empty-preview.db --once
.venv/bin/python backend/app/dashboard.py --db data/dev/empty-preview.db --port 8765
```

Open **http://127.0.0.1:8765**; Ctrl+C stops the preview. It has no current market,
ticks or forecast, so unavailable states are expected. Do not add production
credentials or point this command at a production file. This is a local preview
of the existing SQLite application, not the planned PostgreSQL service. A real
PP application/start command will be documented when that runtime is qualified.
There is no second live collector in this quick start.

## Connecting to a VM

Access is restricted. Developers need an individually approved operator/deploy
identity, its private key kept outside Git, and a host key verified through an
existing trusted route. GitHub CD uses separate scoped keys for each environment;
do not reuse an operator key as a CD deployment identity or put key material
in a README. The existing approved operator key is already attached to both
hosts; future CD uses separate restricted environment identities.

Find the current PP address in the [Lightsail console](https://lightsail.aws.amazon.com/ls/webapp/us-east-2/instances/tradebot-preprod-01/connect)
or, with existing authenticated read access, run:

```sh
aws lightsail get-instance --region us-east-2 \
  --instance-name tradebot-preprod-01 \
  --query 'instance.{Name:name,PublicIP:publicIpAddress,PrivateIP:privateIpAddress,State:state.name}'
```

For an already authorized SSH identity, set local path/address variables and use
strict host verification. Example operator user is `ubuntu`; use the actual
approved identity for your role:

```sh
export TRADEBOT_VM_HOST='18.119.253.233'  # replace with verified current PP address
export TRADEBOT_SSH_KEY='/absolute/path/to/your/approved-key'
export TRADEBOT_KNOWN_HOSTS='/absolute/path/to/verified/known_hosts'
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o ConnectTimeout=10 -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" \
  -i "$TRADEBOT_SSH_KEY" "ubuntu@$TRADEBOT_VM_HOST"
```

A different Wi-Fi network may require an explicitly authorized current IPv4
`/32` in Lightsail SSH rules. An unknown host key must be independently verified;
do not turn host verification off. Browser SSH is the existing fallback when
the pinned operator route is unavailable. Do not open database or API ports to
the internet to make a deployment work.

Once the candidate app is installed, use its verified private port through an
SSH tunnel. Set `TRADEBOT_REMOTE_PORT` to the port confirmed by the runtime
configuration; the local baseline dashboard uses 8765, while the deployed
FastAPI service may have a different private port:

```sh
ssh -N -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_SSH_KEY" \
  -L "8765:127.0.0.1:${TRADEBOT_REMOTE_PORT:?set the verified private app port}" \
  "ubuntu@$TRADEBOT_VM_HOST"
```

Then browse http://127.0.0.1:8765. This tunnel will not work against an uninstalled
PP app. For an approved production read-only inspection, basic safe checks are:

```sh
git -C /opt/tradebot rev-parse HEAD
systemctl is-active tradebot-api tradebot-ensemble tradebot-lifecycle
```

Active processes or HTTP 200 alone do not establish advancing feeds, correct
market identity, fresh features or persistence. Do not dump process environments,
credentials or configuration files into logs. Heavy database checks, maintenance,
service restarts and storage changes require their applicable operator scope.

## CI, deployment and versions

[GitHub Actions](https://github.com/JakeMofa/Trading_Bot_Analytics/actions) is the
entry point. The four environment names are **CI Preprod**, **CD Preprod**,
**CI Prod/Main**, **CD Prod/Main**. Shared `CI — Tradebot checks` runs backend/
legacy SQLite regressions, the real PostgreSQL foundation, release/transport
safeguards, dependency audit and workflow validation, then reports fail-closed
**PR readiness**. The two environment CI
wrappers reuse successful exact push checks. Definitions are registered on main (PR #14) and aligned into preprod (PR #15).
The PostgreSQL job is added by PR #16; when its workflow is promoted to main,
main source checks include that same required gate. No production host check
is implied by a generated CI run.

For a release:

1. Review feature code into preprod; require CI on the exact source commit.
2. From main, manually run **Release — publish version and package** with the
   source branch, full SHA and an unused explicit SemVer such as `v0.1.0-rc.1`.
3. Manually run **CD Preprod** for that published version after PP runtime
   qualification and connection setup are complete.
4. Review preprod → main. The merge result has its own SHA: require its CI,
   publish that main candidate and test that exact version in PP again.
5. Manually run **CD Prod/Main**, supplying matching PP acceptance. Production
   environment approval is required. No merge, tag or release auto-deploys.

This promotes code between two VMs; it does not move the PP VM/database to prod.
The database foundation is installed. Application/controller and deployment
bindings are still separate checkpoints: no private runner or
environment deployment secrets were registered at the November 12 inventory,
and both target profiles are unqualified. Full PostgreSQL application/database
qualification is still separate. PR #14 registered configuration; CP1 installed the PP database only.

Where to inspect versions and outcomes:

| GitHub location | What it contains | Retention/status |
| --- | --- | --- |
| [Actions](https://github.com/JakeMofa/Trading_Bot_Analytics/actions) → a run → artifacts/summary | CI audit and bounded deployment evidence | Configured for 90 days; not the durable rollback store |
| [Releases](https://github.com/JakeMofa/Trading_Bot_Analytics/releases) | Explicit candidate versions, source archive, checksums and manifest with source/CI/registry bindings | Retained; no automatic pruning in this PR |
| [Packages](https://github.com/JakeMofa/Trading_Bot_Analytics/packages) | Versioned GHCR source carriers at `ghcr.io/jakemofa/trading_bot_analytics/releases` | Retained by digest/version, no mutable `latest` or automatic cleanup |
| [Deployments](https://github.com/JakeMofa/Trading_Bot_Analytics/deployments) / repository Environments | Actual PP/production attempts and results | Separate from candidate Release status |

Releases/Packages remain empty until the first successful explicit publication;
a CI pass does not publish a version. The registry carrier is a scratch image
used as a source envelope, **not a runnable app image**. It does not install
Docker on either VM. Manifests distinguish candidate, deployed and validated
states; a candidate is never labelled production merely because tests passed.

Retained versions identify rollback candidates. Applying old code still needs
current schema/data compatibility and qualification: the current CD route
rejects blind deployment of an old non-HEAD SHA. A reviewed revert PR can produce
a new tested candidate. No code rollback restores database contents or replaces
an engine migration plan. See the [detailed release and recovery controls](.github/ci/ENVIRONMENTS.md).

## Contributing and next work

Keep PRs small and focused. Test the touched contracts and record evidence in
the master roadmap. PostgreSQL schema PRs must supply isolated migration,
compatibility, exact-value, archive/replay and forward-recovery tests; the
existing SQLite suite does not certify PostgreSQL or live Supabase behavior.
No shared writable production DB for PP. Retention enablement, production
migration and legacy retirement remain separately reviewed operations.

The next small PR is **checkpoint 2: versioned business schema and migrations**,
including drift, wrong-environment, repeat/upgrade and exact-data tests. Separate
PRs then add the application adapter, lifecycle/history, and qualified CD host
controller/bindings. Follow the master roadmap rather than bundling them into
the foundation PR. I7 freshness/rollover, continuous verified
retention, history recovery and sustained-operation evidence remain required
before closing Phase 1.75. Redis and larger-scale orchestration stay deferred.
