"""Pure read-only feed translation for the future PP live collector.

These functions do not open a feed, enable collection, or write a database.
Original wire values remain in raw_payload and source_time.
"""
from .contract import exact_decimal, source_timestamp, content_hash


PROVENANCE = {
    'data_mode': 'pp_live',
    'collector': 'polymarket_us_btc_15m_v1',
}


def coinbase_ticker(message, received_at):
    """Map an Exchange BTC-USD ticker to one immutable PostgreSQL price event."""
    if message.get('type') != 'ticker' or message.get('product_id') != 'BTC-USD':
        return None
    trade_id = message.get('trade_id')
    if isinstance(trade_id, bool) or not isinstance(trade_id, (str, int)) or not str(trade_id):
        raise ValueError('ticker trade identity required')
    original, _ = source_timestamp(message.get('time'))
    source_timestamp(received_at)
    price = message.get('price')
    if exact_decimal(price) <= 0:
        raise ValueError('ticker price must be positive')
    size = message.get('last_size')
    if size is not None and exact_decimal(size) < 0:
        raise ValueError('ticker size must be nonnegative')
    return {
        'source': 'coinbase', 'event_id': 'exchange-trade-' + str(trade_id),
        'kind': 'price', 'symbol': 'BTC-USD', 'source_time': original,
        'received_at': received_at, 'price': str(price),
        'size': None if size is None else str(size), 'payload': message,
        'raw_payload': message,
        'provenance': {**PROVENANCE, 'feed': 'coinbase_exchange_ws',
                       'price_role': 'reference_not_settlement'},
    }


def polymarket_market(raw, received_at):
    """Map an official US BTC 15-minute market; omit unrelated markets."""
    source_timestamp(received_at)
    terms = raw.get('assetPriceTerms') or {}
    if (terms.get('asset') or {}).get('symbol', '').lower() != 'btc' or \
            terms.get('marketType') != 'ASSET_PRICE_MARKET_TYPE_UP_DOWN' or terms.get('horizon') != '15m':
        return None
    start, start_epoch = source_timestamp(terms['windowStart'])
    end, end_epoch = source_timestamp(terms['windowEnd'])
    if end_epoch - start_epoch != 900:
        raise ValueError('market window must be exactly 15 minutes')
    market_id, slug = raw.get('id'), raw.get('slug')
    if not isinstance(market_id, (str, int)) or not str(market_id) or not isinstance(slug, str) or not slug:
        raise ValueError('market identity required')
    target = terms.get('priceToBeat')
    if isinstance(target, dict):
        target = target.get('value')
    if target is not None and exact_decimal(target) <= 0:
        raise ValueError('target price must be positive')
    updated = raw.get('updatedAt')
    if updated is not None:
        source_timestamp(updated)
    payload = {'slug': slug, 'start': start, 'end': end, 'duration': 900,
               'target_usd': None if target is None else str(target),
               'status': raw.get('status'), 'index_symbol': terms.get('indexSymbol'),
               'rules': raw.get('description')}
    if not isinstance(payload['status'], str) or not payload['status']:
        raise ValueError('market status required')
    return {
        'source': 'polymarket_us',
        'event_id': 'market-' + str(market_id) + '-' + content_hash(raw),
        'kind': 'market', 'market_id': str(market_id),
        'source_time': updated, 'received_at': received_at,
        'payload': payload, 'raw_payload': raw,
        'provenance': {**PROVENANCE, 'feed': 'polymarket_us_rest',
                       'source_time_present': updated is not None},
    }
