"""Pure read-only feed translation for the future PP live collector.

These functions do not open a feed, enable collection, or write a database.
Original wire values remain in raw_payload and source_time.
"""
from datetime import datetime, timezone

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


def coinbase_closed_candle(row, received_at):
    """Map one completed Exchange 60-second bucket without inventing gaps."""
    source_timestamp(received_at)
    if not isinstance(row, list) or len(row) != 6:
        raise ValueError('invalid Coinbase candle shape')
    second, low, high, opened, closed, volume = row
    if isinstance(second, bool) or not isinstance(second, int) or second % 60:
        raise ValueError('Coinbase candle time must be an aligned minute')
    values = [exact_decimal(value) for value in (low, high, opened, closed, volume)]
    if any(value <= 0 for value in values[:4]) or values[4] < 0:
        raise ValueError('invalid Coinbase candle values')
    if not values[0] <= values[2] <= values[1] or not values[0] <= values[3] <= values[1]:
        raise ValueError('Coinbase candle OHLC is inconsistent')
    at = datetime.fromtimestamp(second, timezone.utc).isoformat()
    payload = {'time': second, 'granularity': 60,
               'low': str(low), 'high': str(high), 'open': str(opened),
               'close': str(closed), 'volume': str(volume)}
    return {'source': 'coinbase', 'event_id': 'exchange-candle-60-' + str(second),
            'kind': 'candle', 'symbol': 'BTC-USD', 'source_time': at,
            'received_at': received_at, 'payload': payload,
            'raw_payload': canonical_json(row),
            'provenance': {**PROVENANCE, 'feed': 'coinbase_exchange_rest_candles',
                           'source_time_role': 'bucket_start_not_last_trade',
                           'price_role': 'reference_not_settlement'}}


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
            # Each REST response is a distinct observation, even when the
            # book and its last trade sample are unchanged between polls.
            'event_id': 'bbo-' + market_event['market_id'] + '-' + content_hash([raw, received_at]),
            'kind': 'quote', 'market_id': market_event['market_id'],
            'source_time': original, 'received_at': received_at,
            'payload': payload, 'raw_payload': canonical_json(raw),
            'provenance': {**PROVENANCE, 'feed': 'polymarket_us_bbo',
                           'source_time_role': 'last_price_sample_not_book_update',
                           'quote_prices_are_probabilities': False}}
