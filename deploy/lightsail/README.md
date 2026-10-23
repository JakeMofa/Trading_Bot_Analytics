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
