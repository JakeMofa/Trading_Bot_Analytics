"""Private generated Supabase wire fixture, never a network/cloud service."""
import hashlib,json,os
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
import httpx
from raw_generations import Stop
from compatible_cloud import KEYS,exact_json,CompatibleCloud
from cloud_memory import SupabaseHTTP
class GeneratedRemote:
    def __init__(self,root):
        self.root=Path(root)
        if self.root.is_symlink() or not self.root.resolve().parent.name.startswith('generated-ab-'):raise Stop('generated wire fixture required')
        self.root.mkdir(mode=0o700,exist_ok=True)
    def _file(self,prefix,key):return self.root/(prefix+'-'+hashlib.sha256(key.encode()).hexdigest())
    def _read(self,file):return json.loads(file.read_text(),parse_float=Decimal) if file.exists() else []
    def _write(self,file,data):
        temporary=file.with_name(file.name+'.partial')
        with temporary.open('w') as f:f.write(exact_json(data));f.flush();os.fsync(f.fileno())
        temporary.replace(file)
    def handle(self,request):
        if request.headers.get('apikey')!='generated-only':return httpx.Response(401)
        path=request.url.path;method=request.method
        with (self.root/'requests.txt').open('a') as f:f.write(method+' '+('storage' if '/storage/' in path else path.rsplit('/',1)[-1])+'\n')
        if '/storage/v1/object/' in path:
            key=path.split('/storage/v1/object/',1)[1].removeprefix('authenticated/')
            file=self._file('object',key)
            if method=='GET':return httpx.Response(200,content=file.read_bytes()) if file.exists() else httpx.Response(404)
            if method=='POST':
                if request.headers.get('x-upsert')!='false':return httpx.Response(400)
                if file.exists():return httpx.Response(409)
                with file.open('xb') as f:f.write(request.content);f.flush();os.fsync(f.fileno())
                return httpx.Response(201)
        table=path.rsplit('/',1)[-1];keys=('bucket','object_path') if table=='raw_archives' else KEYS.get(table)
        if keys:
            file=self._file('table',table);rows=self._read(file)
            if method=='GET':
                def matches(row):
                    for key in keys:
                        value=request.url.params[key][3:]
                        try:value=json.loads(value)
                        except ValueError:pass
                        if row.get(key)!=value:return False
                    return True
                return httpx.Response(200,content=exact_json([r for r in rows if matches(r)]).encode())
            if method=='POST':
                incoming=json.loads(request.content,parse_float=Decimal)
                for row in incoming:
                    found=[r for r in rows if all(r[k]==row[k] for k in keys)]
                    if found and 'ignore-duplicates' in request.headers.get('Prefer',''):continue
                    rows=[r for r in rows if any(r[k]!=row[k] for k in keys)]+[row]
                self._write(file,rows);return httpx.Response(201)
        return httpx.Response(404)
    def client(self,deadline):
        native=SupabaseHTTP(SimpleNamespace(url='https://fixture.invalid',secret_key='generated-only'),
                            client=httpx.Client(transport=httpx.MockTransport(self.handle)))
        return CompatibleCloud(native,deadline)
