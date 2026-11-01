"""Offline analysis of opt-in Linux strace6.8 generated fixture diagnostics.

Fails closed on ambiguous locks or missing syscall exits. Not production telemetry.
"""
import re,json,ast,pathlib,sys
p=pathlib.Path(sys.argv[1])
events=[];pending={};markers=[]
for n,line in enumerate((p/'trace.txt').read_text().splitlines(),1):
 m=re.match(r'(\d+)\s+(\d+\.\d+)\s+(.*)',line)
 if not m:continue
 pid,t,body=int(m[1]),float(m[2]),m[3]
 if '<unfinished ...>' in body:
  assert pid not in pending
  pending[pid]=(t,body.replace(' <unfinished ...>',''),n);continue
 if body.startswith('<... '):
  a=pending.pop(pid);start,first,ln=a
  body=first+body.split('resumed>',1)[1];end_observed=t;t=start;n=ln
 else:end_observed=t
 d=re.search(r'<([\d.]+)>$',body)
 if not d:continue
 end=max(t+float(d[1]),end_observed)
 if not (body.startswith(('fcntl(', 'fdatasync(', 'fsync(', 'pwrite64(')) or 'LOCKDIAG' in body):continue
 body=re.sub(r'(pwrite64\([^,]+, )"(?:[^"\\]|\\.)*"',r'\1"<generated payload omitted>"',body)
 e={'pid':pid,'start':t,'end':end,'body':body,'line':n,'duration':float(d[1])};events.append(e)
 if 'LOCKDIAG' in body:
  q=re.search(r'write\(2.*?, ("(?:[^"\\]|\\.)*")',body)
  if q:
   v=json.loads(ast.literal_eval(q[1]).split('LOCKDIAG ',1)[1]);v['trace_line']=n;markers.append(v)
assert not pending,pending
rows=[]
for mark in markers:
 if mark['event']!='begin_entry':continue
 pid=mark['pid'];start=mark['real_ns']/1e9
 ce=next((x for x in markers if x['pid']==pid and x['event']=='commit_entry' and x['real_ns']>mark['real_ns']),None)
 if ce is None:continue
 cr=next((x for x in markers if x['pid']==pid and x['event']=='commit_return' and x['real_ns']>ce['real_ns']),None)
 if cr is None:continue
 finish=cr['real_ns']/1e9;entry=ce['real_ns']/1e9
 def islock(x,kind):return x['pid']==pid and 'fixture.db-shm>' in x['body'] and 'F_SETLK,' in x['body'] and 'l_start=120, l_len=1' in x['body'] and 'l_type='+kind in x['body'] and ') = 0 ' in x['body']
 acq=[x for x in events if start<=x['start']<=entry and islock(x,'F_WRLCK')];assert len(acq)==1,len(acq)
 rel=[x for x in events if entry<=x['start']<=finish and islock(x,'F_UNLCK')];assert len(rel)==1,len(rel)
 a,u=acq[0],rel[0]
 inside=[x for x in events if x['pid']==pid and entry<=x['start']<=finish]
 def ops(segment,name,file):return [x for x in segment if x['body'].startswith(name+'(') and file in x['body']]
 before=[x for x in inside if x['end']<=u['start']];after=[x for x in inside if x['start']>=u['end']]
 collector_locks=[x for x in events if x['pid']!=pid and 'fixture.db-shm>' in x['body'] and 'l_start=120, l_len=1' in x['body'] and 'l_type=F_WRLCK' in x['body'] and x['start']>=u['end'] and x['end']<finish and ') = 0 ' in x['body']]
 rows.append({'batch':len(rows)+1,'pid':pid,'commit_entry':entry,'commit_return':finish,'commit_ms':(cr['mono_ns']-ce['mono_ns'])/1e6,'lock_hold_lower_ms':(u['start']-a['end'])*1000,'lock_hold_upper_ms':(u['end']-a['start'])*1000,'commit_before_release_ms':(u['end']-entry)*1000,'post_release_ms':(finish-u['end'])*1000,'acquire':a,'release':u,'before_wal_writes':len(ops(before,'pwrite64','fixture.db-wal>')),'before_wal_syncs':ops(before,'fdatasync','fixture.db-wal>'),'after_wal_syncs':ops(after,'fdatasync','fixture.db-wal>'),'after_db_writes':len(ops(after,'pwrite64','fixture.db>')),'after_db_syncs':ops(after,'fdatasync','fixture.db>'),'collector_acquisitions_before_commit_return':collector_locks})
report=json.loads((p/'stdout.jsonl').read_text().splitlines()[0])
assert rows, 'no completed lock intervals'
# The indexed harness has exactly one explicit setup BEGIN before the actor.
# Require the indexed profile; first BEGIN is setup, not retention.
assert report['timestamp_engine']=='indexed_invalid_v1'
rows=rows[1:]
for i,x in enumerate(rows,1):x['batch']=i
assert rows, 'no completed retention lock intervals'
result={'method':'strace syscall entry/exit brackets; includes tracing overhead','historical_failure_reclassified':False,'batch_count':len(rows),'slowest':max(rows,key=lambda x:x['commit_ms']),'checkpoint_batches':[x for x in rows if x['after_db_writes']],'max_lock_hold_upper_ms':max(x['lock_hold_upper_ms'] for x in rows),'collector':report['collector'],'elapsed_seconds':report['elapsed_seconds'],'production_guard_errors':report['production_guard_errors'],'all_batches':rows}
(p/'analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('all_batches','checkpoint_batches')},indent=2))
print('checkpoint summaries',json.dumps([{k:x[k] for k in ('batch','commit_ms','lock_hold_upper_ms','commit_before_release_ms','post_release_ms','after_db_writes','after_db_syncs','collector_acquisitions_before_commit_return')} for x in result['checkpoint_batches']],indent=2))
