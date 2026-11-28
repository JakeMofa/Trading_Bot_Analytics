#!/usr/bin/env python3
"""Send low-cardinality local Benchmark measurements to Grafana Prometheus."""
import argparse
import base64
from datetime import datetime
import http.client
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
from urllib.request import build_opener, ProxyHandler

ORIGIN = 'pp-live-pp-benchmark-watch'
HOST = 'pp-benchmark'
METRICS_HOST = 'prometheus-prod-56-prod-us-east-2.grafana.net'
LOCAL_URL = 'http://127.0.0.1:8000/system/telemetry'
SOURCES = ('coinbase', 'polymarket', 'robinhood')
FEEDS = ('coinbase_stream', 'coinbase_candles', 'polymarket_catalog', 'polymarket_book',
         'polymarket_reference', 'robinhood_reference')
REASONS = ('auth','rate_limit','http_4xx','http_5xx','transport','invalid','retry','write')


def varint(value):
    encoded = bytearray()
    while value > 127:
        encoded.append(128 | (value & 127))
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def field(number, value):
    return varint(number * 8 + 2) + varint(len(value)) + value


def encode(samples):
    """Prometheus WriteRequest v1, packed in a single raw Snappy literal."""
    series = []
    for name, value, at, labels in samples:
        if not math.isfinite(value):
            raise ValueError('non-finite metric')
        tags = sorted(dict(labels, __name__=name).items())
        label_bytes = b''.join(field(1, field(1,k.encode()) + field(2,v.encode())) for k,v in tags)
        sample = b'\x09' + struct.pack('<d',value) + b'\x10' + varint(round(at * 1000))
        series.append(field(1, label_bytes + field(2,sample)))
    data = b''.join(series)
    length = len(data) - 1
    width = (length.bit_length()+7)//8
    literal = bytes([length << 2]) if length < 60 else bytes([(59 + width) << 2]) + length.to_bytes(width, 'little')
    return varint(len(data)) + literal + data


def send(samples):
    user = os.environ['GRAFANA_METRICS_USER']
    token = (Path(os.environ['CREDENTIALS_DIRECTORY'])/'metrics-write').read_text().strip()
    auth = base64.b64encode((user+':'+token).encode()).decode()
    connection = http.client.HTTPSConnection(METRICS_HOST, timeout=6)
    try:
        connection.request('POST','/api/prom/push',encode(samples),headers={
            'Authorization':'Basic '+auth,'Content-Type':'application/x-protobuf',
            'Content-Encoding':'snappy','X-Prometheus-Remote-Write-Version':'0.1.0'})
        status = connection.getresponse().status
        if not 200 <= status < 300:
            raise RuntimeError('remote_write_http_'+str(status))
    finally:
        connection.close()


def collect(snapshot, at, previous, elapsed):
    common = {'host':HOST, 'origin':ORIGIN}
    rows = []
    def emit(name,value,labels=common,observed=at):
        if value is not None:
            rows.append((name,float(value),observed,labels))

    emit('pp_benchmark_metrics_heartbeat',1)
    valid = bool(snapshot and snapshot.get('origin')==ORIGIN and
                 0 <= at-snapshot['observed_at'] < 10)
    emit('pp_benchmark_monitor_api_up',valid)
    emit('pp_benchmark_monitor_api_request_seconds',elapsed)
    if not valid:
        return rows
    refreshed = snapshot.get('windows')
    emit('pp_benchmark_monitor_database_sample_ok',refreshed is not None)
    for w in refreshed or ():
        stamp = w['observed_at']
        if not 0 <= at-stamp < 45 or w['slot'] not in ('A','B'):
            continue
        tags = dict(common,slot=w['slot'],generation=w['generation'])
        for metric,key in [('pp_archive_pending_rows','pending'),('pp_archive_acknowledged_rows_total','acknowledged'),
                           ('pp_archive_oldest_pending_age_seconds','oldest_age')]:
            emit(metric,w[key],tags,stamp)
        prev = previous.get(w['generation'])
        if prev and w['acknowledged'] is not None and stamp > prev[0] and w['acknowledged'] >= prev[1]:
            emit('pp_archive_ack_rate',(w['acknowledged']-prev[1])/(stamp-prev[0]),tags,stamp)
        if w['acknowledged'] is not None:
            previous[w['generation']] = (stamp,w['acknowledged'])
        else:
            previous.pop(w['generation'],None)
        if not w['current']:
            continue
        emit('pp_collector_enabled',w['enabled'],tags,stamp)
        emit('pp_benchmark_active_window',1,tags,stamp)
        saved_at = snapshot.get('database_quote_received_at')
        if saved_at:
            emit('pp_collector_last_quote_receipt_timestamp_seconds',datetime.fromisoformat(saved_at).timestamp(),tags)
        counts = snapshot.get('quote_counts') or {}
        emit('pp_benchmark_session_saved_quotes',counts.get('saved'),tags)
        for source in SOURCES:
            desired = snapshot.get('feed_enabled',{}).get(source)
            if type(desired) is bool:
                emit('pp_benchmark_feed_expected',int(desired),dict(tags,source=source))
            for basis in ('provider','pp_receipt'):
                age = snapshot['reference_age'].get(source,{}).get(basis)
                if age is not None and age >= 0:
                    emit('tradebot_btc_feed_age_seconds',age,dict(tags,source=source,basis=basis),snapshot['observed_at'])
        health = snapshot.get('source_health')
        if health and 0 <= at-health['observed_at'] <= 60:
            emit('pp_benchmark_source_monitor_up',1,tags)
            for feed in FEEDS:
                for reason in REASONS:
                    emit('pp_benchmark_source_events_total',health['counts'].get(feed+'/'+reason,0),
                         dict(tags,feed=feed,reason=reason))
    # Keep only the active and still-attached generations between rounds.
    if refreshed is not None:
        observed = {w['generation'] for w in refreshed}
        for generation in previous.keys()-observed:
            del previous[generation]
    return rows


def run(once=False, dry_run=False):
    opener = build_opener(ProxyHandler({}))
    previous = {}
    while True:
        start = time.monotonic()
        try:
            with opener.open(LOCAL_URL,timeout=3) as response:
                body = response.read(65537)
            snapshot = json.loads(body) if len(body) <= 65536 else None
        except (OSError,ValueError):
            snapshot = None
        rows = collect(snapshot,time.time(),previous,time.monotonic()-start)
        try:
            if dry_run:
                print(json.dumps(rows))
            else:
                send(rows)
        except (OSError,RuntimeError) as e:
            print('benchmark_metrics_write_failed',str(e) if type(e) is RuntimeError else type(e).__name__,flush=True)
            if once:
                return 1
        if once:
            return 0
        time.sleep(max(0,15-(time.monotonic()-start)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--dry-run',action='store_true',help='print observed measurements without transmitting')
    args=parser.parse_args()
    sys.exit(run(args.once,args.dry_run))
