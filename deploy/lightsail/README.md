# Lightsail initial numerical collector deployment

The October 23, 2026 deployment uses Ubuntu 24.04, Lightsail `small_3_0`
(2 vCPU / 2 GiB / 60 GB), in the project's selected Region `us-east-2`.
The API binds to localhost. Only SSH from the operator's current public /32 is
allowed by both Lightsail and UFW. Update both restrictions when that IP changes.

Code lives in `/opt/tradebot`; the three services run as the non-root `tradebot`
user. FastAPI is the sole collector owner. Do not run `streaming.py` separately.

## Install and cut over

1. Run the full backend test suite before migration. Preserve unrelated local
   changes, all historical backups, and the integration branch. Use a feature
   branch for fixes; never deploy or modify `main` as part of this procedure.
2. Stop the old ensemble, API/collector and any lifecycle worker. Checkpoint
   SQLite with `PRAGMA wal_checkpoint(TRUNCATE)`. Require `integrity_check = ok`
   and zero `foreign_key_check` rows. Record counts, checkpoints and SHA-256.
3. Install Git, Python 3 + venv, and SQLite on the VM; create `tradebot` with
   home `/opt/tradebot`. Transfer the exact tracked revision. A Git bundle from
   the source branch avoids sending GitHub credentials to the VM; set `origin`
   back to `https://github.com/JakeMofa/Trading_Bot_Analytics.git` after cloning.
4. Create `.venv` and install `backend/requirements.txt`; run the full suite on
   Linux before starting production.
5. Transfer only the production DB over pinned SSH; do not migrate historical
   backups. Compare SHA-256, integrity, foreign keys, table counts and cloud
   checkpoints before starting any writer. Keep the Mac's DB stopped after cutover.
6. Transfer a minimal `.env` securely (mode 600, owner `tradebot`). Include only
   the two Polymarket read-only stream credentials, Supabase URL/secret, and
   runtime settings. Never transfer OpenAI or AWS credentials. Do not source
   `.env` as a shell script or print it. Use the application's literal parser.
7. Required initial flags: `ENABLE_OPENAI_ANALYST=false`,
   `ENABLE_LOCAL_RETENTION=false`, `ENABLE_SUPABASE_SYNC=true`,
   `ENABLE_CLOUD_LIFECYCLE=true`, `SQLITE_DB_PATH=data/btc_intelligence.db`,
   `FASTAPI_HOST=127.0.0.1`, `FASTAPI_PORT=8000`, `FASTAPI_RELOAD=false`.
   Use the cadence/batch defaults in `.env.example` and
   `MAX_LOCAL_STORAGE_MB=2048`.
8. As root run `sh deploy/lightsail/install-services.sh` from `/opt/tradebot`.
   This verifies and enables the units but does not start them.
9. Start `tradebot-api`, validate `/health` and `/state/current`, then start
   `tradebot-lifecycle`, then `tradebot-ensemble`. Verify `/forecast/current`,
   `/models/current`, `/cloud/status`, both live streams and new persisted rows.
10. Verify raw archive upload + authenticated readback from the VM, structured
    checkpoint advancement, disabled retention, absent OpenAI credentials and
    unchanged AI-analysis counts. Reboot once and verify automatic recovery.

The service preflight fails closed on changed soak flags or missing DB/credentials.
ExecStart also forces OpenAI/retention off. Services restart after exit with backoff;
repeated rapid failures eventually trip systemd's start limit and need investigation.
Journald is capped at 100 MB persistent / 50 MB runtime. API docs/health have no
authentication and must stay private; use an SSH tunnel to inspect them remotely.

## Routine operations

```sh
sudo systemctl status tradebot-api tradebot-lifecycle tradebot-ensemble
sudo systemctl show tradebot-api tradebot-lifecycle tradebot-ensemble \
  -p ActiveState -p MainPID -p NRestarts -p MemoryCurrent
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/cloud/status
```

Inspect journals locally when needed; do not publish configuration or unsanitized
logs. Reconnect counters include values restored from historical `feed_health`.
Missing `trade_flow` and `btc_order_book` remain expected until Phase 2.

