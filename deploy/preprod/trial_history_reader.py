"""Source-bound exact trial raw-history reader attestation; no cloud or activation.

The root-managed proof attests independently collected evidence. This module
checks bindings and local files, not remote policy truth. No secret content is
read except the dedicated reader UID. Missing marker is the sole OFF outcome;
malformed, stale or mismatched evidence raises DeploymentHold.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from controller import require

TRIAL_ORIGIN='pp-live-pp-trial-20261119-07'
TRIAL_SQL_READER='tradebot_pp_trial_20261119_07_reader'
RUNTIME_SECRETS=Path('/etc/tradebot/pp-runtime')
TRIAL_HISTORY_READER_FILES=tuple('trial_history_reader_'+field for field in ('api_key','email','password','uid'))
TRIAL_HISTORY_READER_OVERLAY='runtime.trial-history-reader.compose.yaml'
AUTHORITY_FILENAME='trial_20261119_07_history_reader_authority.json'
PROOF_FILENAME='trial_20261119_07_history_reader_proof.json'


def trial_history_reader_source(name):
    require(name in TRIAL_HISTORY_READER_FILES,'unreviewed_trial_history_reader_file')
    return RUNTIME_SECRETS/('trial_20261119_07_history_reader_'+name.removeprefix('trial_history_reader_'))
HOSTED_DENIED=['old_origin','retained_trial_01_origin','retained_trial_02_origin','retained_trial_03_origin','retained_trial_04_origin','retained_trial_05_origin','retained_trial_06_origin','list','upload','sign','public']
POLICY_FIXTURE_DENIED=['production_origin','replace','move','delete']
SCOPE='pp_trial_raw_get_only_v1'
HEX=re.compile(r'[0-9a-f]{64}\Z')


def _uuid(value):
    try: return isinstance(value,str) and str(uuid.UUID(value))==value
    except (ValueError,AttributeError): return False


def _metadata(path,uid,maximum):
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==uid
            and stat.S_IMODE(info.st_mode)==0o400 and 0<info.st_size<=maximum,
            'unsafe_trial_history_reader_file')
    return info


def _read_owned(path,uid,maximum):
    before=_metadata(path,uid,maximum)
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        def stamp(value):
            return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns,value.st_uid,value.st_mode,value.st_nlink)
        opened=os.fstat(descriptor)
        require(stamp(opened)==stamp(before),
                'trial_history_reader_file_changed')
        raw=os.read(descriptor,maximum+1)
        after=os.fstat(descriptor)
        require(len(raw)==before.st_size and stamp(after)==stamp(before),
                'trial_history_reader_file_changed')
        return raw
    finally: os.close(descriptor)


def _json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            require(key not in result,'duplicate_trial_history_reader_key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def validate_trial_reader_attestation(context,authority,evidence,*,initial_a=None):
    """Pure validation. Final candidate SHA/image are bound in authority only."""
    require(isinstance(authority,dict) and set(authority)=={
        'schema_version','scope','origin_id','source_sha','image_id','initial_a',
        'reader_uid','writer_uid','policy_proof_sha256'},'invalid_trial_history_reader_authority')
    require(authority['schema_version']==1 and type(authority['schema_version']) is int
        and authority['scope']==SCOPE and authority['origin_id']==TRIAL_ORIGIN
        and isinstance(authority['source_sha'],str) and bool(re.fullmatch('[0-9a-f]{40}',authority['source_sha']))
        and isinstance(authority['image_id'],str) and bool(re.fullmatch('sha256:[0-9a-f]{64}',authority['image_id']))
        and authority['source_sha']==context.request.source_sha and authority['image_id']==context.image
        and isinstance(authority['policy_proof_sha256'],str) and HEX.fullmatch(authority['policy_proof_sha256'])
        and _uuid(authority['initial_a']) and _uuid(authority['reader_uid']) and _uuid(authority['writer_uid'])
        and authority['reader_uid']!=authority['writer_uid'],'unqualified_trial_history_reader_profile')
    require(initial_a is None or (_uuid(initial_a) and initial_a==authority['initial_a']),
            'trial_history_reader_anchor_mismatch')
    require(isinstance(evidence,dict) and set(evidence)=={
        'schema_version','project_ref','bucket','origin_id','initial_a','reader_uid','writer_uid',
        'effective_role','sql_reader_role','authenticated_get','writer_get','sql_read_only','hosted_denied','policy_fixture_denied','fixture'},
        'invalid_trial_history_reader_proof')
    require(type(evidence['schema_version']) is int and evidence['schema_version']==1
        and evidence['project_ref']=='xttdqeimdujweijxcuro' and evidence['bucket']=='market-raw'
        and evidence['origin_id']==TRIAL_ORIGIN and evidence['initial_a']==authority['initial_a']
        and evidence['reader_uid']==authority['reader_uid'] and evidence['writer_uid']==authority['writer_uid']
        and evidence['effective_role']=='authenticated' and evidence['sql_reader_role']==TRIAL_SQL_READER
        and evidence['authenticated_get']=='pass' and evidence['writer_get']=='pass'
        and evidence['sql_read_only']=='pass' and evidence['hosted_denied']==HOSTED_DENIED
        and evidence['policy_fixture_denied']==POLICY_FIXTURE_DENIED,
        'incomplete_trial_history_reader_proof')
    fixture=evidence['fixture']
    require(isinstance(fixture,dict) and set(fixture)=={'generation_id','object_key','sha256','bytes'}
        and _uuid(fixture['generation_id']) and isinstance(fixture['sha256'],str)
        and HEX.fullmatch(fixture['sha256']) and type(fixture['bytes']) is int
        and 1<=fixture['bytes']<=2*1024*1024,'invalid_trial_history_reader_fixture')
    prefix='raw-v1/'+hashlib.sha256(TRIAL_ORIGIN.encode()).hexdigest()+'/'
    require(fixture['object_key']==prefix+fixture['generation_id']+'/'+fixture['sha256']+'.jsonl.gz',
            'trial_history_reader_fixture_scope_mismatch')
    return True


def trial_history_reader_enabled(context,initial_a=None):
    marker=RUNTIME_SECRETS/AUTHORITY_FILENAME
    try: marker.lstat()
    except FileNotFoundError: return False
    except OSError: require(False,'unsafe_trial_history_reader_authority')
    try:
        authority=_json(_read_owned(marker,0,4096))
        raw=_read_owned(RUNTIME_SECRETS/PROOF_FILENAME,0,8192)
        require(isinstance(authority,dict) and hashlib.sha256(raw).hexdigest()==authority.get('policy_proof_sha256'),
                'trial_history_reader_proof_changed')
        validate_trial_reader_attestation(context,authority,_json(raw),initial_a=initial_a)
        for name in TRIAL_HISTORY_READER_FILES: _metadata(trial_history_reader_source(name),10001,4096)
        uid=_read_owned(trial_history_reader_source('trial_history_reader_uid'),10001,4096).decode('ascii').strip()
        require(uid==authority['reader_uid'],'trial_history_reader_identity_mismatch')
        return True
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        require(False,'invalid_trial_history_reader_binding')
