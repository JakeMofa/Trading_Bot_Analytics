"""Root-only exact trial child launch/readiness; no collector or retirement calls."""
import hashlib
import json
import re
import ssl
import stat
import time
import uuid
from pathlib import Path
from controller import Budget,HostBinding,_secure_file,require
from linux_actions import LinuxActions,PROJECT,RUNTIME_SECRETS,TRIAL_ORIGIN,cycle_environment
from trial_cloud_profile import WRITER_SQL,WRITER_AUTH,overlay,service_name,profile_name,validate_profile

CLOUD_DIR=Path('/etc/tradebot/cloud')
AUTHORITY=RUNTIME_SECRETS/'trial_20261119_02_writer_authority.json'
PROOF=RUNTIME_SECRETS/'trial_20261119_02_writer_proof.json'
WRITER_ROLE='tradebot_pp_trial_20261119_02_writer'
READER_ROLE='tradebot_pp_trial_20261119_02_reader'
VERDICTS=('sql_writer_insert','sql_reader_select','sql_wrong_origin_denied','sql_reader_mutation_denied',
          'storage_upload_readback','storage_wrong_origin_denied','storage_reader_get','storage_reader_create_denied','sql_retained_trial_denied','storage_retained_trial_denied')


def _metadata(path,*,uid,mode,limit):
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==uid and stat.S_IMODE(info.st_mode)==mode
            and info.st_nlink==1 and 0<info.st_size<=limit,'unsafe_trial_cloud_file')
    return info.st_dev,info.st_ino


def writer_proof(context,initial_a):
    """Root attestation of actual hosted tests, bound to this release and anchor."""
    for path in (AUTHORITY,PROOF):_metadata(path,uid=0,mode=0o400,limit=8192)
    authority=json.loads(_secure_file(AUTHORITY)[0]);raw=_secure_file(PROOF)[0];proof=json.loads(raw)
    require(set(authority)=={'version','scope','origin_id','initial_a','source_sha','image_id','proof_sha256'}
            and type(authority.get('version')) is int and authority==dict(version=1,scope='pp-trial-cloud-writer-v1',origin_id=TRIAL_ORIGIN,
                initial_a=initial_a,source_sha=context.request.source_sha,image_id=context.image,
                proof_sha256=hashlib.sha256(raw).hexdigest()),'unqualified_trial_writer_authority')
    fields={'version','origin_id','sql_writer_role','sql_reader_role','archive_writer_uid','archive_reader_uid',*VERDICTS}
    require(set(proof)==fields and type(proof['version']) is int and proof['version']==1 and proof['origin_id']==TRIAL_ORIGIN
            and proof['sql_writer_role']==WRITER_ROLE and proof['sql_reader_role']==READER_ROLE
            and all(proof[key]=='pass' for key in VERDICTS),'incomplete_trial_writer_proof')
    for key in ('archive_writer_uid','archive_reader_uid'):
        require(isinstance(proof[key],str) and str(uuid.UUID(proof[key]))==proof[key],'invalid_trial_auth_identity')
    require(proof['archive_writer_uid']!=proof['archive_reader_uid'],'trial_writer_reader_identity_alias')
    files={**WRITER_SQL,**WRITER_AUTH}
    identities=set()
    directory=CLOUD_DIR.lstat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid==0 and stat.S_IMODE(directory.st_mode)==0o700,
            'unsafe_pp_cloud_directory')
    for name,path in files.items():
        identity=_metadata(Path(path),uid=0,mode=0o644 if name=='pp_history_ca' else 0o600,
                           limit=16384 if name=='pp_history_ca' else 4096)
        require(identity not in identities,'aliased_trial_cloud_file');identities.add(identity)
    from structured_probe_control import CA_SHA256
    pem=Path(WRITER_SQL['pp_history_ca']).read_text(encoding='ascii')
    require(pem.count('-----BEGIN CERTIFICATE-----')==1
            and hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()==CA_SHA256,'wrong_pp_cloud_ca')
    require(Path(WRITER_AUTH['trial_archive_uid']).read_text().strip()==proof['archive_writer_uid'],
            'trial_archive_writer_identity_mismatch')
    from trial_history_reader import trial_history_reader_source
    reader=trial_history_reader_source('trial_history_reader_uid')
    _metadata(reader,uid=10001,mode=0o400,limit=64)
    require(reader.read_text().strip()==proof['archive_reader_uid'],'trial_archive_reader_identity_mismatch')
    legacy=CLOUD_DIR/'supabase_auth_uid'
    _metadata(legacy,uid=0,mode=0o600,limit=64)
    require(legacy.read_text().strip() not in (proof['archive_writer_uid'],proof['archive_reader_uid']),
            'trial_identity_reuses_legacy_writer')
    return authority['proof_sha256']


