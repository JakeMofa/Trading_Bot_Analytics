"""Default-off application routing for the qualified A/B adapter.

Generated-root and migration bounds remain enforced. Production path/volume
authorization requires its own reviewed cutover.
"""
from pathlib import Path
import os
import sys

from cloud_memory import enabled


def configured_runtime(environ=None):
    env = os.environ if environ is None else environ
    if not enabled(env.get('ENABLE_AB_STORAGE','false')):
        return None
    if enabled(env.get('ENABLE_OPENAI_ANALYST','false')):
        raise RuntimeError('A/B rollout requires paid AI disabled')
    if enabled(env.get('ENABLE_LOCAL_RETENTION','false')):
        raise RuntimeError('A/B rollout forbids legacy row retention')
    root = env.get('AB_STORAGE_ROOT')
    legacy = env.get('SQLITE_DB_PATH')
    threshold = env.get('AB_GENERATION_BYTES')
    if not root or not legacy or not threshold:
        raise RuntimeError('A/B root, legacy path and generation threshold required')
    try:
        size = int(threshold)
    except (TypeError,ValueError):
        raise RuntimeError('invalid A/B generation threshold') from None
    if not 0 < size < 2*1024**3:
        raise RuntimeError('A/B threshold exceeds qualified resource envelope')
    mode=env.get('AB_STARTUP_MODE','full-import')
    if mode not in ('full-import','fresh-b'):raise RuntimeError('unsupported A/B startup mode')
    ceiling=int(env.get('MAX_LOCAL_STORAGE_MB','2048'))*1024**2 if mode=='fresh-b' else 2*1024**3
    if not 2*1024**3<=ceiling<=8*1024**3:raise RuntimeError('unsupported fresh-B aggregate budget')
    try:
        rows=int(env.get('AB_MIGRATION_ROWS','60000' if mode=='fresh-b' else '10000'))
        audit_bytes=int(env.get('AB_MIGRATION_BYTES',str(128*1024**2)))
    except (ValueError,TypeError):raise RuntimeError('invalid explicit audit envelope') from None
    if not 0<rows<=250000 or not 0<audit_bytes<=256*1024**2:raise RuntimeError('migration scope exceeds supported audit envelope')
    recovery_keys=('AB_RECOVERY_MANIFEST','AB_RECOVERY_DEPENDENCIES','AB_RECOVERY_STREAM','AB_RECOVERY_MANIFEST_SHA256','AB_RECOVERY_DEPENDENCY_SHA256','AB_RECOVERY_STREAM_SHA256')
    recovery={k:env.get(k) for k in recovery_keys}
    if any(recovery.values()) and (mode!='fresh-b' or not all(recovery.values())):raise RuntimeError('complete explicit fresh-B recovery binding required')
    recovery=recovery if any(recovery.values()) else None
    try:
        verify_objects=int(env.get('AB_RETIRE_VERIFY_OBJECTS','0'))
        verify_age=int(env.get('AB_RETIRE_VERIFY_MAX_AGE','300'))
    except (TypeError,ValueError):raise RuntimeError('invalid retirement verification policy') from None
    if not 0<=verify_objects<=8 or not 1<=verify_age<=21600:raise RuntimeError('retirement verification policy out of bounds')
    return StorageRuntime(root,legacy,size,enabled(env.get('ENABLE_AB_RETIREMENT','false')),fresh_b=mode=='fresh-b',aggregate_bytes=ceiling,migration_rows=rows,migration_bytes=audit_bytes,recovery_files=recovery,verify_objects=verify_objects,verify_age=verify_age)


def adapter_modules():
    directory = Path(__file__).resolve().parents[1]/'prototype'
    if str(directory) not in sys.path:
        sys.path.insert(0,str(directory))
    from application_store import ApplicationStore, ApplicationWorker
    return ApplicationStore, ApplicationWorker


class StorageRuntime:
    def __init__(self,root,legacy,threshold,retirement=False,fresh_b=False,aggregate_bytes=2*1024**3,migration_rows=None,migration_bytes=128*1024**2,recovery_files=None,verify_objects=0,verify_age=300):
        self.root = Path(root)
        self.legacy = Path(legacy)
        self.threshold = threshold
        self.aggregate_bytes = aggregate_bytes
        self.migration_bytes=migration_bytes;self.recovery_files=recovery_files
        self.migration_rows = migration_rows or (60000 if fresh_b else 10000)
        self.fresh_b = fresh_b
        self.retirement = retirement
        self.verify_objects,self.verify_age=verify_objects,verify_age
        self.handle = None

    @property
    def database(self):
        return str(self.root/'core.db')

    def open(self,role):
        if self.handle is not None:
            raise RuntimeError('storage runtime already opened')
        collector, worker = adapter_modules()
        if role == 'collector':
            from migration_budget import MigrationBudget
            import time
            budget=MigrationBudget(row_limit=self.migration_rows,byte_limit=self.migration_bytes,deadline=time.monotonic()+170)
            recovery=None
            if self.recovery_files:
                from recovery_capsule import RecoveryCapsule
                r=self.recovery_files
                recovery=RecoveryCapsule(r['AB_RECOVERY_MANIFEST'],r['AB_RECOVERY_DEPENDENCIES'],r['AB_RECOVERY_STREAM'],manifest_sha256=r['AB_RECOVERY_MANIFEST_SHA256'],dependency_sha256=r['AB_RECOVERY_DEPENDENCY_SHA256'],stream_sha256=r['AB_RECOVERY_STREAM_SHA256'],deadline=budget.deadline)
            self.handle = collector(self.root,self.legacy,routing=True,
                                    retirement=self.retirement,generation_bytes=self.threshold,fresh_b=self.fresh_b,aggregate_bytes=self.aggregate_bytes,
                                    migration_budget=budget,recovery=recovery)
        else:
            self.handle = worker(self.root,self.legacy,routing=True,role=role)
        return self.handle

    def connection(self):
        if self.handle is None:
            raise RuntimeError('storage runtime not started')
        return self.handle.connection()

    def read_connection(self):
        if self.handle is None:
            raise RuntimeError('storage runtime not started')
        return self.handle.worker_connection('history')

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def retire_verified(self,cloud,now):
        """Separate lifecycle capability. It never owns the collector lock."""
        if not self.retirement:
            return {'status':'disabled'}
        from application_store import RetirementProtocol
        from raw_generations import Stop
        actor = RetirementProtocol(self.root,self.legacy)
        outcomes = {}
        progress={}
        try:
            pending = actor.core.execute(
                "SELECT id FROM generations WHERE state IN ('sealed','draining','retiring') ORDER BY started"
            ).fetchall()
            if len(pending)>2:
                raise RuntimeError('generation registry exceeds two slots')
            for (gid,) in pending:
                try:
                    if self.verify_objects:
                        from incremental_retirement import step
                        progress[gid]=step(actor,gid,cloud,now,max_objects=self.verify_objects,max_age=self.verify_age)
                        outcomes[gid]=progress[gid]['status']
                    else:
                        actor.retire(gid,cloud,now)
                        outcomes[gid] = 'retired'
                except Stop as error:
                    # Holds are finite, visible, and revisited by the next
                    # lifecycle poll. Verification exceptions propagate.
                    outcomes[gid] = str(error)
            return {'status':'held' if any(value!='retired' for value in outcomes.values()) else 'ok',
                    'generations':outcomes, 'verification_progress':progress}
        finally:
            actor.close()
