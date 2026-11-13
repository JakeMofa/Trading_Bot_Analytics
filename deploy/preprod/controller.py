"""PP-only deployment controller core; Linux runtime actions remain an adapter.

This module does not install a host entrypoint or enable a deployment target.
An installed, root-owned entrypoint must construct HostBinding.from_marker(),
RootAuthorization and Controller using fixed paths, then supply qualified Actions.
Never load the adapter from the received archive before authorization is consumed.
Actions must use Budget.run (or equivalent bounded subprocesses); opaque callbacks
cannot be forcibly interrupted by Python. No database restore/rollback API exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import time
from typing import Protocol
import uuid

INSTANCE = 'tradebot-preprod-01'
CHECKS = frozenset({'api','sse','schema','migration','data_correctness','collector_ownership',
                    'disabled_flags','recovery','freshness','market_identity'})
COMPRESSED_LIMIT = 16 * 1024**2
EXPANDED_LIMIT = 64 * 1024**2
MEMBER_LIMIT = 4096
FILE_LIMIT = 8 * 1024**2
REQUIRED_FILES = frozenset({'deploy/preprod/Dockerfile','deploy/preprod/compose.yaml',
                           'deploy/preprod/runtime.compose.yaml','backend/postgres/api.py','backend/postgres/migrate.py'})


class DeploymentHold(RuntimeError):
    """Fixed public code only; arbitrary child/adapter diagnostics never escape."""


def require(condition, code):
    if not condition:
        raise DeploymentHold(code)


def _instant(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'authority_timezone_required')
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Request:
    source_sha: str
    artifact_sha256: str
    controller_sha256: str
    environment: str = 'preprod'
    instance: str = INSTANCE

    def validate(self):
        require(self.environment == 'preprod' and self.instance == INSTANCE, 'wrong_target')
        require(bool(re.fullmatch('[0-9a-f]{40}', self.source_sha)), 'invalid_source_sha')
        require(all(re.fullmatch('[0-9a-f]{64}', value) for value in
                    (self.artifact_sha256, self.controller_sha256)), 'invalid_digest')

    @classmethod
    def parse(cls, command):
        require(isinstance(command,str) and len(command)<=512, 'invalid_command')
        parts=command.split(' ')
        require(len(parts)==6 and parts[0]=='deploy-v1', 'invalid_command')
        result=cls(parts[3],parts[4],parts[5],parts[1],parts[2])
        result.validate()
        return result

    def bindings(self):
        return {key:getattr(self,key) for key in ('environment','instance','source_sha','artifact_sha256','controller_sha256')}


def _secure_file(path, expected_uid=0, private=True):
    path=Path(path)
    require(not path.parent.is_symlink(), 'unsafe_parent')
    parent=path.parent.stat()
    require(parent.st_uid==expected_uid and not parent.st_mode & 0o022, 'unsafe_parent')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==expected_uid and info.st_nlink==1,
                'unsafe_trusted_file')
        require(not info.st_mode & (0o077 if private else 0o022), 'unsafe_trusted_file_mode')
        require(info.st_size <= (16384 if private else 256*1024), 'trusted_file_too_large')
        with os.fdopen(descriptor,'rb',closefd=False) as stream:
            content=stream.read((16384 if private else 256*1024)+1)
        return content,info
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class HostBinding:
    hostname: str
    environment: str
    project: str
    live_collector_authorized: bool
    paid_ai_authorized: bool
    production_data_copied: bool

    def validate(self):
        require(self.hostname==INSTANCE and self.environment=='preprod' and self.project=='Tradebot', 'wrong_host_binding')
        require(self.live_collector_authorized is False and self.paid_ai_authorized is False
                and self.production_data_copied is False, 'unsafe_host_binding')

    @classmethod
    def from_marker(cls, path='/etc/tradebot/preprod-host.json'):
        require(os.geteuid()==0, 'root_entrypoint_required')
        content,_=_secure_file(path,private=False)
        marker=json.loads(content)
        result=cls(socket.gethostname(),**{key:marker.get(key) for key in
            ('environment','project','live_collector_authorized','paid_ai_authorized','production_data_copied')})
        result.validate()
        return result


class RootAuthorization:
    """Root-created one-use permit. Receipt hard-link survives interrupted consume."""
    def __init__(self,path,expected_uid=0):
        self.path=Path(path)
        self.expected_uid=expected_uid
        self._fingerprint=None
        self._permit=None

    def validate(self,request,now):
        content,info=_secure_file(self.path,self.expected_uid)
        permit=json.loads(content)
        require(permit.get('version')==1 and all(permit.get(key)==value for key,value in request.bindings().items()),
                'authority_binding_mismatch')
        require(permit.get('data_mode')=='generated' and permit.get('allow_migration') is True
                and permit.get('live_collector_enabled') is False and permit.get('paid_ai_enabled') is False
                and permit.get('retention_enabled') is False and permit.get('production_data_mounted') is False,
                'authority_scope_mismatch')
        nonce=permit.get('nonce')
        require(isinstance(nonce,str) and str(uuid.UUID(nonce))==nonce, 'authority_nonce_invalid')
        issued,expires=_instant(permit['issued_at']),_instant(permit['expires_at'])
        require(issued<=now<expires and 0<(expires-issued).total_seconds()<=3600, 'authority_expired_or_invalid')
        self._fingerprint=(info.st_dev,info.st_ino,hashlib.sha256(content).hexdigest())
        self._permit=permit

    def consume(self,request,now):
        prior=self._fingerprint
        require(prior is not None, 'authority_not_validated')
        self.validate(request,now)
        require(self._fingerprint==prior, 'authority_changed')
        receipt=self.path.with_name('consumed-'+self._permit['nonce']+'.json')
        # link is exclusive: concurrent attempts and replayed permits cannot overwrite
        # the durable receipt. A crash before unlink leaves a non-reusable permit.
        try:
            os.link(self.path,receipt,follow_symlinks=False)
        except FileExistsError:
            raise DeploymentHold('authority_already_consumed') from None
        descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
            require(receipt.lstat().st_ino==prior[1], 'authority_changed')
            self.path.unlink()
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return self._permit['nonce']


class Budget:
    def __init__(self,seconds,clock=time.monotonic):
        self.clock=clock
        self.deadline=clock()+seconds

    def timeout(self,maximum=None):
        remaining=self.deadline-self.clock()
        require(remaining>0, 'deadline_exceeded')
        return remaining if maximum is None else min(maximum,remaining)

    def run(self,args,*,cwd=None,env=None,input=None,timeout=None,output_limit=65536):
        """No shell, bounded streams and process-group cleanup; errors hide output."""
        require(isinstance(args,(tuple,list)) and args and all(isinstance(arg,str) for arg in args), 'invalid_child_command')
        require(1<=output_limit<=65536 and (input is None or len(input)<=FILE_LIMIT), 'child_io_bound')
        child_deadline=self.clock()+self.timeout(timeout)
        with tempfile.TemporaryFile() as source:
            if input is not None:
                source.write(input if isinstance(input,bytes) else input.encode())
            source.seek(0)
            process=subprocess.Popen(args,stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     cwd=cwd,env=env,start_new_session=True)
            selector=selectors.DefaultSelector()
            output={'stdout':bytearray(),'stderr':bytearray()}
            completed=False
            try:
                selector.register(process.stdout,selectors.EVENT_READ,'stdout')
                selector.register(process.stderr,selectors.EVENT_READ,'stderr')
                while selector.get_map():
                    remaining=min(self.timeout(),child_deadline-self.clock())
                    require(remaining>0,'child_deadline_exceeded')
                    for ready,_ in selector.select(min(remaining,.25)):
                        data=os.read(ready.fd,8192)
                        if not data:
                            selector.unregister(ready.fileobj)
                        else:
                            output[ready.data].extend(data)
                            require(len(output[ready.data])<=output_limit,'child_output_bound')
                code=process.wait(timeout=min(self.timeout(),max(.001,child_deadline-self.clock())))
                require(self.clock()<child_deadline,'child_deadline_exceeded')
                require(code==0,'child_failed')
                completed=True
                return bytes(output['stdout'])
            finally:
                selector.close()
                if not completed:
                    try:
                        os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait(timeout=2)
                process.stdout.close()
                process.stderr.close()


def _read_bundle(stream,budget):
    chunks=[]
    size=0
    try:
        descriptor=stream.fileno()
    except (AttributeError,io.UnsupportedOperation):
        descriptor=None
    selector=selectors.DefaultSelector() if descriptor is not None else None
    try:
        if selector:
            try:
                selector.register(descriptor,selectors.EVENT_READ)
            except PermissionError:  # regular files do not support epoll
                selector.close()
                selector=None
        while True:
            remaining=budget.timeout()
            if selector and not selector.select(min(remaining,.25)):
                continue
            chunk=os.read(descriptor,65536) if descriptor is not None else stream.read(65536)
            if not chunk:
                break
            size+=len(chunk)
            require(size<=COMPRESSED_LIMIT,'archive_compressed_bound')
            chunks.append(chunk)
        return b''.join(chunks)
    finally:
        if selector:
            selector.close()


def extract_archive(stream,destination,request,budget):
    """Validate complete bounded tar before creating any extracted member."""
    compressed=_read_bundle(stream,budget)
    require(hashlib.sha256(compressed).hexdigest()==request.artifact_sha256,'archive_digest_mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as zipped:
        expanded=zipped.read(EXPANDED_LIMIT+1)
    require(len(expanded)<=EXPANDED_LIMIT,'archive_expanded_bound')
    budget.timeout()
    with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as archive:
        members=[]
        names=set()
        total=0
        for member in archive:
            require(len(members)<MEMBER_LIMIT,'archive_member_bound')
            name=member.name.rstrip('/')
            parts=PurePosixPath(name).parts
            require(name and len(name)<=512 and not name.startswith('/') and '\\' not in name
                    and all(part not in ('','.','..') for part in name.split('/'))
                    and not any(ord(char)<32 or ord(char)==127 for char in name), 'archive_unsafe_path')
            require(member.isfile() or member.isdir(),'archive_unsafe_type')
            require(not member.issparse() and not member.mode & 0o7000,'archive_unsafe_mode')
            require(name not in names,'archive_duplicate_member')
            require(not any(part in {'.git','.env','.venv','node_modules'} for part in parts)
                    and parts[0]!='data','archive_forbidden_content')
            require(0<=member.size<=FILE_LIMIT and (not member.isdir() or member.size==0),'archive_file_bound')
            total+=member.size
            require(total<=EXPANDED_LIMIT,'archive_expanded_bound')
            names.add(name)
            members.append((member,name))
        require(archive.pax_headers.get('comment')==request.source_sha,'archive_source_mismatch')
        files={name for member,name in members if member.isfile()}
        require(REQUIRED_FILES<=files,'archive_runtime_files_missing')
        # Explicit file/ancestor conflicts are rejected before extraction.
        require(all(not any(str(parent) in files for parent in PurePosixPath(name).parents if str(parent)!='.')
                    for _,name in members),'archive_path_conflict')
        destination=Path(destination)
        destination.mkdir(mode=0o700)
        for member,name in members:
            budget.timeout()
            target=destination/name
            if member.isdir():
                target.mkdir(mode=0o700,parents=True,exist_ok=True)
                continue
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,'wb') as output,archive.extractfile(member) as source:
                shutil.copyfileobj(source,output,length=65536)
                output.flush()
                os.fsync(output.fileno())
            # Docker COPY preserves source modes; non-root runtime must be able to
            # read code in the image. The enclosing candidate directory stays 0700.
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
        for directory,_,_ in os.walk(destination):
            Path(directory).chmod(0o755)


@dataclass(frozen=True)
class Context:
    request: Request
    source: Path
    staging: Path
    image: str | None = None
    failed_stage: str | None = None
    migration_started: bool = False


class Actions(Protocol):
    """Trusted installed adapter, not code imported from the incoming archive.

    preflight is read-only, including runtime config/environment/role checks.
    build returns a pinned local image ID; migrate explicitly invokes the migration
    profile; start never runs migrations implicitly. smoke executes generated-only
    runtime acceptance and returns every CHECKS member plus explicit disabled flags.
    recover fences candidate writers and preserves the current database, credentials
    and volume. It may restart the candidate forward; it must never restore a DB
    or blindly run a prior application against an incompatible migrated schema.
    """
    def preflight(self,context:Context,budget:Budget)->None: ...
    def build(self,context:Context,budget:Budget)->str: ...
    def migrate(self,context:Context,budget:Budget)->None: ...
    def start(self,context:Context,budget:Budget)->None: ...
    def smoke(self,context:Context,budget:Budget)->dict: ...
    def recover(self,context:Context,budget:Budget)->dict: ...


class Controller:
    def __init__(self,binding,authority,controller_path,staging_root,*,expected_uid=0,
                 clock=time.monotonic,wall_clock=lambda:datetime.now(timezone.utc)):
        self.binding,self.authority=binding,authority
        self.controller_path,self.staging_root=Path(controller_path),Path(staging_root)
        self.expected_uid,self.clock,self.wall_clock=expected_uid,clock,wall_clock

    @staticmethod
    def _journal(context,state):
        destination=context.staging/'controller-journal.json'
        temporary=context.staging/'controller-journal.tmp'
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'w') as stream:
            json.dump({**context.request.bindings(),**state},stream,sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,destination)

    def deploy(self,request,stream,actions):
        from dataclasses import replace
        budget=Budget(600,self.clock)
        context=None
        mutation_started=False
        stage='validation'
        result={'gate':'BLOCKED',**request.bindings(),'acceptance_scope':'generated_only'}
        try:
            request.validate()
            self.binding.validate()
            content,_=_secure_file(self.controller_path,self.expected_uid,private=False)
            require(hashlib.sha256(content).hexdigest()==request.controller_sha256,'controller_digest_mismatch')
            self.authority.validate(request,self.wall_clock())
            root=self.staging_root.lstat()
            require(stat.S_ISDIR(root.st_mode) and root.st_uid==self.expected_uid and not root.st_mode & 0o077,
                    'unsafe_staging_root')
            staging=Path(tempfile.mkdtemp(prefix='candidate-',dir=self.staging_root))
            context=Context(request,staging/'source',staging)
            extract_archive(stream,context.source,request,budget)
            stage='preflight'
            actions.preflight(context,budget)
            budget.timeout()
            nonce=self.authority.consume(request,self.wall_clock())
            # From this durable point, failures preserve staged source for forward recovery.
            mutation_started=True
            self._journal(context,{'stage':'authorized','nonce':nonce,'migration_started':False})
            stage='build'
            image=actions.build(context,budget)
            budget.timeout()
            require(isinstance(image,str) and bool(re.fullmatch('sha256:[0-9a-f]{64}',image)), 'unbound_image_id')
            context=replace(context,image=image,migration_started=True)
            stage='migrate'
            self._journal(context,{'stage':stage,'migration_started':True,'image':image})
            actions.migrate(context,budget)
            budget.timeout()
            stage='start'
            self._journal(context,{'stage':stage,'migration_started':True,'image':image})
            actions.start(context,budget)
            budget.timeout()
            stage='smoke'
            evidence=actions.smoke(context,budget)
            budget.timeout()
            require(evidence.get('checks')==dict.fromkeys(CHECKS,'PASS'),'incomplete_runtime_acceptance')
            require(evidence.get('acceptance_scope')=='generated_only','wrong_acceptance_scope')
            flags=('live_collector_enabled','paid_ai_enabled','retention_enabled','production_data_mounted')
            require(all(evidence.get(flag) is False for flag in flags),'unsafe_runtime_flags')
            result.update(gate='PASS',checks=evidence['checks'],**{flag:False for flag in flags})
            self._journal(context,{'stage':'complete','migration_started':True,'image':image,'gate':'PASS'})
        except Exception as error:
            result.update(reason=str(error) if isinstance(error,DeploymentHold) else 'controller_action_failed',failed_stage=stage)
            if mutation_started and context:
                recovery_budget=Budget(180,self.clock)
                try:
                    recovered=actions.recover(replace(context,failed_stage=stage),recovery_budget)
                    recovery_budget.timeout()
                    require(recovered.get('strategy') in ('stop_candidate_keep_database','forward_candidate')
                            and recovered.get('database_preserved') is True
                            and recovered.get('new_acknowledgements_preserved') is True
                            and recovered.get('database_restored') is False,'recovery_not_proven')
                    result['recovery']={key:recovered[key] for key in ('strategy','database_preserved','new_acknowledgements_preserved','database_restored')}
                except Exception:
                    result['recovery']={'status':'unproven_preserve_and_inspect'}
                try:
                    self._journal(context,{'stage':'failed','failed_stage':stage,'migration_started':context.migration_started,
                                           'gate':'BLOCKED','recovery':result['recovery']})
                except Exception:
                    result['journal_status']='unavailable'
        finally:
            if context and not mutation_started:
                shutil.rmtree(context.staging)
        return result


if __name__=='__main__':
    raise SystemExit('Controller core only: qualified root entrypoint and Linux Actions adapter required; target remains disabled.')