def _reader(context,anchor):
    from trial_history_reader import trial_history_reader_enabled
    require(trial_history_reader_enabled(context,anchor),'trial_reader_readiness_missing')
    return True


def _compose(actions,context,budget,anchor,args,*,archive=False,reader=True):
    folder=context.source/'deploy/preprod'
    files=['compose.yaml','runtime.compose.yaml','runtime.live.compose.yaml','runtime.live-cycle.compose.yaml',
           'runtime.live-trial.compose.yaml']
    if reader:
        from trial_history_reader import TRIAL_HISTORY_READER_OVERLAY
        files.append(TRIAL_HISTORY_READER_OVERLAY)
    files.append(overlay(archive))
    command=['docker','compose','--env-file','/dev/null','--project-name',PROJECT,'--project-directory',str(folder)]
    for name in files:command+=['-f',str(folder/name)]
    env=actions._environment(context.image);env.update(cycle_environment(anchor,TRIAL_ORIGIN))
    return budget.run([*command,'--profile','migration','--profile',profile_name(archive),*args],
                      cwd=context.source,env=env,timeout=30)


def preflight(installed,budget,*,archive=False):
    from transition_control import _read_active,_candidate,_image_binding,_owned_runtime,TransitionRequest
    from live_transition import LiveTransition
    HostBinding.from_marker().validate()
    active=_read_active()
    require(active['state']=='ready_off' and active.get('trial_origin')==TRIAL_ORIGIN,'exact_trial_ready_profile_required')
    anchor=active.get('initial_a');cycle_environment(anchor,TRIAL_ORIGIN)
    request=TransitionRequest('enter',*[active[key] for key in ('source_sha','artifact_sha256','controller_sha256','image_id')],
                              initial_a=anchor,trial_origin=TRIAL_ORIGIN)
    context=_candidate(request);actions=_image_binding(context,budget);_owned_runtime(actions,context,budget)
    digest=hashlib.sha256(_secure_file(installed,private=False)[0]).hexdigest()
    require(digest==active['controller_sha256'],'trial_cloud_controller_mismatch')
    proof=writer_proof(context,anchor);_reader(context,anchor)
    actions._runtime(context,budget,live=True,initial_a=anchor,trial_origin=TRIAL_ORIGIN)
    actions._host_operator(live=True,trial_origin=TRIAL_ORIGIN)
    live=LiveTransition(actions,context,budget,initial_a=anchor,trial_origin=TRIAL_ORIGIN)
    base=actions._json(actions._compose(context,budget,['config','--format','json']))
    cfg=actions._json(live._compose_live(['config','--format','json']))
    child=actions._json(_compose(actions,context,budget,anchor,['config','--format','json'],archive=archive))
    validate_profile(base,cfg,child,context.source,context.image,anchor,archive=archive,trial_reader=True)
    return context,actions,anchor,proof,base


