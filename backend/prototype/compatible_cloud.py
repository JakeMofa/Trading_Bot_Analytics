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

class CompatibleCloud:
    def __init__(self,cloud,deadline):self.cloud,self.deadline=cloud,deadline
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
                    timeout=max(.001,self.deadline-time.monotonic()))
                if response.status_code in (401,403):raise ArchiveHold('archive upload authorization hold')
                response.raise_for_status()
            except (httpx.RequestError,httpx.HTTPStatusError):
                # No second POST, including on 409/ambiguous 5xx. Reconcile GET.
                compare();return b''
            compare();return b''
        self._hard(operation)
    def verify_object(self,bucket,path,expected_sha256,expected_bytes):
        data=self.download_bytes(bucket,path)
        if len(data)!=expected_bytes or hashlib.sha256(data).hexdigest()!=expected_sha256:raise ArchiveHold('archive verification mismatch')
        return {'verified_at':iso(datetime.now(timezone.utc)),'sha256':expected_sha256,'bytes':expected_bytes}
    def upsert(self,table,rows,on_conflict):
        # The raw manifest has an immutable object identity. Other existing
        # structured/checkpoint upserts remain one-attempt operations, never retried.
        def operation():
            remaining=lambda:max(.001,self.deadline-time.monotonic())
            if table=='raw_archives':
                if on_conflict!='bucket,object_path' or len(rows)!=1:raise ArchiveHold('manifest identity required')
                row=rows[0]
                def remote():
                    response=self.cloud.client.get(f'{self.cloud.config.url}/rest/v1/raw_archives',
                        params={'bucket':'eq.'+row['bucket'],'object_path':'eq.'+row['object_path'],'limit':2},
                        headers=self.cloud._headers(),timeout=remaining());response.raise_for_status()
                    found=response.json()
                    if not isinstance(found,list) or len(found)>1:raise ArchiveHold('manifest identity ambiguous')
                    if found:
                        # Verification time can refresh; content and boundaries cannot.
                        fields=('source','market_id','started_at','ended_at','bucket','object_path','compression','content_type','sha256','event_count','uncompressed_bytes','compressed_bytes','first_source_id','last_source_id','metadata')
                        if any(found[0].get(k)!=row.get(k) for k in fields):raise ArchiveHold('manifest immutable conflict')
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
            self.cloud.upsert(table,rows,on_conflict)
            return b''
        self._hard(operation)
        return len(rows)
    def close(self):self.cloud.close()
