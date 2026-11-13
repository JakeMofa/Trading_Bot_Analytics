import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller as c

NOW=datetime(2026,11,13,tzinfo=timezone.utc)
SHA='a'*40


def bundle(extra=(),source=SHA):
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.PAX_FORMAT,pax_headers={'comment':source}) as archive:
        for name in sorted(c.REQUIRED_FILES):
            member=tarfile.TarInfo(name)
            data=b'# generated source fixture\n'
            member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
        for member,data in extra:
            archive.addfile(member,io.BytesIO(data) if data is not None else None)
    return gzip.compress(raw.getvalue(),mtime=0)


class Clock:
    def __init__(self):self.now=1000.0
    def __call__(self):return self.now


class Actions:
    def __init__(self,fail=None,clock=None,advance=0,evidence=None,recovery=None):
        self.calls=[]
        self.fail=fail
        self.clock=clock
        self.advance=advance
        self.evidence=evidence
        self.recovery=recovery
        self.recovery_context=None
        self.recovery_seconds=None
    def call(self,stage):
        self.calls.append(stage)
        if stage==self.fail:
            raise RuntimeError('private credential diagnostics must never escape')
        if stage=='build' and self.clock:
            self.clock.now+=self.advance
    def preflight(self,context,budget):self.call('preflight')
    def build(self,context,budget):
        self.call('build')
        return 'sha256:'+'b'*64
    def migrate(self,context,budget):self.call('migrate')
    def start(self,context,budget):self.call('start')
    def smoke(self,context,budget):
        self.call('smoke')
        return self.evidence if self.evidence is not None else {
            'checks':dict.fromkeys(c.CHECKS,'PASS'),'acceptance_scope':'generated_only',
            'live_collector_enabled':False,'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False}
    def recover(self,context,budget):
        self.recovery_context=context
        self.recovery_seconds=budget.timeout()
        self.call('recover')
        return self.recovery if self.recovery is not None else {
            'strategy':'stop_candidate_keep_database','database_preserved':True,
            'new_acknowledgements_preserved':True,'database_restored':False}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.stage=self.root/'staging'
        self.stage.mkdir(mode=0o700)
        self.installed=self.root/'controller.py'
        self.installed.write_bytes(b'qualified installed core fixture')
        self.installed.chmod(0o600)
        self.raw=bundle()
        self.request=c.Request(SHA,hashlib.sha256(self.raw).hexdigest(),hashlib.sha256(self.installed.read_bytes()).hexdigest())
        self.binding=c.HostBinding(c.INSTANCE,'preprod','Tradebot',False,False,False)
        self.authority_path=self.root/'authorization.json'
        self.clock=Clock()
        self.permit={**self.request.bindings(),'version':1,'nonce':str(uuid.uuid4()),
                     'data_mode':'generated','allow_migration':True,'live_collector_enabled':False,
                     'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False,
                     'issued_at':(NOW-timedelta(seconds=1)).isoformat(),'expires_at':(NOW+timedelta(minutes=10)).isoformat()}
        self.write_permit()
    def tearDown(self):self.temp.cleanup()
    def write_permit(self):
        self.authority_path.write_text(json.dumps(self.permit))
        self.authority_path.chmod(0o600)
    def controller(self,binding=None):
        return c.Controller(binding or self.binding,c.RootAuthorization(self.authority_path,os.geteuid()),
            self.installed,self.stage,expected_uid=os.geteuid(),clock=self.clock,wall_clock=lambda:NOW)
    def deploy(self,actions=None,raw=None,request=None,binding=None):
        return self.controller(binding).deploy(request or self.request,io.BytesIO(raw or self.raw),actions or Actions())

    def test_budget_override_can_only_reduce_work_allowance(self):
        for value in (0,-1,601):
            with self.subTest(value=value),self.assertRaises(c.DeploymentHold):
                c.Controller(self.binding,c.RootAuthorization(self.authority_path,os.geteuid()),
                             self.installed,self.stage,expected_uid=os.geteuid(),work_seconds=value)

    def test_before_migration_recovery_can_preserve_prior_runtime(self):
        actions=Actions(fail='build',recovery={'strategy':'prior_runtime_unchanged',
            'database_preserved':True,'new_acknowledgements_preserved':True,'database_restored':False})
        result=self.deploy(actions)
        self.assertEqual(result['gate'],'BLOCKED')
        self.assertFalse(actions.recovery_context.migration_started)
        self.assertEqual(result['recovery']['strategy'],'prior_runtime_unchanged')

    def test_success_requires_real_adapter_evidence_and_consumes_once(self):
        actions=Actions()
        result=self.deploy(actions)
        self.assertEqual(result['gate'],'PASS')
        self.assertEqual(result['acceptance_scope'],'generated_only')
        self.assertEqual(actions.calls,['preflight','build','migrate','start','smoke'])
        self.assertFalse(self.authority_path.exists())
        self.assertEqual(len(list(self.root.glob('consumed-*.json'))),1)
        source=next(self.stage.glob('candidate-*'))
        self.assertEqual((source/'source/backend/postgres/api.py').stat().st_mode & 0o777,0o644)
        self.assertEqual((source/'source/backend/postgres').stat().st_mode & 0o777,0o755)
        self.assertEqual(source.stat().st_mode & 0o777,0o700)
        self.assertEqual(json.loads((source/'controller-journal.json').read_text())['stage'],'complete')
        # Reissuing the same nonce cannot revive this permission.
        self.write_permit()
        replay=Actions()
        self.assertEqual(self.deploy(replay)['gate'],'BLOCKED')
        self.assertEqual(replay.calls,['preflight'])

    def test_strict_remote_command(self):
        command=f'deploy-v1 preprod {c.INSTANCE} {SHA} '+self.request.artifact_sha256+' '+self.request.controller_sha256
        self.assertEqual(c.Request.parse(command),self.request)
        for bad in (command+'; id',command+' ',command.replace('preprod','production'),command.replace('deploy-v1','sh'),command.replace(' ','  ',1)):
            with self.subTest(command=bad),self.assertRaises(c.DeploymentHold):c.Request.parse(bad)

    def test_wrong_host_fails_before_adapter(self):
        actions=Actions()
        result=self.deploy(actions,binding=replace(self.binding,hostname='tradebot-analytics-01'))
        self.assertEqual(result['reason'],'wrong_host_binding')
        self.assertEqual(actions.calls,[])
        self.assertTrue(self.authority_path.exists())

    def test_wrong_source_artifact_controller_authority_and_expiry(self):
        for field,value in [('source_sha','c'*40),('artifact_sha256','c'*64),('controller_sha256','c'*64),
                            ('expires_at',(NOW-timedelta(seconds=1)).isoformat()),('live_collector_enabled',True),('data_mode','live')]:
            with self.subTest(field=field):
                original=self.permit[field]
                self.permit[field]=value
                self.write_permit()
                actions=Actions()
                self.assertEqual(self.deploy(actions)['gate'],'BLOCKED')
                self.assertEqual(actions.calls,[])
                self.permit[field]=original
        self.write_permit()
        self.installed.write_bytes(b'changed installed controller')
        self.assertEqual(self.deploy()['reason'],'controller_digest_mismatch')

    def test_unsafe_authority_permissions_and_symlink(self):
        self.authority_path.chmod(0o644)
        self.assertEqual(self.deploy()['reason'],'unsafe_trusted_file_mode')
        self.authority_path.unlink()
        self.authority_path.symlink_to(self.installed)
        self.assertEqual(self.deploy()['gate'],'BLOCKED')

    def test_archive_digest_source_comment_and_malicious_types(self):
        bad_entries=[]
        for path in ('../escape','/absolute','backend/../../escape','backend\\escape','.env','data/local.db'):
            item=tarfile.TarInfo(path);item.size=1
            bad_entries.append((item,b'x'))
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE):
            item=tarfile.TarInfo('evil');item.type=kind;item.linkname='/etc/passwd'
            bad_entries.append((item,None))
        for entry in bad_entries:
            with self.subTest(name=entry[0].name,type=entry[0].type):
                raw=bundle([entry])
                request=replace(self.request,artifact_sha256=hashlib.sha256(raw).hexdigest())
                self.permit['artifact_sha256']=request.artifact_sha256
                self.write_permit()
                actions=Actions()
                self.assertEqual(self.deploy(actions,raw,request)['gate'],'BLOCKED')
                self.assertEqual(actions.calls,[])
                self.assertEqual(list(self.stage.iterdir()),[])
        raw=bundle(source='d'*40)
        request=replace(self.request,artifact_sha256=hashlib.sha256(raw).hexdigest())
        self.permit['artifact_sha256']=request.artifact_sha256;self.write_permit()
        self.assertEqual(self.deploy(raw=raw,request=request)['reason'],'archive_source_mismatch')

    def test_archive_duplicate_and_file_ancestor_conflicts(self):
        for name in ('backend/postgres/api.py','backend'):
            item=tarfile.TarInfo(name);item.size=1
            raw=bundle([(item,b'x')])
            request=replace(self.request,artifact_sha256=hashlib.sha256(raw).hexdigest())
            self.permit['artifact_sha256']=request.artifact_sha256;self.write_permit()
            self.assertEqual(self.deploy(raw=raw,request=request)['gate'],'BLOCKED')

    def test_preflight_failure_leaves_permission_and_runtime_untouched(self):
        actions=Actions(fail='preflight')
        result=self.deploy(actions)
        self.assertEqual(result['gate'],'BLOCKED')
        self.assertEqual(actions.calls,['preflight'])
        self.assertTrue(self.authority_path.exists())
        self.assertEqual(list(self.stage.iterdir()),[])
        self.assertNotIn('private credential',json.dumps(result))

    def test_migrate_start_smoke_failures_preserve_database_and_never_pass(self):
        for stage in ('build','migrate','start','smoke'):
            with self.subTest(stage=stage):
                self.permit['nonce']=str(uuid.uuid4());self.write_permit()
                actions=Actions(fail=stage)
                result=self.deploy(actions)
                self.assertEqual(result['gate'],'BLOCKED')
                self.assertEqual(result['failed_stage'],stage)
                self.assertEqual(actions.calls[-1],'recover')
                self.assertFalse(result['recovery']['database_restored'])
                self.assertTrue(result['recovery']['new_acknowledgements_preserved'])
                self.assertEqual(actions.recovery_context.migration_started,stage!='build')
                self.assertFalse(self.authority_path.exists())
                self.assertNotIn('private credential',json.dumps(result))

    def test_recovery_does_not_claim_schema_rollback_or_unknown_safety(self):
        actions=Actions(fail='migrate',recovery={'strategy':'restart_prior_without_compatibility','database_restored':True})
        result=self.deploy(actions)
        self.assertEqual(result['gate'],'BLOCKED')
        self.assertEqual(result['recovery'],{'status':'unproven_preserve_and_inspect'})

    def test_work_and_recovery_have_separate_budgets(self):
        actions=Actions(clock=self.clock,advance=601)
        result=self.deploy(actions)
        self.assertEqual(result['reason'],'deadline_exceeded')
        self.assertEqual(actions.calls,['preflight','build','recover'])
        self.assertEqual(actions.recovery_seconds,180)

    def test_missing_freshness_and_false_recovery_evidence_cannot_pass(self):
        evidence=Actions().smoke(None,None)
        evidence['checks']['freshness']='UNKNOWN'
        result=self.deploy(Actions(evidence=evidence))
        self.assertEqual(result['gate'],'BLOCKED')
        self.assertEqual(result['reason'],'incomplete_runtime_acceptance')

    def test_authorization_replacement_during_readonly_preflight_is_rejected(self):
        test=self
        class Replacing(Actions):
            def preflight(self,context,budget):
                self.call('preflight')
                test.permit['nonce']=str(uuid.uuid4())
                test.write_permit()
        actions=Replacing()
        self.assertEqual(self.deploy(actions)['reason'],'authority_changed')
        self.assertEqual(actions.calls,['preflight'])


class BudgetTests(unittest.TestCase):
    def test_bounded_child_success_and_sanitized_failure(self):
        self.assertEqual(c.Budget(3).run([sys.executable,'-c','print("ok")']),b'ok\n')
        with self.assertRaisesRegex(c.DeploymentHold,'child_failed') as error:
            c.Budget(3).run([sys.executable,'-c','import sys; print("secret",file=sys.stderr); sys.exit(2)'])
        self.assertNotIn('secret',str(error.exception))

    def test_child_timeout_and_output_bomb_are_terminated(self):
        with self.assertRaises(c.DeploymentHold):
            c.Budget(.1).run([sys.executable,'-c','import time; time.sleep(5)'])
        with self.assertRaisesRegex(c.DeploymentHold,'child_output_bound'):
            c.Budget(3).run([sys.executable,'-c','print("x"*70000)'])


if __name__=='__main__':unittest.main()
