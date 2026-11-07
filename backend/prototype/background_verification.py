"""Generated-only full readback diagnostic. Does NOT authorize retirement.

Separate supervised phase, not a change to the normal lifecycle30s budget.
Each object uses the existing authenticated transport and supported bounded gzip
format validator; the generation is never downloaded/materialized as one body.
"""
import json, math, resource, sys, time
from application_store import RetirementProtocol
from incremental_retirement import initialize, step, catalog
from archive_reads import HardArchiveReads, BoundedArchiveReads
from compatible_cloud import CompatibleCloud
from raw_generations import Stop


def verify_phase(root, legacy, gid, cloud_factory, now, *, deadline):
    """Read-only raw diagnostic plus derived core receipts; hard parent deadline.

    cloud_factory receives each chunk's ORIGINAL deadline and must construct the
    existing CompatibleCloud. No upload/delete method is called. Cancellation
    kills/reaps the phase child. GET runs directly INSIDE that supervised child,
    with no nested GET child left behind; no production lifecycle integration.
    """
    if type(deadline) not in (int,float) or not math.isfinite(deadline):
        raise Stop('invalid full verification deadline')
    if not 0 < deadline-time.monotonic() <= 120:
        raise Stop('full verification diagnostic deadline must fit120s')
    def operation():
        if sys.platform=='linux':
            soft,hard=resource.getrlimit(resource.RLIMIT_AS)
            cap=512*1024**2
            finite=[x for x in (soft,hard,cap) if x!=resource.RLIM_INFINITY]
            cap=min(finite)
            resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
        started=time.monotonic();actor=RetirementProtocol(root,legacy)
        total=objects=cycles=0
        try:
            initialize(actor)
            with actor.core:
                actor.core.execute('DELETE FROM ab_retire_checks WHERE gen=?',(gid,))
            # Bind the full pass, rather than only its last chunk.
            with actor.core:actor.core.execute('INSERT OR IGNORE INTO ab_retire_epoch VALUES(?,0)',(gid,))
            binding=catalog(actor,gid)[0]
            while True:
                if time.monotonic()>=deadline:raise Stop('full verification phase expired')
                chunk_deadline=min(deadline,time.monotonic()+30)
                cloud=cloud_factory(chunk_deadline)
                if not isinstance(cloud,CompatibleCloud) or cloud.deadline!=chunk_deadline:
                    cloud.close();raise Stop('bounded authenticated transport required')
                class Metered:
                    def __init__(self):self.deadline=chunk_deadline
                    def download_bytes(self,bucket,path):
                        nonlocal total,objects
                        body=BoundedArchiveReads(cloud.cloud,chunk_deadline).download_bytes(bucket,path)
                        total+=len(body);objects+=1
                        return body
                try:result=step(actor,gid,Metered(),now,max_objects=1,max_age=300,finalize=False,deadline=chunk_deadline)
                finally:cloud.close()
                cycles+=1
                if catalog(actor,gid)[0]!=binding:raise Stop('generation changed during full verification phase')
                if result['status']=='ready':break
                if not result['objects_checked']:raise Stop('full verification made no progress')
            factor=1 if sys.platform=='darwin' else 1024
            return json.dumps({'status':'VERIFIED_DIAGNOSTIC_ONLY','retirement_authorized':False,
                'seconds':time.monotonic()-started,'objects':objects,'transfer_bytes':total,
                'cycles':cycles,'covered_rows':result['covered_rows'],
                'phase_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*factor,
                'get_child_peak_rss_bytes':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*factor,
                'download_temporary_disk_bytes':0}).encode()
        finally:actor.close()
    return json.loads(HardArchiveReads(None,deadline,max_bytes=16384,operation=operation).download_bytes('unused','unused'))
