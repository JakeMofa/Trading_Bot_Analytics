"""Build a deterministic self-contained PP controller; does not install it."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
ENTRY='''import fcntl,hashlib,json,os,signal,stat,sys
from pathlib import Path
from controller import Controller,DeploymentHold,HostBinding,Request,RootAuthorization,_secure_file,require
from linux_actions import LinuxActions

def interrupted(signum,frame):
    raise DeploymentHold("operator_connection_interrupted")

def main():
    if os.geteuid()!=0 or len(sys.argv)!=2:
        raise DeploymentHold("fixed_root_entrypoint_required")
    binding=HostBinding.from_marker()
    parts=sys.argv[1].split(' ')
    if parts[0]=='identity-v1':
        require(len(parts)==4 and parts[1:3]==['preprod','tradebot-preprod-01'],'invalid_identity_command')
        content,_=_secure_file(Path(sys.argv[0]).resolve(),private=False)
        digest=hashlib.sha256(content).hexdigest()
        require(parts[3]==digest,'controller_digest_mismatch')
        print(json.dumps({'gate':'IDENTITY_PASS','environment':'preprod','instance':'tradebot-preprod-01',
                          'controller_sha256':digest,'runtime_qualified':False,'database_changed':False}),flush=True)
        return 0
    request=Request.parse(sys.argv[1])
    lock=os.open("/run/tradebot-pp-deploy/controller.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    info=os.fstat(lock)
    if info.st_uid!=0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise DeploymentHold("unsafe_controller_lock")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for name in ("SIGTERM","SIGINT","SIGHUP"):
        signal.signal(getattr(signal,name),interrupted)
    controller=Controller(binding,RootAuthorization("/run/tradebot-pp-deploy/authorization.json"),
                          Path(sys.argv[0]).resolve(),"/var/lib/tradebot-pp/deployments")
    result=controller.deploy(request,sys.stdin.buffer,LinuxActions())
    print(json.dumps(result,sort_keys=True),flush=True)
    return 0 if result.get("gate")=="PASS" else 1

try:
    raise SystemExit(main())
except (DeploymentHold,OSError,ValueError):
    print(json.dumps({"gate":"BLOCKED","environment":"preprod","reason":"entrypoint_precondition_failed"}),flush=True)
    raise SystemExit(1)
'''


def build(destination):
    target=Path(destination)
    files={'__main__.py':ENTRY.encode()}
    for name in ('controller.py','linux_actions.py'):
        files[name]=(HERE/name).read_bytes()
    with target.open('xb') as output:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
            for name,data in sorted(files.items()):
                item=zipfile.ZipInfo(name,(2026,1,1,0,0,0))
                item.compress_type=zipfile.ZIP_DEFLATED
                item.external_attr=0o100644<<16
                bundle.writestr(item,data)
    target.chmod(0o600)
    blob=target.read_bytes()
    if len(blob)>256*1024:raise ValueError('controller exceeds installed hash-check bound')
    return {'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'installed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    print(json.dumps(build(args.output),sort_keys=True))
