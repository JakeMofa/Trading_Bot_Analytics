"""Fixed representative-shape resource proposal, never an execution permission.

No fixtures are created here. The current 2GiB/170s/180s qualification is unchanged.
Cardinalities below are stress assumptions, NOT inferred from sparse legacy IDs.
"""
import math
GIB=1024**3
SPEC={
 'observations':720000,'stream_events':12200000,
 'observation_payload_lengths':(732,7408,7411,7475,7830),
 'stream_payload_lengths':(435,436,437),
 'legacy_main_bytes':5323907072,'legacy_wal_bytes':45178880,
 'simulated_hours':144,'core_bytes_per_raw_identity_assumption':512,
 'structured_evidence_allowance_bytes':2*GIB,
 'index_fraction_assumption':1.0,'aggregate_wal_allowance_bytes':GIB,
 'TEMP_archive_allowance_bytes':2*GIB,'recovery_allowance_bytes':GIB,
 'requested_workspace_bytes':40*GIB,'filesystem_free_floor_bytes':10*GIB,
 'requested_wall_seconds':48*3600,'per_process_as_bytes':512*1024**2,
 'max_processes':3,'required_host_available_memory_bytes':2048*1024**2,
 'core_feature_snapshot_target':18289,'prediction_target':27743,
 'legacy_markets_target':1826,'direct_reference_rows_target':20,'direct_reference_observation_targets':8,
 'embedded_reference_cardinality':'UNKNOWN_DO_NOT_FABRICATE',
}
def plan(spec=SPEC):
    # Largest fixed shape, rather than an average of a tiny recent sample.
    raw=spec['observations']*max(spec['observation_payload_lengths'])+spec['stream_events']*max(spec['stream_payload_lengths'])
    ledger=(spec['observations']+spec['stream_events'])*spec['core_bytes_per_raw_identity_assumption']
    parts={'legacy':spec['legacy_main_bytes']+spec['legacy_wal_bytes'],
           'raw_payload':raw,'raw_indexes_assumed':math.ceil(raw*spec['index_fraction_assumption']),
           'core_ledger_assumed':ledger,'structured_evidence':spec['structured_evidence_allowance_bytes'],
           'aggregate_WAL':spec['aggregate_wal_allowance_bytes'],'TEMP_archive':spec['TEMP_archive_allowance_bytes'],
           'recovery':spec['recovery_allowance_bytes']}
    return {'result':'NOT_PROVEN','spec':spec,'parts_bytes':parts,'total_assumed_bytes':sum(parts.values()),
            'current_2GiB_limit_cannot_fit':raw>2*GIB,'proposed_workspace_fits_assumptions':sum(parts.values())<=spec['requested_workspace_bytes'],
            'normal_production_ceiling':None,'migration_production_ceiling':None,
            'holds':['resource amendment unapproved','host free-space/memory prerequisite',
                     'exact raw and embedded-reference cardinality unknown','rate/burst and ledger assumptions unqualified']}
if __name__=='__main__':
    import json
    print(json.dumps(plan(),indent=2))
