# Lightsail deployment — October 23, 2026

The numerical collector/API/lifecycle stack is running on AWS independently of
the Mac. Initial live validation, market rollover, private cloud archive
readback and automatic reboot recovery passed. The final performance revision
was verified at **5:38 p.m. CDT (22:38 UTC)**. A full 24-hour stability review is
still pending; do not treat this report as a completed 24-hour soak.

| Requested field | Verified result |
|---|---|
| AWS Region | `us-east-2` (Ohio), selected in the local AWS profile; AZ `us-east-2a` |
| Lightsail plan | Ubuntu 24.04 LTS, `small_3_0`, 2 vCPU / 2 GiB RAM / 60 GB SSD, AWS API price $12/month |
| Instance | `tradebot-analytics-01` |
| Public/static IP | `3.13.133.25`, static IP `tradebot-analytics-ip`, attached |
| AWS plan | Active Free plan at provisioning; $100 credits reported. No paid-plan upgrade performed. |
| Branch | `codex/lightsail-deployment`, based on integration `codex/fastapi-phase1-5` at `2766234` |
| Runtime code commit | `66bed207e3dd1675c1a003142be6629d3a852092`; subsequent deployment-report commits change documentation only |
| Tests | 138 passed on the Mac and on Ubuntu/Python 3.12; Linux unit files verified with `systemd-analyze verify`; unsafe startup flags and OpenAI key aliases refused |
| FastAPI | Active, `/health` = `ok`, bound to `127.0.0.1:8000`; `/state/current`, `/forecast/current`, `/models/current`, `/cloud/status` checked |
| Collector | Running inside FastAPI only; Mac collector/ensemble stopped, Mac DB unchanged after cutover |
| Coinbase | `live`; `coinbase.price_usd` present, ~0.03-second price age in the final snapshot |
| Polymarket US | `live`; rollover to `cpc-btc-updown-15m-2026-10-23-2230z` verified; target stored as exact decimal `81240.71` |
| Forecasting | Current RAM baseline forecast present; separate `ensemble_v1` process saves fresh numerical forecasts to SQLite |
| SQLite integrity | `ok`, zero foreign-key violations; transferred checksum and initial row counts matched |
| SQLite size | 236,077,056 bytes (~225 MiB); WAL 19,067,392 bytes (~18.2 MiB), sampled while live |
| RAM usage | ~480 MiB used / ~1,906 MiB usable host RAM, using `MemTotal - MemAvailable`; no swap |
| CPU usage | Final 1-second sample 1%; pre-fix catch-up/ensemble samples reached ~62%. Initial samples do not establish 24-hour capacity. |
| Disk usage | 2,998,702,080 used / 61,285,326,848 bytes total (~2.79 / 57.08 GiB); ~54.27 GiB free |
| Lifecycle | Active; last cycle `ok`, process running, no recorded error stage/type |
| Supabase structured sync | Advancing on the VM; final sampled checkpoints: features 7,240, predictions 7,510, candles 49,108; market checkpoint also advancing |
| Raw archive verification | First VM cycle archived 15,420 observations and 80,590 Coinbase events. Latest object from each feed independently downloaded and verified by compressed bytes, SHA-256 and decompressed JSONL event count. Final manifest inventory: **299 verified, zero unverified**, including post-reboot archives. |
| OpenAI enabled | **false** in all three process environments; no OpenAI credentials or aliases deployed; historical `ai_suggestions` count unchanged at 1,277 |
| Retention enabled | **false** in all three process environments; lifecycle retention status `disabled`, no deleted-row count recorded |
| systemd/service status | `tradebot-api`, `tradebot-lifecycle`, `tradebot-ensemble`: enabled and active; zero automatic restarts at final check. `tradebot-soak.timer`: enabled and active. |
| Errors/warnings | No application error lines or warning-priority journal entries at final check. Resolved boot SSH-reload issue, historical foreign-key gaps and expensive ensemble scans are described below. |

