import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import release_candidate as rc

SHA = 'a'*40
VERSION = '0.0.0-example.1'
BRANCH = 'codex/ci-pr-quality-gates'


class FakeAPI:
    def __init__(self):
        self.tag = None
        self.release = None
        self.writes = []
        self.run = {'id':123,'head_sha':SHA,'head_branch':BRANCH,'event':'push','status':'completed','conclusion':'success'}
    def call(self, method, path, value=None, binary=False):
        if method == 'GET':
            if '/heads/' in path:return {'object':{'sha':SHA}}
            if '/runs?' in path:return {'workflow_runs':[self.run] if self.run else []}
            if '/tags/' in path and path.startswith('/git'):return self.tag
            if path.startswith('/releases/tags/'):return self.release
        self.writes.append((method,path,value))
        if path == '/git/refs':
            self.tag={'object':{'type':'commit','sha':value['sha']}};return self.tag
        if path == '/releases':
            self.release={**value,'id':1,'assets':[]};return self.release
        if binary:
            name=path.split('name=')[1]
            asset={'name':name,'size':len(value),'digest':'sha256:'+hashlib.sha256(value).hexdigest()}
            self.release['assets'].append(asset);return asset
        self.release.update(value);return self.release


class ReleaseTests(unittest.TestCase):
    def env(self):
        return {'GITHUB_REPOSITORY':rc.REPO,'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/'+BRANCH,'GITHUB_SHA':SHA}

    def test_version_ref_scope_sha_and_missing_failed_merge_ci_rejected(self):
        api=FakeAPI();args=[api,BRANCH,SHA,VERSION,rc.SCOPE,self.env()]
        self.assertEqual(rc.qualify(*args)['tested_sha'],SHA)
        for version in ['1.02.3','phase1.75','v1.2.3','1.2','1.2.3-01','1.2.3;bad']:
            with self.assertRaises(ValueError):rc.qualify(api,BRANCH,SHA,version,rc.SCOPE,self.env())
        for index,value in [(1,'unapproved'),(2,'a'*7),(4,'production'),(5,{**self.env(),'GITHUB_EVENT_NAME':'push'}),(5,{**self.env(),'GITHUB_SHA':'b'*40})]:
            changed=list(args);changed[index]=value
            with self.assertRaises(ValueError):rc.qualify(*changed)
        api.run=None
        with self.assertRaises(ValueError):rc.qualify(*args)
        for key,value in [('event','pull_request'),('conclusion','failure'),('status','in_progress'),('head_sha','b'*40),('head_branch','main')]:
            api.run=FakeAPI().run;api.run[key]=value
            with self.assertRaises(ValueError):rc.qualify(*args)

    def test_publication_is_create_only_and_idempotent_and_collisions_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            manifest={'tag':'v'+VERSION,'version':VERSION,'source_sha':SHA,'ci':{'url':'https://example.invalid/evidence'},'roadmap':'https://example.invalid/roadmap','assets':{}}
            (output/'release-manifest.json').write_text(json.dumps(manifest))
            api=FakeAPI()
            with patch.object(rc,'validate_artifacts'):
                rc.publish(api,output,manifest)
                count=len(api.writes)
                rc.publish(api,output,manifest)
                self.assertEqual(count,len(api.writes))
                api.release['assets'][0]['digest']='sha256:'+'0'*64
                with self.assertRaises(ValueError):rc.publish(api,output,manifest)
                api.release['assets'][0]['digest']='sha256:'+hashlib.sha256((output/'release-manifest.json').read_bytes()).hexdigest()
                api.tag['object']['sha']='b'*40
                with self.assertRaises(ValueError):rc.publish(api,output,manifest)
                api.tag['object']['sha']=SHA
                api.release['body']='different release'
                with self.assertRaises(ValueError):rc.publish(api,output,manifest)
                self.assertFalse(any(path.startswith('/git/refs/') for method,path,value in api.writes))

    def test_interrupted_draft_resumes_without_replacing_tag_or_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            manifest={'tag':'v'+VERSION,'version':VERSION,'source_sha':SHA,
                      'ci':{'url':'https://example.invalid/ci'},'roadmap':'fixture','assets':{}}
            (output/'release-manifest.json').write_text(json.dumps(manifest))
            api=FakeAPI();original=api.call
            def failed_upload(method,path,value=None,binary=False):
                if binary:raise RuntimeError('generated interruption')
                return original(method,path,value,binary)
            with patch.object(rc,'validate_artifacts'),patch.object(api,'call',side_effect=failed_upload):
                with self.assertRaises(RuntimeError):rc.publish(api,output,manifest)
            self.assertTrue(api.release['draft'])
            self.assertEqual(api.tag['object']['sha'],SHA)
            with patch.object(rc,'validate_artifacts'):
                rc.publish(api,output,manifest)
            self.assertFalse(api.release['draft'])
            self.assertEqual(sum(path=='/git/refs' for method,path,value in api.writes),1)

    def test_real_exact_bundle_hashes_and_mismatches(self):
        import subprocess
        sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        evidence={'id':123,'source_sha':sha,'tested_sha':sha,'url':'https://example.invalid/ci'}
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'candidate'
            manifest=rc.build(output,sha,BRANCH,VERSION,rc.SCOPE,evidence)
            rc.validate_artifacts(output,manifest)
            second=rc.build(Path(temp)/'second',sha,BRANCH,VERSION,rc.SCOPE,evidence)
            self.assertEqual(manifest,second)
            changed=copy.deepcopy(manifest);changed['tested_sha']='b'*40
            (output/'release-manifest.json').write_bytes(rc.canonical(changed))
            with self.assertRaises(ValueError):rc.validate_artifacts(output,changed)
            (output/'release-manifest.json').write_bytes(rc.canonical(manifest))
            (output/'requirements.txt').write_text('different')
            with self.assertRaises(ValueError):rc.validate_artifacts(output,manifest)
