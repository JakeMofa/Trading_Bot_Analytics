"""Generated attestation/overlay checks only; never asserts actual hosted policy PASS."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
import trial_history_reader as reader

A='00000000-0000-4000-8000-000000000001'
W='00000000-0000-4000-8000-0000000000cc'
R='00000000-0000-4000-8000-0000000000dd'
F='00000000-0000-4000-8000-000000000003'
CONTEXT=SimpleNamespace(request=SimpleNamespace(source_sha='a'*40),image='sha256:'+'b'*64)


def fixture():
    evidence=dict(schema_version=1,project_ref='xttdqeimdujweijxcuro',bucket='market-raw',
        origin_id=reader.TRIAL_ORIGIN,initial_a=A,reader_uid=R,writer_uid=W,effective_role='authenticated',
        sql_reader_role=reader.TRIAL_SQL_READER,authenticated_get='pass',writer_get='pass',sql_read_only='pass',
        hosted_denied=list(reader.HOSTED_DENIED),policy_fixture_denied=list(reader.POLICY_FIXTURE_DENIED),fixture=dict(generation_id=F,sha256='c'*64,bytes=210,
            object_key='raw-v1/'+hashlib.sha256(reader.TRIAL_ORIGIN.encode()).hexdigest()+'/'+F+'/'+'c'*64+'.jsonl.gz'))
    raw=json.dumps(evidence,sort_keys=True).encode()
    authority=dict(schema_version=1,scope=reader.SCOPE,origin_id=reader.TRIAL_ORIGIN,
        source_sha=CONTEXT.request.source_sha,image_id=CONTEXT.image,initial_a=A,reader_uid=R,writer_uid=W,
        policy_proof_sha256=hashlib.sha256(raw).hexdigest())
    return authority,evidence,raw


class TrialHistoryReaderTests(unittest.TestCase):
    def test_exact_reader_proof_with_final_source_bound_separately(self):
        authority,evidence,_=fixture()
        self.assertTrue(reader.validate_trial_reader_attestation(CONTEXT,authority,evidence,initial_a=A))
        self.assertNotIn('source_sha',evidence)
        self.assertNotEqual(evidence['fixture']['generation_id'],evidence['initial_a'])

    def test_identity_scope_role_anchor_denials_and_digest_mismatches_hold(self):
        authority,evidence,_=fixture()
        for field,value in [('origin_id','pp-live-pp'),('source_sha','d'*40),('image_id','sha256:'+'e'*64),
            ('reader_uid',W),('initial_a','not-a-uuid'),('schema_version',True)]:
            candidate=deepcopy(authority);candidate[field]=value
            with self.assertRaises(DeploymentHold): reader.validate_trial_reader_attestation(CONTEXT,candidate,evidence,initial_a=A)
        for mutate in (lambda p:p.update(sql_reader_role='tradebot_pp_history'),
            lambda p:p.update(hosted_denied=p['hosted_denied'][:-1]),
            lambda p:p.update(policy_fixture_denied=p['policy_fixture_denied'][:-1]),lambda p:p.update(authenticated_get='not_run'),
            lambda p:p.update(sql_read_only='not_run'),lambda p:p.update(writer_uid=R),
            lambda p:p['fixture'].update(object_key='raw-v1/wrong-origin'),
            lambda p:p['fixture'].update(bytes=0),lambda p:p['fixture'].update(sha256='wrong')):
            candidate=deepcopy(evidence);mutate(candidate)
            with self.assertRaises(DeploymentHold): reader.validate_trial_reader_attestation(CONTEXT,authority,candidate,initial_a=A)
        with self.assertRaises(DeploymentHold): reader.validate_trial_reader_attestation(CONTEXT,authority,evidence,initial_a=F)

    def test_missing_marker_is_only_off_case_and_no_secret_reads_occur(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(reader,'RUNTIME_SECRETS',Path(folder)),patch.object(reader,'_read_owned') as read:
            self.assertFalse(reader.trial_history_reader_enabled(CONTEXT,A));read.assert_not_called()
            (Path(folder)/reader.AUTHORITY_FILENAME).write_text('invalid')
            read.side_effect=ValueError('fixture invalid')
            with self.assertRaises(DeploymentHold):reader.trial_history_reader_enabled(CONTEXT,A)

    def test_first_trial_proof_files_are_preserved_and_cannot_enable_second_trial(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(reader,'RUNTIME_SECRETS',Path(folder)),patch.object(reader,'_read_owned') as read:
            old=Path(folder)/'trial_history_reader_authority.json';old.write_text('retained-first-trial')
            self.assertFalse(reader.trial_history_reader_enabled(CONTEXT,A));read.assert_not_called()
            self.assertEqual(old.read_text(),'retained-first-trial')
        authority,evidence,_=fixture();authority['origin_id']='pp-live-pp-trial-20261119-01'
        with self.assertRaises(DeploymentHold):reader.validate_trial_reader_attestation(CONTEXT,authority,evidence,initial_a=A)

    def test_fifth_reader_requires_fresh_files_and_retained_fourth_denial(self):
        self.assertEqual(reader.TRIAL_ORIGIN,'pp-live-pp-trial-20261119-05')
        self.assertEqual(reader.TRIAL_SQL_READER,'tradebot_pp_trial_20261119_05_reader')
        self.assertIn('retained_trial_04_origin',reader.HOSTED_DENIED)
        with tempfile.TemporaryDirectory() as folder,patch.object(reader,'RUNTIME_SECRETS',Path(folder)),patch.object(reader,'_read_owned') as read:
            old=Path(folder)/'trial_20261119_04_history_reader_authority.json'
            old.write_text('retained-third-trial')
            self.assertFalse(reader.trial_history_reader_enabled(CONTEXT,A))
            read.assert_not_called()
            self.assertEqual(old.read_text(),'retained-third-trial')
            self.assertEqual(reader.trial_history_reader_source('trial_history_reader_uid').name,
                             'trial_20261119_05_history_reader_uid')
        authority,evidence,_=fixture()
        evidence['hosted_denied'].remove('retained_trial_04_origin')
        authority['policy_proof_sha256']=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
        with self.assertRaises(DeploymentHold):
            reader.validate_trial_reader_attestation(CONTEXT,authority,evidence,initial_a=A)

    def test_enabled_reader_reads_only_proof_marker_and_uid_not_password_or_key(self):
        authority,evidence,raw=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/reader.AUTHORITY_FILENAME).write_text('present')
            values={reader.AUTHORITY_FILENAME:json.dumps(authority).encode(),
                    reader.PROOF_FILENAME:raw,reader.trial_history_reader_source('trial_history_reader_uid').name:R.encode()}
            with patch.object(reader,'RUNTIME_SECRETS',root),patch.object(reader,'_metadata') as metadata,\
                 patch.object(reader,'_read_owned',side_effect=lambda path,*_:values[path.name]) as read:
                self.assertTrue(reader.trial_history_reader_enabled(CONTEXT,A))
                self.assertEqual([call.args[0].name for call in read.call_args_list],list(values))
                self.assertEqual([call.args[0].name for call in metadata.call_args_list],[reader.trial_history_reader_source(name).name for name in reader.TRIAL_HISTORY_READER_FILES])
                values[reader.PROOF_FILENAME]=raw+b' '
                with self.assertRaises(DeploymentHold): reader.trial_history_reader_enabled(CONTEXT,A)

    def test_private_file_helper_rejects_mode_owner_links_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'proof';path.write_bytes(b'fixture');path.chmod(0o400)
            self.assertEqual(reader._read_owned(path,os.geteuid(),32),b'fixture')
            with self.assertRaises(DeploymentHold):reader._read_owned(path,os.geteuid()+1,32)
            path.chmod(0o600)
            with self.assertRaises(DeploymentHold):reader._read_owned(path,os.geteuid(),32)
            path.chmod(0o400);link=Path(folder)/'link';link.symlink_to(path)
            with self.assertRaises(DeploymentHold):reader._read_owned(link,os.geteuid(),32)
            hard=Path(folder)/'hard';os.link(path,hard)
            with self.assertRaises(DeploymentHold):reader._read_owned(path,os.geteuid(),32)
        with self.assertRaises(DeploymentHold):reader._json(b'{"scope":1,"scope":2}')

    def test_api_overlay_mounts_exact_reader_auth_only(self):
        source=(Path(reader.__file__).parent/reader.TRIAL_HISTORY_READER_OVERLAY).read_text()
        mounts=re.findall(r'^      - ([a-z_]+)$',source,re.M)
        self.assertEqual(mounts,list(reader.TRIAL_HISTORY_READER_FILES))
        for name in reader.TRIAL_HISTORY_READER_FILES:
            self.assertIn(name+': {file: "${PP_RUNTIME_SECRET_DIR:?missing runtime directory}/'+reader.trial_history_reader_source(name).name+'"}',source)
        self.assertIn('TRADEBOT_ORIGIN_ID: '+reader.TRIAL_ORIGIN,source)
        self.assertIn("TRADEBOT_PP_ARCHIVE_HISTORY: 'true'",source)
        self.assertNotIn('writer_dsn',source);self.assertNotIn('lifecycle_dsn',source)
        self.assertNotIn('trial_archive_',source)


if __name__=='__main__':unittest.main()
