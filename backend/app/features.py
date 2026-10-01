"""Versioned, read-only feature snapshots from data already saved in SQLite."""
from datetime import timezone
from decimal import Decimal
import json

from collector import amount, timestamp, utcnow

VERSION = 1
MAX_PRICE_AGE_SECONDS = 30
MAX_CANDLE_AGE_SECONDS = 60


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS feature_snapshots (
      id INTEGER PRIMARY KEY, market_id TEXT NOT NULL REFERENCES markets(id),
      as_of TEXT NOT NULL, version INTEGER NOT NULL,
      values_json TEXT NOT NULL, quality_json TEXT NOT NULL,
      evidence_json TEXT NOT NULL,
      UNIQUE(market_id, as_of, version));
    CREATE INDEX IF NOT EXISTS feature_snapshots_market_time
      ON feature_snapshots(market_id, as_of);
    ''')


def _dec(value):
    return Decimal(value) if value is not None else None


def _price(db, as_of):
    cutoff = as_of.isoformat()
    candidates = []
    for table, source, key in (('stream_events', 'coinbase_stream', 'event_id'),
                               ('reference_prices', 'coinbase_rest', 'id')):
        row = db.execute(f'''SELECT {key}, price, source_time, received_at FROM {table}
          WHERE source='coinbase' AND source_time IS NOT NULL
            AND julianday(source_time)<=julianday(?)
            AND julianday(received_at)<=julianday(?)
          ORDER BY julianday(source_time) DESC LIMIT 1''', (cutoff, cutoff)).fetchone()
        if row:
            age = (as_of - timestamp(row[2])).total_seconds()
            if age >= 0:
                candidates.append((timestamp(row[2]), source == 'coinbase_stream', source, row, age))
    if not candidates:
        return None, {'status': 'missing', 'source': None, 'source_time': None,
                      'age_seconds': None, 'input_id': None}
    _, _, source, row, age = max(candidates)
    status = 'fresh' if age <= MAX_PRICE_AGE_SECONDS else 'stale'
    return (_dec(row[1]) if status == 'fresh' else None), {
        'status': status, 'source': source, 'source_time': timestamp(row[2]).isoformat(),
        'age_seconds': age, 'input_id': str(row[0])}


def _candles(db, as_of):
    wanted = int(as_of.timestamp()) // 60 * 60 - 60
    rows = db.execute('''SELECT time,close,volume FROM candles
      WHERE first_seen IS NOT NULL AND julianday(first_seen)<=julianday(?)
        AND source='coinbase' AND symbol='BTC-USD' AND granularity=60
        AND time BETWEEN ? AND ? ORDER BY time''', (as_of.isoformat(), wanted-16*60, wanted)).fetchall()
    candles = {row[0]: (_dec(row[1]), _dec(row[2])) for row in rows}
    return max(candles) if candles else None, candles


def calculate(db, market_id, as_of=None):
    """Return values, quality and input references, without saving or network calls."""
    as_of = as_of or utcnow()
    if as_of.tzinfo is None:
        raise ValueError('as_of needs timezone')
    as_of = as_of.astimezone(timezone.utc)
    cutoff = as_of.isoformat()
    market = db.execute('''SELECT start,end,duration,first_seen FROM markets
      WHERE id=? AND duration=900 AND julianday(first_seen)<=julianday(?)''',
      (market_id, cutoff)).fetchone()
    if not market:
        return None
    start, end = timestamp(market[0]), timestamp(market[1])
    if not start <= as_of < end:
        return None
    metadata = db.execute('''SELECT id,received_at,payload FROM observations
      WHERE market_id=? AND kind='metadata' AND julianday(received_at)<=julianday(?)
      ORDER BY julianday(received_at) DESC,id DESC LIMIT 1''',
      (market_id, cutoff)).fetchone()
    if not metadata:
        return None
    terms = (json.loads(metadata[2]).get('assetPriceTerms') or {})
    target_text = amount(terms.get('priceToBeat'))
    target = _dec(target_text)
    price, price_info = _price(db, as_of)
    latest, candles = _candles(db, as_of)
    candle_age = as_of.timestamp() - (latest + 60) if latest is not None else None
    candle_usable = candle_age is not None and 0 <= candle_age < 2*MAX_CANDLE_AGE_SECONDS
    values = {
        'target_usd': target_text, 'reference_price_usd': str(price) if price is not None else None,
        'distance_usd': str(price-target) if price is not None and target is not None else None,
        'distance_pct': str((price/target-1)*100) if price is not None and target not in (None, 0) else None,
        'seconds_remaining': (end-as_of).total_seconds(),
        'return_1m': None, 'return_5m': None, 'return_15m': None,
        'realized_volatility_15m': None, 'volume_btc_5m': None, 'volume_btc_15m': None}
    if candle_usable:
        for minutes in (1, 5, 15):
            times = [latest-i*60 for i in range(minutes, -1, -1)]
            if all(t in candles and candles[t][0] is not None and candles[t][0] > 0 for t in times):
                closes = [candles[t][0] for t in times]
                values[f'return_{minutes}m'] = str(closes[-1]/closes[0]-1)
                if minutes == 15:
                    logs = [(closes[i]/closes[i-1]).ln() for i in range(1, len(closes))]
                    mean = sum(logs)/Decimal(len(logs))
                    values['realized_volatility_15m'] = str((sum((x-mean)**2 for x in logs)/Decimal(len(logs))).sqrt())
            if minutes in (5, 15):
                volume_times = [latest-i*60 for i in range(minutes-1, -1, -1)]
                if all(t in candles and candles[t][1] is not None for t in volume_times):
                    values[f'volume_btc_{minutes}m'] = str(sum(candles[t][1] for t in volume_times))
    candle_status = ('fresh' if candle_age is not None and candle_age < MAX_CANDLE_AGE_SECONDS
                     else 'lagging' if candle_usable else 'missing_or_stale')
    quality = {'price': price_info, 'candle_status': candle_status,
               'candle_age_seconds': candle_age,
               'missing_features': [key for key, value in values.items() if value is None],
               'late_join': timestamp(market[3]) > start}
    evidence = {'metadata_observation_id': metadata[0], 'metadata_received_at': metadata[1],
                'price': price_info, 'latest_completed_candle_time': latest,
                'candle_inputs': [{'time': t, 'close': str(candles[t][0]) if candles[t][0] is not None else None,
                                   'volume': str(candles[t][1]) if candles[t][1] is not None else None}
                                  for t in sorted(candles)]}
    return values, quality, evidence


def capture(db, as_of=None):
    """Save one snapshot for the active known 15-minute market, if any."""
    initialize(db)
    as_of = as_of or utcnow()
    if as_of.tzinfo is None:
        raise ValueError('as_of needs timezone')
    as_of = as_of.astimezone(timezone.utc)
    row = db.execute('''SELECT id FROM markets WHERE duration=900 AND status='MARKET_STATUS_OPEN'
      AND julianday(start)<=julianday(?) AND julianday(end)>julianday(?)
      AND julianday(first_seen)<=julianday(?) ORDER BY start DESC LIMIT 1''',
      (as_of.isoformat(),)*3).fetchone()
    if not row:
        return None
    result = calculate(db, row[0], as_of)
    if result is None:
        return None
    values, quality, evidence = result
    with db:
        db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,values_json,quality_json,evidence_json)
          VALUES(?,?,?,?,?,?) ON CONFLICT(market_id,as_of,version) DO NOTHING''',
          (row[0], as_of.isoformat(), VERSION, json.dumps(values), json.dumps(quality), json.dumps(evidence)))
    return row[0], values, quality
