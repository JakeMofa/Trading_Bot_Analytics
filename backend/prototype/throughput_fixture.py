"""Generate the two exact synthetic archive objects for throughput review."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path

from retention_recovery import identity, verify_archive


def build(index):
    if index not in (1, 2):
        raise ValueError('only two reviewed fixture identities')
    generation = f'{72000000000000000000000000000000+index:032d}'
    start = datetime(2026,11,5,tzinfo=timezone.utc)
    rows = []
    for event in range(1024):
        at = (start+timedelta(milliseconds=event)).isoformat(timespec='microseconds')
        rows.append(dict(source='coinbase',event_id=f'ab72-throughput-v1-{index}-{event:04d}',
                         received_at=at,source_time=at,price='12345.000000000000001',
                         size='0.00000001',side='buy',
                         payload=dict(synthetic=True,padding=hashlib.shake_256(f'{index}-{event}'.encode()).hexdigest(512))))
    raw = ''.join(json.dumps(dict(dataset='stream_events',row=row),separators=(',',':'))+'\n' for row in rows).encode()
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',mtime=0) as stream:
        stream.write(raw)
    body = output.getvalue()
    sha = hashlib.sha256(body).hexdigest()
    key = f'ab72-readiness/2026-11-03-v1/throughput-2026-11-05-v1/{generation}/stream_events/{sha}.jsonl.gz'
    manifest = dict(source='coinbase',bucket='market-raw',object_path=key,
                    sha256=sha,compressed_bytes=len(body),event_count=len(rows),
                    started_at=rows[0]['received_at'],ended_at=rows[-1]['received_at'],
                    verified_at=rows[-1]['received_at'],
                    metadata=dict(dataset='stream_events',generation_id=generation,
                                  verification='authenticated_readback_sha256',
                                  first_source_key=json.dumps([rows[0]['source'],rows[0]['event_id']]),
                                  last_source_key=json.dumps([rows[-1]['source'],rows[-1]['event_id']])))
    expected = {identity('stream_events',row):row for row in rows}
    _, found = verify_archive(manifest,body,expected)
    if found != expected or len(body)>1024**2:
        raise ValueError('synthetic throughput fixture verification failed')
    return manifest, body


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700,exist_ok=False)
    manifests = []
    for index in (1,2):
        manifest, body = build(index)
        (args.output/manifest['object_path'].split('/')[-1]).write_bytes(body)
        manifests.append(manifest)
    (args.output/'manifests.json').write_text(json.dumps(manifests,indent=2)+'\n')
    print(json.dumps([{'object_path':m['object_path'],'bytes':m['compressed_bytes'],
                       'rows':m['event_count'],'sha256':m['sha256']} for m in manifests]))
