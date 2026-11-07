import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_ab_candidate import verify_export,validate_path,MANIFEST
class Tests(unittest.TestCase):
    def fixture(self,folder):
        p=Path(folder);(p/'backend').mkdir();(p/'backend/source.py').write_bytes(b'generated source')
        (p/'backend/source.py').chmod(0o644)
        data=(p/'backend/source.py').read_bytes();m={'source_sha':'a'*40,'files':{'backend/source.py':{'mode':'100644','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
        (p/MANIFEST).write_text(json.dumps(m));return p
    def test_exact_file_set_sha_and_bytes(self):
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f);self.assertEqual(verify_export(p,'a'*40)['source_sha'],'a'*40)
            with self.assertRaises(ValueError):verify_export(p,'b'*40)
            (p/'backend/source.py').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_export(p)
    def test_untracked_extra_or_symlink_cannot_pass(self):
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f);(p/'extra').write_bytes(b'not tracked')
            with self.assertRaises(ValueError):verify_export(p)
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f);(p/'backend/source.py').unlink();(p/'backend/source.py').symlink_to(p/MANIFEST)
            with self.assertRaises(ValueError):verify_export(p)
    def test_no_database_environment_or_path_escape(self):
        for path in ['../x','/x','backend/data/x','backend/x.db','backend/.env','backend/__pycache__/x.pyc','deploy/key.pem','backend/.aws/config','docs/secrets.json','backend/x.db-wal','backend/credentials.ini']:
            with self.subTest(path=path),self.assertRaises(ValueError):validate_path(path)

    def test_manifest_cannot_forge_git_blob_binding(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f)
            with patch('build_ab_candidate.tracked_entries',return_value=[('backend/source.py','100644','0'*40)]):
                with self.assertRaises(ValueError):verify_export(p,'a'*40,repo='generated')
    def test_executable_mode_changes_fail(self):
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f);(p/'backend/source.py').chmod(0o755)
            with self.assertRaises(ValueError):verify_export(p)

    def test_real_exact_git_export_never_includes_working_tree_or_local_data(self):
        import os,subprocess
        from build_ab_candidate import export
        repo=Path(os.environ.get('AB_SOURCE_REPOSITORY',Path(__file__).resolve().parents[2]))
        sha=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
        with tempfile.TemporaryDirectory() as f:
            out=Path(f)/'candidate';manifest=export(repo,sha,out)
            self.assertEqual(verify_export(out,sha,repo=repo)['source_sha'],sha)
            self.assertFalse((out/'.git').exists());self.assertFalse((out/'.env copy').exists())
            self.assertTrue((out/'backend/app/collector.py').exists())
    def test_sensitive_tracked_entry_rejected_before_blob_is_read(self):
        from unittest.mock import patch
        from build_ab_candidate import export
        def git(command):
            if 'rev-parse' in command:return b'a'*40+b'\n'
            if 'ls-tree' in command:return b'100644 blob '+b'0'*40+b'\tbackend/credentials.json\0'
            raise AssertionError('sensitive blob must never be read')
        with tempfile.TemporaryDirectory() as f,patch('build_ab_candidate.subprocess.check_output',side_effect=git):
            with self.assertRaises(ValueError):export(f,'a'*40,Path(f)/'candidate')
            self.assertFalse((Path(f)/'candidate').exists())
    def test_manifest_symlink_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as f:
            p=self.fixture(f);(p/MANIFEST).unlink();(p/MANIFEST).symlink_to(p/'backend/source.py')
            with self.assertRaises(ValueError):verify_export(p)
    def test_workflow_uses_runner_context_only_in_supported_step_scope(self):
        import re
        workflow=Path(__file__).resolve().parents[2]/'.github/workflows/python-tests.yml'
        text=workflow.read_text()
        self.assertNotRegex(text,r'defaults:\s*\n\s+run:\s*\n\s+working-directory:\s*\$\{\{\s*runner\.')
        self.assertRegex(text,r'name: Run unit tests\n\s+working-directory: \$\{\{ runner.temp \}\}/ab-test-candidate')
