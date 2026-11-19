# Cold readback performance: binary result-format investigation

November 19, 2026. Research and generated local measurements only. **No transport,
constructor, environment flag, profile, grant, host, deployment or cloud change.**
The release chat owns implementation and qualification of any optimization.

## Finding and recommendation

Targeting binary results for the bounded revision `bytea` SELECT is a measured
bandwidth opportunity: the generated page used about **48% fewer PostgreSQL
server-to-client stream bytes** for exact revision retrieval and **32% fewer**
for complete structured retirement readback. This does not establish a PP
latency improvement or qualify the 240-second final-work budget. Keep the
existing four-second operation cap.

Prioritize a separately reviewed, default-off **per-query** binary-result
candidate and matched read-only PP comparison of identical reviewed IDs and
canonical hashes. Preserve every receipt, size, identity, deadline and projection
guard. Do not turn on binary results globally or combine it with session reuse
in the first comparison; those have different compatibility and latency effects.
No such source candidate or runtime activation was added here.

## Driver and format evidence

Installed psycopg is **3.2.13**, with libpq **170006**. Its actual
`Connection.execute` signature has keyword-only `binary: bool = False`; the
[pinned official source](https://raw.githubusercontent.com/psycopg/psycopg/3.2.13/psycopg/psycopg/connection.py)
confirms the parameter. [Psycopg documentation](https://www.psycopg.org/psycopg3/docs/basic/params.html#binary-parameters-and-results)
describes binary result selection and warns that every selected type needs a
compatible binary loader. This changes result encoding, independently of the
existing prepared-statement setting.

The fixture reported `bytea_output=hex`. PostgreSQL's text output uses two hex
digits for each byte, plus a prefix; binary output avoids that expansion.
[PostgreSQL 17 bytea formats](https://www.postgresql.org/docs/17/datatype-binary.html)
The experiment changed only the revision SELECT's result format in an ephemeral
wrapper. All nine candidate columns reported format zero for text and one for
binary; their OIDs were bigint 20, bytea 17 and text 25. Slight integer-format
size differences also contribute to the measured totals.

The candidate CASE expressions can strip domains. Therefore the old deployed
query was separately checked: exact source `74a850b` was loaded into an ephemeral
module and executed with both formats through full G=1 structured readback.
Its eight columns, including directly selected domain hash fields, were exposed
by this native server as OIDs `[20,20,17,25,25,25,25,25]`; both modes returned
all 500 original envelopes with the same hash. This is a **native PG17.2 / driver
3.2.13 codec result**, not proof for live PP's server/pooler configuration.

## Fixture, method and exact identities

- Native PostgreSQL **17.2 Homebrew**, generated private schema only, loopback
  connections, trusted local fixture login, no TLS or cloud credentials.
- 500 rich canonical envelopes: **499 candles and one mutable current price**;
  **K=500 distinct projection keys**. Rich JSON includes nested levels, nullable
  inputs, exact decimal strings and source/availability timestamps.
- Initial generation A has **1,974,824 stored envelope bytes**.
  Its canonical list has **1,975,325 bytes**, SHA256
  `9616f63207fa5d24ad130da39568ccd7f606e53ea3a45f70cc7cb66554dc9242`.
- G=0 means no newer replacement generation. The bounded G=1 fixture adds one
  newer generation B with one current-price replacement: **4,039 bytes**,
  SHA256 `847401531b5a7c1b9fac70311f66e575e6c49d9c8416c0992ad63cd48e4a7f76`.
  Full readback returns original A records while verifying B's checkpoint,
  receipt, envelope and final projection. G=1 executes two revision SELECTs.
- Three alternating text/binary pairs for each path, separately via a byte-counting
  TCP proxy and direct TCP: **36 successful calls**, all requesting **four seconds**
  and returning all 500 exact canonical A envelopes. Prepared statements remain
  disabled in both arms. Seed writes are local setup, outside the read benchmark.
- Both proxy sockets use TCP_NODELAY. Counts are actual forwarded **TCP stream
  payload bytes**, including PostgreSQL protocol/startup/query/transaction framing;
  they exclude TCP/IP headers, TLS, Supavisor and unrelated interface traffic.
  Direct TCP timing avoids proxy overhead; its bytes were not measured.
- Tables were analyzed and data warmed before the matched comparison. Initial
  un-analyzed diagnostics were substantially slower and the first full-read
  fixture failed strict numeric-spelling validation; those preliminary attempts
  are excluded. The generated volume string was corrected to its exact `1E-9`
  representation before the reported fixture. No validation was relaxed.

The requested initial source was `417d81366f3681de4ee21a00cea77a4fe343e63c`.
Completion HEAD was `c3a05d3ce522ada5fa4a5259f7bc128193c456bf`. Git comparison confirms the transport
is identical between those commits. Actual transport-file SHA256:
`b3097c1b8f78417ffc6f3c7929d289b42badc9efe546f768b7341fd3ae74aeb6`. The ephemeral old-query probe's source digest is
recorded separately in the evidence.

## Measured byte counts and local timings

Server-to-client bytes per complete operation through the counting proxy:

| Path | Text bytes | Binary bytes | Reduction |
|---|---:|---:|---:|
| Exact revisions | 4,107,568 | 2,135,852 | 48.002% |
| Structured retirement read, G=0 | 6,168,753 | 4,197,037 | 31.963% |
| Structured retirement read, G=1 | 6,177,623 | 4,201,880 | 31.982% |

Client-to-server counts were unchanged between result-format arms: 4,203 bytes
for revision reads, 163,726 for G=0 structured readback, and 165,934 for G=1.
Projection reads still use their existing text format and guards, explaining why
the full-path reduction is smaller than the revision-only reduction.

Direct-loopback mean elapsed milliseconds, three samples per arm:

| Path | Text ms | Binary ms |
|---|---:|---:|
| Exact revisions | 73.05 | 68.11 |
| Structured retirement read, G=0 | 215.97 | 210.70 |
| Structured retirement read, G=1 | 209.48 | 206.64 |

These small samples are descriptive, with overlapping full-path ranges; they
are not production percentiles or a powered speedup claim. In the final proxy
G=1 samples, text averaged **221.74 ms** and binary
**223.99 ms**, demonstrating that a reliable byte reduction
does not ensure lower elapsed time in each local comparison.

Direct TCP G=0 revision-phase mean milliseconds:

| Phase | Text ms | Binary ms |
|---|---:|---:|
| Physical connection setup | 2.322 | 2.045 |
| Revision execute / receive result | 6.587 | 4.228 |
| Revision fetchall / driver conversion | 2.328 | 0.408 |
| Revision JSON / canonical validation / receipt hashing | 62.529 | 62.260 |

`execute` includes PostgreSQL execution, local network and libpq result buffering;
`fetchall` measures Python row/type materialization. The residual local phase is
derived from the complete revision decoder and includes JSON decoding, canonical
re-encoding, schema validation and receipt hashing. It is not a server-only SQL
timer. Individual projection-pipeline timing is retained in each sample.

## Guards, remaining opportunities and limitations

All **12 negative checks** passed, six per format: undersized envelope budget,
wrong generation, wrong role identity, corrupt receipt, noncanonical envelope
and corrupted current projection. All successful reads and two old-query codec
probes matched the canonical SHA. The owned fixture
`/tmp/tradebot-cold-perf-ukuhf4g6` was stopped in `finally`; no source or runtime setting changed.
This is not a comprehensive release test suite or complete A/B retirement:
there was no raw retrieval, concurrent live collection, reader drainage, local
deletion, permit or retirement authority.

Existing restricted session reuse is a second opportunity. The actual PP
receipt-metadata comparison in [PR #155](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/155)
measured connection setup savings, while the existing source keeps transactions
and identity checks distinct. Its results cannot be substituted for full rich
retirement timing. This experiment opens a fresh physical session per operation;
it does not wire reuse into retirement or benchmark a combined binary/reuse arm.

Real PP has a different record mix, K, replacement-generation count G, server
statistics, TLS/pooler path, round trips and load. Each newer generation can add
checkpoint and revision work that binary formatting does not eliminate. The
release owner must measure the actual bounded path before relying on any time
savings or the overall final-work margin. No paid feature or product migration
is justified by this byte experiment alone.

## Evidence and reproduction

[Machine-readable samples and checks](evidence/cold-readback-performance-2026-11-19.json)
include every pair, phase timing, byte count, result OID/format and exact hashes.
No raw private records or credentials are present. The generated harness digest
is `f1d89a9c3edeeb173fb2d534cff86ba84b8a82e4c60f83fc1433434954af4da2`.
Run from the repository root with the existing pinned backend environment:

```sh
/tmp/tradebot-cold-reader-venv/bin/python /tmp/tradebot-cold-readback-performance.py
```

The exact generated harness follows for reproducibility. It creates fresh local
schemas, counts loopback streams, verifies both formats and stops its own server.
It performs no hosted operation and must not be redirected to a real database.

```python
from pathlib import Path
from contextlib import contextmanager
import socket,select,threading,time,tempfile,subprocess,getpass,os,sys,json,inspect,statistics,uuid,types
from datetime import datetime,timezone
import psycopg
from psycopg.rows import dict_row
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'backend'))
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.history_v2_envelope import TABLE_KEYS
from postgres.archive_codec import encoded,sha256,ArchiveIntegrityError,ArchiveLimit

class Proxy:
 def __init__(self,target):
  self.target=target;self.count=[0,0];self.active=0;self.condition=threading.Condition();self.stopped=False
  self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen();self.listener.settimeout(.2)
  self.port=self.listener.getsockname()[1];self.thread=threading.Thread(target=self.accept,daemon=True);self.thread.start()
 def accept(self):
  while not self.stopped:
   try:client,_=self.listener.accept()
   except socket.timeout:continue
   except OSError:return
   with self.condition:self.active+=1
   threading.Thread(target=self.forward,args=(client,),daemon=True).start()
 def forward(self,client):
  server=socket.create_connection(self.target)
  for s in (client,server):s.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
  try:
   while True:
    ready,_,_=select.select([client,server],[],[],1)
    for s in ready:
     data=s.recv(131072)
     if not data:return
     direction=0 if s is client else 1
     with self.condition:self.count[direction]+=len(data)
     (server if s is client else client).sendall(data)
  finally:
   client.close();server.close()
   with self.condition:self.active-=1;self.condition.notify_all()
 def snapshot(self):
  with self.condition:return tuple(self.count)
 def closed(self):
  with self.condition:
   if not self.condition.wait_for(lambda:self.active==0,timeout=2):raise RuntimeError('proxy connection did not close')
 def close(self):
  self.closed();self.stopped=True;self.listener.close();self.thread.join(1)

def delta(a,b):return dict(client_to_server=b[0]-a[0],server_to_client=b[1]-a[1])
class RevisionConnection:
 def __init__(self,connection,stats,binary,proxy):self.connection,self.stats,self.binary,self.proxy=connection,stats,binary,proxy
 def __getattr__(self,name):return getattr(self.connection,name)
 def execute(self,statement,values=None):
  if not isinstance(statement,str) or 'WITH sizes' not in statement:return self.connection.execute(statement,values)
  before=self.proxy.snapshot();started=time.perf_counter()
  cursor=self.connection.execute(statement,values,binary=self.binary)
  self.stats['revision_execute_seconds']=time.perf_counter()-started
  self.stats['result_formats']=[cursor.pgresult.fformat(i) for i in range(cursor.pgresult.nfields)]
  self.stats['result_oids']=[c.type_code for c in cursor.description]
  outer=self
  class Result:
   def fetchall(self):
    started=time.perf_counter();rows=cursor.fetchall()
    outer.stats['revision_fetch_type_decode_seconds']=time.perf_counter()-started
    outer.stats['revision_protocol_bytes']=delta(before,outer.proxy.snapshot())
    outer.stats['decoded_envelope_bytes']=sum(len(bytes(row['envelope'])) for row in rows if row['envelope'] is not None)
    return rows
  return Result()
class ExperimentalTransport(HistoryV2PostgresTransport):
 def __init__(self,*args,binary=False,stats,proxy,**kw):
  super().__init__(*args,**kw);self.binary,self.stats,self.proxy=binary,stats,proxy
 def _read_revisions(self,connection,ids,max_bytes,**kw):
  started=time.perf_counter();call={'generation_id':kw.get('generation_id',self.generation_id),'rows':len(ids)}
  try:return super()._read_revisions(RevisionConnection(connection,call,self.binary,self.proxy),ids,max_bytes,**kw)
  finally:
   call['revision_total_seconds']=time.perf_counter()-started
   call['revision_local_canonical_validation_hash_seconds']=call['revision_total_seconds']-call.get('revision_execute_seconds',0)-call.get('revision_fetch_type_decode_seconds',0)
   calls=self.stats.setdefault('revision_calls',[]);calls.append(call)
   for key in ('revision_total_seconds','revision_execute_seconds','revision_fetch_type_decode_seconds','revision_local_canonical_validation_hash_seconds'):
    self.stats[key]=sum(c.get(key,0) for c in calls)
   self.stats['revision_protocol_bytes']={direction:sum(c.get('revision_protocol_bytes',{}).get(direction,0) for c in calls) for direction in ('client_to_server','server_to_client')}
 def _projection_rows(self,connection,records,**kw):
  started=time.perf_counter()
  try:return super()._projection_rows(connection,records,**kw)
  finally:self.stats['projection_pipeline_seconds']=time.perf_counter()-started

base=Path(tempfile.mkdtemp(prefix='tradebot-cold-perf-',dir='/tmp'));pg='/opt/homebrew/opt/postgresql@17/bin/'
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
 proxy=Proxy(('127.0.0.1',server_port));network=f'host=127.0.0.1 port={proxy.port} dbname=tradebot_cold_perf user={getpass.getuser()} sslmode=disable gssencmode=disable'
 samples=[]
 def measure(route,path,binary,pair,newer_generations):
  stats={'route':route,'path':path,'pair':pair,'binary':binary,'request_timeout_seconds':4,'distinct_projection_keys':500,'newer_replacement_generations':newer_generations};before=proxy.snapshot()
  def connect(**_):
   started=time.perf_counter()
   selected=network if route=='counting_proxy' else f'host=127.0.0.1 port={server_port} dbname=tradebot_cold_perf user={getpass.getuser()} sslmode=disable gssencmode=disable'
   db=psycopg.connect(selected,row_factory=dict_row,prepare_threshold=None)
   stats['setup_seconds']=time.perf_counter()-started;return db
  transport=ExperimentalTransport(connect,origin_id=origin,generation_id=generation,expected_database=identity['db'],expected_role=identity['role'],binary=binary,stats=stats,proxy=proxy)
  started=time.perf_counter()
  if path=='revisions':returned=transport.read_revisions(list(range(1,501)),max_bytes=4*1024**2,timeout_seconds=4)
  else:
   returned,size=transport.read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4)
   stats['reconstruction_accounted_bytes']=size
  stats['whole_operation_seconds']=time.perf_counter()-started
  proxy.closed();stats['whole_operation_protocol_bytes']=delta(before,proxy.snapshot()) if route=='counting_proxy' else None
  if route=='direct_tcp':
   stats['revision_protocol_bytes']=None
   for call in stats['revision_calls']:call['revision_protocol_bytes']=None
  assert encoded(returned)==expected;stats['returned_canonical_sha256']=sha256(encoded(returned));stats['returned_count']=len(returned)
  samples.append(stats)
  print('sample',route,path,'binary',binary,'seconds',round(stats['whole_operation_seconds'],4),'S2C',stats['whole_operation_protocol_bytes'],flush=True)
 for route in ('counting_proxy','direct_tcp'):
  for path in ('revisions','retirement_g0'):
   for pair in range(3):
    for binary in ((False,True) if pair%2==0 else (True,False)):measure(route,path,binary,pair+1,0)
 newer_generation='00000000-0000-4000-8000-000000000020'
 newer=price_record(501,newer_generation,'2026-11-19T10:00:01+00:00','100.6800')
 HistoryV2PostgresTransport(plain,origin_id=origin,generation_id=newer_generation,expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True).put_structured([newer],timeout_seconds=4)
 with psycopg.connect(direct) as db:db.execute('ANALYZE')
 for route in ('counting_proxy','direct_tcp'):
  for pair in range(3):
   for binary in ((False,True) if pair%2==0 else (True,False)):measure(route,'retirement_g1',binary,pair+1,1)
 guards=[]
 for binary in (False,True):
  def make(gen=generation,role=identity['role']):return ExperimentalTransport(lambda **_:psycopg.connect(network,row_factory=dict_row,prepare_threshold=None),origin_id=origin,generation_id=gen,expected_database=identity['db'],expected_role=role,binary=binary,stats={},proxy=proxy)
  def must_fail(name,call,error):
   try:call()
   except error:guards.append(dict(binary=binary,guard=name,passed=True))
   else:raise AssertionError(name+' did not hold')
   proxy.closed()
  must_fail('bounded_envelope_suppression',lambda:make().read_revisions(list(range(1,501)),max_bytes=1000,timeout_seconds=4),ArchiveLimit)
  must_fail('wrong_generation',lambda:make('00000000-0000-4000-8000-000000000020').read_revisions([1],max_bytes=4096,timeout_seconds=4),ArchiveIntegrityError)
  must_fail('wrong_role_identity',lambda:make(role='wrong_role').read_revisions([1],max_bytes=4096,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute("UPDATE history_v2.structured_receipts SET payload_hash=%s WHERE outbox_id=1",('b'*64,))
  must_fail('corrupt_receipt',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_receipts SET payload_hash=%s WHERE outbox_id=1',(sha256(encoded(records[0]['payload'])),))
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_revision_payloads SET envelope=%s WHERE outbox_id=1',(encoded(records[0])+b' ',))
  must_fail('noncanonical_envelope',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.structured_revision_payloads SET envelope=%s WHERE outbox_id=1',(encoded(records[0]),))
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.candles SET close=100.01 WHERE time=%s',(records[0]['payload']['time'],))
  must_fail('corrupt_current_projection',lambda:make().read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4),ArchiveIntegrityError)
  with psycopg.connect(direct) as db:db.execute('UPDATE history_v2.candles SET close=%s WHERE time=%s',(records[0]['payload']['close'],records[0]['payload']['time']))
 # Probe the exact deployed old query separately: its directly selected
 # domain columns are not assumed equivalent to the candidate CASE expressions.
 deployed_source=subprocess.check_output(['git','show','74a850b:backend/postgres/history_v2_transport.py'],text=True)
 deployed_module=types.ModuleType('postgres._deployed_readback_performance');deployed_module.__package__='postgres'
 exec(compile(deployed_source,'<generated-native-probe-of-74a850b>','exec'),deployed_module.__dict__)
 codec_probes=[]
 for binary in (False,True):
  probe={}
  @contextmanager
  def deployed_factory(**_):
   with psycopg.connect(network,row_factory=dict_row,prepare_threshold=None) as db:
    yield RevisionConnection(db,probe,binary,proxy)
  old=deployed_module.HistoryV2PostgresTransport(deployed_factory,origin_id=origin,generation_id=generation,expected_database=identity['db'],expected_role=identity['role'])
  returned,size=old.read_retirement_revisions(records,max_bytes=4*1024**2,timeout_seconds=4)
  proxy.closed();assert encoded(returned)==expected
  codec_probes.append(dict(deployed_source='74a850b',binary=binary,full_g1_readback_pass=True,returned_count=len(returned),canonical_sha256=sha256(encoded(returned)),result_oids=probe['result_oids'],result_formats=probe['result_formats'],request_timeout_seconds=4))
 summary=[]
 for route in ('counting_proxy','direct_tcp'):
  for path in ('revisions','retirement_g0','retirement_g1'):
   modes={}
   for binary in (False,True):
    selected=[s for s in samples if s['route']==route and s['path']==path and s['binary']==binary]
    modes[str(binary).lower()]={key:statistics.mean(s[key] for s in selected) for key in ('setup_seconds','revision_execute_seconds','revision_fetch_type_decode_seconds','revision_local_canonical_validation_hash_seconds','whole_operation_seconds')}
    modes[str(binary).lower()]['min_whole_operation_seconds']=min(s['whole_operation_seconds'] for s in selected)
    modes[str(binary).lower()]['max_whole_operation_seconds']=max(s['whole_operation_seconds'] for s in selected)
    if route=='counting_proxy':
     modes[str(binary).lower()]['server_to_client_protocol_bytes']=statistics.mean(s['whole_operation_protocol_bytes']['server_to_client'] for s in selected)
     modes[str(binary).lower()]['revision_server_to_client_protocol_bytes']=statistics.mean(s['revision_protocol_bytes']['server_to_client'] for s in selected)
   summary.append(dict(route=route,path=path,modes=modes,s2c_reduction_percent=100*(1-modes['true']['server_to_client_protocol_bytes']/modes['false']['server_to_client_protocol_bytes']) if route=='counting_proxy' else None))
 result=dict(scope='generated local PostgreSQL cleartext TCP protocol; not PP/TLS bandwidth or production performance',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),psycopg_version=psycopg.__version__,libpq_version=psycopg.pq.version(),connection_execute_signature=str(inspect.signature(psycopg.Connection.execute)),server_version='17.2 Homebrew',bytea_output=bytea_output,records=500,fixture_composition={'core.candles':499,'core.current_prices':1},distinct_projection_keys=500,newer_replacement_fixture={'generations':1,'records':1,'canonical_envelope_bytes':len(encoded(newer)),'canonical_envelope_sha256':sha256(encoded(newer))},canonical_page_bytes=len(expected),stored_envelope_bytes=sum(len(encoded(r)) for r in records),canonical_page_sha256=sha256(expected),samples=samples,summary=summary,guard_checks=guards,deployed_query_codec_probes=codec_probes,deployed_transport_source_sha256=sha256(deployed_source.encode()),source_changes=False,runtime_changes=False,request_timeout_seconds=4,warmed_analyzed_fixture=True,proxy_tcp_nodelay_both_sockets=True,fixture_path=str(base))
finally:
 if proxy:proxy.close()
 subprocess.run([pg+'pg_ctl','-D',str(base/'data'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
 result['fixture_stopped']=True
 if result.get('samples'):
  path=ROOT/'docs/PLAN/evidence/cold-readback-performance-2026-11-19.json';path.write_text(json.dumps(result,indent=2)+'\n')
 print('Stopped generated fixture',base,flush=True)
print(json.dumps(result.get('summary'),indent=2))
```
