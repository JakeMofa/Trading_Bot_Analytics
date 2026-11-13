"""Storage-free port of deployed d56b4a7 features/gaussian_distance_v1.

Decimal candle arithmetic, complete-minute coverage and population log-return
volatility match the deployed model. Gaussian CDF alone uses floating point.
Exchange observations remain reference inputs, never official settlement.
"""
from decimal import Decimal
from math import erf, log, sqrt

from .domain import timestamp

MODEL = 'gaussian_distance_v1'
FEATURE_VERSION = 'features_v1'


def calculate(market, price, candles, as_of):
    as_of = timestamp(as_of)
    start, end = timestamp(market['start']), timestamp(market['end'])
    if not start <= as_of < end or timestamp(market['first_seen']) > as_of:
        return None
    target = Decimal(market['target_usd']) if market.get('target_usd') is not None else None
    price_info = {'status': 'missing', 'source': None, 'source_time': None, 'age_seconds': None, 'input_id': None}
    reference = None
    if price and timestamp(price['source_time']) <= as_of and timestamp(price['received_at']) <= as_of:
        age = (as_of - timestamp(price['source_time'])).total_seconds()
        price_info = {'status': 'fresh' if age <= 30 else 'stale', 'source': price['source'],
                      'source_time': price['source_time'], 'received_at': price['received_at'],
                      'age_seconds': age, 'input_id': price['event_id'],
                      'origin': price['origin'], 'provenance': price.get('provenance', {})}
        if age <= 30:
            reference = Decimal(price['price_usd'])
    wanted = int(as_of.timestamp()) // 60 * 60 - 60
    rows = {int(timestamp(row['start']).timestamp()): row for row in candles
            if row['source'] == 'coinbase' and row['symbol'] == 'BTC-USD' and row['granularity'] == 60
            and timestamp(row['received_at']) <= as_of
            and wanted-16*60 <= int(timestamp(row['start']).timestamp()) <= wanted}
    latest = max(rows) if rows else None
    candle_age = as_of.timestamp() - (latest + 60) if latest is not None else None
    usable = candle_age is not None and 0 <= candle_age < 120
    values = {'target_usd': str(target) if target is not None else None,
              'reference_price_usd': str(reference) if reference is not None else None,
              'distance_usd': str(reference-target) if reference is not None and target is not None else None,
              'distance_pct': str((reference/target-1)*100) if reference is not None and target not in (None, 0) else None,
              'seconds_remaining': (end-as_of).total_seconds(),
              'return_1m': None, 'return_5m': None, 'return_15m': None,
              'realized_volatility_15m': None, 'volume_btc_5m': None, 'volume_btc_15m': None}
    if usable:
        for minutes in (1, 5, 15):
            times = [latest-i*60 for i in range(minutes, -1, -1)]
            if all(t in rows and rows[t].get('close') is not None and Decimal(rows[t]['close']) > 0 for t in times):
                closes = [Decimal(rows[t]['close']) for t in times]
                values[f'return_{minutes}m'] = str(closes[-1]/closes[0]-1)
                if minutes == 15:
                    logs = [(closes[i]/closes[i-1]).ln() for i in range(1, len(closes))]
                    mean = sum(logs)/Decimal(len(logs))
                    values['realized_volatility_15m'] = str((sum((x-mean)**2 for x in logs)/Decimal(len(logs))).sqrt())
            if minutes in (5, 15):
                times = [latest-i*60 for i in range(minutes-1, -1, -1)]
                if all(t in rows and rows[t].get('volume') is not None for t in times):
                    values[f'volume_btc_{minutes}m'] = str(sum(Decimal(rows[t]['volume']) for t in times))
    quality = {'price': price_info,
               'candle_status': 'fresh' if candle_age is not None and candle_age < 60 else 'lagging' if usable else 'missing_or_stale',
               'candle_age_seconds': candle_age,
               'missing_features': [key for key, value in values.items() if value is None],
               'late_join': timestamp(market['first_seen']) > start}
    evidence = {'market': market, 'price': price_info, 'latest_completed_candle_time': latest,
                'candle_inputs': [rows[t] for t in sorted(rows)]}
    return values, quality, evidence


def baseline(values, quality):
    if quality['price']['status'] != 'fresh':
        return None, 'reference_price_not_fresh'
    if quality['candle_status'] not in ('fresh', 'lagging'):
        return None, 'completed_candles_missing_or_stale'
    required = ('target_usd', 'reference_price_usd', 'realized_volatility_15m', 'seconds_remaining')
    if any(values.get(name) is None for name in required):
        return None, 'required_feature_missing'
    target, price, sigma, seconds = [Decimal(str(values[name])) for name in required]
    if any(not number.is_finite() or number <= 0 for number in (target, price, sigma, seconds)):
        return None, 'invalid_or_zero_model_input'
    sigma_float = float(sigma)
    if sigma_float == 0:
        return None, 'volatility_below_float_precision'
    z = log(float(price/target)) / (sigma_float * sqrt(float(seconds/60)))
    probability = (1 + erf(z/sqrt(2))) / 2
    return min(1-1e-6, max(1e-6, probability)), None


def forecast(market, snapshot, now):
    now = timestamp(now)
    at = timestamp(snapshot['as_of'])
    if (snapshot['market_id'] != market['id'] or not timestamp(market['start']) <= at <= now < timestamp(market['end'])
            or (now-at).total_seconds() > 30):
        return None
    probability, reason = baseline(snapshot['values'], snapshot['quality'])
    return {'market_id': market['id'], 'model_version': MODEL, 'as_of': at.isoformat(),
            'probability_up': str(probability) if probability is not None else None,
            'probability_down': str(1-probability) if probability is not None else None,
            'seconds_remaining': snapshot['values']['seconds_remaining'], 'abstain_reason': reason,
            'experimental': True,
            'assumptions': {'status': 'untrained_uncalibrated_proxy',
                            'model': 'zero_drift_normal_log_return',
                            'volatility': 'population_stddev_of_15_completed_one_minute_log_returns',
                            'price_source': 'Coinbase BTC-USD reference; Polymarket settles via BRTI'}}
