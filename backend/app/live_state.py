"""In-memory current-state engine for the active BTC 15-minute market.

This module is deliberately storage-agnostic. Collectors may persist evidence to
SQLite, but the hot forecast path can read current state from this object without
querying SQLite on every update.
"""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from math import log
from statistics import pstdev
from threading import RLock

from collector import timestamp, utcnow

TICK_HISTORY_SECONDS = 60 * 60
RETURN_WINDOWS_SECONDS = (5, 10, 30, 60, 180, 300, 900)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('datetime must include timezone')
        return value.astimezone(timezone.utc).isoformat()
    return timestamp(str(value)).isoformat()


def _float(value):
    if value is None:
        return None
    try:
        return float(value.get('value') if isinstance(value, dict) else value)
    except (TypeError, ValueError):
        return None


class LiveState:
    """Thread-safe in-memory state used by collectors, models and the API layer."""

    def __init__(self, tick_history_seconds=TICK_HISTORY_SECONDS):
        if tick_history_seconds < 900:
            raise ValueError('tick history must retain at least 15 minutes')
        self.tick_history_seconds = int(tick_history_seconds)
        self._lock = RLock()
        self._market = None
        self._ticks = deque()
        self._polymarket = None
        self._feature_snapshot = None
        self._forecast = None
        self._models = {}
        self._feeds = {}
        self._updated_at = None

    def _touch(self, at=None):
        self._updated_at = _iso(at or utcnow())

    def set_market(self, market):
        """Set the active market and reset market-scoped derived state on rollover."""
        if not market:
            with self._lock:
                self._market = None
                self._polymarket = None
                self._feature_snapshot = None
                self._forecast = None
                self._models = {}
                self._touch()
            return
        required = ('id', 'slug', 'start', 'end')
        missing = [name for name in required if not market.get(name)]
        if missing:
            raise ValueError(f'market missing required fields: {missing}')
        normalized = {
            'id': str(market['id']),
            'slug': str(market['slug']),
            'start': _iso(market['start']),
            'end': _iso(market['end']),
            'target_usd': str(market['target_usd']) if market.get('target_usd') is not None
                          else str(market['target']) if market.get('target') is not None else None,
            'status': market.get('status'),
        }
        with self._lock:
            previous_id = self._market.get('id') if self._market else None
            self._market = normalized
            if previous_id != normalized['id']:
                self._polymarket = None
                self._feature_snapshot = None
                self._forecast = None
                self._models = {}
            self._touch()

    def market_identity(self):
        with self._lock:
            if not self._market:
                return None
            return self._market['id'], self._market['slug']

    def update_coinbase_ticker(self, message, received_at=None):
        if message.get('type') != 'ticker' or message.get('product_id') != 'BTC-USD':
            return False
        price = _float(message.get('price'))
        source_time = message.get('time')
        if price is None or price <= 0 or not source_time:
            raise ValueError('incomplete Coinbase ticker')
        source_dt = timestamp(source_time)
        event = {
            'event_id': str(message.get('trade_id')) if message.get('trade_id') is not None else None,
            'source_time': source_dt.isoformat(),
            'received_at': _iso(received_at or utcnow()),
            'price_usd': price,
            'size_btc': _float(message.get('last_size')),
            'side': message.get('side'),
        }
        with self._lock:
            self._ticks.append((source_dt.timestamp(), event))
            if len(self._ticks) > 1 and self._ticks[-2][0] > self._ticks[-1][0]:
                self._ticks = deque(sorted(self._ticks, key=lambda item: item[0]))
            cutoff = self._ticks[-1][0] - self.tick_history_seconds
            while self._ticks and self._ticks[0][0] < cutoff:
                self._ticks.popleft()
            self._touch(event['received_at'])
        return True

    def update_polymarket(self, message, received_at=None):
        data = message.get('marketData') or message.get('market_data')
        if not data:
            return False
        slug = data.get('marketSlug') or data.get('market_slug')
        with self._lock:
            if self._market and slug and slug != self._market['slug']:
                return False
        bids = data.get('bids') or []
        offers = data.get('offers') or []
        sample = (data.get('stats') or {}).get('lastPriceSample') or {}
        quote = {
            'slug': slug,
            'received_at': _iso(received_at or utcnow()),
            'source_time': data.get('transactTime') or data.get('transact_time'),
            'best_bid': _float((bids[0] or {}).get('px')) if bids else None,
            'best_ask': _float((offers[0] or {}).get('px')) if offers else None,
            'up_probability': _float(sample.get('longPx')),
            'down_probability': _float(sample.get('shortPx')),
            'sample_time': sample.get('ts'),
        }
        with self._lock:
            self._polymarket = quote
            self._touch(quote['received_at'])
        return True

    def set_feature_snapshot(self, market_id, as_of, values, quality, snapshot_id=None):
        with self._lock:
            if self._market and str(market_id) != self._market['id']:
                return False
            self._feature_snapshot = {
                'snapshot_id': snapshot_id,
                'market_id': str(market_id),
                'as_of': _iso(as_of),
                'values': deepcopy(values or {}),
                'quality': deepcopy(quality or {}),
            }
            self._touch(as_of)
        return True

    def set_forecast(self, model_version, probability_up=None, abstain_reason=None,
                     as_of=None, confidence=None, reasons=None):
        record = {
            'model_version': model_version,
            'probability_up': _float(probability_up),
            'probability_down': None if probability_up is None else 1 - float(probability_up),
            'abstain_reason': abstain_reason,
            'confidence': _float(confidence),
            'reasons': list(reasons or []),
            'as_of': _iso(as_of or utcnow()),
        }
        with self._lock:
            self._models[model_version] = record
            self._forecast = record
            self._touch(record['as_of'])
        return deepcopy(record)

    def update_feed_health(self, source, status, detail=None, updated_at=None,
                           last_data_at=None, reconnects=None):
        with self._lock:
            prior = self._feeds.get(source, {})
            self._feeds[source] = {
                'source': source,
                'status': status,
                'detail': detail,
                'updated_at': _iso(updated_at or utcnow()),
                'last_data_at': _iso(last_data_at) if last_data_at else prior.get('last_data_at'),
                'reconnects': int(reconnects if reconnects is not None
                                  else prior.get('reconnects', 0)),
            }
            self._touch(self._feeds[source]['updated_at'])

    def _return_locked(self, seconds):
        if not self._ticks:
            return None
        current_epoch, current = self._ticks[-1]
        cutoff = current_epoch - seconds
        base = None
        for epoch, event in self._ticks:
            if epoch <= cutoff:
                base = event
            else:
                break
        if not base or base['price_usd'] <= 0:
            return None
        return current['price_usd'] / base['price_usd'] - 1

    def _tick_volatility_locked(self, seconds=300):
        if len(self._ticks) < 3:
            return None
        end = self._ticks[-1][0]
        prices = [event['price_usd'] for epoch, event in self._ticks
                  if epoch >= end - seconds and event['price_usd'] > 0]
        if len(prices) < 3:
            return None
        returns = [log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
        return pstdev(returns) if len(returns) >= 2 else None

    def forecast_inputs(self, now=None):
        """Build baseline-compatible inputs from RAM only."""
        now = now or utcnow()
        if now.tzinfo is None:
            raise ValueError('now needs timezone')
        now = now.astimezone(timezone.utc)
        with self._lock:
            if not self._market or not self._ticks or not self._feature_snapshot:
                return None
            latest_epoch, latest = self._ticks[-1]
            target = _float(self._market.get('target_usd'))
            if target is None:
                target = _float(self._feature_snapshot['values'].get('target_usd'))
            if target is None:
                return None
            end = timestamp(self._market['end'])
            seconds_remaining = (end - now).total_seconds()
            if seconds_remaining <= 0:
                return None
            price_age = max(0.0, now.timestamp() - latest_epoch)
            saved_quality = deepcopy(self._feature_snapshot.get('quality') or {})
            quality = {
                'price': {
                    'status': 'fresh' if price_age <= 30 else 'stale',
                    'source': 'coinbase_stream_ram',
                    'source_time': latest['source_time'],
                    'age_seconds': price_age,
                },
                'candle_status': saved_quality.get('candle_status', 'missing_or_stale'),
                'candle_age_seconds': saved_quality.get('candle_age_seconds'),
                'late_join': saved_quality.get('late_join'),
            }
            values = deepcopy(self._feature_snapshot.get('values') or {})
            values.update({
                'target_usd': str(target),
                'reference_price_usd': str(latest['price_usd']),
                'distance_usd': str(latest['price_usd'] - target),
                'distance_pct': str((latest['price_usd'] / target - 1) * 100),
                'seconds_remaining': seconds_remaining,
            })
            for seconds in RETURN_WINDOWS_SECONDS:
                key = {
                    5: 'return_5s', 10: 'return_10s', 30: 'return_30s',
                    60: 'return_1m_live', 180: 'return_3m_live',
                    300: 'return_5m_live', 900: 'return_15m_live',
                }[seconds]
                values[key] = self._return_locked(seconds)
            values['tick_volatility_5m'] = self._tick_volatility_locked(300)
            return values, quality

    def baseline_forecast(self, now=None):
        """Evaluate gaussian_distance_v1 directly from RAM without a DB read."""
        inputs = self.forecast_inputs(now)
        if inputs is None:
            return None
        from forecasts import MODEL, baseline
        values, quality = inputs
        probability_up, reason = baseline(values, quality)
        return {
            'model_version': MODEL,
            'probability_up': probability_up,
            'probability_down': None if probability_up is None else 1 - probability_up,
            'abstain_reason': reason,
            'source': 'live_state_ram',
        }

    def snapshot(self, now=None):
        now = now or utcnow()
        if now.tzinfo is None:
            raise ValueError('now needs timezone')
        now = now.astimezone(timezone.utc)
        with self._lock:
            coinbase = None
            if self._ticks:
                epoch, latest = self._ticks[-1]
                coinbase = deepcopy(latest)
                coinbase['age_seconds'] = max(0.0, now.timestamp() - epoch)
                coinbase['returns'] = {
                    '5s': self._return_locked(5),
                    '10s': self._return_locked(10),
                    '30s': self._return_locked(30),
                    '1m': self._return_locked(60),
                    '3m': self._return_locked(180),
                    '5m': self._return_locked(300),
                    '15m': self._return_locked(900),
                }
                coinbase['tick_volatility_5m'] = self._tick_volatility_locked(300)
            market = deepcopy(self._market)
            if market:
                market['seconds_remaining'] = max(
                    0.0, (timestamp(market['end']) - now).total_seconds())
            return {
                'updated_at': self._updated_at,
                'market': market,
                'coinbase': coinbase,
                'polymarket': deepcopy(self._polymarket),
                'feature_snapshot': deepcopy(self._feature_snapshot),
                'forecast': deepcopy(self._forecast),
                'models': deepcopy(self._models),
                'feeds': deepcopy(self._feeds),
            }
