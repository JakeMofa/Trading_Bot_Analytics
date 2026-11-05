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
    return StorageRuntime(root,legacy,size,enabled(env.get('ENABLE_AB_RETIREMENT','false')))


def adapter_modules():
    directory = Path(__file__).resolve().parents[1]/'prototype'
    if str(directory) not in sys.path:
        sys.path.insert(0,str(directory))
    from application_store import ApplicationStore, ApplicationWorker
    return ApplicationStore, ApplicationWorker


class StorageRuntime:
    def __init__(self,root,legacy,threshold,retirement=False):
        self.root = Path(root)
        self.legacy = Path(legacy)
        self.threshold = threshold
        self.retirement = retirement
        self.handle = None

    @property
    def database(self):
        return str(self.root/'core.db')

    def open(self,role):
        if self.handle is not None:
            raise RuntimeError('storage runtime already opened')
        collector, worker = adapter_modules()
        if role == 'collector':
            self.handle = collector(self.root,self.legacy,routing=True,
                                    retirement=self.retirement,generation_bytes=self.threshold)
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
        try:
            pending = actor.core.execute(
                "SELECT id FROM generations WHERE state IN ('sealed','draining','retiring') ORDER BY started"
            ).fetchall()
            if len(pending)>2:
                raise RuntimeError('generation registry exceeds two slots')
            for (gid,) in pending:
                try:
                    actor.retire(gid,cloud,now)
                    outcomes[gid] = 'retired'
                except Stop as error:
                    # Holds are finite, visible, and revisited by the next
                    # lifecycle poll. Verification exceptions propagate.
                    outcomes[gid] = str(error)
            return {'status':'held' if any(value!='retired' for value in outcomes.values()) else 'ok',
                    'generations':outcomes}
        finally:
            actor.close()