Monitor CPU, RAM, disk, DB/WAL growth, feed freshness, rollover, lifecycle and
archive checkpoints for 24 hours. Retention is deliberately off; the 2 GiB SQLite
cap stops collection rather than deleting evidence. Do not call the 24-hour soak
complete after only the initial smoke test. Do not enable retention, AI, Phase 2
or trading during this milestone.

Start `tradebot-soak.timer` after the three application services. It records
read-only resource/endpoint/process snapshots every five minutes on the VM,
independent of the Mac. `data/cloud-soak.jsonl` keeps at most 288 snapshots
(approximately 24 hours). Inspect it with `sudo -u tradebot` or root. The
unprivileged timer reports journal warning counts as unavailable if it cannot
read the system journal; a privileged manual snapshot can include those counts.
Run `sudo python3 deploy/lightsail/metrics.py --integrity` for an on-demand
snapshot including SQLite integrity and foreign-key checks. These checks are
omitted from the periodic timer to avoid repeated full-database scans.

To roll back ownership, stop **all three VM services first**, checkpoint/verify
and transfer its newer DB back securely, then restart the Mac. Starting the old
Mac DB would fork observation IDs and archive checkpoints; never run two writers
or independently advance both copies. Preserve all backups and deployment keys
outside Git. Instance stop/reboot does not provide disaster recovery; redundant
backup/restore and measured retention policy remain follow-up work.

## Phase 1.5 dashboard (production verified October 25, 2026)

FastAPI serves the dashboard at `/dashboard` on its existing localhost port 8000.
Market is the default page; Models, History and System are separate navigation
areas. Do not start a separate port-8765 dashboard server or collector. The old
`dashboard.py` launcher now points to FastAPI; `--once` is diagnostic only.

After reviewing and intentionally deploying the tested feature revision, restart
only `tradebot-api` for the new API/UI code. The existing ensemble/lifecycle and
five-minute monitor remain their current single instances. No firewall or public
binding change is needed. From the operator Mac, use the existing pinned SSH host:

```sh
ssh -N -L 8000:127.0.0.1:8000 <existing-operator-ssh-host>
```

Open `http://127.0.0.1:8000/dashboard`. Keep this API private; there is no public
authentication layer in this phase. Validate Market live updates and all four
pages, `/models/current`, `/system/status` and `/system/history` after deployment.

The System history reader defaults to `cloud-soak.jsonl` alongside the configured
SQLite path (`/opt/tradebot/data/cloud-soak.jsonl` on this VM). Optional
`SYSTEM_TELEMETRY_PATH` overrides the server-side path; clients cannot choose it.
Responses are read-only, capped at 288 samples and project only approved metrics.
CPU and service states use timestamped five-minute snapshots (stale after 15
minutes); cheap resource/file metrics and RAM feed ages are read on request.
Missing files/fields remain unavailable. Keep `tradebot-soak.timer` running to
advance the historical graphs. Reconnect totals are cumulative across restarts;
archive object counts are unavailable locally, while dataset verification and
checkpoints come from existing local lifecycle records. No remote cloud query is
made by the dashboard. Free-form cloud error details/source keys are redacted.

The original feature-branch closeout did not deploy production. The October 25
manual CD release below is now verified. OpenAI and retention stay OFF,
collector ownership stays with FastAPI, and the separate 24-hour soak review
remains required before future phases.

## Controlled manual CD

`.github/workflows/deploy-tradebot.yml` deploys only on `workflow_dispatch` from
`codex/lightsail-deployment`. Its push trigger runs deployment-control tests only;
it registers/validates the workflow without deploying or changing `main`. Supply
the full current deployment-branch SHA. The deploy job independently checks the
branch HEAD, dispatch SHA and successful exact-SHA push run of `python-tests.yml`.
Concurrent production deployments queue; the VM also takes an exclusive lock.

The job needs a trusted self-hosted runner labeled `tradebot-private` on the
operator's existing allowed SSH address. Use an ephemeral runner for one job,
then remove its registration and local credentials. Production keeps running
without the runner or Mac; another manual deployment needs a runner online.
Do not open SSH to hosted-runner address ranges or expose port 8000. GitHub's
Actions UI may not offer the Run button until the workflow is on the default
branch; after its validation run, use the dispatch API/CLI against the deployment
branch where supported. Do not modify main to work around registration failures.

