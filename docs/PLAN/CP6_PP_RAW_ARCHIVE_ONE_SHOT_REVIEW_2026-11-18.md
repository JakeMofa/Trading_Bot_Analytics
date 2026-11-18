# CP6 PP raw archive one-shot entry point — review

This candidate adds a **default-OFF application entry point** for one bounded
archive cycle of one already sealed `pp-live-pp` generation. It does not add a
Compose profile, host controller command, credential mount, schedule, cloud
invocation, local partition retirement, or production path.

The operator must separately review and bind an exact canonical generation
UUID, sealed row count, and current manifest count. The entry point rechecks
those facts before any cloud I/O. It uses the existing create-only Supabase
Storage transport and restricted Auth identity for raw objects, plus the
separate TLS-verified `history_v2` transport for structured rows. A
same-origin advisory lock prevents competing structured sync during this one
cycle. Its limits are 25 raw and 25 outbox rows, 256 KiB decoded/object bytes,
1 MiB aggregate cycle bytes, eight cloud operations and 20 seconds. Errors
report a sanitized HOLD; the raw generation remains locally available.

The result reports **raw coverage** separately from cycle completion and
states retirement OFF. A `raw_coverage=archived` result does not prove all
structured rows are acknowledged or authorize local deletion. The existing
partition-retirement method still rejects real Supabase transport.

Generated tests cover exact PP identity and secret paths, OFF flags, changed
seal/progress rejection before the archive worker, bounded result scope and
the explicit execute gate. An isolated PostgreSQL test also exercises the
wrapper over an actual sealed generation and mock authenticated readback.
Linux PostgreSQL CI is required for that case.

**Remaining runtime gates:** independent root-owned Storage Auth credential
staging and mount; a reviewed default-OFF Compose profile; a one-use host
permit/controller command; exact image/source CI and PP installation;
bounded live sealed-generation upload/readback while B collects. Separate
permission-continuity and recovery evidence must precede any retirement
enablement. The structured `history_v2` one-shot diagnostic and its pending
outbox drain are distinct prerequisites to a complete lifecycle.
