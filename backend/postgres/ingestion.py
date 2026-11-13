"""Explicit bounded generated/replay input. This module has no live connector."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from .config import Settings
from .domain import timestamp, utcnow
from .store import Store


def generated_events(now=None):
    now = timestamp(now or utcnow())
    start = datetime.fromtimestamp(int(now.timestamp())//900*900,timezone.utc)
    market_id = 'generated-btc-15m-'+str(int(start.timestamp()))
    provenance = {'data_mode':'generated','generator':'cp3_v1','settlement_source':'synthetic_only'}
    def event(source,event_id,kind,payload,at=None,**extra):
        return {'source':source,'event_id':event_id,'kind':kind,'source_time':(at or now).isoformat(),
                'received_at':now.isoformat(),'payload':payload,'provenance':provenance,**extra}
    events = []
    # Current and next boundaries prove discovery without waiting for resolution.
    for offset in (0,900):
        boundary = start+timedelta(seconds=offset)
        identity = 'generated-btc-15m-'+str(int(boundary.timestamp()))
        events.append(event('polymarket_us',identity,'market',{
            'slug':identity,'start':boundary.isoformat(),'end':(boundary+timedelta(minutes=15)).isoformat(),
            'duration':900,'target_usd':'100000.1234567890123456789','status':'MARKET_STATUS_OPEN',
            'rules':'Generated test fixture; no official outcome'},market_id=identity))
    minute = int(now.timestamp())//60*60-60
    for index in range(17):
        second = minute-(16-index)*60
        close = str(100000+(index%3)*7+index)
        events.append(event('coinbase',f'generated-candle-{second}','candle',{
            'time':second,'granularity':60,'open':close,'high':close,'low':close,'close':close,'volume':'0.1234567890123456789'},
            at=datetime.fromtimestamp(second,timezone.utc),symbol='BTC-USD'))
    events.append(event('coinbase','generated-price-'+now.isoformat(),'price',{},
                        price='100025.1234567890123456789',size='0.0000000000000000001',symbol='BTC-USD'))
    events.append(event('polymarket_us','generated-quote-'+now.isoformat(),'quote',{
        'slug':market_id,'up_probability':'0.52','down_probability':'0.48','best_bid':'0.51','best_ask':'0.53'},market_id=market_id))
    return events


def replay(store, path, limit=500):
    if not 1 <= limit <= 500:
        raise ValueError('replay batch is bounded to 500 records')
    file = Path(path)
    if file.stat().st_size > 2*1024*1024:
        raise ValueError('replay input is bounded to 2 MiB')
    events = [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
    if len(events) > limit:
        raise ValueError('replay exceeds batch limit')
    return [store.ingest(event) for event in events]


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--generated',action='store_true')
    group.add_argument('--replay-file')
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(settings)
    store.verify()
    if args.generated:
        if settings.data_mode != 'generated':
            raise ValueError('generated seed requires generated mode')
        records = [store.ingest(event) for event in generated_events()]
    else:
        if settings.data_mode != 'replay':
            raise ValueError('replay input requires replay mode')
        records = replay(store,args.replay_file)
    print(json.dumps({'acknowledged':len(records),'mode':settings.data_mode,'origin_id':settings.origin_id}))


if __name__ == '__main__':
    main()
