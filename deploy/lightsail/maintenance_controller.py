"""Single-attempt quiescent release state machine; effects supplied by tested host.

No concurrent-write proof reuse. No data restoration, cleanup or WAL operations.
Budgets begin once and never reset between verification/deployment/recovery.
"""
import time
import os
from pathlib import Path

WRITERS=('tradebot-api','tradebot-ensemble','tradebot-lifecycle')
OTHER=600; VERIFY=1800; REAP=10; RECOVERY=180; INTERRUPTION=2590
MIN_HEADROOM_MIB=128 # user-approved one-use pinned rollover maintenance only

class Stop(RuntimeError):pass


def run(host, clock=time.monotonic, *, generated_transition=False):
    report={'status':'STOP','changed':False,'stop_requested':[],'recovery_failures':[],
            'multi_cycle_acceptance':'NOT_PERFORMED','boundary_acceptance':'NOT_PERFORMED'}
    first=None;other=0.;verify=0.;old=None;states=None;monitor=None;recovery_end=None
    transition_intent=False
    def left(kind):
        limit=(VERIFY-verify) if kind=='verify' else (OTHER-other)
        if first is not None:limit=min(limit,first+INTERRUPTION-clock()-RECOVERY-REAP)
        if limit<=0:raise Stop('work/recovery reservation exhausted')
        return limit
    def work(kind,fn,*args):
        nonlocal other,verify
        budget=left(kind);at=clock()
        report.setdefault('events',[]).append({'phase':getattr(fn,'__name__','operation'),'at':host.utcnow()})
        try:return fn(*args,budget)
        finally:
            elapsed=clock()-at
            if kind=='verify':verify+=elapsed
            else:other+=elapsed
            if elapsed>budget:raise Stop('operation exceeded reserved budget')
    try:
        # Must not stop anything unless exact CI/helper/runtime/flags/disk match.
        if generated_transition:
            root=Path(host.generated_root)
            if (root.is_symlink() or not root.is_dir() or not root.name.startswith('generated-ab-')
                or root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077
                or Path('/opt/tradebot')==root.resolve() or Path('/opt/tradebot') in root.resolve().parents):
                raise Stop('generated transition only; no production route')
            # Start before preflight/preparation; never hide these costs.
            first=clock();report['operation_started_at']=host.utcnow()
        at=clock()
        states,old=host.preflight();report['old']=old
        if generated_transition:
            other+=clock()-at;left('other')
        monitor={'restoration_intent':True}
        monitor=work('other',host.pause_monitor)
        for unit in WRITERS:
            if (states or {}).get(unit)=='active':
                if first is None:first=clock();report['first_writer_stop_at']=host.utcnow()
                report['stop_requested'].append(unit) # intent before possibly partial stop
                work('other',host.stop,unit)
        work('other',host.require_quiescence)
        allocation=work('other',host.allocation)
        report['allocation']=allocation
        reserve=512 if generated_transition else MIN_HEADROOM_MIB
        if allocation['headroom_mib']<reserve:raise Stop('physical headroom below'+str(reserve)+'MiB')
        binding=work('other',host.identity)
        report['checks']=work('verify',host.verify,REAP)
        if report['checks'].get('status')!='PASS':raise Stop('complete verification failed')
        if work('other',host.identity)!=binding:raise Stop('verification binding changed')
        work('other',host.require_quiescence)
        report['changed']=True # partial checkout requires rollback too
        if generated_transition:
            transition_intent=True;report['forward_recovery_required']=True
        work('other',host.checkout_release)
        for unit in WRITERS:
            if (states or {}).get(unit)=='active':work('other',host.start,unit)
        if monitor is not None:work('other',host.restore_monitor,monitor);monitor=None
        report['smoke']=work('other',host.smoke)
        if report['smoke'].get('status')!='PASS':raise Stop('functional smoke failed')
        report['status']='GENERATED_TRANSITION_SMOKE_TESTED' if generated_transition else 'DEPLOYED_SMOKE_TESTED'
    except BaseException as error:
        report['failure_type']=type(error).__name__
        if isinstance(error,Stop) or type(error).__name__=='Stop':report['reason']=str(error)
        if first is not None:
            end=min(first+INTERRUPTION,clock()+RECOVERY);recovery_end=end
            def recover(fn,*args):
                remaining=end-clock()
                if remaining<=0:raise Stop('absolute recovery deadline')
                return fn(*args,remaining)
            # Reap owned verification before recovery; never signal unknown owners.
            try:recover(host.reap_owned_child)
            except BaseException as failure:report['recovery_failures'].append(['child',type(failure).__name__])
            safe=not report['recovery_failures']
            if generated_transition and transition_intent:
                # Cutover may have committed before throwing. Never infer that
                # a failed call means no durable new writes. Freeze all roles.
                for unit in WRITERS:
                    try:recover(host.stop,unit)
                    except BaseException as failure:report['recovery_failures'].append([unit+':forward-stop',type(failure).__name__])
                report['recovery_action']='PRESERVE_FILES_RECOVER_FORWARD'
                safe=False
            if report['changed'] and safe:
                for unit in WRITERS:
                    if (states or {}).get(unit)=='active':
                        try:recover(host.stop,unit)
                        except BaseException as failure:
                            safe=False;report['recovery_failures'].append([unit+':rollback-stop',type(failure).__name__])
                if safe:
                    try:recover(host.checkout_old,old)
                    except BaseException as failure:report['recovery_failures'].append(['code',type(failure).__name__])
            for unit in WRITERS:
                if (states or {}).get(unit)=='active':
                    if generated_transition:
                        report['recovery_action']='PRESERVE_STOPPED_STATE_RECOVER_FORWARD' if transition_intent else 'PRESERVE_STOPPED_STATE'
                        continue
                    if any(x[0]=='child' for x in report['recovery_failures']):
                        report['recovery_failures'].append([unit,'blocked_by_unreaped_child']);continue
                    try:recover(host.start,unit)
                    except BaseException as failure:report['recovery_failures'].append([unit,type(failure).__name__])
        if monitor is not None:
            try:host.restore_monitor(monitor,max(.001,min(30,(recovery_end-clock()) if recovery_end else OTHER-other)))
            except BaseException as failure:report['recovery_failures'].append(['monitor',type(failure).__name__])
        report['status']='MANUAL_ACTION_REQUIRED' if report['recovery_failures'] else 'STOP'
    finally:
        report['other_seconds']=other;report['verification_seconds']=verify
        report['interruption_upper_seconds']=clock()-first if first is not None else 0
        if report['interruption_upper_seconds']>INTERRUPTION:report['status']='MANUAL_ACTION_REQUIRED'
        host.save(report)
    return report
