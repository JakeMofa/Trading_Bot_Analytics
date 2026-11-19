# Structured cold-history source and API composition candidate

November 19, 2026. Source candidate only; no hosted configuration, credentials,
cloud data, deployed service or collector changed. Production is unqualified.

## Implemented

The existing uncommitted `cold_structured_history.py` prototype and its six
tests were copied unchanged from the `codex/pp-cold-history-prototype-20261119`
worktree after inspection. The original worktree is untouched. Module SHA256:
`62eb8f4797e4a17a1e94d8c27ecc89b3ea04cb8e91fdaf4e808aed330485c814`.
This preserves its reviewed exact-ID manifest, scope-bound continuation,
decimal strings, missing fields and honest incomplete-coverage response.

`cold_structured_source.py` adds a narrow read-only source. It composes the
existing `HistoryV2PostgresTransport` receipt/canonical-envelope decoder rather
than duplicating import logic. It exposes no import, ACK, backfill, checkpoint
or retirement methods. The caller must supply a separately reviewed private
connection factory for `tradebot_pp_history_reader`; the existing
`tradebot_pp_history` writer is rejected. Each connection starts a read-only
transaction, disables prepared statements and verifies the expected database,
direct login, nonprivileged role, schema USAGE/no CREATE, SELECT on both exact
history tables, and absence of effective table/column mutation privileges in
`history_v2`, including PG17 MAINTAIN. Limits are 50 IDs, 256 KiB and four
seconds. PostgreSQL transaction/statement/lock limits use the existing helper.

`cold_structured_queries.py` adds an injected server-owned registry of at most
32 reviewed query IDs. Each binding includes one reader, immutable manifest,
entity type and market. Requests cannot supply a manifest, generation, origin
or SQL. Continuation retains the original `scope_sha256` and `after_id`; a
changed registry manifest rejects an old cursor before remote work. One query
may run at once per registry and starts are limited to four per second; excess
requests fail without queuing. This is process-local admission, not a global
multi-process quota.

`create_app(..., structured_history=registry)` optionally adds
`GET /history/structured/{query_id}`. The route is absent by default. App
composition rejects a nonregistry service or a non-PP-live origin. Unknown
queries return 404, admission/rate failures 429, and unavailable/corrupt/bounded
reads 503 with a sanitized error code. Successful responses preserve original
records and disclose `whole_market_coverage: not_established`, historical-only
provenance and no retirement authority. Existing local prediction history,
current forecast, state and health have no cloud fallback or dependency.

The `configured_cold_history` helper is separately default-off behind exact
`TRADEBOT_PP_COLD_STRUCTURED_HISTORY=true`; construction does not connect.
No production entry point calls it, builds the registry or injects the API
route. Changing that flag alone cannot expose the route.

## Validation

An isolated `/tmp` virtual environment installed the repository's pinned
`backend/requirements.txt` (Python 3.13.1, psycopg 3.2.13). A disposable native
Homebrew PostgreSQL 17.2 cluster
listened only on its temporary Unix socket. Its fixture used a minimal exact
receipt/revision schema and a dedicated non-superuser/non-bypass reader with
origin-scoped RLS; it was stopped after testing.

Combined affected suite: **65 tests run, 51 passed, 14 explicit skips, zero
failures/errors**. It includes all **23 cold-history tests**: 19 generated/API
tests and four native PostgreSQL tests. Native tests verify original canonical
bytes, PP-only row visibility, wrong-login and corrupt-receipt rejection,
effective table INSERT/column UPDATE/column REFERENCES/MAINTAIN grant rejection,
actual read-only transactions, and the whole-transaction deadline on slow SQL.
API tests verify exact decimal JSON, pagination, prior-cursor rejection after
manifest change, unknown-query/no-cloud behavior, rate/single-flight admission,
and unaffected local/current routes during cloud failure. Existing API/history
regressions include a real loopback HTTP SSE initial frame and reconnect.

The 14 skips belong to existing full-app/native-history fixtures: two require
the complete generated app database, one requires app/lifecycle roles, and
eleven require the complete native history transport fixture. They were not
supplied by the new minimal source fixture. The imported cold prototype's six
tests pass. `compileall` and `git diff --check` pass. Exact-source Linux CI and
full-schema integration remain release gates. A dependency deprecation warning
from Starlette's existing httpx TestClient is unrelated to this change.

The final command ran from the candidate repository root, after
`python3 -m venv /tmp/tradebot-cold-reader-venv` and
`/tmp/tradebot-cold-reader-venv/bin/pip install -r backend/requirements.txt`:

