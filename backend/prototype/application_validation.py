"""Bounded logical checks for application rows; never normalizes stored evidence."""
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import json

DECIMALS={
 'markets':('target','final'), 'stream_events':('price','size'),
 'reference_prices':('price',), 'candles':('low','high','open','close','volume'),
 'predictions':('probability_up','probability_down','ensemble_up_prob','ensemble_down_prob'),
}
TIMES={'received_at','source_time','first_seen','last_seen','as_of','created_at','start','end',
       'published_at','linked_at','known_at'}
JSON_FIELDS={'payload','raw_json','values_json','quality_json','evidence_json',
             'categories_json','assumptions_json','component_scores'}
LAYOUT_VERSION=2


def timestamp(value):
    if not isinstance(value,str):raise ValueError('timestamp text required')
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('timezone required')
    return at


def row_check(table,row):
    for key in TIMES & row.keys():
        if row[key] is not None:timestamp(row[key])
    for key in DECIMALS.get(table,()):
        value=row.get(key)
        if value is not None:
            if not isinstance(value,str):raise ValueError('exact decimal text required: '+table+'.'+key)
            try:valid=Decimal(value).is_finite()
            except InvalidOperation:valid=False
            if not valid:raise ValueError('nonfinite/malformed decimal: '+table+'.'+key)
    for key in JSON_FIELDS & row.keys():
        value=row[key]
        if value is not None:
            json.loads(value,parse_float=Decimal,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if table=='markets':
        if not row.get('id') or not row.get('slug'):raise ValueError('market identity missing')
        if timestamp(row['end'])<=timestamp(row['start']):raise ValueError('market interval malformed')
    if table in ('observations','stream_events') and not row.get('received_at'):raise ValueError('receipt provenance missing')
    if table=='observations':
        if type(row.get('id')) is not int or row['id']<=0 or not row.get('market_id') or not row.get('kind'):
            raise ValueError('observation identity/provenance missing')
    if table=='stream_events':
        if 'source_key' in row and row['source_key']!=timestamp(row['source_time']).astimezone(timezone.utc).isoformat(timespec='microseconds'):
            raise ValueError('derived source key differs')
        if not row.get('source') or not row.get('event_id') or not row.get('source_time'):
            raise ValueError('stream identity/provenance missing')


def header(db,required,exact=False):
    if db.execute('PRAGMA user_version').fetchone()[0]!=0:raise ValueError('unsupported SQLite user_version')
    for name,columns in required.items():
        info=db.execute('PRAGMA table_info('+name+')').fetchall()
        actual={r[1] for r in info}
        if exact:
            primary={r[1]:r[5] for r in info if r[5]}
            expected={'generation':{'id':1},'observations':{'id':1},'stream_events':{'source':1,'event_id':2}}[name]
            if primary!=expected:raise ValueError('incompatible primary identity: '+name)
        if not set(columns)<=actual or (exact and set(columns)!=actual):raise ValueError('incompatible schema: '+name)


def protected_core(db,legacy,columns,budget):
    """Check protected copies and semantic links; point reads, never raw-history audit."""
    import hashlib
    canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    def fingerprint(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
    for event_id,expected in db.execute('SELECT id,fingerprint FROM ab_legacy_pins'):
        budget.check()
        local=db.execute('SELECT '+','.join(columns['observations'])+' FROM observations WHERE id=?',(event_id,)).fetchone()
        original=legacy.execute('SELECT '+','.join(columns['observations'])+' FROM observations WHERE id=?',(event_id,)).fetchone()
        if local is None or original is None or tuple(local)!=tuple(original) or fingerprint(dict(local))!=expected:
            raise ValueError('protected legacy observation differs')
    for source,event,record in db.execute('SELECT source,event_id,record FROM ab_legacy_stream_pins'):
        budget.check();original=legacy.execute('SELECT '+','.join(columns['stream_events'])+' FROM stream_events WHERE source=? AND event_id=?',(source,event)).fetchone()
        if original is None or json.loads(record)!=dict(original):raise ValueError('protected legacy price differs')
        row_check('stream_events',dict(original))
    for event_id,record,sha in db.execute('SELECT id,record,sha256 FROM ab_evidence'):
        budget.check()
        if hashlib.sha256(record.encode()).hexdigest()!=sha:raise ValueError('protected core evidence checksum')
        evidence=json.loads(record)
        receipt=db.execute('SELECT sha256 FROM ab_raw_receipts WHERE id=?',(event_id,)).fetchone()
        if not receipt or fingerprint(evidence['row'])!=receipt[0]:raise ValueError('protected body differs from acknowledgement')
        row_check(evidence['dataset'],evidence['row'])
        if evidence['dataset']=='observations':
            copy=db.execute('SELECT '+','.join(columns['observations'])+' FROM observations WHERE id=?',(event_id,)).fetchone()
            if copy is not None and dict(copy)!=evidence['row']:raise ValueError('protected current observation differs')
    for snapshot in db.execute('SELECT * FROM feature_snapshots'):
        budget.check();evidence=json.loads(snapshot['evidence_json']);values=json.loads(snapshot['values_json'])
        if snapshot['version'] not in (1,2):raise ValueError('unsupported feature version')
        metadata=db.execute('SELECT * FROM observations WHERE id=?',(evidence.get('metadata_observation_id'),)).fetchone()
        if metadata is None or metadata['market_id']!=snapshot['market_id']:raise ValueError('protected snapshot metadata missing/mismatched')
        if timestamp(metadata['received_at'])!=timestamp(evidence['metadata_received_at']):raise ValueError('metadata provenance timestamp differs')
        metadata_body=json.loads(metadata['payload'],parse_float=Decimal)
        target=(metadata_body.get('assetPriceTerms') or {}).get('priceToBeat')
        if isinstance(target,dict):target=target.get('value')
        if values.get('target_usd') is not None and (target is None or Decimal(str(target))!=Decimal(values['target_usd'])):
            raise ValueError('target provenance value differs')
        info=evidence.get('price') or {};price=None
        if info.get('source')=='coinbase_stream':
            record=db.execute('SELECT record FROM ab_legacy_stream_pins WHERE source=? AND event_id=?',('coinbase',str(info['input_id']))).fetchone()
            if record:price=json.loads(record[0])
            else:
                record=db.execute("SELECT p.record FROM ab_evidence p JOIN ab_events e ON e.id=p.id WHERE e.dataset='stream_events' AND e.event_key=?",('coinbase:'+str(info['input_id']),)).fetchone()
                if record:price=json.loads(record[0])['row']
            if price is None:raise ValueError('protected snapshot price missing')
        elif info.get('source')=='coinbase_rest':
            found=db.execute('SELECT * FROM reference_prices WHERE id=?',(info['input_id'],)).fetchone()
            if found:price=dict(found)
            else:raise ValueError('protected reference price missing')
        elif info.get('source') is not None or info.get('input_id') is not None:raise ValueError('unknown price provenance')
        if price is None and values.get('reference_price_usd') is not None:raise ValueError('missing price provenance')
        if price:
            if timestamp(info['source_time'])!=timestamp(price['source_time']):raise ValueError('price provenance timestamp differs')
            if values.get('reference_price_usd') is not None and Decimal(values['reference_price_usd'])!=Decimal(price['price']):
                raise ValueError('price provenance value differs')
    if db.execute('SELECT 1 FROM predictions p JOIN feature_snapshots f ON f.id=p.snapshot_id WHERE p.market_id!=f.market_id LIMIT 1').fetchone():
        raise ValueError('prediction/snapshot market mismatch')
