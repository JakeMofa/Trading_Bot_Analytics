"""Explicit PP operator installation/authorization; never dispatches a release."""
import argparse
from datetime import datetime,timedelta,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid
import zipfile

from controller import HostBinding,Request,require
from transition_control import ACTIVE, ENTER_AUTHORITY, ON_AUTHORITY, TransitionRequest, _candidate, _read_active

PROBE_AUTHORITY=Path('/run/tradebot-pp-deploy/structured-probe.json')
RAW_ARCHIVE_AUTHORITY=Path('/run/tradebot-pp-deploy/raw-archive-probe.json')

USER='tradebot-preprod-deploy'
HOME=Path('/var/lib/tradebot-pp-deploy')
LIB=Path('/usr/local/lib/tradebot-pp')
AUTHORITY=Path('/run/tradebot-pp-deploy')
STAGING=Path('/var/lib/tradebot-pp/deployments')
WRAPPER=Path('/usr/local/bin/tradebot-pp-deploy')
SUDOERS=Path('/etc/sudoers.d/tradebot-preprod-deploy')


def command(args,allowed=(0,)):
    result=subprocess.run(args,capture_output=True,text=True,timeout=15)
    require(result.returncode in allowed,'operator_command_failed')
    return result


def directory(path,mode):
    require(not path.is_symlink(),'unsafe_operator_directory')
    path.mkdir(mode=mode,parents=True,exist_ok=True)
    info=path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022,'unsafe_operator_directory')
    path.chmod(mode)


def write_new_or_same(path,data,mode):
    require(not path.is_symlink(),'unsafe_operator_file')
    if path.exists():
        info=path.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022,'unsafe_operator_file')
        require(path.read_bytes()==data,'existing_operator_configuration_differs')
        path.chmod(mode)
        return
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def checked_bundle(path,expected):
    require(re.fullmatch('[0-9a-f]{64}',expected) is not None,'invalid_bundle_digest')
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=256*1024,'invalid_bundle_file')
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected,'bundle_digest_mismatch')
    with zipfile.ZipFile(path) as archive:
        require(set(archive.namelist())=={'__main__.py','controller.py','linux_actions.py',
            'live_profile.py','live_transition.py','transition_control.py',
            'structured_probe_profile.py','structured_probe_control.py',
            'raw_archive_probe_profile.py','raw_archive_probe_control.py'} and len(archive.namelist())==10,
            'unexpected_bundle_members')
        require(sum(i.file_size for i in archive.infolist())<=256*1024,'bundle_expanded_bound')
    return raw


def install_authorized_key(home,key):
    # OpenSSH reads AuthorizedKeysFile using the target UID. Root ownership
    # prevents edits, while public read/traverse permissions allow authentication.
    directory(home/'.ssh',0o755)
    forced='restrict,command="'+str(WRAPPER)+'" '+key+'\n'
    write_new_or_same(home/'.ssh/authorized_keys',forced.encode(),0o644)


def read_installed_controller(path):
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022,
            'unsafe_existing_controller')
    return path.read_bytes()


def install(bundle,digest,public_key_file):
    HostBinding.from_marker().validate()
    raw=checked_bundle(bundle,digest)
    key=public_key_file.read_text().strip()
    require(re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{68}(?: [A-Za-z0-9._@-]{1,100})?',key) is not None,'invalid_deploy_public_key')
    command(['ssh-keygen','-l','-f',str(public_key_file)])
    existing=command(['getent','passwd',USER],allowed=(0,2))
    if existing.returncode==2:
        command(['useradd','--system','--user-group','--create-home','--home-dir',str(HOME),'--shell','/bin/sh',USER])
        existing=command(['getent','passwd',USER])
    fields=existing.stdout.strip().split(':')
    require(len(fields)==7 and fields[0]==USER and int(fields[2])>0 and fields[5]==str(HOME) and fields[6]=='/bin/sh','unexpected_deploy_identity')
    require(command(['id','-nG',USER]).stdout.strip().split()==[USER],'deployment_identity_extra_groups')
    # sshd accepts root-owned authorized keys. The deploy identity cannot alter
    # its forced command, authorize another key, or join the Docker group.
    info=HOME.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,int(fields[2])) and not info.st_mode & 0o022,'unsafe_deploy_home')
    os.chown(HOME,0,0);directory(HOME,0o755)
    install_authorized_key(HOME,key)
    directory(LIB,0o755);directory(AUTHORITY,0o700);directory(STAGING,0o700)
    wrapper=b'#!/bin/sh\nset -eu\nexec sudo -n /usr/bin/python3 -I /usr/local/lib/tradebot-pp/controller.pyz "${SSH_ORIGINAL_COMMAND-}"\n'
    write_new_or_same(WRAPPER,wrapper,0o755)
    rule=(USER+' ALL=(root) NOPASSWD: /usr/bin/python3 -I /usr/local/lib/tradebot-pp/controller.pyz *\n').encode()
    pending=LIB/'sudoers.pending'
    write_new_or_same(pending,rule,0o400)
    command(['visudo','-cf',str(pending)])
    write_new_or_same(SUDOERS,rule,0o440)
    write_new_or_same(LIB/(digest+'.pyz'),raw,0o600)
    current=LIB/'controller.pyz'
    if current.exists():
        previous=read_installed_controller(current)
        write_new_or_same(LIB/(hashlib.sha256(previous).hexdigest()+'.pyz'),previous,0o600)
    temporary=LIB/'controller.pending'
    write_new_or_same(temporary,raw,0o600)
    os.replace(temporary,current)
    return {'result':'INSTALLED_NOT_AUTHORIZED','environment':'preprod','controller_sha256':digest,
            'deployment_dispatched':False,'runtime_qualified':False,'database_changed':False}


