"""Read-only postflight for the exact first quote identified by the Benchmark trace."""
import argparse
from datetime import datetime, timezone
import json

from .archive_codec import encoded, sha256, wire
from .cloud_origin_binding import DISPLAY_ORIGIN, DISPLAY_READER
from .cloud_runtime_profile import cloud_files
from .config import Settings
from .domain import canonical, digest
from .history_v2_transport import HistoryV2PostgresTransport
from .pp_history_connection import PPHistoryConnectionFactory
from .store import Store


def verify(store, generation, market, event_id, expected_hash, reader_factory):
    if (store.settings.environment, store.settings.data_mode, store.origin) != (
            'preprod', 'pp_live', DISPLAY_ORIGIN):
        raise ValueError('exact display origin required')
    with store.connection(readonly=True) as db:
        row = db.execute("""SELECT content_hash,payload,received_at FROM raw.events
            WHERE origin_id=%s AND generation_id=%s AND market_id=%s AND event_id=%s
              AND kind='quote' AND source='polymarket_us'""",
            (DISPLAY_ORIGIN, generation, market, event_id)).fetchone()
        if (not row or row['content_hash'] != expected_hash
                or row['payload'].get('provenance', {}).get('feed') != 'polymarket_us_websocket'):
            raise ValueError('local WebSocket quote identity mismatch')
        evidence = digest([DISPLAY_ORIGIN, 'polymarket_us', event_id, expected_hash])
        outbox = db.execute("""SELECT id,origin_id,generation_id,entity_type,entity_id,
            content_hash,payload,acknowledged_at FROM ops.outbox
            WHERE origin_id=%s AND generation_id=%s AND entity_type='core.protected_evidence'
              AND entity_id=%s AND content_hash=%s""",
            (DISPLAY_ORIGIN, generation, canonical([DISPLAY_ORIGIN, evidence]), expected_hash)).fetchone()
        if not outbox or outbox['acknowledged_at'] is None:
            raise ValueError('verified archive acknowledgement pending')
        acknowledged = outbox.pop('acknowledged_at')
        stored = outbox['payload']
        if (stored['event_id'] != event_id or stored['market_id'] != market
                or stored['payload']['data'] != row['payload']['data']):
            raise ValueError('outbox differs from local quote')
    page = [wire(outbox)]
    reader = HistoryV2PostgresTransport(reader_factory, origin_id=DISPLAY_ORIGIN,
        generation_id=generation, expected_database='postgres', expected_role=DISPLAY_READER,
        retain_revisions=True, sync_barriers=True)
    hosted = reader.read_structured_authenticated(page, max_bytes=256*1024, timeout_seconds=15)
    if encoded(page) != encoded(hosted):
        raise ValueError('hosted quote differs from acknowledged envelope')
    return {'origin_id': DISPLAY_ORIGIN, 'generation_id': generation, 'event_id': event_id,
            'market_id': market, 'content_hash': expected_hash, 'outbox_id': page[0]['id'],
            'envelope_sha256': sha256(encoded(page)), 'received_at': row['received_at'].isoformat(),
            'worker_acknowledged_at': acknowledged.isoformat(), 'independent_readback_at':
            datetime.now(timezone.utc).isoformat(), 'best_bid': row['payload']['data'].get('best_bid'),
            'best_ask': row['payload']['data'].get('best_ask')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('generation', 'market', 'event-id', 'content-hash'):
        parser.add_argument('--'+arg, required=True)
    args = parser.parse_args()
    files = cloud_files(DISPLAY_ORIGIN, reader=True)
    reader = PPHistoryConnectionFactory(files['TRADEBOT_PP_HISTORY_DSN_FILE'],
        files['TRADEBOT_PP_HISTORY_CA_FILE'], origin_id=DISPLAY_ORIGIN, reader=True)
    result = verify(Store(Settings.from_env()), args.generation, args.market,
                    args.event_id, args.content_hash, reader)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
