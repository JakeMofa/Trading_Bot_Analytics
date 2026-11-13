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
        require(set(archive.namelist())=={'__main__.py','controller.py','linux_actions.py'} and len(archive.namelist())==3,'unexpected_bundle_members')
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    a=sub.add_parser('install');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--sha256',required=True);a.add_argument('--public-key-file',type=Path,required=True)
    a=sub.add_parser('authorize');a.add_argument('--source-sha',required=True);a.add_argument('--artifact-sha256',required=True);a.add_argument('--controller-sha256',required=True)
    args=parser.parse_args()
    try:
        HostBinding.from_marker().validate()
        directory(AUTHORITY,0o700)
        lock=os.open(AUTHORITY/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        info=os.fstat(lock)
        require(info.st_uid==0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077,'unsafe_controller_lock')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.operation=='install':
            require(not (AUTHORITY/'authorization.json').exists(),'unused_authority_requires_reconciliation')
        result=install(args.bundle,args.sha256,args.public_key_file) if args.operation=='install' else authorize(args.source_sha,args.artifact_sha256,args.controller_sha256)
        print(json.dumps(result,sort_keys=True))
    except Exception:
        raise SystemExit('PP operator preparation STOP; inspect bounded configuration evidence, not credentials') from None