Ready to leave running for the initial 24/7 cloud soak: **yes**. Collection and
forecasting no longer depend on the Mac staying powered on. Keep the Mac's old
collector stopped: resuming its stale database would fork observation IDs and
archive checkpoints. Indefinite unattended collection is not yet established:
retention is intentionally off and the 2,048 MiB local storage guard stops
collection rather than deleting evidence when its cap is reached.

## Configuration and access

- Code/runtime path: `/opt/tradebot`, service user `tradebot` (non-root).
- Private `.env` (mode 600) contains only the required Polymarket read-only
  stream credentials, Supabase URL/secret and runtime settings. It is ignored
  by Git. OpenAI, AWS and GitHub credentials were not deployed.
- Git bundles carried only tracked source/history from the feature branch;
  the VM's `origin` points to `JakeMofa/Trading_Bot_Analytics`. No unrelated Mac
  changes, `.env copy`, virtual environment or databases entered these commits.
- Lightsail and UFW allow only TCP 22 from the operator's provisioning /32.
  No public API, HTTP, database or other application port is opened. The SSH
  host key is pinned locally. Password authentication and root login are disabled.
- The VM has no new cloud database/cache/container/load-balancer service.
  No trading, Phase 2 ingestion, AI toggle or retention activation was added.
- The full operating procedure is in `deploy/lightsail/README.md`.

## Integrity and performance repairs

Preflight found ten historical prediction links whose eight outcome-observation
rows had been removed during earlier retention. Those exact eight rows were
recovered from the read-only local
`data/backups/pre_retention_phase1_75.db`. A separate pre-repair safety copy was
preserved. The ~1.98 GB historical backup was never transferred, modified or
deleted. After recovery both SQLite integrity and foreign-key checks passed.
Retention now excludes observations referenced by prediction history, including
references added between a dry-run and apply; automatic retention remains off.

Initial ensemble calculations on the smaller VM took ~157 seconds because
outcome-evidence scans repeated for every snapshot when historical metadata was
no longer local. Per-call negative lookup caching reduced a real Mac-data
comparison from 6,553 to 386 queries and 94.94 to 5.97 seconds, with identical
complete results. A missing `(market_id,kind,received_at)` observation index was
then added idempotently. Matching took 0.038 seconds on an indexed Mac DB copy
and **0.0786 seconds on the VM**; indexed/unindexed complete results matched.
Regression tests cover delayed evidence visibility and preserving exact
decimals/raw rows/foreign keys during an existing-database index upgrade.

The first boot's cloud-init script attempted to reload `ssh.service` before it
was active. SSH configuration validation and explicitly starting the service
resolved that issue. The original initialization log retains the warning;
application services, firewall and reboot recovery are healthy.

## Initial-soak evidence and remaining gate

The VM records CPU, memory, disk, SQLite/WAL sizes, process state/restarts,
live feed freshness, forecasts and cloud checkpoints every five minutes.
`/opt/tradebot/data/cloud-soak.jsonl` keeps at most 288 snapshots (~24 hours).
It runs as the application user and needs no Mac connection. Unprivileged
journal warning counts may be unavailable; privileged manual snapshots and the
initial journal check cover those separately. Journald is size-capped.

Local deployment evidence and the SSH key are under ignored
`data/deploy/lightsail/`; VM evidence is under ignored `/opt/tradebot/data/`.
Neither location is committed. Backups remain preserved.

- [x] Linux tests, database transfer/integrity, active market and baseline forecast.
- [x] Coinbase/Polymarket live streams and one market rollover.
- [x] Structured sync and authenticated raw archive readback from the VM.
- [x] Reboot recovery with services and timer enabled.
- [x] Fresh, fast numerical ensemble output; OpenAI and retention disabled.
- [ ] Review a full 24-hour run of the final version, no earlier than **October
  24 after approximately 5:38 p.m. America/Chicago**. Check coverage gaps, process
  errors/restarts, market rollover, memory/CPU and disk growth, structured and
  archive checkpoint advancement, and archive verification failures.
- [ ] Establish long-term backup/restore, disk-growth and retention policy after
  that evidence. Phase 2, hourly collection and AI remain deferred.

The five-minute timer records evidence; it does not send alerts or certify the
soak automatically. Review the saved snapshots before claiming completion.