def _inspect_worker(owner,budget,base,*,archive=False):
    from structured_probe_control import _sync_container
    from trial_cloud_profile import child_service
    row=_sync_container(owner,budget,archive=archive)
    require(row is not None and row['State'].get('Running') is True and not row['State'].get('OOMKilled',False),
            'trial_cloud_worker_not_running')
    expected=child_service(base,owner['initial_a'],archive=archive)
    env=dict(value.split('=',1) for value in row['Config'].get('Env',[]) if '=' in value)
    require(all(env.get(k)==v for k,v in expected['environment'].items())
            and set(k for k in env if k.startswith(('TRADEBOT_','ENABLE_')))==
                set(k for k in expected['environment'] if k.startswith(('TRADEBOT_','ENABLE_')))
            and row['Config'].get('Cmd')==expected['command'] and row['Config'].get('User')=='0:0',
            'trial_cloud_worker_scope_mismatch')
    host=row['HostConfig']
    require(host.get('ReadonlyRootfs') is True and host.get('Privileged') is False and host.get('CapDrop')==['ALL']
            and host.get('Memory')==128*1024**2 and host.get('MemorySwap')==128*1024**2
            and host.get('NanoCpus')==250000000 and host.get('PidsLimit')==64,'trial_cloud_worker_isolation_mismatch')
    files=WRITER_AUTH if archive else WRITER_SQL
    mounts={item.get('Destination'):item for item in row.get('Mounts',[]) if item.get('Destination','').startswith('/run/secrets/')}
    sources={'/run/secrets/'+key:value for key,value in files.items()}
    sources['/run/secrets/lifecycle_dsn']='/run/tradebot-pp-deploy/probe-local-dsn'
    require(set(mounts)==set(sources) and all(mounts[k].get('Source')==v and mounts[k].get('RW') is False for k,v in sources.items())
            and all(item.get('Destination') in {'/tmp',*mounts} for item in row.get('Mounts',[])),
            'trial_cloud_worker_mount_mismatch')
    egress='raw_archive_probe_egress' if archive else 'structured_probe_egress'
    require(set(row['NetworkSettings']['Networks'])=={PROJECT+'_database',PROJECT+'_'+egress}
            and not host.get('PortBindings'),'trial_cloud_worker_network_mismatch')
    return row


def start(installed,*,archive=False):
    from structured_probe_control import (ARCHIVE_STATE,SYNC_STATE,_require_stopped,_write_sync_owner,
                                          _stage_local_secret,recurring_control)
    path=ARCHIVE_STATE if archive else SYNC_STATE;_require_stopped(path)
    budget=Budget(120);context,actions,anchor,proof,base=preflight(installed,budget,archive=archive)
    owner=dict(attempt_id=actions.attempt_id,image=context.image,source_sha=context.request.source_sha,
               origin_id=TRIAL_ORIGIN,initial_a=anchor,writer_proof_sha256=proof)
    _write_sync_owner(owner,path)
    name=('tradebot-pp-sealed-' if archive else 'tradebot-pp-sync-')+actions.attempt_id
    args=['run','--detach','--no-deps','--name',name,'--label','tradebot.deployment_attempt='+actions.attempt_id,
          '--label','tradebot.deployment_source='+context.request.source_sha,service_name(archive)]
    try:
        with _stage_local_secret():
            _compose(actions,context,budget,anchor,args,archive=archive)
            for _ in range(20):
                row=_inspect_worker(owner,budget,base,archive=archive)
                raw=budget.run(['docker','logs','--tail','8',row['Id']],env=actions._environment(context.image),timeout=5)
                marker=b'{"status": "sealed_archive_worker_ready"}' if archive else b'{"status": "structured_worker_ready"}'
                if marker in raw.splitlines():break
                time.sleep(.25)
            else:require(False,'trial_cloud_worker_readiness_timeout')
    except BaseException:
        recurring_control('stop',Budget(65),archive=archive)
        raise
    return dict(status='started',origin_id=TRIAL_ORIGIN,initial_a=anchor,retirement='off',collector_enabled=False)


def require_ready(context,anchor,budget):
    """Called before ON permit issue/consumption; never starts a service."""
    from structured_probe_control import ARCHIVE_STATE,SYNC_STATE
    proof=writer_proof(context,anchor);_reader(context,anchor)
    base=LinuxActions()._json(LinuxActions()._compose(context,budget,['config','--format','json']))
    for archive,path in ((False,SYNC_STATE),(True,ARCHIVE_STATE)):
        owner=json.loads(_secure_file(path)[0])
        require(owner.get('origin_id')==TRIAL_ORIGIN and owner.get('initial_a')==anchor
                and owner.get('source_sha')==context.request.source_sha and owner.get('image')==context.image
                and owner.get('writer_proof_sha256')==proof,'trial_cloud_worker_binding_mismatch')
        _inspect_worker(owner,budget,base,archive=archive)
    return True
