"""Disposable local PG17 matched canonical-byte reuse proof; never accepts a DSN.

Creates generated-only database/schema, compares pinned 0219819 baseline and
current source, then stops its own local server in finally. No hosted operations.
"""
from pathlib import Path
from contextlib import contextmanager
import socket,select,threading,time,tempfile,subprocess,getpass,os,sys,json,inspect,statistics,uuid,types
from datetime import datetime,timezone
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.history_v2_envelope import TABLE_KEYS
from postgres.archive_codec import encoded,sha256,ArchiveIntegrityError,ArchiveLimit

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bin-dir',type=Path,default=Path('/opt/homebrew/opt/postgresql@17/bin'))
args=parser.parse_args()
base=Path(tempfile.mkdtemp(prefix='tradebot-canonical-reuse-',dir='/tmp'));pg=str(args.bin_dir.resolve())+'/'
server_socket=socket.socket();server_socket.bind(('127.0.0.1',0));server_port=server_socket.getsockname()[1];server_socket.close()
subprocess.run([pg+'initdb','-D',str(base/'data'),'-A','trust','--no-locale','-E','UTF8'],check=True,stdout=subprocess.DEVNULL)
subprocess.run([pg+'pg_ctl','-D',str(base/'data'),'-l',str(base/'server.log'),'-o',f'-k {base} -h 127.0.0.1 -p {server_port}','-w','start'],check=True,stdout=subprocess.DEVNULL)
proxy=None;result={}
try:
 subprocess.run([pg+'createdb','-h',str(base),'-p',str(server_port),'tradebot_cold_perf'],check=True)
 direct=f'host={base} port={server_port} dbname=tradebot_cold_perf user={getpass.getuser()} sslmode=disable'
 with psycopg.connect(direct,row_factory=dict_row) as db:
  for role in ('anon','authenticated','service_role','tradebot_pp_history'):db.execute(f'CREATE ROLE {role} NOLOGIN')
  for file in ('backend/postgres/history_v2_contract.sql','supabase/migrations/20261118012340_structured_receipts_v2.sql','supabase/migrations/20261119020000_pp_structured_revision_payloads.sql'):db.execute((ROOT/file).read_text())
  identity=db.execute('SELECT current_database() db,current_user role').fetchone()
  bytea_output=db.execute('SHOW bytea_output').fetchone()['bytea_output']
 origin='pp-live-pp';generation='00000000-0000-4000-8000-000000000019';records=[]
 for i in range(1,501):
  payload=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',granularity=60,time=1795000000+i*60,
   low='100.00000000000000000001',high='101.23000000000000000009',open='100.4500',close='100.6700',volume='1E-9',
   first_seen='2026-11-19T10:00:00+00:00',payload={'generated_only':True,'source_time':'2026-11-19T09:59:59.123456789+00:00',
    'available_at':'2026-11-19T10:00:00+00:00','unavailable':None,'levels':[{'price':f'100.{n:08d}','size':'0.00000001'} for n in range(12)],
    'indicators':{'volatility':'0.0000000000123','missing_flow':None},'source_note':('generated research evidence '+str(i)+'|')*80})
  payload['content_hash']=sha256(encoded(payload))
  records.append(dict(id=i,origin_id=origin,generation_id=generation,entity_type='core.candles',
   entity_id=encoded([payload[k] for k in TABLE_KEYS['core.candles']]).decode(),content_hash=payload['content_hash'],payload=payload))
 # One mutable key in the 500-row page permits a separately measured G=1
 # newer-generation reconstruction without changing the base page size.
 def price_record(index,gen,stamp,price):
  payload=dict(origin_id=origin,source='coinbase',symbol='BTC-USD',event_id=f'generated-tick-{index}',generation_id=gen,
   source_time=stamp,source_epoch=str(int(datetime.fromisoformat(stamp).timestamp())),received_at=stamp,available_at=stamp,
   price=price,size='1E-9',payload=records[-1]['payload']['payload'])
  payload['content_hash']=sha256(encoded(payload))
  return dict(id=index,origin_id=origin,generation_id=gen,entity_type='core.current_prices',entity_id=encoded([payload[k] for k in TABLE_KEYS['core.current_prices']]).decode(),content_hash=payload['content_hash'],payload=payload)
 records[-1]=price_record(500,generation,'2026-11-19T10:00:00+00:00','100.6700')
 plain=lambda **_:psycopg.connect(direct,row_factory=dict_row,prepare_threshold=None)
 seed=HistoryV2PostgresTransport(plain,origin_id=origin,generation_id=generation,expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True)
 seed.put_structured(records,timeout_seconds=60)
 with psycopg.connect(direct) as db:db.execute('ANALYZE')
 expected=encoded(records);assert len(expected)<4*1024**2
 with psycopg.connect(direct,autocommit=True) as db:db.execute((ROOT/'supabase/migrations/20261119103056_pp_receipt_latest_identity_index.sql').read_text())

 from postgres.retirement_accounting import Accounting,_ACTIVE
 baseline_source=subprocess.check_output(['git','show','0219819:backend/postgres/history_v2_transport.py'],cwd=ROOT,text=True)
 baseline_module=types.ModuleType('postgres._canonical_benchmark_baseline');baseline_module.__package__='postgres'
 exec(compile(baseline_source,'<0219819-baseline>','exec'),baseline_module.__dict__)
 variants={'baseline':baseline_module.HistoryV2PostgresTransport,'candidate':HistoryV2PostgresTransport}
 samples=[]
 def measure(name,group,pair):
  transport=variants[name](plain,origin_id=origin,generation_id=generation,expected_database=identity['db'],expected_role=identity['role'],indexed_latest=True)
  accounting=Accounting();token=_ACTIVE.set(accounting);began=time.perf_counter()
  try:returned,size=transport.read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4)
  finally:_ACTIVE.reset(token)
  elapsed=time.perf_counter()-began
  assert encoded(returned)==expected
  stats=dict(variant=name,newer_generations=group,pair=pair,seconds=elapsed,canonical_sha256=sha256(encoded(returned)),authenticated_size=size,phases=accounting.snapshot()['phases'])
  samples.append(stats)
  print(name,'G',group,'pair',pair,round(elapsed,6),flush=True)
 for group in (0,1):
  if group:
   newer_generation='00000000-0000-4000-8000-000000000020'
   newer=price_record(501,newer_generation,'2026-11-19T10:00:01+00:00','100.6800')
   HistoryV2PostgresTransport(plain,origin_id=origin,generation_id=newer_generation,expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True).put_structured([newer],timeout_seconds=4)
   with psycopg.connect(direct) as db:db.execute('ANALYZE')
  for pair in range(1,9):
   for name in (('baseline','candidate') if pair%2 else ('candidate','baseline')):measure(name,group,pair)
 guards=[]
 for name,cls in variants.items():
  def make(gen=generation,role=identity['role']):return cls(plain,origin_id=origin,generation_id=gen,expected_database=identity['db'],expected_role=role,indexed_latest=True)
  def must_fail(label,call,error):
   try:call()
   except error:guards.append(dict(variant=name,guard=label,passed=True))
   else:raise AssertionError(name+' '+label+' did not hold')
  must_fail('bounded_envelope_suppression',lambda:make().read_revisions(list(range(1,501)),max_bytes=1000,timeout_seconds=4),ArchiveLimit)
  must_fail('wrong_generation',lambda:make('00000000-0000-4000-8000-000000000021').read_revisions([1],max_bytes=4096,timeout_seconds=4),ArchiveIntegrityError)
  must_fail('wrong_role_identity',lambda:make(role='wrong_role').read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  bad=[dict(r) for r in records];bad[0]={**bad[0],'origin_id':'production'}
  must_fail('cross_origin_expected_page',lambda:make().read_retirement_revisions(bad,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  bad=[dict(r) for r in records];bad[0]={**bad[0],'payload':{**bad[0]['payload'],'close':'100.6800'}}
  must_fail('canonical_expected_bytes_mismatch',lambda:make().read_retirement_revisions(bad,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  for column in ('payload_hash','envelope_hash','content_hash'):
   with psycopg.connect(direct) as db:
    original=db.execute('SELECT '+column+' FROM history_v2.structured_receipts WHERE outbox_id=1').fetchone()[0]
    db.execute('UPDATE history_v2.structured_receipts SET '+column+'=%s WHERE outbox_id=1',('b'*64,))
   must_fail('corrupt_receipt_'+column,lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
   with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_receipts SET '+column+'=%s WHERE outbox_id=1',(original,))
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_revision_payloads SET envelope=%s WHERE outbox_id=1',(encoded(records[0])+b' ',))
  must_fail('noncanonical_envelope',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_revision_payloads SET envelope=%s WHERE outbox_id=1',(encoded(records[0]),))
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.current_prices SET price=100.01 WHERE origin_id=%s',(origin,))
  must_fail('corrupt_newer_current_projection',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.current_prices SET price=%s WHERE origin_id=%s',(newer['payload']['price'],origin))
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_receipts SET envelope_hash=%s WHERE outbox_id=501',('b'*64,))
  must_fail('corrupt_newer_envelope_receipt',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_receipts SET envelope_hash=%s WHERE outbox_id=501',(sha256(encoded(newer)),))
 summary={}
 for group in (0,1):
  summary[str(group)]={}
  for name in variants:
   rows=[s['seconds'] for s in samples if s['variant']==name and s['newer_generations']==group]
   summary[str(group)][name]=dict(mean_seconds=statistics.mean(rows),median_seconds=statistics.median(rows),min_seconds=min(rows),max_seconds=max(rows))
 result=dict(scope='generated warmed local PG17 full-path source comparison; no PP/TLS/Supavisor speedup established',baseline_source_sha='0219819',candidate_transport_sha256=sha256((ROOT/'backend/postgres/history_v2_transport.py').read_bytes()),driver=psycopg.__version__,libpq=psycopg.pq.version(),server_version=subprocess.check_output([pg+'postgres','--version'],text=True).strip(),records=500,distinct_projection_keys=500,canonical_page_sha256=sha256(expected),canonical_page_bytes=len(expected),samples=samples,summary=summary,guards=guards,request_timeout_seconds=4,formats='text in both arms',connections='fresh in both arms',indexed_latest=True)
finally:
 if proxy:proxy.close()
 subprocess.run([pg+'pg_ctl','-D',str(base/'data'),'-m','immediate','-w','stop'],check=True,stdout=subprocess.DEVNULL)
 if result:
  target=ROOT/'docs/PLAN/evidence/readback-canonical-byte-reuse-generated-2026-11-19.json';target.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(dict(summary=result['summary'],guard_count=len(result['guards']),output=str(target))),flush=True)
