"""Bounded explicit historical evidence read, never a live feature fallback."""
import gzip, io, json, math, time
from decimal import Decimal
from retention_recovery import verify_archive, identity, COLUMNS, MAX_LINE, MAX_RAW
from retention import _manifest_interval
from raw_generations import Stop, digest
from compatible_cloud import CompatibleCloud
from application_validation import row_check


def read_history(connection, cloud, generation, dataset, requested, deadline):
    if not connection.readonly or getattr(connection.store,'role',None)!='history':
        raise Stop('archive replay requires explicit history worker')
    if not isinstance(cloud,CompatibleCloud) or type(deadline) not in (int,float) or not math.isfinite(deadline):
        raise Stop('bounded authenticated replay required')
    if cloud.deadline>deadline or not 0<deadline-time.monotonic()<=30:
        raise Stop('archive replay deadline')
    if dataset not in COLUMNS or not isinstance(requested,list) or not 1<=len(requested)<=100:
        raise Stop('archive history request bound')
    for key in requested:
        if not isinstance(key,list):raise Stop('archive identity list required')
        if dataset=='observations':
            if len(key)!=1 or type(key[0]) is not int or key[0]<=0:raise Stop('exact observation identity required')
        elif len(key)!=3 or not all(isinstance(value,str) and value for value in key):
            raise Stop('exact stream identity required')
    wanted={tuple(key) for key in requested}
    if len(wanted)!=len(requested):raise Stop('duplicate history request identity')
    if not connection.db.execute('SELECT 1 FROM ab_generations WHERE id=?',(generation,)).fetchone():
        raise Stop('unknown historical generation')
    catalog=connection.db.execute('SELECT path,metadata FROM ab_manifests WHERE gen=? AND dataset=? ORDER BY path LIMIT 10001',(generation,dataset)).fetchall()
    if len(catalog)>10000:raise Stop('archive history catalog bound')
    result={};proofs=[];downloads=0
    for path,text in catalog:
        if time.monotonic()>=deadline:raise Stop('archive replay deadline')
        manifest=json.loads(text)
        if manifest.get('object_path')!=path or not path.startswith(generation+'/') or manifest.get('metadata',{}).get('generation_id')!=generation:
            raise Stop('archive history generation mismatch')
        lo,hi=_manifest_interval(dataset,manifest,'market-raw')
        def order(key):return key if dataset=='observations' else (key[2],key[0],key[1])
        selected={key for key in wanted if lo<=order(key)<=hi}
        if not selected:continue
        downloads+=1
        if downloads>8:raise Stop('archive history object budget')
        body=cloud.download_bytes('market-raw',path)
        proof,found=verify_archive(manifest,body,selected)
        # ApplicationStore's supported JSONL encoder appends original payload
        # TEXT last, preserving decimals and lexical fingerprint across removal.
        exact={};total=0
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            while True:
                line=stream.readline(MAX_LINE+1)
                if not line:break
                total+=len(line)
                if len(line)>MAX_LINE or total>MAX_RAW:raise Stop('archive history decoded bound')
                item=json.loads(line,parse_float=Decimal)
                key=identity(dataset,item['row'])
                if key not in found:continue
                text_line=line.decode().rstrip('\r\n')
                marker=',"payload":'
                if marker not in text_line or not text_line.endswith('}}'):raise Stop('archive payload lexical provenance unavailable')
                raw=dict(item['row']);raw['payload']=text_line.split(marker,1)[1][:-2]
                row_check(dataset,raw)
                if dataset=='observations':
                    evidence=connection.db.execute("SELECT r.sha256 FROM ab_events e JOIN ab_raw_receipts r ON r.id=e.id WHERE e.gen=? AND e.dataset=? AND e.id=? AND e.status='committed'",(generation,dataset,raw['id'])).fetchone()
                else:
                    evidence=connection.db.execute("SELECT r.sha256 FROM ab_events e JOIN ab_raw_receipts r ON r.id=e.id WHERE e.gen=? AND e.dataset=? AND e.event_key=? AND e.status='committed'",(generation,dataset,raw['source']+':'+raw['event_id'])).fetchone()
                row={column:raw[column] for column in COLUMNS[dataset]}
                if not evidence or evidence[0]!=digest(row):raise Stop('archive history acknowledged fingerprint mismatch')
                exact[key]=row
        for key,row in exact.items():
            if key in result:raise Stop('overlapping archive history identities')
            result[key]=row
        proofs.append(proof)
    if set(result)!=wanted:raise Stop('requested archived history unavailable')
    if time.monotonic()>=deadline:raise Stop('archive replay deadline')
    return {'status':'ok','generation_id':generation,'dataset':dataset,
            'records':[result[tuple(key)] for key in requested],
            'archives':proofs,'provenance':'authenticated_archive_and_committed_core_receipt'}
