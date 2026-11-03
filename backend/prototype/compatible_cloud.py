"""Generated qualification of existing Supabase wire schema, no production setup.

Reads retry only safe transient failures. Writes are single conditional attempts;
ambiguous responses reconcile exact remote identity before any acknowledgement.
The original phase deadline encloses each child and every GET/backoff/body read.
"""
import hashlib,json,time
from urllib.parse import quote
import httpx
from archive_reads import HardArchiveReads,BoundedArchiveReads,ArchiveHold,ArchiveMissing
from raw_generations import canonical,iso
from datetime import datetime,timezone
from decimal import Decimal
from raw_generations import stamp

KEYS={'markets':('id',),'official_outcomes':('market_id',),'feature_snapshots':('source_id',),
      'predictions':('source_id',),'news_events':('source_id',),
      'candles':('source','symbol','granularity','time'),'sync_checkpoints':('dataset',)}
def exact_json(value):
    if isinstance(value,Decimal):
        if not value.is_finite():raise ArchiveHold('nonfinite exact cloud value')
        return str(value)
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+':'+exact_json(v) for k,v in value.items())+'}'
    if isinstance(value,(list,tuple)):return '['+','.join(exact_json(v) for v in value)+']'
    return json.dumps(value,allow_nan=False,separators=(',',':'))
def equivalent(a,b,key=None):
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(equivalent(a[k],b[k],k) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a,(float,Decimal)) and isinstance(b,(int,float,Decimal)):return Decimal(str(a))==Decimal(str(b))
    if isinstance(b,(float,Decimal)) and isinstance(a,int):return Decimal(a)==Decimal(str(b))
    if key in ('start','end','as_of','first_seen','last_seen','confirmed_at','created_at','published_at','last_source_time','started_at','ended_at') and a and b:
        try:return stamp(a)==stamp(b)
        except (ValueError,TypeError):return False
    return a==b

def same_row(prior,wanted):
    return all(equivalent(prior.get(k),v,k) for k,v in wanted.items() if k not in ('synced_at','updated_at'))

def allowed_update(table,prior,row):
    if table=='markets':
        fixed=('id','slug','duration','start','end','first_seen')
        return all(equivalent(prior.get(k),row.get(k),k) for k in fixed) and stamp(row['last_seen'])>stamp(prior['last_seen'])
    if table=='official_outcomes':return stamp(row['confirmed_at'])>stamp(prior['confirmed_at'])
    if table=='sync_checkpoints':
        # Never rewind an already-confirmed remote checkpoint after ambiguity.
        if row.get('rows_synced',0)<prior.get('rows_synced',0):return False
        for field in ('last_source_id','last_source_time'):
            old,new=prior.get(field),row.get(field)
            if old is not None and (new is None or (stamp(new)<stamp(old) if field.endswith('time') else new<old)):return False
        if prior.get('last_source_time') and row.get('last_source_time') and stamp(prior['last_source_time'])==stamp(row['last_source_time']):
            old,new=prior.get('last_source_key'),row.get('last_source_key')
            if old is not None:
                if new is None:return False
                if row.get('dataset')=='archive:stream_events':
                    try:old,new=json.loads(old),json.loads(new)
                    except (ValueError,TypeError):return False
                    if not all(isinstance(x,list) and len(x)==2 and all(isinstance(v,str) for v in x) for x in (old,new)):return False
                if new<old:return False
        return True
    return False

