"""Bounded generated smoke against a running API; emits no credentials or SQL."""
import argparse
import json
import time
from urllib.parse import urlparse

import httpx

from .config import Settings
from .domain import timestamp, utcnow
from .ingestion import generated_events
from .store import IdentityConflict, Store
from .worker import CalculationWorker


def qualify(base_url, timeout=20):
    settings=Settings.from_env()
    if settings.data_mode!='generated' or not settings.origin_id.startswith('generated-'):
        raise ValueError('acceptance only writes an explicit generated origin')
    parsed=urlparse(base_url)
    if parsed.scheme!='http' or parsed.hostname not in ('api','localhost','127.0.0.1') or parsed.username or parsed.password:
        raise ValueError('acceptance endpoint must be the isolated local API')
    store=Store(settings)
    store.verify()
    now=utcnow()
    events=generated_events(now)
    acknowledgements=[store.ingest(event) for event in events]
    price_event=next(event for event in events if event['kind']=='price')
    duplicate=store.ingest(price_event)
    if not duplicate['duplicate']:
        raise AssertionError('idempotent replay failed')
    try:
        store.ingest(dict(price_event,price='1'))
    except IdentityConflict:
        conflict_detected=True
    else:
        raise AssertionError('conflicting source identity accepted')
    worker=CalculationWorker(store)
    worker.discover_once()
    snapshot_id=worker.calculate_once()
    if snapshot_id is None:
        raise AssertionError('no publishable generated snapshot')
    deadline=time.monotonic()+timeout
    latencies=[]
    with httpx.Client(base_url=base_url,timeout=2,trust_env=False) as client:
        while True:
            started=time.monotonic()
            response=client.get('/state/current')
            response.raise_for_status()
            latencies.append(time.monotonic()-started)
            state=response.json()
            feature=state.get('feature_snapshot') or {}
            if (feature.get('quality',{}).get('price',{}).get('input_id')==price_event['event_id']
                    and timestamp(feature['as_of'])>=now
                    and (state.get('coinbase') or {}).get('event_id')==price_event['event_id']):
                break
            if time.monotonic()>=deadline:
                raise AssertionError('running API did not publish acknowledged snapshot')
            time.sleep(.1)
        if state['coinbase']['price_usd']!=price_event['price'] or state['collector']['enabled']:
            raise AssertionError('current price precision/collector invariant failed')
        if state['data_mode']!='generated' or state['origin_id']!=settings.origin_id:
            raise AssertionError('API environment/origin mismatch')
        history=client.get('/history/predictions?limit=10')
        history.raise_for_status()
        if not history.json()['items']:
            raise AssertionError('persisted history unavailable')
        dashboard=client.get('/dashboard')
        dashboard.raise_for_status()
        if "new EventSource('/events')" not in dashboard.text or 'environment-label' not in dashboard.text:
            raise AssertionError('deployed dashboard contract missing')
        chart=client.get('/history/coinbase-chart')
        chart.raise_for_status()
        if not chart.json()['points']:
            raise AssertionError('bounded chart missing current input')
        for reconnect in range(2):
            with client.stream('GET','/events') as stream:
                stream.raise_for_status()
                first=next(line for line in stream.iter_lines() if line.startswith('data: '))
                streamed=json.loads(first[6:])
                if (streamed.get('market') or {}).get('id')!=state['market']['id']:
                    raise AssertionError('SSE market differs from current RAM')
                streamed_feature=streamed.get('feature_snapshot') or {}
                if streamed_feature.get('quality',{}).get('price',{}).get('input_id')!=price_event['event_id']:
                    raise AssertionError('SSE did not carry persisted snapshot')
    return {'status':'pass','scope':'generated_local_api','origin_id':settings.origin_id,
            'acknowledged_events':len(acknowledgements),'conflict_detected':conflict_detected,
            'exact_decimal_roundtrip':True,'api_ram_after_commit':True,'sse_connections':2,
            'dashboard_contract':True,'bounded_chart':True,'prediction_history':True,
            'api_max_seconds':round(max(latencies),6),'collector_enabled':False,
            'unsupported':['real_feeds','production_preview','ensemble','news','evaluation','capacity']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://api:8000')
    args=parser.parse_args()
    print(json.dumps(qualify(args.base_url),sort_keys=True))


if __name__=='__main__':
    main()
