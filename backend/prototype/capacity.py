"""Explicit preliminary aggregate budgets; never changes a runtime guard."""
import math
GIB=1024**3;MIB=1024**2

def proposal(legacy_main,legacy_wal,filesystem_free,profile):
    # Budget caps, not claims that the production core or WAL have been measured.
    core=math.ceil(legacy_main/GIB)*GIB
    raw=20*1024*144*3600
    sample_wal=max(profile.get('wal_peak_bytes',{}).values(),default=0)
    all_wal=math.ceil(3*max(legacy_wal,sample_wal)/MIB)*MIB
    # Three independently recoverable DB roles; empirical allowance, not a bound.
    recovery=math.ceil(3*max(legacy_wal,profile.get('allocation_before_retirement',{}).get('peak_bytes',0))/MIB)*MIB
    temporary=2*GIB # existing generated whole-workspace ceiling, proposed FS allowance
    normal=math.ceil((core+raw+all_wal+recovery)/GIB)*GIB
    migration=math.ceil((core+raw+all_wal+recovery+legacy_main+legacy_wal)/GIB)*GIB
    projected_free=filesystem_free-max(0,migration-(legacy_main+legacy_wal))-temporary
    return {'result':'NOT_PROVEN','normal_ceiling_bytes':normal,'migration_ceiling_bytes':migration,
        'components':{'core_budget_cap_bytes':core,'raw_144h_estimate_bytes':raw,'aggregate_wal_allowance_bytes':all_wal,
            'recovery_allowance_bytes':recovery,'retained_legacy_bytes':legacy_main+legacy_wal,
            'archive_TEMP_filesystem_allowance_bytes':temporary,'filesystem_free_floor_bytes':10*GIB},
        'projected_filesystem_free_bytes':projected_free,'filesystem_arithmetic_pass':projected_free>=10*GIB,
        'migration_expiry_hours_after_cutover':96,'review_hours_after_cutover':72,
        'blocked_retirement_extra_raw_slots':0,'guard_action_if_slots_or_quotas_block':'STOP; no queue or automatic increase',
        'not_proven':['production core/identity-ledger/protected-evidence shape and growth','daily raw+index rate and bursts',
            'full-scale per-file and aggregate peak WAL','full-scale TEMP/verification/recovery peak',
            'production legacy/feature/archive adapter qualification'],
        'basis':'20KiB/s whole-DB planning estimate applied to raw+indexes; core cap derived from measured whole legacy main; WAL/recovery allowances empirical'}
