import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import release_package as r
import environment_pipeline as p

SHA='a'*40
DIGEST='b'*64


def tar(name='backend/app/example.py', kind=None, data=b'print(1)'):
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz') as archive:
        info=tarfile.TarInfo(name);info.size=len(data)
        if kind:info.type=kind;info.linkname='/etc/passwd';info.size=0
        archive.addfile(info,io.BytesIO(data) if info.isfile() else None)
    return raw.getvalue()


class API:
    def __init__(self):
        self.raw=tar();self.data=r.manifest(SHA,'v0.1.0-rc.1',r.check_archive(self.raw),12,72,'c'*64)
        self.data.update(controls_sha=SHA, source_branch='main')
        self.data['registry']=r.REGISTRY+'@sha256:'+DIGEST
        self.run={'event':'workflow_dispatch','status':'completed','conclusion':'success',
                  'path':'.github/workflows/release-candidate.yml','head_branch':'main','head_sha':SHA,
                  'repository':{'full_name':p.REPO}}
        self.assets=[{'id':1,'name':'release-manifest.json','size':1024},{'id':2,'name':'source.tar.gz','size':1000}]
        self.ref={'object':{'type':'commit','sha':SHA}}
    def read(self,path,binary=False,max_bytes=1024**2):
        if path.startswith('/releases/tags/'):
            return {'draft':False,'tag_name':'v0.1.0-rc.1','assets':self.assets}
        if path.startswith('/git/ref/'):
            return self.ref
        if path.startswith('/actions/runs/'):
            return self.run
        if path.endswith('/1'):return json.dumps(self.data).encode()
        if path.endswith('/2'):return self.raw
        raise AssertionError(path)