def authorize(source,artifact,controller):
    HostBinding.from_marker().validate()
    request=Request(source,artifact,controller);request.validate()
    checked_bundle(LIB/'controller.pyz',controller)
    directory(AUTHORITY,0o700)
    now=datetime.now(timezone.utc)
    permit={**request.bindings(),'version':1,'nonce':str(uuid.uuid4()),
        'issued_at':now.isoformat(),'expires_at':(now+timedelta(minutes=30)).isoformat(),
        'data_mode':'generated','allow_migration':True,'live_collector_enabled':False,
        'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False}
    path=AUTHORITY/'authorization.json'
    require(not path.exists() and not path.is_symlink(),'existing_authority_requires_reconciliation')
    write_new_or_same(path,(json.dumps(permit,sort_keys=True)+'\n').encode(),0o600)
    return {'result':'ONE_ATTEMPT_AUTHORIZED',**request.bindings(),'expires_at':permit['expires_at'],
            'deployment_dispatched':False}


def _scope_permit(path,fields):
    directory(AUTHORITY,0o700)
    now=datetime.now(timezone.utc)
    permit={**fields,'version':1,'nonce':str(uuid.uuid4()),
        'issued_at':now.isoformat(),'expires_at':(now+timedelta(minutes=30)).isoformat(),
        'paid_ai_enabled':False,'cloud_enabled':False,'retirement_enabled':False,
        'production_data_mounted':False}
    require(not path.exists() and not path.is_symlink(),'existing_authority_requires_reconciliation')
    write_new_or_same(path,(json.dumps(permit,sort_keys=True)+'\n').encode(),0o600)
    return {'result':'ONE_ATTEMPT_AUTHORIZED','scope':fields['scope'],
            'expires_at':permit['expires_at'],'deployment_dispatched':False}


def authorize_live_enter(source,artifact,controller,image):
    HostBinding.from_marker().validate()
    request=TransitionRequest('enter',source,artifact,controller,image)
    request.validate()
    checked_bundle(LIB/'controller.pyz',controller)
    _candidate(request)
    if ACTIVE.exists() or ACTIVE.is_symlink():
        require(_read_active()['state']=='generated_restored','unfinished_transition_requires_leave')
    return _scope_permit(ENTER_AUTHORITY,{**request.bindings(),'scope':'pp_live_ready_off'})


def authorize_live_on(seconds):
    HostBinding.from_marker().validate()
    require(isinstance(seconds,int) and 1<=seconds<=1800,'invalid_live_session_duration')
    active=_read_active()
    require(active['state']=='ready_off','live_profile_not_ready')
    checked_bundle(LIB/'controller.pyz',active['controller_sha256'])
    return _scope_permit(ON_AUTHORITY,{k:active[k] for k in ('environment','instance','source_sha',
        'artifact_sha256','controller_sha256','image_id')}|
        {'transition_nonce':active['nonce'],'scope':'pp_live_session_on','max_seconds':seconds})


def authorize_structured_probe(generation_id,expected_state,first_outbox_id):
    """Stage one exact PP outbox page; this does not make a cloud call."""
    HostBinding.from_marker().validate()
    require(isinstance(generation_id,str) and str(uuid.UUID(generation_id))==generation_id
            and expected_state in ('collecting','sealed','verified')
            and type(first_outbox_id) is int and first_outbox_id>0,
            'invalid_structured_probe_target')
    active=_read_active()
    require(active['state']=='ready_off','live_profile_not_ready')
    checked_bundle(LIB/'controller.pyz',active['controller_sha256'])
    request=TransitionRequest('enter',*[active[k] for k in
        ('source_sha','artifact_sha256','controller_sha256','image_id')])
    _candidate(request)
    return _scope_permit(PROBE_AUTHORITY,{k:active[k] for k in
        ('environment','instance','source_sha','artifact_sha256','controller_sha256','image_id')}|
        {'scope':'pp_structured_one_shot','generation_id':generation_id,
         'expected_state':expected_state,'expected_first_outbox_id':first_outbox_id})


def authorize_raw_archive_probe(generation_id,seal_count,manifest_count):
    """Stage one exact sealed-generation cycle; no cloud call or retirement."""
    HostBinding.from_marker().validate()
    require(isinstance(generation_id,str) and str(uuid.UUID(generation_id))==generation_id
            and type(seal_count) is int and seal_count>=0
            and type(manifest_count) is int and 0<=manifest_count<=128,
            'invalid_raw_archive_probe_target')
    active=_read_active()
    require(active['state']=='ready_off','live_profile_not_ready')
    checked_bundle(LIB/'controller.pyz',active['controller_sha256'])
    request=TransitionRequest('enter',*[active[k] for k in
        ('source_sha','artifact_sha256','controller_sha256','image_id')])
    _candidate(request)
    return _scope_permit(RAW_ARCHIVE_AUTHORITY,{k:active[k] for k in
        ('environment','instance','source_sha','artifact_sha256','controller_sha256','image_id')}|
        {'scope':'pp_raw_archive_one_shot','generation_id':generation_id,
         'expected_seal_count':seal_count,'expected_manifest_count':manifest_count})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    a=sub.add_parser('install');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--sha256',required=True);a.add_argument('--public-key-file',type=Path,required=True)
    a=sub.add_parser('authorize');a.add_argument('--source-sha',required=True);a.add_argument('--artifact-sha256',required=True);a.add_argument('--controller-sha256',required=True)
    a=sub.add_parser('authorize-live-enter');a.add_argument('--source-sha',required=True);a.add_argument('--artifact-sha256',required=True);a.add_argument('--controller-sha256',required=True);a.add_argument('--image-id',required=True)
    a=sub.add_parser('authorize-live-on');a.add_argument('--max-seconds',type=int,required=True)
    a=sub.add_parser('authorize-structured-probe');a.add_argument('--generation-id',required=True);a.add_argument('--expected-state',required=True);a.add_argument('--first-outbox-id',type=int,required=True)
    a=sub.add_parser('authorize-raw-archive-probe');a.add_argument('--generation-id',required=True);a.add_argument('--expected-seal-count',type=int,required=True);a.add_argument('--expected-manifest-count',type=int,required=True)
    args=parser.parse_args()
    try:
        HostBinding.from_marker().validate()
        directory(AUTHORITY,0o700)
        lock=os.open(AUTHORITY/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        info=os.fstat(lock)
        require(info.st_uid==0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077,'unsafe_controller_lock')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.operation=='install':
            require(not any(path.exists() for path in (AUTHORITY/'authorization.json',ENTER_AUTHORITY,ON_AUTHORITY,PROBE_AUTHORITY,RAW_ARCHIVE_AUTHORITY)),
                    'unused_authority_requires_reconciliation')
            if ACTIVE.exists() or ACTIVE.is_symlink():
                require(_read_active()['state']=='generated_restored','unfinished_transition_requires_leave')
        if args.operation=='install':
            result=install(args.bundle,args.sha256,args.public_key_file)
        elif args.operation=='authorize':
            result=authorize(args.source_sha,args.artifact_sha256,args.controller_sha256)
        elif args.operation=='authorize-live-enter':
            result=authorize_live_enter(args.source_sha,args.artifact_sha256,args.controller_sha256,args.image_id)
        elif args.operation=='authorize-structured-probe':
            result=authorize_structured_probe(args.generation_id,args.expected_state,args.first_outbox_id)
        elif args.operation=='authorize-raw-archive-probe':
            result=authorize_raw_archive_probe(args.generation_id,args.expected_seal_count,args.expected_manifest_count)
        else:
            result=authorize_live_on(args.max_seconds)
        print(json.dumps(result,sort_keys=True))
    except Exception:
        raise SystemExit('PP operator preparation STOP; inspect bounded configuration evidence, not credentials') from None
