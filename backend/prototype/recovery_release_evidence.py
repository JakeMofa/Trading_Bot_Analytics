"""Allowlisted release attestation. Exact private manifest remains unchanged.

No machine paths, inode/device IDs, row identities, raw bodies or dependencies are
published. Checksums bind the private originals without treating sanitization as
source authentication or production authorization.
"""
import hashlib,json,re,math
from pathlib import Path
from raw_generations import canonical,digest

def attestation(manifest_file,expected_file_sha,qualification_file,expected_qualification_sha):
    raw=Path(manifest_file).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_file_sha:raise ValueError('exact recovery manifest checksum mismatch')
    m=json.loads(raw)
    if digest({k:v for k,v in m.items() if k!='manifest_sha256'})!=m['manifest_sha256']:raise ValueError('manifest canonical checksum mismatch')
    if m.get('format')!='AB72_SELECTED_RECOVERY_V1' or m.get('source_integrity')!='ok' or m.get('source_fk_violations')!=0:raise ValueError('source verification not proven')
    proof_raw=Path(qualification_file).read_bytes()
    if hashlib.sha256(proof_raw).hexdigest()!=expected_qualification_sha:raise ValueError('qualification checksum mismatch')
    q=json.loads(proof_raw)
    if (q.get('status')!='PASS_ISOLATED_SELECTED_RECOVERY' or q.get('manifest_file_sha256')!=expected_file_sha or q.get('manifest_sha256')!=m['manifest_sha256']
        or q.get('production_authorized') is not False or q.get('conflicts')!=0 or q.get('unverifiable_rows')!=0
        or q.get('first_stage',{}).get('synchronous')!=2 or q.get('retry_stage',{}).get('changed_rows')!=0):raise ValueError('stage verification not proven')
    if q.get('observations')!=m['observations'] or q.get('stream_events')!=m['stream_events']:raise ValueError('stage selection mismatch')
    catalog=m['records']
    if digest(catalog)!=m['selection_sha256'] or len(catalog)!=m['observations']+m['stream_events']:raise ValueError('selected catalog checksum/count mismatch')
    result={'format':'AB72_SANITIZED_RECOVERY_ATTESTATION_V1','exact_private_manifest_file_sha256':expected_file_sha,
            'production_authorized':False,'historical_origin_attestation':'NOT_PROVEN',
            'qualification_report_sha256':expected_qualification_sha,
            'allocation_coverage':'sampled named inputs/export/stage; anonymous TEMP NOT PROVEN',
            'excluded':['machine paths','device/inode bindings','per-row identities','raw bodies','dependency rows'],
            'verified_checks':['source integrity','source foreign keys','legacy schema/primary identities','selected row provenance','protected reference consistency','staged integrity/foreign keys','FULL durability','zero-change retry']}
    for name in ('source_sha256','source_schema_sha256','dependency_sha256','manifest_sha256','selection_sha256'):
        if not re.fullmatch('[0-9a-f]{64}',m[name]):raise ValueError('malformed evidence hash')
        result[name]=m[name]
    for name in ('observations','stream_events','supporting_markets','snapshot_dependencies','prediction_dependencies','selected_serialized_bytes'):
        if type(m[name]) is not int or m[name]<0:raise ValueError('malformed evidence count')
        result[name]=m[name]
    result['stage']={k:q[k] for k in ('status','elapsed_seconds','aggregate_peak_bytes','rss_bytes','linux_memory_limit_applied')}
    for k in ('elapsed_seconds','aggregate_peak_bytes','rss_bytes'):
        if not isinstance(q[k],(int,float)) or not math.isfinite(q[k]) or q[k]<0:raise ValueError('malformed measurement')
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True);p.add_argument('--expected-sha256',required=True);p.add_argument('--qualification',required=True);p.add_argument('--expected-qualification-sha256',required=True);a=p.parse_args()
    print(json.dumps(attestation(a.manifest,a.expected_sha256,a.qualification,a.expected_qualification_sha256),sort_keys=True,indent=2))