class ReleaseTests(unittest.TestCase):
    def test_versions_are_explicit_and_not_shell_fragments(self):
        for item in ['v0.0.0','v1.2.3','v0.1.0-rc.1','v1.0.0-preview']:
            self.assertEqual(r.version(item),item)
        for item in ['latest','v01.2.3','v1.2','1.2.3','v1.2.3-01','v1.2.3;echo bad','v1.2.3\n']:
            with self.subTest(item=item),self.assertRaises(p.PipelineHold):r.version(item)

    def test_archive_is_bounded_and_excludes_secrets_data_and_links(self):
        self.assertEqual(len(r.check_archive(tar())),64)
        r.check_archive(tar('.env.example'))
        for name in ['../escape','/absolute','data/production.json','.env','.env copy','folder/.env.local',
                     'database.sqlite','key.pem','.git/config','folder/run.log']:
            with self.subTest(name=name),self.assertRaises(p.PipelineHold):r.check_archive(tar(name))
        with self.assertRaises(p.PipelineHold):r.check_archive(tar(kind=tarfile.SYMTYPE))
        with self.assertRaises(p.PipelineHold):r.check_archive(b'x'*(r.LIMIT+1))

    def test_absence_only_accepts_404_not_authentication_or_transport_errors(self):
        class Absent:
            def __init__(self,code):self.code=code
            def read(self,path):raise urllib.error.HTTPError('https://api.github.com',self.code,'synthetic',{},None)
        r.absent(Absent(404),'/example')
        for code in [400,401,403,429,500]:
            with self.subTest(code=code),self.assertRaises(p.PipelineHold):r.absent(Absent(code),'/example')
        with self.assertRaises(p.PipelineHold):r.absent(API(),'/git/ref/tags/v0.1.0')

    def test_manifest_distinguishes_candidate_deployment_and_database_state(self):
        data=r.manifest(SHA,'v0.1.0-rc.1',DIGEST,12,72,'c'*64)
        self.assertEqual(data['state'],'CANDIDATE')
        self.assertFalse(data['deployed']);self.assertFalse(data['acceptance_validated'])
        self.assertFalse(data['database_rollback_supported']);self.assertFalse(data['database_changes_applied'])
        with self.assertRaises(p.PipelineHold):r.manifest('short','v1.0.0',DIGEST,1,1,'c'*64)

    def test_carrier_does_not_install_or_execute_app_or_embed_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);r.write_carrier(root,r.manifest(SHA,'v1.0.0',DIGEST,1,1,'c'*64))
            text=(root/'Dockerfile').read_text()
            self.assertTrue(text.startswith('FROM scratch\n'));self.assertNotIn('RUN ',text)
            self.assertNotIn('ENV ',text);self.assertNotIn('ENTRYPOINT',text)
            self.assertEqual((root/'.dockerignore').read_text().splitlines()[0],'*')
            self.assertIn('org.opencontainers.image.source',text)

    def test_load_binds_version_source_registry_ci_and_exact_bytes(self):
        data,raw=r.load_candidate(API(),'v0.1.0-rc.1',SHA)
        self.assertEqual(r.check_archive(raw),data['artifact_sha256'])
        for key,value in [('version','v2.0.0'),('source_sha','d'*40),('registry','ghcr.io/foreign/name@sha256:'+DIGEST),
                          ('artifact_sha256','e'*64),('repository','foreign/repo')]:
            api=API();api.data[key]=value
            with self.subTest(key=key),self.assertRaises(p.PipelineHold):r.load_candidate(api,'v0.1.0-rc.1',SHA)

    def test_failed_untrusted_or_pending_publication_cannot_deploy(self):
        for change in [{'event':'push'},{'status':'in_progress'},{'conclusion':'failure'},{'head_branch':'preprod'},
                       {'head_sha':'d'*40},{'path':'.github/workflows/other.yml'},{'repository':{'full_name':'foreign/repo'}}]:
            api=API();api.run.update(change)
            with self.subTest(change=change),self.assertRaises(p.PipelineHold):r.load_candidate(api,'v0.1.0-rc.1',SHA)

    def test_mutated_tag_duplicate_or_oversized_assets_fail(self):
        for change in ['tag','duplicate','oversize','content']:
            api=API()
            if change=='tag':api.ref['object']['sha']='d'*40
            if change=='duplicate':api.assets.append(api.assets[0])
            if change=='oversize':api.assets[0]['size']=70000
            if change=='content':api.raw=tar(data=b'changed')
            with self.subTest(change=change),self.assertRaises(p.PipelineHold):r.load_candidate(api,'v0.1.0-rc.1',SHA)

    def test_prepare_has_no_publication_side_effect_on_wrong_branch_or_sha(self):
        env={'GITHUB_REF':'refs/heads/preprod','GITHUB_EVENT_NAME':'workflow_dispatch','APPROVED_REVISION':SHA}
        with patch.object(r,'command') as command,self.assertRaises(p.PipelineHold):r.prepare(Path('/unused'),API(),env)
        command.assert_not_called()
        env.update(GITHUB_REF='refs/heads/main',GITHUB_SHA='d'*40)
        with self.assertRaises(p.PipelineHold):r.prepare(Path('/unused'),API(),env)

    def test_registry_absence_checks_all_pages_and_rejects_collisions_or_auth_errors(self):
        class Catalog:
            def __init__(self, rows=None, error=None):self.rows=rows;self.error=error;self.calls=[]
            def read_registry(self,page):
                self.calls.append(page)
                if self.error:raise urllib.error.HTTPError('https://api.github.com',self.error,'synthetic',{},None)
                return self.rows[page-1]
        r.registry_absent(Catalog(error=404),'v1.0.0')
        for code in [401,403,429,500]:
            with self.subTest(code=code),self.assertRaises(p.PipelineHold):r.registry_absent(Catalog(error=code),'v1.0.0')
        cat=Catalog(rows=[[{'metadata':{}}]*100,[{'metadata':{'container':{'tags':['v1.0.0']}}}]])
        with self.assertRaises(p.PipelineHold):r.registry_absent(cat,'v1.0.0')
        self.assertEqual(cat.calls,[1,2])
        r.registry_absent(Catalog(rows=[[]]),'v1.0.0')

    def test_package_changed_after_preparation_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source.tar.gz').write_bytes(tar())
            r.write_carrier(root,r.manifest(SHA,'v0.1.0-rc.1','0'*64,1,1,'c'*64))
            env={'APPROVED_REVISION':SHA,'RELEASE_VERSION':'v0.1.0-rc.1'}
            with patch.object(r,'command') as command,self.assertRaises(p.PipelineHold):r.package(root,env)
            command.assert_not_called()

    def test_successful_publication_binds_digest_and_remains_a_candidate(self):
        api=API();data=api.data
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source.tar.gz').write_bytes(api.raw)
            r.write_carrier(root,data)
            env={'APPROVED_REVISION':SHA,'RELEASE_VERSION':data['version'],'GITHUB_REF':'refs/heads/main',
                 'GITHUB_ACTOR':'synthetic','GH_TOKEN':'synthetic-token','GITHUB_RUN_ID':'72'}
            def called(args, **kwargs):
                if 'imagetools' in args:return json.dumps({'digest':'sha256:'+DIGEST}).encode()
                return b''
            with patch.object(r,'command',side_effect=called) as command,patch.object(r,'registry_absent'):
                published=r.package(root,env)
            self.assertEqual(published['registry'],r.REGISTRY+'@sha256:'+DIGEST)
            self.assertTrue(any(c.args[0][:2]==['docker','push'] for c in command.call_args_list))
            with patch.object(r,'command',return_value=b'') as command,patch.object(r,'absent'),patch.object(p,'qualify_ci'):
                r.publish(root,api,env)
            self.assertEqual(command.call_count,2)
            notes=(root/'NOTES.md').read_text()
            self.assertIn('not deployed',notes);self.assertIn('acceptance NOT PERFORMED',notes)
            self.assertIn('--draft',command.call_args_list[0].args[0])
            self.assertNotIn('--clobber',str(command.call_args_list))
            self.assertIn('source.tar.gz',(root/'SHA256SUMS').read_text())

    def test_cd_and_release_are_manual_and_permissions_do_not_leak_to_prs(self):
        for file in ['cd-pp.yml','cd-prod.yml','release-candidate.yml']:
            text=Path('.github/workflows',file).read_text()
            self.assertIn('workflow_dispatch:',text)
            self.assertNotIn('  push:',text);self.assertNotIn('pull_request_target',text)
        release=Path('.github/workflows/release-candidate.yml').read_text()
        self.assertIn("github.ref == 'refs/heads/main'",release)
        self.assertIn('packages: write',release)
        self.assertNotIn('latest',Path('.github/ci/release_package.py').read_text().split('REGISTRY =',1)[0])
        source=Path('.github/workflows/python-tests.yml').read_text()
        self.assertNotIn('secrets.',source);self.assertNotIn('packages: write',source)
        self.assertIn('name: PR readiness',source)
        self.assertNotIn('prototype/',source)


if __name__=='__main__':unittest.main()
