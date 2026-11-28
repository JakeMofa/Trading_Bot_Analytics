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


class QuoteContractError(ValueError):
    def __init__(self, category, message):
        self.category = category
        super().__init__(message)


def _quote_price(item):
    if item is None:
        return None
    amount = item.get('value') if isinstance(item, dict) else item
    try:
        number = exact_decimal(amount)
        if not 0 <= number <= 1:
            raise ValueError('outside unit interval')
    except ValueError:
        raise QuoteContractError('invalid_quote', 'invalid unit interval quote') from None
    return str(amount)


def _book_level(data, side):
    levels = data.get(side, [])
    if not isinstance(levels, list):
        raise QuoteContractError('invalid_quote', 'invalid order book side')
    levels_by_price = []
    for level in levels:
        if not isinstance(level, dict) or level.get('px') is None:
            raise QuoteContractError('invalid_quote', 'order book level lacks price')
        price = _quote_price(level['px'])
        qty = level.get('qty')
        if qty is not None:
            qty = str(exact_decimal(qty))
            if exact_decimal(qty) < 0:
                raise QuoteContractError('invalid_quote', 'negative book quantity')
        levels_by_price.append((price, qty))
    best = max if side == 'bids' else min
    return best(levels_by_price, key=lambda level: exact_decimal(level[0])) if levels_by_price else (None, None)


def polymarket_bbo(raw, market_event, received_at, *, route='bbo'):
    """Return a matching official quote, or None for a recognized empty book."""
    source_timestamp(received_at)
    data = raw.get('marketData') if isinstance(raw, dict) else None
    if not isinstance(data, dict) or data.get('marketSlug') != market_event['payload']['slug']:
        raise QuoteContractError('identity_mismatch', 'BBO market identity mismatch')
    book = route == 'book' and not any(k in data for k in ('bestBid', 'bestAsk'))
    if book:
        bid, bid_qty = _book_level(data, 'bids')
        ask, ask_qty = _book_level(data, 'offers')
        original = data.get('transactTime')
        time_role = 'order_book_transaction_time'
    else:
        bid = _quote_price(data.get('bestBid'))
        ask = _quote_price(data.get('bestAsk'))
        sample = data.get('lastPriceSample')
        if sample is not None and not isinstance(sample, dict):
            raise QuoteContractError('invalid_source_time', 'invalid BBO price sample')
        original = (sample or {}).get('ts')
        time_role = 'last_price_sample_not_book_update'
    if original is not None:
        try:
            source_timestamp(original)
        except ValueError:
            raise QuoteContractError('invalid_source_time', 'invalid quote source timestamp') from None
    payload = {'slug': data['marketSlug'], 'best_bid': bid, 'best_ask': ask,
               'long_quote': _quote_price(data.get('longQuote')),
               'short_quote': _quote_price(data.get('shortQuote')), 'up_probability': None,
               'down_probability': None}
    if book:
        payload.update(best_bid_qty=bid_qty, best_ask_qty=ask_qty)
    if bid is None and ask is None:
        # Protobuf JSON can omit unpopulated fields. Require an actual venue
        # state or explicit price/level fields before interpreting empty sides.
        if data.get('state') == 'MARKET_STATE_OPEN' or any(
                key in data for key in (('bids', 'offers') if book else ('bestBid', 'bestAsk'))):
            return None
        raise QuoteContractError('invalid_quote', 'unrecognized empty quote response')
    return {'source': 'polymarket_us',
            'event_id': 'bbo-' + market_event['market_id'] + '-' + content_hash([raw, received_at]),
            'kind': 'quote', 'market_id': market_event['market_id'],
            'source_time': original, 'received_at': received_at,
            'payload': payload, 'raw_payload': canonical_json(raw),
            'provenance': {**PROVENANCE, 'feed': 'polymarket_us_book' if book else 'polymarket_us_bbo',
                           'source_time_role': time_role, 'quote_prices_are_probabilities': False}}
