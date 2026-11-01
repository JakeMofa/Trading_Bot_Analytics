"""Whitelist-only transport evidence and Actions summary. No raw log artifacts."""
import json
import os
from pathlib import Path
import re
import sys

STATES={'STOP','FAIL','PASS','DEPLOYED_SMOKE_TESTED','MANUAL_ACTION_REQUIRED','deployed_pending_acceptance'}
NUMBERS=('other_seconds','verification_seconds','interruption_upper_seconds','physical_mib','headroom_mib')
def sanitize(value):
    result={}
    status=value.get('status',value.get('deployment'))
    if status in STATES:result['status']=status
    for name in ('release','old','NEW_REVISION','OLD_REVISION'):
        v=value.get(name)
        if isinstance(v,str) and re.fullmatch('[0-9a-f]{40}',v):result[name]=v
    for name in NUMBERS:
        if type(value.get(name)) in (int,float):result[name]=value[name]
    for name in ('multi_cycle_acceptance','boundary_acceptance','helper_restoration'):
        if value.get(name) in ('NOT_PERFORMED','PASS','FAILED'):result[name]=value[name]
    for name in ('allocation','smoke'):
        if isinstance(value.get(name),dict):result[name]=sanitize(value[name])
    checks=value.get('checks',{})
    if isinstance(checks,dict):checks=checks.get('checks',[])
    if isinstance(checks,list):
        result['checks']=[{'check':c['check'],'status':c.get('status')} for c in checks
            if isinstance(c,dict) and c.get('check') in ('quick_check','foreign_key_check') and c.get('status') in STATES]
    return result

def main():
    records=[]
    for line in sys.stdin:
        if len(line)>2*1024*1024:continue
        try:value=json.loads(line)
        except ValueError:continue
        if isinstance(value,dict):
            record=sanitize(value)
            if record.get('status'):records.append(record);print(json.dumps(record),flush=True)
    path=Path(os.environ['RUNNER_TEMP'])/'release-evidence.jsonl'
    path.write_text(''.join(json.dumps(r)+'\n' for r in records))
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
        stream.write('## Tradebot controlled release\n\n')
        stream.write('Authoritative roadmap: [INTELLIGENCE_REBUILD_PLAN.md](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/codex/phase1-75-retention-enable/docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).\n\n')
        stream.write('Last reported state: **'+(records[-1]['status'] if records else 'NO SANITIZED REPORT')+'**.\n\n')
        stream.write('A smoke pass is not multi-cycle or real-boundary acceptance. See sanitized artifact; no raw logs or database attached.\n')
    if not records:raise SystemExit(1)
if __name__=='__main__':main()
