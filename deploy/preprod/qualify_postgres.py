"""Linux generated-only integration. Never connects to PP/prod or cloud."""
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import tarfile
import time
from unittest.mock import patch
import uuid
import unittest
from collections import Counter
import foundation as f

REPO=Path(__file__).resolve().parents[2]
REDACTIONS=[]
DEADLINE=0
PHASE="initialization"
CI_FOUNDATION_SECRETS=Path('/etc/tradebot/pp-postgres')
CI_RUNTIME_SECRETS=Path('/etc/tradebot/pp-runtime')


def claim_ci_directory(path,owned):
    """Only a fresh generated fixture may claim these fixed Linux adapter paths."""
    if path.exists() or path.is_symlink():
        raise RuntimeError('fixed controller fixture path already exists; refusing reuse')
    path.mkdir(mode=0o700)
    info=path.lstat()
    owned.append((path,info.st_dev,info.st_ino))


def cleanup_ci_directories(owned):
    for path,device,inode in reversed(owned):
        info=path.lstat()
        if path.is_symlink() or (info.st_dev,info.st_ino)!=(device,inode) or info.st_uid!=0:
            raise RuntimeError('owned fixture path changed; preserving it for inspection')
        shutil.rmtree(path)


def qualify_controller(root):
    """Real core/Actions with only PP hostname identity substituted on CI Linux."""
    from controller import Budget,Context,Controller,HostBinding,Request,RootAuthorization
    from controller_bundle import build
    from linux_actions import LinuxActions
    source_sha=command(['git','rev-parse','HEAD']).strip()
    if not re.fullmatch('[0-9a-f]{40}',source_sha):raise RuntimeError('full CI source identity required')
    artifact=root/'controller-source.tar.gz'
    command(['git','archive','--format=tar.gz','--output='+str(artifact),source_sha],timeout=30)
    if artifact.stat().st_size>16*1024**2:raise RuntimeError('controller source archive bound exceeded')
    blob=artifact.read_bytes()
    # CI must execute the exact controller/adapter code bound by the source archive.
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        for name in ('controller.py','linux_actions.py'):
            with archive.extractfile('deploy/preprod/'+name) as source:
                if source.read()!=(f.HERE/name).read_bytes():
                    raise RuntimeError('controller working source differs from exact archive')
    controller_path=root/'controller.pyz'
    packaged=build(controller_path)
    request=Request(source_sha,hashlib.sha256(blob).hexdigest(),packaged['sha256'])
    now=datetime.now(timezone.utc)
    authorization=root/'authorization.json'
    authorization.write_text(json.dumps({**request.bindings(),'version':1,'nonce':str(uuid.uuid4()),
        'issued_at':now.isoformat(),'expires_at':(now+timedelta(minutes=20)).isoformat(),
        'data_mode':'generated','allow_migration':True,'live_collector_enabled':False,
        'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False}))
    authorization.chmod(0o600)
    staging=root/'controller-staging';staging.mkdir(mode=0o700)
    binding=HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)
    actions=LinuxActions()
    remaining=DEADLINE-time.monotonic()
    if remaining<=180:raise RuntimeError('insufficient controller recovery reserve')
    controller=Controller(binding,RootAuthorization(authorization),controller_path,staging,work_seconds=min(600,remaining-180))
    # This is the sole substitution: OS, headroom, root credentials, Docker,
    # mounts, schema, actions, API, source freshness and recovery remain real.
    with patch.object(HostBinding,'from_marker',return_value=binding):
        result=controller.deploy(request,io.BytesIO(blob),actions)
    if result.get('gate')!='PASS' or result.get('acceptance_scope')!='generated_only':
        print(json.dumps({'controller':result,'failed_smoke_phase':actions.smoke_phase,
                          'qualification_scope':'generated_ci_host_identity_substituted'},sort_keys=True),file=sys.stderr)
        raise RuntimeError('real Linux controller generated acceptance failed')
    if authorization.exists() or len(list(root.glob('consumed-*.json')))!=1:
        raise RuntimeError('controller one-use authority consumption not proven')
    replay=controller.deploy(request,io.BytesIO(blob),LinuxActions())
    if replay.get('gate')!='BLOCKED':raise RuntimeError('consumed controller authority accepted twice')
    # Exercise concrete forward-preserving failure recovery as well as the API
    # restart/readback already required by LinuxActions.smoke(). No DB restore.
    candidates=list(staging.glob('candidate-*'))
    if len(candidates)!=1:raise RuntimeError('controller retained staging is ambiguous')
    candidate=candidates[0]
    journal=json.loads((candidate/'controller-journal.json').read_text())
    context=Context(request,candidate/'source',candidate,journal['image'],failed_stage='smoke',migration_started=True)
    remaining=DEADLINE-time.monotonic()
    if remaining<=0:raise RuntimeError('no remaining generated recovery budget')
    recovery=actions.recover(context,Budget(min(180,remaining)))
    if recovery!={'strategy':'stop_candidate_keep_database','database_preserved':True,
                  'new_acknowledgements_preserved':True,'database_restored':False}:
        raise RuntimeError('real Linux forward-preserving recovery incomplete')
    return {'result':result,'qualification_scope':'generated_ci_host_identity_substituted',
            'actual_pp_host_binding':'UNQUALIFIED','controller_bundle_sha256':packaged['sha256'],
            'one_use_replay_rejected':True,'api_restart_persisted_acknowledgement':True,'recovery':recovery}


def controller_fixture_owned(owned):
    if {path for path,_,_ in owned}!={CI_FOUNDATION_SECRETS,CI_RUNTIME_SECRETS}:
        return False
    for path,device,inode in owned:
        info=path.lstat()
        if path.is_symlink() or (info.st_dev,info.st_ino)!=(device,inode) or info.st_uid!=0:
            return False
    return True


def isolate_controller_fixture(runtime_env,owned):
    """Reset only this CI-owned generated volume before real controller proof.

    Earlier integration suites intentionally use arbitrary fixture origins. A
    production controller must not learn those origins just to pass CI. The
    main harness already owns this disposable project and removes it on exit.
    """
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0 or
            f.MARKER.exists() or f.MARKER.is_symlink() or
            not CI_FOUNDATION_SECRETS.is_dir() or not CI_RUNTIME_SECRETS.is_dir() or
            not controller_fixture_owned(owned)):
        raise RuntimeError('controller fixture reset requires isolated root CI')
    runtime(['down','--volumes','--remove-orphans'],runtime_env)
    if f.run(['docker','volume','ls','--filter','name=^tradebot_pp_pgdata$','--format','{{.Name}}']):
        raise RuntimeError('generated controller volume was not removed')
    f.start(CI_FOUNDATION_SECRETS)
    # The reviewed runtime overlay mounts the existing generated lifecycle
    # secret. No credential value is read into this helper or logged.
    runtime(['up','-d','--force-recreate','--wait','--wait-timeout','60','postgres'],runtime_env)
    f.sql("CREATE ROLE tradebot_lifecycle LOGIN CONNECTION LIMIT 3 NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; "
          "DO $$ BEGIN EXECUTE format('ALTER ROLE tradebot_lifecycle PASSWORD %L',"
          "btrim(pg_read_file('/run/secrets/lifecycle'),E'\\n\\r ')); END $$; "
          "GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle;",CI_FOUNDATION_SECRETS)
    if f.sql("SELECT to_regclass('ops.outbox') IS NULL;",CI_FOUNDATION_SECRETS)!='t':
        raise RuntimeError('controller fixture is not fresh')


FAILED_RECOVERY_MODULE='test_postgres_failed_trial_drain'
TERMINAL_ARCHIVE_MODULE='test_postgres_third_trial_final_drain'
APPLICATION_TEST_PHASES=(('application_lifecycle',180),('terminal_archive_recovery',90),
                         ('failed_trial_recovery',90))


def partition_application_tests(suite):
    """Partition one discovery without omitting or duplicating a test identity."""
    def cases(node):
        if isinstance(node,unittest.TestSuite):
            for child in node:
                yield from cases(child)
        elif isinstance(node,unittest.TestCase):
            yield node
        else:
            raise RuntimeError('unexpected application test node')
    original=list(cases(suite))
    module_phases={FAILED_RECOVERY_MODULE:'failed_trial_recovery',
                   TERMINAL_ARCHIVE_MODULE:'terminal_archive_recovery'}
    groups={phase:[] for phase,_ in APPLICATION_TEST_PHASES}
    for case in original:
        module=type(case).__module__
        if case.id().startswith('unittest.loader._FailedTest.'):
            module=case.id().removeprefix('unittest.loader._FailedTest.')
        groups[module_phases.get(module,'application_lifecycle')].append(case)
    if not all(groups.values()):
        raise RuntimeError('all PostgreSQL application qualification phases are required')
    before=Counter(case.id() for case in original)
    after=Counter(case.id() for group in groups.values() for case in group)
    if before!=after:
        raise RuntimeError('application test partition lost or duplicated a test')
    return {phase:unittest.TestSuite(group) for phase,group in groups.items()}


def application_test_code(phase):
    if phase not in dict(APPLICATION_TEST_PHASES):
        raise ValueError('unknown application test phase')
    return ("import sys,unittest; sys.path.insert(0,"+repr(str(f.HERE))+"); "
            "from qualify_postgres import partition_application_tests; "
            "all_tests=unittest.defaultTestLoader.discover('backend/tests',pattern='test_postgres*.py'); "
            "s=partition_application_tests(all_tests)["+repr(phase)+"]; "
            "r=unittest.TextTestRunner(verbosity=2).run(s); "
            "raise SystemExit(0 if r.wasSuccessful() and not r.skipped and r.testsRun else 1)")


def emit_child_output(stdout,stderr):
    output=(stdout or '')+'\n'+(stderr or '')
    for secret in sorted(REDACTIONS,key=len,reverse=True):
        output=output.replace(secret,'[REDACTED]')
    output=re.sub(r'postgres(?:ql)?://[^\s\x22\x27]+','[REDACTED_DSN]',output)
    # Redact before truncation, so a tail boundary cannot expose half a secret.
    print(output[-50000:],file=sys.stderr)


def command(args,env=None,timeout=120):
    remaining=min(timeout,DEADLINE-time.monotonic())
    if remaining<=0:raise RuntimeError('qualification deadline exceeded')
    process=subprocess.Popen(args,env=env,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    started=time.monotonic()
    try:
        stdout,stderr=process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        killed=False
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:stdout,stderr=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            killed=True
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            stdout,stderr=process.communicate()
        emit_child_output(stdout,stderr)
        print(json.dumps(dict(phase=PHASE,reason='child_deadline',budget_seconds=remaining,
            elapsed_seconds=round(time.monotonic()-started,3),term_requested=True,
            kill_requested=killed,reaped=process.returncode is not None),sort_keys=True),file=sys.stderr)
        raise RuntimeError('qualification child deadline; terminated and reaped') from None
    emit_child_output(stdout,stderr)
    if process.returncode:raise RuntimeError('generated integration subprocess failed: '+str(process.returncode))
    return stdout


def qualify_cloud_contract(secret_dir):
    """Apply the proposed cloud DDL to the disposable CI database only."""
    contract=(REPO/'backend/postgres/history_v2_contract.sql').read_text()
    ddl=(REPO/'supabase/migrations/20261116050000_history_v2_private.sql').read_text()
    marker='CREATE SCHEMA history_v2;'
    if marker not in ddl or marker not in contract or ddl.split(marker,1)[-1]!=contract.split(marker,1)[-1]:
        raise RuntimeError('cloud migration diverged from reviewed contract')
    if 'CREATE SCHEMA history_v2;' not in ddl or 'CREATE TABLE public.' in ddl:
        raise RuntimeError('cloud contract scope changed')
    f.sql('CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;',secret_dir)
    before=f.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';",secret_dir).strip()
    f.sql('BEGIN;\n'+ddl+'\nCOMMIT;',secret_dir,timeout=40)
    proof=json.loads(f.sql("""SELECT json_build_object(
      'public_tables_before', %s,
      'public_tables_after', (SELECT count(*) FROM information_schema.tables WHERE table_schema='public'),
      'private_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE n.nspname='history_v2' AND c.relkind='r'),
      'rls_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname='history_v2' AND c.relkind='r' AND c.relrowsecurity),
      'anon_schema_access', has_schema_privilege('anon','history_v2','USAGE'),
      'authenticated_schema_access', has_schema_privilege('authenticated','history_v2','USAGE'),
      'service_schema_access', has_schema_privilege('service_role','history_v2','USAGE'),
      'anon_table_access', has_table_privilege('anon','history_v2.markets','SELECT'),
      'authenticated_table_access', has_table_privilege('authenticated','history_v2.markets','SELECT'),
      'service_table_access', has_table_privilege('service_role','history_v2.markets','SELECT'),
      'exact_epoch', history_v2.source_epoch('1969-12-31T23:59:59.999999999Z')::text);
      """ % before,secret_dir))
    if (proof['public_tables_before']!=proof['public_tables_after'] or
        proof['private_tables']!=10 or proof['rls_tables']!=10 or
        any(proof[key] for key in ('anon_schema_access','authenticated_schema_access',
                                   'service_schema_access','anon_table_access',
                                   'authenticated_table_access','service_table_access')) or
        proof['exact_epoch']!='-0.000000001'):
        raise RuntimeError('generated cloud contract privacy or precision check failed')
    return proof


def qualify_structured_receipts(secret_dir):
    """Apply the additive receipt table only to disposable generated CI data."""
    ddl=(REPO/'supabase/migrations/20261118012340_structured_receipts_v2.sql').read_text()
    if ('CREATE TABLE history_v2.structured_receipts' not in ddl or
            'ALTER TABLE history_v2.structured_receipts ENABLE ROW LEVEL SECURITY' not in ddl or
            'GRANT ' in ddl or 'CREATE TABLE public.' in ddl):
        raise RuntimeError('private structured receipt migration scope changed')
    f.sql('BEGIN;\n'+ddl+'\nCOMMIT;',secret_dir,timeout=40)
    proof=json.loads(f.sql("""SELECT json_build_object(
      'private_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE n.nspname='history_v2' AND c.relkind='r'),
      'rls', (SELECT relrowsecurity FROM pg_class WHERE oid='history_v2.structured_receipts'::regclass),
      'anon_access', has_table_privilege('anon','history_v2.structured_receipts','SELECT'),
      'authenticated_access', has_table_privilege('authenticated','history_v2.structured_receipts','SELECT'),
      'service_access', has_table_privilege('service_role','history_v2.structured_receipts','SELECT'));
      """,secret_dir))
    if (proof['private_tables']!=11 or proof['rls'] is not True or
            any(proof[key] for key in ('anon_access','authenticated_access','service_access'))):
        raise RuntimeError('generated receipt privacy check failed')
    return proof


def qualify_pp_history_role(secret_dir):
    """Prove exact-origin grants and denials in disposable PostgreSQL only."""
    ddl=(REPO/'supabase/migrations/20261118020000_pp_history_v2_role.sql').read_text()
    if 'CREATE ROLE tradebot_pp_history NOLOGIN' not in ddl:
        raise RuntimeError('PP private history role scope changed')
    f.sql('BEGIN;\n'+ddl+'\nCOMMIT;', secret_dir, timeout=40)
    proof=json.loads(f.sql("""SELECT json_build_object(
      'role_no_login', NOT r.rolcanlogin,
      'role_no_bypass', NOT r.rolbypassrls,
      'role_no_superuser', NOT r.rolsuper,
      'role_no_inherit', NOT r.rolinherit,
      'role_connection_limit', r.rolconnlimit,
      'pp_policies', (SELECT count(*) FROM pg_policies WHERE schemaname='history_v2'
                         AND 'tradebot_pp_history'=ANY(roles)),
      'pp_select_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='history_v2' AND c.relkind='r'
        AND has_table_privilege('tradebot_pp_history',c.oid,'SELECT')),
      'pp_insert_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='history_v2' AND c.relkind='r'
        AND has_table_privilege('tradebot_pp_history',c.oid,'INSERT')),
      'pp_update_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='history_v2' AND c.relkind='r'
        AND has_table_privilege('tradebot_pp_history',c.oid,'UPDATE')),
      'anon_schema_access', has_schema_privilege('anon','history_v2','USAGE'),
      'authenticated_schema_access', has_schema_privilege('authenticated','history_v2','USAGE'),
      'service_schema_access', has_schema_privilege('service_role','history_v2','USAGE'),
      'pp_coverage_access', has_table_privilege('tradebot_pp_history','history_v2.coverage','SELECT'),
      'pp_receipt_access', CASE WHEN to_regclass('history_v2.structured_receipts') IS NULL
        THEN false ELSE has_table_privilege('tradebot_pp_history',
          to_regclass('history_v2.structured_receipts'),'SELECT') END,
      'pp_delete_access', has_table_privilege('tradebot_pp_history','history_v2.generation_checkpoints','DELETE'),
      'pp_immutable_update', has_table_privilege('tradebot_pp_history','history_v2.predictions','UPDATE'))
      FROM pg_roles r WHERE r.rolname='tradebot_pp_history';""",secret_dir))
    if (not all(proof[key] for key in ('role_no_login','role_no_bypass','role_no_superuser',
                                     'role_no_inherit')) or
        proof['role_connection_limit']!=2 or proof['pp_policies']!=21 or
        proof['pp_select_tables']!=9 or proof['pp_insert_tables']!=9 or
        proof['pp_update_tables']!=3 or
        any(proof[key] for key in ('anon_schema_access','authenticated_schema_access',
                                  'service_schema_access','pp_coverage_access',
                                  'pp_receipt_access','pp_delete_access',
                                  'pp_immutable_update'))):
        raise RuntimeError('PP private history privilege check failed')
    f.sql((REPO/'deploy/preprod/tests/pp_history_v2_role.sql').read_text(),
          secret_dir,timeout=20)
    return proof


def qualify_pp_receipt_grants(secret_dir):
    """Exercise the receipt extension only in disposable generated PostgreSQL."""
    # PG17/Supabase can auto-grant an inbound ADMIN-only edge to its creator.
    # Exercise that exact cloud-catalog shape without any PP privilege gain.
    f.sql('GRANT tradebot_pp_history TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE;',
          secret_dir)
    # qualify_structured_receipts applied the reviewed table migration first.
    ddl=(REPO/'supabase/migrations/20261118031407_pp_structured_receipt_grants.sql').read_text()
    if ('GRANT SELECT, INSERT ON history_v2.structured_receipts TO tradebot_pp_history' not in ddl or
            'ALTER ROLE' in ddl or 'CREATE ROLE' in ddl):
        raise RuntimeError('PP receipt grant scope changed')
    f.sql('BEGIN;\n'+ddl+'\nCOMMIT;',secret_dir,timeout=40)
    proof=json.loads(f.sql("""SELECT json_build_object(
      'role_no_login', NOT r.rolcanlogin,
      'receipt_select', has_table_privilege('tradebot_pp_history',
        'history_v2.structured_receipts','SELECT'),
      'receipt_insert', has_table_privilege('tradebot_pp_history',
        'history_v2.structured_receipts','INSERT'),
      'receipt_update', has_table_privilege('tradebot_pp_history',
        'history_v2.structured_receipts','UPDATE'),
      'receipt_delete', has_table_privilege('tradebot_pp_history',
        'history_v2.structured_receipts','DELETE'),
      'receipt_policies', (SELECT count(*) FROM pg_policies
        WHERE schemaname='history_v2' AND tablename='structured_receipts'
          AND 'tradebot_pp_history'=ANY(roles)),
      'anon_access', has_table_privilege('anon',
        'history_v2.structured_receipts','SELECT'),
      'authenticated_access', has_table_privilege('authenticated',
        'history_v2.structured_receipts','SELECT'),
      'service_access', has_table_privilege('service_role',
        'history_v2.structured_receipts','SELECT'))
      FROM pg_roles r WHERE r.rolname='tradebot_pp_history';""",secret_dir))
    if (not all(proof[key] for key in ('role_no_login','receipt_select','receipt_insert')) or
            proof['receipt_policies']!=2 or
            any(proof[key] for key in ('receipt_update','receipt_delete',
                                      'anon_access','authenticated_access','service_access'))):
        raise RuntimeError('PP private receipt privilege check failed')
    f.sql((REPO/'deploy/preprod/tests/pp_structured_receipt_grants.sql').read_text(),
          secret_dir,timeout=20)
    proof['receipt_schema_source']='supabase/migrations/20261118012340_structured_receipts_v2.sql'
    return proof


def qualify_pp_storage_policy(secret_dir):
    """Exercise a substituted review template against disposable Storage RLS."""
    fixture=(REPO/'deploy/preprod/tests/pp_storage_policy_fixture.sql').read_text()
    template=(REPO/'supabase/review/pp_market_raw_storage_policies.sql.in').read_text()
    marker='__PP_STORAGE_AUTH_UID__'
    email_marker='__PP_STORAGE_AUTH_EMAIL__'
    if template.count(marker)!=4 or template.count(email_marker)!=1 or \
            'storage.object.upload' not in template or \
            'storage.object.get_authenticated' not in template or \
            'object.get_authenticated_info' not in template or \
            'storage.allow_any_operation' not in template:
        raise RuntimeError('PP Storage review template scope changed')
    f.sql(fixture,secret_dir,timeout=20)
    try:
        f.sql(template,secret_dir,timeout=20)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('unbound PP Storage template unexpectedly applied')
    if f.sql("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects';",
             secret_dir).strip()!='0':
        raise RuntimeError('unbound PP Storage template left a policy')
    # This UUID belongs only to the generated fixture. It is not a credential
    # or a proposed live Auth user, and the unfilled template is never applied.
    candidate=(template.replace(marker,'00000000-0000-4000-8000-0000000000aa')
              .replace(email_marker,'pp-storage-archive@example.invalid'))
    f.sql("UPDATE auth.users SET raw_app_meta_data='{}'::jsonb;",secret_dir)
    try:
        f.sql(candidate,secret_dir,timeout=20)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('wrong Auth metadata admitted PP Storage policy')
    if f.sql("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects';",
             secret_dir).strip()!='0':
        raise RuntimeError('failed Auth binding left a Storage policy')
    f.sql("UPDATE auth.users SET raw_app_meta_data="
          "'{\"tradebot_role\":\"pp_storage_archive\",\"tradebot_origin\":\"pp-live-pp\"}'::jsonb;",
          secret_dir)
    f.sql("UPDATE auth.users SET email_confirmed_at=NULL;",secret_dir)
    try:
        f.sql(candidate,secret_dir,timeout=20)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('unconfirmed Auth user admitted PP Storage policy')
    f.sql("UPDATE auth.users SET email_confirmed_at=now();",secret_dir)
    f.sql(candidate,secret_dir,timeout=20)
    proof=json.loads(f.sql("""SELECT json_build_object(
      'private_bucket', (SELECT NOT public FROM storage.buckets WHERE id='market-raw'),
      'policies', (SELECT count(*) FROM pg_policies WHERE schemaname='storage'
                         AND tablename='objects'),
      'upload_insert_only', EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage'
                         AND tablename='objects' AND policyname='tradebot_pp_raw_upload'
                         AND cmd='INSERT' AND roles::text[]=ARRAY['authenticated']::text[]),
      'readback_select_only', EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage'
                         AND tablename='objects' AND policyname='tradebot_pp_raw_readback'
                         AND cmd='SELECT' AND roles::text[]=ARRAY['authenticated']::text[]))""",secret_dir))
    if (proof['private_bucket'] is not True or proof['policies']!=2 or
        proof['upload_insert_only'] is not True or
        proof['readback_select_only'] is not True):
        raise RuntimeError('PP Storage policy metadata mismatch')
    f.sql((REPO/'deploy/preprod/tests/pp_storage_policy_denials.sql').read_text(),
          secret_dir,timeout=20)
    from bind_market_raw_policy import render_rollback,render_readback_patch
    rollback=render_rollback('00000000-0000-4000-8000-0000000000aa',
                             'pp-storage-archive@example.invalid',
                             project_ref='xttdqeimdujweijxcuro',bucket='market-raw')
    f.sql(rollback.decode('ascii'),secret_dir,timeout=20)
    if f.sql("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects';",
             secret_dir).strip()!='0' or \
       f.sql("SELECT count(*) FROM storage.objects;",secret_dir).strip()!='2':
        raise RuntimeError('policy-only rollback changed generated objects or left policies')
    current_readback=("storage.allow_any_operation(ARRAY[\n"
                      "      'storage.object.get_authenticated','object.get_authenticated_info'])")
    old_readback="storage.allow_only_operation('storage.object.get_authenticated')"
    if candidate.count(current_readback)!=1:
        raise RuntimeError('reviewed readback policy expression changed')
    f.sql("INSERT INTO storage.objects(bucket_id,name,owner_id) VALUES ("
          "'market-raw',"
          "'raw-v1/6157f7800b12255ab48111b5c6258a444712a38baca54d3b0929ede8994b2ae8/"
          "500b0871-6f59-46de-a17c-537f6b0aee5d/"
          "5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf.jsonl.gz',"
          "'00000000-0000-4000-8000-0000000000aa');",secret_dir)
    legacy_candidate=candidate.replace(current_readback,old_readback)
    f.sql(legacy_candidate,secret_dir,timeout=20)
    hash_sql=("SELECT encode(sha256(convert_to(jsonb_agg(to_jsonb(p) ORDER BY p.policyname)::text,"
              "'UTF8')),'hex') FROM pg_policies p WHERE p.schemaname='storage'"
              " AND p.tablename='objects';")
    catalog_hash=f.sql(hash_sql,secret_dir).strip()
    patch=render_readback_patch('00000000-0000-4000-8000-0000000000aa',
                                'pp-storage-archive@example.invalid',
                                project_ref='xttdqeimdujweijxcuro',bucket='market-raw',
                                expected_policy_sha256=catalog_hash).decode('ascii')
    try:
        f.sql(patch.replace(catalog_hash,'f'*64),secret_dir,timeout=20)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('wrong policy catalog hash admitted readback amendment')
    if f.sql(hash_sql,secret_dir).strip()!=catalog_hash:
        raise RuntimeError('failed readback amendment changed policy catalog')
    f.sql(patch,secret_dir,timeout=20)
    f.sql((REPO/'deploy/preprod/tests/pp_storage_readback_patch_denials.sql').read_text(),
          secret_dir,timeout=20)
    if f.sql("SELECT count(*) FROM storage.objects;",secret_dir).strip()!='3':
        raise RuntimeError('readback amendment changed generated objects')
    reader_uid = '00000000-0000-4000-8000-0000000000bb'
    reader_policy = (REPO/'supabase/review/pp_history_reader_policies.sql.in').read_text()
    # Bind the separate identity and add deliberately permissive policies to
    # exercise the reader's restrictive gates. Roll back the isolated fixture.
    sql = reader_policy.replace('__PP_HISTORY_READER_UID__',reader_uid).replace(
        '__PP_STORAGE_AUTH_UID__','00000000-0000-4000-8000-0000000000aa')
    sql = sql.replace('BEGIN;', """BEGIN;
        INSERT INTO auth.users VALUES ('00000000-0000-4000-8000-0000000000bb',
        'reader@example.invalid','authenticated',now(),
        '{"tradebot_role":"pp_storage_history_reader","tradebot_origin":"pp-live-pp"}');""", 1)
    checks = (REPO/'deploy/preprod/tests/pp_history_reader_denials.sql').read_text()
    f.sql(sql.removesuffix('COMMIT;\n') + checks, secret_dir,timeout=20)
    proof['history_reader_scoped_get_and_mutation_denials'] = True
    f.sql(rollback.decode('ascii'),secret_dir,timeout=20)
    if f.sql("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects';",
             secret_dir).strip()!='0' or \
       f.sql("SELECT count(*) FROM storage.objects;",secret_dir).strip()!='3':
        raise RuntimeError('amended policy rollback changed objects or left policies')
    return proof


def qualify_watch_diagnostic_slot(container):
    """Two independent Linux processes contend before either can start a second psql."""
    from controller import Budget
    from linux_actions import LinuxActions, WATCH_DIAGNOSTIC_LOCK

    f.run(['docker','exec',container,'flock','-F',WATCH_DIAGNOSTIC_LOCK,'sh','-ec',
           'code=0; flock -n -E 75 -F "$1" true || code=$?; test "$code" = 75',
           'check-reader-lock',WATCH_DIAGNOSTIC_LOCK])
    actions = LinuxActions(watch_diagnostics=True)
    actions.pg_id = container
    for query in (actions._sql, actions._reader_sql):
        if query(Budget(10),"SELECT session_user||':'||current_setting('transaction_read_only')") != 'tradebot_reader:on':
            raise RuntimeError('generated watch diagnostic login or read-only mode differs')


def main():
    global DEADLINE, PHASE
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0 or f.MARKER.exists() or f.MARKER.is_symlink():
        raise RuntimeError('only isolated root Linux CI is allowed')
    if any(path.exists() or path.is_symlink() for path in (CI_FOUNDATION_SECRETS,CI_RUNTIME_SECRETS)):
        raise RuntimeError('fixed controller fixture secret paths already exist; refusing any runtime mutation')
    DEADLINE=time.monotonic()+600
    f.DEADLINE=DEADLINE
    started=time.monotonic()
    PHASE="installer_effective_uid"
    root_controls=("import unittest; s=unittest.defaultTestLoader.discover('deploy/preprod/tests',"
                   "pattern='test_install_controller_root.py'); r=unittest.TextTestRunner(verbosity=2).run(s); "
                   "raise SystemExit(0 if r.wasSuccessful() and not r.skipped and r.testsRun else 1)")
    command([sys.executable,'-c',root_controls],timeout=15)
    with tempfile.TemporaryDirectory(prefix='tradebot-pg-qualified-') as folder:
        root=Path(folder)
        runtime_env=None
        owned=[]
        foundation_attempted=False
        secret_parent=CI_FOUNDATION_SECRETS.parent
        created_parent=False
        try:
            if secret_parent.is_symlink():raise RuntimeError('unsafe fixed secret parent')
            if not secret_parent.exists():
                secret_parent.mkdir(mode=0o700);created_parent=True
            parent_info=secret_parent.stat()
            if parent_info.st_uid!=0 or parent_info.st_mode & 0o022:raise RuntimeError('unsafe fixed secret parent')
            claim_ci_directory(CI_FOUNDATION_SECRETS,owned)
            claim_ci_directory(CI_RUNTIME_SECRETS,owned)
            PHASE="foundation"
            # Never let generated cleanup adopt an existing named project/volume.
            if (f.run(['docker','ps','-a','--filter','label=com.docker.compose.project=tradebot-pp-foundation','--format','{{.ID}}'])
                    or f.run(['docker','volume','ls','--filter','name=^tradebot_pp_pgdata$','--format','{{.Name}}'])):
                raise RuntimeError('generated CI project or volume already exists; refusing reuse')
            foundation_attempted=True
            f.start(CI_FOUNDATION_SECRETS)
            baseline=f.verify(CI_FOUNDATION_SECRETS)
            PHASE="isolated_role_provisioning"
            cid=f.compose(['ps','-q','postgres'],CI_FOUNDATION_SECRETS)
            qualify_watch_diagnostic_slot(cid)
            info=json.loads(f.run(['docker','inspect','--format','{{json .NetworkSettings.Networks}}',cid]))
            address=next(iter(info.values()))['IPAddress']
            passwords={name:(CI_FOUNDATION_SECRETS/name).read_text().strip() for name in f.ROLES}
            passwords['lifecycle']=secrets.token_hex(32)
            REDACTIONS.extend(passwords.values())
            f.compose(['exec','-T','postgres','sh','-ec','umask 077; cat > /tmp/generated-lifecycle-password; chown postgres:postgres /tmp/generated-lifecycle-password'],CI_FOUNDATION_SECRETS,input=passwords['lifecycle'])
            f.sql("CREATE ROLE tradebot_lifecycle LOGIN CONNECTION LIMIT 3 NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; DO $$ BEGIN EXECUTE format('ALTER ROLE tradebot_lifecycle PASSWORD %L',pg_read_file('/tmp/generated-lifecycle-password')); END $$; GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle;",CI_FOUNDATION_SECRETS)
            f.compose(['exec','-T','postgres','rm','/tmp/generated-lifecycle-password'],CI_FOUNDATION_SECRETS)
            dsns={name:'postgresql://'+role+':'+passwords[name]+'@'+address+':5432/tradebot_pp' for name,role in {**f.ROLES,'lifecycle':'tradebot_lifecycle'}.items()}
            REDACTIONS.extend(dsns.values())
            # The isolated CI database uses the same reviewed generated origin
            # as PP; the controller must not admit a third production origin.
            env={**os.environ,'PYTHONPATH':str(REPO/'backend'),'TRADEBOT_ENVIRONMENT':'preprod','TRADEBOT_DATA_MODE':'generated','TRADEBOT_ORIGIN_ID':'generated-pp','TRADEBOT_COLLECTOR_ENABLED':'false'}
            names={'migrator':'TRADEBOT_TEST_MIGRATOR_DSN','application':'TRADEBOT_TEST_APP_DSN','reader':'TRADEBOT_TEST_READER_DSN','lifecycle':'TRADEBOT_TEST_LIFECYCLE_DSN'}
            for name,key in names.items():
                p=root/(name+'-dsn');p.write_text(dsns[name]);p.chmod(0o600)
                env[key]=dsns[name];env[key+'_FILE']=str(p)
            env['TRADEBOT_TEST_DSN']=dsns['application']
            env['TRADEBOT_TEST_DSN_FILE']=env['TRADEBOT_TEST_APP_DSN_FILE']
            # A skipped DB case is not a passing qualification.
            PHASE='schema'
            code=("import unittest; s=unittest.defaultTestLoader.discover('backend/tests/postgres',pattern='test*.py'); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(0 if r.wasSuccessful() and not r.skipped and r.testsRun else 1)")
            command([sys.executable,'-c',code],env,timeout=180)
            # Preserve the original 180s application bound. Recovery's real
            # 20,362-ACK qualification gets its own measured, finite 90s phase.
            # Both subprocesses discover the same complete test set and prove
            # the exact module partition; skipped/empty phases remain failures.
            for phase,seconds in APPLICATION_TEST_PHASES:
                PHASE=phase
                command([sys.executable,'-c',application_test_code(phase)],env,timeout=seconds)
            PHASE='generated_cloud_contract'
            cloud_contract=qualify_cloud_contract(CI_FOUNDATION_SECRETS)
            PHASE='generated_pp_history_role'
            pp_history_role=qualify_pp_history_role(CI_FOUNDATION_SECRETS)
            PHASE='generated_structured_receipts'
            receipt_contract=qualify_structured_receipts(CI_FOUNDATION_SECRETS)
            PHASE='generated_pp_receipt_grants'
            pp_receipt_grants=qualify_pp_receipt_grants(CI_FOUNDATION_SECRETS)
            PHASE='generated_pp_immutable_revision_envelopes'
            revision_ddl=(REPO/'supabase/migrations/20261119020000_pp_structured_revision_payloads.sql').read_text()
            f.sql('BEGIN;\n'+revision_ddl+'\nCOMMIT;', CI_FOUNDATION_SECRETS, timeout=40)
            f.sql((REPO/'deploy/preprod/tests/pp_revision_envelopes.sql').read_text(),CI_FOUNDATION_SECRETS)
            PHASE='generated_pp_storage_policy'
            pp_storage_policy=qualify_pp_storage_policy(CI_FOUNDATION_SECRETS)
            env['TRADEBOT_TEST_HISTORY_V2_DSN']=dsns['admin']
            command([sys.executable,'-m','unittest','backend.tests.test_history_v2_transport_pg',
                     'deploy.preprod.tests.test_lifetime_inventory_pg',
                     'deploy.preprod.tests.test_pp20_forward_bootstrap_pg','-v'],
                    env,timeout=90)
            PHASE='runtime_image'
            command(['docker','build','-f','deploy/preprod/Dockerfile','-t','tradebot-pg-test','.'],timeout=200)
            runtime_env={**os.environ,'PP_SECRET_DIR':str(CI_FOUNDATION_SECRETS),'PP_RUNTIME_SECRET_DIR':str(CI_RUNTIME_SECRETS),'PP_APP_IMAGE':'tradebot-pg-test'}
            for name,role in [('app_dsn','application'),('lifecycle_dsn','lifecycle'),('migrator_dsn','migrator')]:
                path=CI_RUNTIME_SECRETS/name;path.write_text(dsns[role].replace('@'+address+':','@postgres:'));path.chmod(0o400);os.chown(path,10001,10001)
            token=CI_RUNTIME_SECRETS/'operator_token'
            token.write_text(secrets.token_hex(32));token.chmod(0o400);os.chown(token,10001,10001)
            (CI_FOUNDATION_SECRETS/'lifecycle').write_text(passwords['lifecycle']);(CI_FOUNDATION_SECRETS/'lifecycle').chmod(0o400);os.chown(CI_FOUNDATION_SECRETS/'lifecycle',999,999)
            PHASE='ci_only_postgres_secret_mount_recreation'
            runtime(['up','-d','--force-recreate','--wait','--wait-timeout','60','postgres'],runtime_env)
            PHASE='runtime_explicit_migration'
            runtime(['run','--rm','--no-deps','migrate'],runtime_env)
            PHASE='runtime_generated_bootstrap'
            runtime(['run','--rm','--no-deps','lifecycle','python','-m','postgres.lifecycle_worker','--once','--bootstrap'],runtime_env)
            PHASE='runtime_services'
            runtime(['up','-d','--no-deps','--wait','--wait-timeout','40','api','calculation','lifecycle','operator'],runtime_env)
            PHASE='runtime_api_sse_acceptance'
            acceptance=json.loads(runtime(['exec','-T','api','python','-m','postgres.acceptance','--base-url','http://api:8000'],runtime_env))
            if acceptance.get('status')!='pass' or acceptance.get('collector_enabled') is not False:
                raise RuntimeError('runtime acceptance incomplete')
            PHASE='controller_fixture_isolation'
            isolate_controller_fixture(runtime_env,owned)
            PHASE='real_linux_controller'
            controller_proof=qualify_controller(root)
            PHASE='resource_accounting'
            sizes=json.loads(f.sql("SELECT json_build_object('database_bytes',pg_database_size(current_database()),'generated_relation_bytes',(SELECT coalesce(sum(pg_total_relation_size(c.oid)),0) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('raw','core','ops','archive') AND c.relkind IN ('r','p')),'wal_bytes',(SELECT sum(size) FROM pg_ls_waldir()));",CI_FOUNDATION_SECRETS))
            if sizes['generated_relation_bytes']>64*1024**2:raise RuntimeError('generated 64 MiB allowance exceeded')
            print(json.dumps({'result':'PASS_GENERATED_POSTGRES_INTEGRATION','elapsed_seconds':round(time.monotonic()-started,3),'baseline':baseline,'sizes':sizes,'runtime':acceptance,'controller':controller_proof,'controller_fixture_isolated':True,'cloud_contract':cloud_contract,'pp_history_role':pp_history_role,'pp_receipt_grants':pp_receipt_grants,'pp_storage_policy':pp_storage_policy,'receipt_contract':receipt_contract,'production_access':False,'cloud_writes':False,'representative_capacity':'NOT_PERFORMED'},sort_keys=True))
        finally:
            f.DEADLINE=time.monotonic()+90
            try:
                if runtime_env:
                    runtime(['down','--volumes','--remove-orphans'],runtime_env,recovery=True)
                elif foundation_attempted:
                    f.compose(['down','--volumes'],CI_FOUNDATION_SECRETS,timeout=90)
            finally:
                cleanup_ci_directories(owned)
                if created_parent:
                    try:secret_parent.rmdir()
                    except OSError:pass

def runtime(args,env,recovery=False):
    cmd=['docker','compose','--env-file','/dev/null','--project-directory',str(f.HERE),'-f',str(f.HERE/'compose.yaml'),'-f',str(f.HERE/'runtime.compose.yaml'),*args]
    if recovery:return f.run(cmd,env=env,timeout=90)
    return command(cmd,env,timeout=90)

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.TimeoutExpired):
        print(json.dumps({'result':'FAIL','phase':PHASE,'scope':'isolated_generated_ci','production_access':False}))
        raise SystemExit('generated PostgreSQL qualification FAIL; see sanitized phase output') from None
