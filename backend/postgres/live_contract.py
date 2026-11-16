"""Pure read-only feed translation for the future PP live collector.

These functions do not open a feed, enable collection, or write a database.
Original wire values remain in raw_payload and source_time.
"""
from .contract import canonical_json, content_hash, exact_decimal, source_timestamp


PROVENANCE = {
    'data_mode': 'pp_live',
    'collector': 'polymarket_us_btc_15m_v1',
}


def coinbase_ticker(message, received_at, raw_wire=None):
    """Map an Exchange BTC-USD ticker to one immutable PostgreSQL price event."""
    if message.get('type') != 'ticker' or message.get('product_id') != 'BTC-USD':
        return None
    if raw_wire is not None and not isinstance(raw_wire, str):
        raise ValueError('ticker raw wire must be text')
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
        'raw_payload': raw_wire if raw_wire is not None else canonical_json(message),
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
        'payload': payload, 'raw_payload': canonical_json(raw),
        'provenance': {**PROVENANCE, 'feed': 'polymarket_us_rest',
                       'source_time_present': updated is not None},
    }


def polymarket_bbo(raw, market_event, received_at):
    """Preserve one US market BBO without calling its prices probabilities."""
    source_timestamp(received_at)
    data = raw.get('marketData') if isinstance(raw, dict) else None
    if not isinstance(data, dict) or data.get('marketSlug') != market_event['payload']['slug']:
        raise ValueError('BBO market identity mismatch')
    sample = data.get('lastPriceSample') or {}
    original = sample.get('ts') if isinstance(sample, dict) else None
    if original is not None:
        source_timestamp(original)
    def value(name):
        item = data.get(name)
        if item is None:
            return None
        amount = item.get('value') if isinstance(item, dict) else item
        number = exact_decimal(amount)
        if not 0 <= number <= 1:
            raise ValueError('BBO quote outside unit interval')
        return str(amount)
    payload = {'slug': data['marketSlug'], 'best_bid': value('bestBid'),
               'best_ask': value('bestAsk'), 'long_quote': value('longQuote'),
               'short_quote': value('shortQuote'), 'up_probability': None,
               'down_probability': None}
    if payload['best_bid'] is None and payload['best_ask'] is None:
        raise ValueError('BBO has no bid or ask')
    return {'source': 'polymarket_us',
            'event_id': 'bbo-' + market_event['market_id'] + '-' + content_hash(raw),
            'kind': 'quote', 'market_id': market_event['market_id'],
            'source_time': original, 'received_at': received_at,
            'payload': payload, 'raw_payload': canonical_json(raw),
            'provenance': {**PROVENANCE, 'feed': 'polymarket_us_bbo',
                           'source_time_role': 'last_price_sample_not_book_update',
                           'quote_prices_are_probabilities': False}}