```sh
/tmp/tradebot-cold-reader-venv/bin/python - <<'PY'
from pathlib import Path
import getpass, subprocess, tempfile, os
base = Path(tempfile.mkdtemp(prefix='tradebot-cold-', dir='/tmp'))
pg = '/opt/homebrew/opt/postgresql@17/bin/'
subprocess.run([pg+'initdb', '-D', str(base/'data'), '-A', 'trust',
                '--no-locale', '-E', 'UTF8'], check=True, stdout=subprocess.DEVNULL)
subprocess.run([pg+'pg_ctl', '-D', str(base/'data'), '-l', str(base/'postgres.log'),
                '-o', f'-k {base} -h "" -p 55479', '-w', 'start'],
               check=True, stdout=subprocess.DEVNULL)
try:
    subprocess.run([pg+'createdb', '-h', str(base), '-p', '55479',
                    'tradebot_cold_history_test'], check=True)
    env = os.environ.copy()
    env['TRADEBOT_TEST_COLD_HISTORY_ADMIN_DSN'] = (
        f'host={base} port=55479 dbname=tradebot_cold_history_test user={getpass.getuser()}')
    script = '''import unittest
suite = unittest.TestSuite()
for pattern in ('test_cold_structured*.py','test_runtime_archive_history.py',
                'test_postgres_application.py','test_postgres_live_query_parity.py',
                'test_history_v2_envelope.py','test_history_v2_transport_pg.py'):
    suite.addTests(unittest.defaultTestLoader.discover('backend/tests', pattern=pattern))
result = unittest.TextTestRunner(verbosity=1).run(suite)
print('Cold-source+API+history regression result:',
      'PASS' if result.wasSuccessful() else 'FAIL', 'run', result.testsRun,
      'skipped', len(result.skipped), 'failures', len(result.failures),
      'errors', len(result.errors))
raise SystemExit(not result.wasSuccessful())
'''
    subprocess.run(['/tmp/tradebot-cold-reader-venv/bin/python', '-c', script],
                   env=env, check=True)
finally:
    subprocess.run([pg+'pg_ctl', '-D', str(base/'data'), '-m', 'fast', '-w', 'stop'],
                   check=True, stdout=subprocess.DEVNULL)
print('Disposable native PG17 fixture stopped:', base)
PY
```

Final output: `Ran 65 tests in 3.533s`, `OK (skipped=14)`,
`Cold-source+API+history regression result: PASS run 65 skipped 14 failures 0 errors 0`,
and `Disposable native PG17 fixture stopped: /tmp/tradebot-cold-qo7l4ey3`.
That local fixture contained generated records only and no cloud credentials.
An earlier combined attempt failed solely because the temporary venv lacked
the repository's pinned uvicorn dependency; installing the complete requirements
resolved it before the reported final pass.

## Remaining gates

- Provision and independently qualify a dedicated read-only hosted role and
  its PP-only grants/RLS; no such live structured-reader role was established
  here. Do not substitute the writer credentials. The namespace privilege check
  is a runtime guard, not a complete credential-holder/role-membership audit.
- Supply a vetted TLS/DSN/secret-file factory. The existing writer-specific
  connection factory is deliberately not reused or broadened. The injected
  factory must enforce I/O deadlines and context-manager cleanup; elapsed-time
  checks cannot cancel an arbitrary blocked Python dependency. In-flight SQL is
  bounded by PostgreSQL, as verified natively.
- Produce and authenticate the exact manifest from authoritative local/cloud
  receipts; operator-owned registry injection is a trust prerequisite, not
  proof of manifest authenticity or whole-market discovery.
- Qualify complete immutable payload coverage and real payload latency after
  the release owner's bounded backfill/capture work. Receipt counts alone are
  insufficient. This candidate does not repair missing envelopes.
- Review server composition, API authentication/network access and process-wide
  resource bounds before enabling a hosted/public route. No existing browser
  proxy or Supabase Data API grant changed. This endpoint is the application's
  optional API hook, not a deployed Supabase REST/RPC surface.
- Keep raw Storage retrieval/verification and separate raw-object recovery
  evidence. This structured endpoint does not replace raw archives, establish
  official outcomes from exchange prices, or authorize local deletion.
- Separately qualify production identities, origin isolation and deployment.
  This PP constructor intentionally rejects a production origin.

Official connection/security references:
[Postgres connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Postgres roles](https://supabase.com/docs/guides/database/postgres/roles), and
[Data API security](https://supabase.com/docs/guides/api/securing-your-api).