class CompatibleCloud:
    def __init__(self,cloud,deadline):self.cloud,self.deadline=cloud,deadline
    def _remaining(self):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise ArchiveHold('original cloud operation deadline exhausted')
        return remaining
    def _hard(self,operation,max_bytes=64*1024**2):
        return HardArchiveReads(self.cloud,self.deadline,max_bytes,operation).download_bytes('unused','unused')
    def download_bytes(self,bucket,path):return HardArchiveReads(self.cloud,self.deadline).download_bytes(bucket,path)
    def upload_bytes(self,bucket,path,data,content_type='application/gzip'):
        if len(data)>64*1024**2:raise ArchiveHold('archive resource bound')
        def operation():
            reader=BoundedArchiveReads(self.cloud,self.deadline)
            def compare():
                prior=reader.download_bytes(bucket,path)
                if prior!=data:raise ArchiveHold('immutable archive conflict')
            try:compare();return b''
            except ArchiveMissing:pass
            try:
                response=self.cloud.client.post(
                    f'{self.cloud.config.url}/storage/v1/object/{quote(bucket,safe="")}/{quote(path,safe="/")}',
                    headers=self.cloud._headers(**{'Content-Type':content_type,'x-upsert':'false'}),content=data,
                    timeout=self._remaining())
                if response.status_code in (401,403):raise ArchiveHold('archive upload authorization hold')
                response.raise_for_status()
            except (httpx.RequestError,httpx.HTTPStatusError):
                # No second POST, including on 409/ambiguous 5xx. Reconcile GET.
                compare();return b''
            compare();return b''
        self._hard(operation)
    def verify_object(self,bucket,path,expected_sha256,expected_bytes):
        def operation():
            data=BoundedArchiveReads(self.cloud,self.deadline).download_bytes(bucket,path)
            if len(data)!=expected_bytes or hashlib.sha256(data).hexdigest()!=expected_sha256:raise ArchiveHold('archive verification mismatch')
            return json.dumps({'verified_at':iso(datetime.now(timezone.utc)),'sha256':expected_sha256,'bytes':expected_bytes}).encode()
        result=json.loads(self._hard(operation,max_bytes=4096))
        if time.monotonic()>=self.deadline:raise ArchiveHold('verification response deadline')
        return result
    def upsert(self,table,rows,on_conflict):
        # The raw manifest has an immutable object identity. Other existing
        # structured/checkpoint upserts remain one-attempt operations, never retried.
        def operation():
            remaining=self._remaining
            if table=='raw_archives':
                if on_conflict!='bucket,object_path' or len(rows)!=1:raise ArchiveHold('manifest identity required')
                row=rows[0]
                def remote():
                    response=self.cloud.client.get(f'{self.cloud.config.url}/rest/v1/raw_archives',
                        params={'bucket':'eq.'+json.dumps(row['bucket']),'object_path':'eq.'+json.dumps(row['object_path']),'limit':2},
                        headers=self.cloud._headers(),timeout=remaining());response.raise_for_status()
                    found=response.json()
                    if not isinstance(found,list) or len(found)>1:raise ArchiveHold('manifest identity ambiguous')
                    if found:
                        # Verification time can refresh; content and boundaries cannot.
                        fields=('source','market_id','started_at','ended_at','bucket','object_path','compression','content_type','sha256','event_count','uncompressed_bytes','compressed_bytes','first_source_id','last_source_id','metadata')
                        if any(not equivalent(found[0].get(k),row.get(k),k) for k in fields):raise ArchiveHold('manifest immutable conflict')
                    return bool(found)
                if remote():return b''
                try:
                    response=self.cloud.client.post(f'{self.cloud.config.url}/rest/v1/raw_archives',params={'on_conflict':on_conflict},
                        headers=self.cloud._headers(**{'Prefer':'resolution=ignore-duplicates,return=minimal','Content-Type':'application/json'}),json=rows,timeout=remaining())
                    if response.status_code in (401,403):raise ArchiveHold('manifest authorization hold')
                    response.raise_for_status()
                except (httpx.RequestError,httpx.HTTPStatusError):
                    if not remote():raise ArchiveHold('ambiguous manifest not confirmed')
                    return b''
                if not remote():raise ArchiveHold('manifest readback missing')
                return b''
            keys=KEYS.get(table)
            if keys is None or on_conflict!=','.join(keys) or not 1<=len(rows)<=1000:raise ArchiveHold('unsupported structured identity/batch')
            def remote(row):
                params={k:'eq.'+json.dumps(row[k],ensure_ascii=False) for k in keys};params['limit']=2
                response=self.cloud.client.get(f'{self.cloud.config.url}/rest/v1/{table}',params=params,headers=self.cloud._headers(),timeout=remaining())
                response.raise_for_status();found=json.loads(response.content,parse_float=Decimal)
                if not isinstance(found,list) or len(found)>1:raise ArchiveHold('structured identity ambiguous')
                return found[0] if found else None
            needed=[]
            for row in rows:
                prior=remote(row)
                if prior is not None and same_row(prior,row):continue
                if prior is not None and not allowed_update(table,prior,row):raise ArchiveHold('structured identity/content conflict')
                needed.append(row)
            if needed:
                try:
                    response=self.cloud.client.post(f'{self.cloud.config.url}/rest/v1/{table}',params={'on_conflict':on_conflict},
                        headers=self.cloud._headers(**{'Prefer':('resolution=merge-duplicates' if table in ('markets','official_outcomes','sync_checkpoints') else 'resolution=ignore-duplicates')+',return=minimal','Content-Type':'application/json'}),
                        content=exact_json(needed).encode(),timeout=remaining())
                    if response.status_code in (401,403):raise ArchiveHold('structured authorization hold')
                    response.raise_for_status()
                except (httpx.RequestError,httpx.HTTPStatusError):
                    # No second POST: require exact post-write state even on a
                    # committed response lost in transit. Otherwise hold.
                    if not all((found:=remote(row)) is not None and same_row(found,row) for row in needed):raise ArchiveHold('ambiguous structured write unconfirmed')
                    return b''
                if not all((found:=remote(row)) is not None and same_row(found,row) for row in needed):raise ArchiveHold('structured readback mismatch')
            return b''
        self._hard(operation)
        return len(rows)
    def close(self):self.cloud.close()