Required repository Actions Secrets (values must never enter source/logs):

- `TRADEBOT_SSH_HOST`: existing VM address.
- `TRADEBOT_SSH_USER`: restricted `tradebot-deploy` OS user.
- `TRADEBOT_SSH_KEY`: dedicated deployment private key.
- `TRADEBOT_SSH_KNOWN_HOSTS`: existing independently pinned SSH host entry.

The dedicated key uses `restrict` and a forced command that invokes the root-owned
`/usr/local/lib/tradebot-cd/deploy.py "$SSH_ORIGINAL_COMMAND"` through a narrowly
scoped sudo rule. That user cannot run arbitrary commands, forward ports or open
a shell through this key. Install reviewed `deploy.py` and `smoke.py` copies under
that root-owned directory; application deployment cannot overwrite these copies.
Updating the root helper is a separate operator action over existing pinned SSH.
Do not copy app credentials to Actions: `.env` stays mode 600 on the VM.

The sender exports only tracked Git history as a bundle with exactly the approved
branch ref. The VM checks the ref, full SHA, ancestry, clean tracked checkout,
active/enabled services, disabled flags, private configuration, free disk and
read-only SQLite quick/foreign-key checks before checkout. Dependency, service-unit
or preflight changes fail closed for reviewed operator provisioning; this Phase
1.5 release changes none. No database migration, retention, archive deletion or
Supabase reset is performed. The protected `.env` hash/permissions/owner are checked
without printing them. Only changed application code restarts `tradebot-api`;
ensemble, lifecycle and the timer retain their existing PIDs.

Root-only records in `/opt/tradebot/data/deployments/` persist `OLD_REVISION`,
`NEW_REVISION`, outcome and restarted services. Baseline smoke allows six attempts and post-deploy smoke allows 24 attempts,
separated by five seconds plus bounded per-request timeouts, to tolerate transient
requests and startup/stream recovery. They require all core/System/history
routes, valid dashboard HTML, an SSE data frame, fresh live streams, running
collector, ensemble exposure, disabled flags and stable services. Cloud status is
reported separately from live health. A material post-checkout failure restores
OLD_REVISION, restarts affected API code, reruns checks appropriate to that revision,
records rollback health and returns failure even when rollback succeeds. Failures
before checkout do not roll back healthy production. Never test rollback by
intentionally breaking the live collector; the simulated-failure test covers this
path. No destructive database repair is attempted.

Run deployment-control tests with:

```sh
python3 -m unittest discover -s deploy/lightsail -p test_cd.py -v
```

After deployment, independently inspect actual journals, process ownership, read-only
SQLite integrity/foreign-key checks, telemetry/checkpoint advancement and all four dashboard tabs
through the private operator tunnel before marking the roadmap complete. Automated
smoke success alone does not certify the visual dashboard or Phase 1.75 soak.


### First verified controlled deployment

Manual CD run [40239236113](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/40239236113)
succeeded October 25, 2026 at approximately 5:19 p.m. America/Chicago, deploying
`a7c098900f8310367fc262a1b837c369bb63dc56` from old production
`1eceb8098f21136692230e11fc6d711290e74298`. Only API restarted; all required
routes/SSE, four dashboard tabs, single collector, disabled flags, unchanged
protected environment, healthy SQLite checks and cloud lifecycle were verified.
The existing source-of-truth plan contains detailed evidence and the two resolved
failed attempts. The first exercised actual rollback; the second stopped before
checkout on a request timeout. Both failures remained visibly FAILED in Actions.

To dispatch a reviewed current deployment-branch revision after its CI passes,
bring a trusted ephemeral `tradebot-private` runner online at the existing allowed
operator address, then run:

```sh
gh workflow run deploy-tradebot.yml --repo JakeMofa/Trading_Bot_Analytics \
  --ref codex/lightsail-deployment -f revision=<full-approved-HEAD-SHA>
```

Wait for the actual deploy job result, then inspect production. A push validation
run is not a deployment. The temporary runner unregisters after one job, so no
persistent Mac runner was installed. Protect the runner machine as production
access: it executes trusted repository workflow code and receives deployment
Secrets. Keep it limited to an authorized deployment window.
