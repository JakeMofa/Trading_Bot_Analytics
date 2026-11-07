"""Reviewed-budget arithmetic, not runtime settings or production authority."""
import math
GIB=1024**3
MIB=1024**2

def proposal(retained_bytes=5369188352):
    if type(retained_bytes) is not int or retained_bytes<0:raise ValueError('measured retained allocation required')
    parts={'retained_legacy_and_observed_fds':retained_bytes,
           'A_main_WAL_SHM':5*GIB,'B_main_WAL_SHM':5*GIB,
           'core_main_WAL_SHM':4*GIB,'archive_working_and_capsule':GIB,
           'verification_TEMP':GIB//2,'recovery_reserve':GIB}
    total=sum(parts.values());ceiling=24*GIB
    upload=846958.;download=721984.;compressed_per_physical=781446./(2*MIB)
    active=4*GIB;projected_compressed=active*compressed_per_physical
    transfer=projected_compressed/upload+2*projected_compressed/download
    cpu=2*projected_compressed*.050744/623236
    objects=math.ceil(projected_compressed/623236)
    # Proposed 60-second archive cadence; eight second-readback objects/cycle.
    verification_floor=max(projected_compressed/download,math.ceil(objects/8)*60)
    return {'status':'PROPOSAL_NOT_AUTHORITY','production_authorized':False,'parts_bytes':parts,
            'aggregate_bytes':ceiling,'parts_total_bytes':total,'unassigned_margin_bytes':ceiling-total,
            'slot_bytes_include_WAL_and_SHM':True,'core_bytes_include_WAL_and_SHM':True,
            'trigger_bytes':active,'maximum_active_age_seconds':72*3600,'filesystem_free_floor_bytes':10*GIB,
            'full_profile_runtime_supported':False,
            'current_blockers':['64MiB per-slot and 2GiB new-layout limits','100000-event lifetime ledger admission',
                '512MiB physical core and 250000-row/256MiB logical core audit','10000 protected-reference and per-dataset manifest limits',
                'normal-runtime aggregate service accounting and write overrun not qualified',
                'fresh final readback must fit <=8 objects and original 30-second operation; cached checks alone cannot retire',
                '5GiB target unqualified within approved 2GiB generated workspace'],
            'temporary_recovery':{'trigger_bytes':2*MIB,'slot_cap_bytes':64*MIB,'retirement_enabled':False,
                'measured_outage_after_seal_simulated_seconds':61.395,'production_runway_seconds':None,
                'ledger_hours_at_assumed_6_7_events_per_second':100000/6.7/3600,
                'not_required_for_staged_core_recovery':True},
            'extrapolations_not_qualification':{'assumed_physical_ingest_bytes_per_second':32.50*1024,
                'active_window_at_trigger_seconds':active/(32.50*1024),
                'archive_compressed_bytes':projected_compressed,
                'upload_readback_recheck_and_cpu_floor_seconds':transfer+cpu,
                'second_readback_floor_with_8_objects_per_60s_cycle_seconds':verification_floor,
                'B_growth_during_transfer_floor_bytes':(transfer+cpu)*32.50*1024,
                'B_growth_during_verification_scheduling_floor_bytes':verification_floor*32.50*1024,
                'object_count_at_small_probe_size':objects,
                'excludes':['manifest/checkpoint API latency','structured backlog','outages/retries','core growth','reader drain tail','burst/WAL growth']},
            'qualification_resource_gap':{'approved_workspace_bytes':2*GIB,
                'proposed_full_envelope_bytes':total,'workspace_shortfall_bytes':max(0,total-2*GIB),
                'minimum_RAM_for_full_fixture':'NOT_MEASURED','total_runtime_for_full_fixture':'NOT_MEASURED'}}

if __name__=='__main__':
    import json
    print(json.dumps(proposal(),indent=2,sort_keys=True))
