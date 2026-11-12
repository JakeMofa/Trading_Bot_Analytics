# Preproduction VM launch — November 11, 2026

Result: **PASS — host provisioned and restart baseline verified.**
This completes the host-launch milestone only. PostgreSQL/application integration,
performance, migration and production acceptance remain open in the
[master roadmap](INTELLIGENCE_REBUILD_PLAN.md).

The user explicitly selected **2 GiB / 60 GB**, superseding the earlier
4 GiB / 80 GB recommendation, and authorized keeping the second VM for PP.

| Setting | Applied |
|---|---|
| Instance | tradebot-preprod-01 |
| Region / zone | us-east-2 / us-east-2a |
| Bundle | small_3_0; 2 vCPU, 2 GiB RAM, 60 GB SSD |
| OS | Ubuntu 24.04.5 LTS |
| Public / private IPv4 | 18.119.253.233 / 172.26.11.9 |
| Static IP | None; resolve by instance name before connecting after stop/start |
| Price | $12/month bundle list price; two VM bundles total $24/month before credits, taxes and usage extras |
| Purpose tags | Project=TradebotAnalytics, Environment=preprod, Role=postgres-qualification |
| SSH | TCP22 from current operator /32 plus Lightsail browser SSH only |
| Application/database public ports | Closed; no API or PostgreSQL listener present |
| Snapshot/add-ons | None |

See the [sanitized evidence](evidence/preprod-vm-launch-2026-11-11.json).
The project remains FREE/ACTIVE; no plan upgrade was performed. Pricing was
freshly verified from the AWS bundle API. [AWS pricing](https://aws.amazon.com/lightsail/pricing/)

## Checks and correction

Duplicate prevention confirmed the PP name did not exist before the single
CreateInstances call. Final AWS reads confirmed exactly two running instances,
the expected PP hardware/tags and the restricted firewall.

Initial startup **failed** because Lightsail appended supplied cloud-config YAML
to a shell launch script. The preprod marker was missing; SSH still worked.
This failure is preserved, not relabelled as a first-boot PASS. Only the custom
section was corrected to shell commands; the AWS-generated prefix was retained.
The correction wrote the PP marker, disabled root/password SSH, validated sshd
configuration and set the hostname. One **PP-only** restart then verified:

- cloud-init status done, empty errors, correct hostname and marker.
- 57.076 GiB filesystem total, 55.051 GiB available at the sample.
- 1,951,736 KiB total RAM, 1,543,040 KiB available at the sample.
- Public-key SSH enabled; password and root SSH login disabled.
- Tradebot, PostgreSQL and Docker units absent/inactive.
- No production SQLite file; no production data transfer or extra market collector.

These are provisioning checks, not full application or sustained-load tests.
No changes or restart were made to production. No database copy/snapshot,
Supabase write, retention enablement or paid AI call occurred.

## Next checkpoint

Prepare isolated PP runtime/PostgreSQL setup and the candidate adapter in small
reviewed changes. Keep the real market collector solely in production; writable
PP tests use generated or separately scoped replay data. PP preview can later
use production's read-only API. Do not mount production DB files or cloud write
credentials into test containers.

Use the selected 2 GiB host with explicit CPU/memory/disk limits and measure its
capacity before workload qualification. Provisioning disk space does not expand
the existing test allowances automatically. Docker/PostgreSQL/application setup,
cloud replay, migrations and production cutover are not completed by this launch.
AWS guidance preference is HIGH, as selected by the user.
