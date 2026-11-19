"""One-use PP20 fenced forward bootstrap; never a CD or retirement receipt.

Run only as a pinned root operator procedure after exact source CI and installed
controller identity qualification. Normal CD remains a separate acceptance gate.
"""
from dataclasses import replace
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import re
import signal
import zipfile
import tempfile

from controller import (Budget,Context,HostBinding,Request,RootAuthorization,
                        _secure_file,extract_archive,require)
from linux_actions import (LinuxActions,SERVICES,PROJECT,NETWORK,API_NETWORK,
                           MEMORY,CPUS,COMMANDS,RUNTIME_SECRETS,expected_environment,
                           service_secrets)
from structured_probe_control import fence_recurring_sync

FAILED_SOURCE='b7b4c9f1eae351c0dde1eafbd27f64571be5aa5a'
FAILED_ARTIFACT='1c45affb799be7601e1d4efeb36021a387dd39074378be264840c472ec00728d'
FAILED_IMAGE='sha256:711fcb3f0267cd8214dafbe2c183b6569a3cec1ccb40cb79f15a8af3bb5366ea'
CONTROLLER='9a7b10324bb9376193a7a5263efd9bd5e40818682f0e2cb77ba84d4373d9081a'
INSTALLED=Path('/usr/local/lib/tradebot-pp/controller.pyz')
ROOT=Path('/var/lib/tradebot-pp/forward-recoveries')
DEPLOYMENTS=Path('/var/lib/tradebot-pp/deployments')
AUTHORITY=Path('/run/tradebot-pp-deploy/forward-bootstrap.json')
OPERATION='pp20-fenced-forward-bootstrap'


def stopped_profile(rows):
    """Old generated profile is accepted only stopped, exact-image and default OFF."""
    require(set(rows)==set(SERVICES),'forward_prior_services_incomplete')
    require(len({r.get('Id') for r in rows.values()})==len(SERVICES),'forward_prior_duplicate_id')
    for service,row in rows.items():
        state=row.get('State',{});config=row.get('Config',{});host=row.get('HostConfig',{})
        require(row.get('Image')==FAILED_IMAGE and state.get('Running') is False
                and state.get('OOMKilled') is False,'forward_prior_not_fenced')
        labels=config.get('Labels',{})
        require(labels.get('com.docker.compose.project')==PROJECT
                and labels.get('com.docker.compose.service')==service
                and labels.get('com.docker.compose.oneoff')=='False'
                and config.get('Cmd')==COMMANDS[service] and config.get('User')=='10001:10001',
                'forward_prior_command_or_owner')
        env=dict(item.split('=',1) for item in config.get('Env',[]) if '=' in item)
        wanted=expected_environment(service).copy();wanted.pop('TRADEBOT_GENERATED_LOCAL_STORAGE',None)
        require(all(env.get(k)==v for k,v in wanted.items())
                and env.get('TRADEBOT_GENERATED_LOCAL_STORAGE','false')=='false'
                and all(env.get(k,'false')=='false' for k in (
                    'TRADEBOT_PP_LIVE_CONTROL','TRADEBOT_PP_LIVE_LIFECYCLE',
                    'TRADEBOT_PP_ARCHIVE_HISTORY','TRADEBOT_PP_EXACT_RETIREMENT',
                    'TRADEBOT_CLOUD_ENABLED','TRADEBOT_RETIREMENT_ENABLED','ENABLE_LOCAL_RETENTION',
                    'ENABLE_OPENAI_ANALYST','ENABLE_SUPABASE_SYNC'))
                and not env.get('TRADEBOT_DATABASE_DSN'),'forward_prior_flags')
        require(host.get('RestartPolicy',{}).get('Name')=='no'
                and host.get('Memory')==host.get('MemorySwap')==MEMORY[service]*1024**2
                and host.get('NanoCpus')==int(CPUS[service]*1e9) and host.get('PidsLimit')==64
                and host.get('ReadonlyRootfs') is True and host.get('Privileged') is False
                and host.get('CapDrop')==['ALL'],'forward_prior_resources')
        networks=set(row.get('NetworkSettings',{}).get('Networks',{}))
        require(networks==({NETWORK,API_NETWORK} if service in ('api','operator') else {NETWORK}),
                'forward_prior_networks')
        mounts=row.get('Mounts',[])
        secrets={m.get('Destination'):m for m in mounts if m.get('Destination','').startswith('/run/secrets/')}
        require(set(secrets)=={'/run/secrets/'+n for n in service_secrets(service)}
                and all(m.get('Source')==str(RUNTIME_SECRETS/Path(n).name) and m.get('RW') is False
                        for n,m in secrets.items())
                and all(m.get('Destination') in {'/tmp',*secrets} for m in mounts),
                'forward_prior_mounts')
        port=8000 if service=='api' else 8001 if service=='operator' else None
        require((host.get('PortBindings') or {})==({f'{port}/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]} if port else {}),
                'forward_prior_ports')


def prior_state(actions,context,budget):
    active=json.loads(_secure_file(DEPLOYMENTS/'active-live-transition.json')[0])
    require(active.get('state')=='generated_restored'
            and active.get('source_sha')=='5efc4bb774b41e65c174aa53882629908ad96ad3'
            and active.get('artifact_sha256')=='9b68e22b2b5f8e86f8308d4f11c38dbe03ddd40b33ce1993b53a9100e6042017'
            and active.get('image_id')=='sha256:36923156e4879f00be3d1bc7568475c818f4798ca4e40e9856a912ce7a5814f2',
            'forward_active_transition_changed')
    matches=[]
    for folder in DEPLOYMENTS.glob('candidate-*'):
        path=folder/'controller-journal.json'
        if not path.exists():continue
        data=json.loads(_secure_file(path)[0])
        if data.get('source_sha')==FAILED_SOURCE and data.get('artifact_sha256')==FAILED_ARTIFACT:
            require(data.get('stage')=='failed' and data.get('failed_stage')=='smoke'
                    and data.get('migration_started') is True and data.get('gate')=='BLOCKED'
                    and data.get('recovery')=={'strategy':'stop_candidate_keep_database',
                        'database_preserved':True,'new_acknowledgements_preserved':True,'database_restored':False},
                    'forward_failed_journal_mismatch')
            matches.append(path)
    require(len(matches)==1,'forward_failed_journal_not_unique')
    rows={}
    for service in SERVICES:
        ids=actions._ids(context,budget,[service],all=True)
        require(len(ids)==1,'forward_prior_services_incomplete')
        rows[service]=actions._inspect(budget,ids)[0]
    stopped_profile(rows)
    image=actions._json(budget.run(['docker','image','inspect',FAILED_IMAGE],
        env=actions._environment('unused'),timeout=10))
    require(len(image)==1 and image[0]['Config']['Labels'].get('tradebot.source_sha')==FAILED_SOURCE,
            'forward_prior_image_source')
    state=database_state(actions,budget)
    require(state.get('versions')==[1,2,3] and state.get('writers')==2 and state.get('unexpected_writers')==0
            and state.get('generated')==state.get('pending')==10000 and state.get('live')==42133
            and state.get('live_pending')==0 and state.get('a')==state.get('b')==1
            and state.get('raw_a')==28411 and state.get('raw_b')==9784
            and type(state.get('through_id')) is int and state.get('raw_not_future') is True
            and bool(re.fullmatch(r'[0-9:+. -]{20,40}',state.get('raw_cutoff',''))),'forward_database_state_changed')
    return state


def database_state(actions,budget):
    return actions._json(actions._reader_sql(budget,"""SELECT json_build_object(
        'versions',(SELECT json_agg(version ORDER BY version) FROM ops.schema_migrations),
        'writers',(SELECT count(*) FROM ops.writer_state WHERE
            ((origin_id='generated-pp' AND generation_id='2ba8b503-f94a-4fbb-bfe5-04569de18435')
             OR (origin_id='pp-live-pp' AND generation_id='23f4ccb8-c243-4eae-bbd2-8c75aae9816a'))
            AND NOT collector_enabled AND collector_session_id IS NULL),
        'unexpected_writers',(SELECT count(*) FROM ops.writer_state WHERE origin_id NOT IN ('generated-pp','pp-live-pp')),
        'generated',(SELECT count(*) FROM ops.outbox WHERE origin_id='generated-pp'),
        'pending',(SELECT count(*) FROM ops.outbox WHERE origin_id='generated-pp' AND acknowledged_at IS NULL),
        'live',(SELECT count(*) FROM ops.outbox WHERE origin_id='pp-live-pp'),
        'live_pending',(SELECT count(*) FROM ops.outbox WHERE origin_id='pp-live-pp' AND acknowledged_at IS NULL),
        'through_id',(SELECT max(id) FROM ops.outbox WHERE origin_id='generated-pp'),
        'raw_cutoff',(SELECT max(received_at)::text FROM raw.events),
        'raw_not_future',(SELECT max(received_at)<clock_timestamp()-interval '1 second' FROM raw.events),
        'a',(SELECT count(*) FROM archive.generations WHERE origin_id='pp-live-pp'
            AND generation_id='2f5ab434-14c0-4a61-8b8e-145c9a05f0e6' AND slot='A' AND state='verified' AND seal_count=28411
            AND seal_hash='bd8e9f5da7951f0ee72a01bf26a48133d258d42da10d24190a1738bcfdc27250'),
        'raw_a',(SELECT count(*) FROM raw.events WHERE generation_id='2f5ab434-14c0-4a61-8b8e-145c9a05f0e6'),
        'raw_b',(SELECT count(*) FROM raw.events WHERE generation_id='23f4ccb8-c243-4eae-bbd2-8c75aae9816a'),
        'b',(SELECT count(*) FROM archive.generations WHERE origin_id='pp-live-pp'
            AND generation_id='23f4ccb8-c243-4eae-bbd2-8c75aae9816a' AND slot='B' AND state='collecting'))"""))


def fingerprint(actions,budget,table,where='true',expression='to_jsonb(t)'):
    return actions._json(actions._reader_sql(budget,"""SELECT json_build_object('count',coalesce(sum(n),0),
        'digest',encode(sha256(convert_to(coalesce(string_agg(page_hash,'' ORDER BY page),''),'UTF8')),'hex'))
        FROM (SELECT page,count(*) n,encode(sha256(convert_to(string_agg(fingerprint,'' ORDER BY fingerprint),'UTF8')),'hex') page_hash
        FROM (SELECT fingerprint,(row_number() OVER(ORDER BY fingerprint)-1)/1024 page
        FROM (SELECT encode(sha256(convert_to(("""+expression+""")::text,'UTF8')),'hex') fingerprint
        FROM """+table+' t WHERE '+where+""") rows) numbered GROUP BY page) pages"""))


def preserved_state(actions,budget,through_id,raw_cutoff):
    require(type(through_id) is int and through_id>0
            and isinstance(raw_cutoff,str) and bool(re.fullmatch(r'[0-9:+. -]{20,40}',raw_cutoff)),
            'forward_invalid_source_bound')
    result={table:fingerprint(actions,budget,table,"origin_id='pp-live-pp'") for table in (
        'core.markets','core.candles','core.current_prices','core.protected_evidence',
        'core.feature_snapshots','core.predictions','core.outcomes','core.snapshot_evidence',
        'archive.generations','ops.writer_state','ops.outbox')}
    result['original_raw']=fingerprint(actions,budget,'raw.events',
        "received_at<='"+raw_cutoff+"'::timestamptz")
    result['generated_generations']=fingerprint(actions,budget,'archive.generations',
        "origin_id='generated-pp'","to_jsonb(t)-'hold_reason'")
    result['all_outcomes']=fingerprint(actions,budget,'core.outcomes')
    result['original_generated_outbox']=fingerprint(actions,budget,'ops.outbox',
        "origin_id='generated-pp' AND id<="+str(through_id),"to_jsonb(t)-'acknowledged_at'")
    return result


def forward(actions,context,budget,before,through_id,raw_cutoff):
    """Use the installed adapter unchanged; skip no migration/schema/smoke check."""
    actions.forward_phase='build'
    image=actions.build(context,budget);context=replace(context,image=image,migration_started=True)
    actions.fence_started=True;actions._fence(context,budget);actions.fence_completed=True
    actions.before_migration=actions._inventory(budget)
    actions.forward_phase='migration4'
    migration=actions._json(actions._oneoff(context,budget,'migrate',timeout=90))
    require(migration=={'environment':'preprod','operation':'migrate','result':[4]},'forward_migration4_not_proven')
    after=actions._inventory(budget)
    require(all(value is None or after.get(table)==value for table,value in actions.before_migration.items()),
            'migration_changed_existing_evidence')
    require(preserved_state(actions,budget,through_id,raw_cutoff)==before,'forward_source_changed_during_migration')
    actions.migrated=True
    # The actual bootstrap performs append-only durable copy and independent
    # authenticated readback before source ACK, then proves >=128 free slots.
    actions.forward_phase='generated_bootstrap_and_start'
    actions.start(context,budget)
    require(preserved_state(actions,budget,through_id,raw_cutoff)==before,'forward_preservation_failed')
    actions.forward_phase='generated_smoke'
    smoke=actions.smoke(context,budget)
    require(preserved_state(actions,budget,through_id,raw_cutoff)==before,'forward_preservation_failed')
    return {'gate':'PP20_FORWARD_BOOTSTRAP_PASS','source_sha':context.request.source_sha,
            'artifact_sha256':context.request.artifact_sha256,'image_id':image,
            'controller_sha256':CONTROLLER,'acceptance_scope':'operator_forward_bootstrap_only',
            'cd_acceptance':False,'live_collector_enabled':False,'retirement_authorized':False,
            'database_restored':False,'original_generated_source_preserved':True,
            'live_and_raw_and_outcomes_preserved':True,'smoke':smoke}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('preflight','execute'))
    parser.add_argument('--source-sha',required=True);parser.add_argument('--artifact-sha256',required=True)
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    request=Request(args.source_sha,args.artifact_sha256,CONTROLLER);request.validate()
    require(os.geteuid()==0,'root_entrypoint_required');HostBinding.from_marker().validate()
    require(hashlib.sha256(_secure_file(INSTALLED,private=False)[0]).hexdigest()==CONTROLLER,'controller_digest_mismatch')
    lock=os.open('/run/tradebot-pp-deploy/controller.lock',os.O_RDWR|os.O_NOFOLLOW)
    with os.fdopen(lock,'wb') as descriptor:
        info=os.fstat(descriptor.fileno());require(stat.S_ISREG(info.st_mode) and info.st_uid==0
            and stat.S_IMODE(info.st_mode)==0o600,'unsafe_controller_lock')
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def interrupted(signum,frame):
            raise RuntimeError('forward_operator_interrupted')
        for name in ('SIGTERM','SIGINT','SIGHUP'):
            signal.signal(getattr(signal,name),interrupted)
        fence_recurring_sync()
        for name in ('authorization.json','live-enter.json','live-on.json','structured-probe.json','raw-archive-probe.json'):
            p=AUTHORITY.parent/name;require(not p.exists() and not p.is_symlink(),'forward_unused_authority')
        if args.mode=='execute':
            authority=RootAuthorization(AUTHORITY)
            permit=json.loads(_secure_file(AUTHORITY)[0])
            require(permit.get('operation')==OPERATION and permit.get('cloud_enabled') is False
                    and permit.get('retirement_enabled') is False,'forward_authority_operation')
            from datetime import datetime,timezone
            authority.validate(request,datetime.now(timezone.utc))
        require(not ROOT.is_symlink(),'unsafe_staging_root');ROOT.mkdir(mode=0o700,exist_ok=True)
        info=ROOT.stat();require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,'unsafe_staging_root')
        # This separate tree never creates a normal deployment PASS candidate.
        staging=Path(tempfile.mkdtemp(prefix='bootstrap-',dir=ROOT))
        context=Context(request,staging/'source',staging);budget=Budget(600);actions=LinuxActions()
        before=None;state=None
        try:
            with args.archive.open('rb') as stream:extract_archive(stream,context.source,request,budget)
            with zipfile.ZipFile(INSTALLED) as archive:
                for name in archive.namelist():
                    if name!='__main__.py':
                        require(archive.read(name)==(context.source/'deploy/preprod'/name).read_bytes(),
                                'forward_source_controller_mismatch')
            actions.preflight(context,budget)
            state=prior_state(actions,context,budget)
            before=preserved_state(actions,budget,state['through_id'],state['raw_cutoff'])
            if args.mode=='preflight':result={'gate':'PP20_FORWARD_PREFLIGHT_PASS','source_sha':request.source_sha,
                'database_changed':False,'through_id':state['through_id'],'preservation':before}
            else:
                authority.consume(request,datetime.now(timezone.utc))
                result=forward(actions,context,budget,before,state['through_id'],state['raw_cutoff'])
        except Exception:
            result={'gate':'PP20_FORWARD_BOOTSTRAP_BLOCKED','phase':getattr(actions,'forward_phase','preflight'),
                    'source_sha':request.source_sha,'database_restored':False,
                    'live_collector_enabled':False,'retirement_authorized':False,
                    'recovery':'unproven_preserve_and_inspect'}
            # The original application was already OFF. Never restore a database
            # or start an old image after the migration boundary.
            try:
                recovery=Budget(180)
                if actions.migration_oneoff_attempted:
                    actions._cleanup_oneoffs(context,recovery)
                    actions._fence(context,recovery)
                    actions._postgres(context,recovery)
                if before is not None:
                    require(preserved_state(actions,recovery,state['through_id'],state['raw_cutoff'])==before,
                            'forward_failure_preservation_unproven')
                    result['recovery']='stopped_database_and_original_source_preserved'
            except Exception:
                pass
        receipt=os.open(staging/'forward-bootstrap-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(receipt,'w') as output:
            output.write(json.dumps(result,sort_keys=True)+'\n');output.flush();os.fsync(output.fileno())
        directory=os.open(staging,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        print(json.dumps(result,sort_keys=True))
        return 0 if result['gate'] in ('PP20_FORWARD_PREFLIGHT_PASS','PP20_FORWARD_BOOTSTRAP_PASS') else 1


if __name__=='__main__':
    raise SystemExit(main())
