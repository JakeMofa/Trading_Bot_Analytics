"""Reconstructible RAM view with publication-time market and source-age guards."""
from copy import deepcopy
from threading import RLock

from .calculation import baseline
from .domain import timestamp, utcnow


class LiveState:
    def __init__(self, settings, clock=utcnow):
        self.settings, self.clock = settings, clock
        self._lock = RLock()
        self._market = None
        self._price = None
        self._quote = None
        self._snapshot = None
        self._forecast = None
        self._revision = 0
        self._updated_at = None
        self._storage_status = 'starting'

    def discover(self, market):
        with self._lock:
            old = self._market
            self._market = deepcopy(market)
            if (old or {}).get('id') != (market or {}).get('id'):
                self._quote = self._snapshot = self._forecast = None
            self._touch()

    def _touch(self):
        self._revision += 1
        self._updated_at = self.clock().isoformat()

    def storage_status(self, value):
        with self._lock:
            if value != self._storage_status:
                self._storage_status = value
                self._touch()

    def publish(self, market_id, price, quote, snapshot, prediction):
        now = self.clock()
        with self._lock:
            market = self._market
            if not market or market['id'] != market_id or not timestamp(market['start']) <= now < timestamp(market['end']):
                return False
            if price and timestamp(price['source_time']) <= now and timestamp(price['received_at']) <= now:
                # Reordered reads cannot rewind the latest accepted event.
                if self._price is None or timestamp(price['source_time']) >= timestamp(self._price['source_time']):
                    self._price = deepcopy(price)
            if (quote and quote.get('market_id') == market_id and quote.get('source_time')
                    and timestamp(quote['source_time']) <= now and timestamp(quote['received_at']) <= now
                    and (self._quote is None or timestamp(quote['source_time']) >= timestamp(self._quote['source_time']))):
                self._quote = deepcopy(quote)
            if snapshot and snapshot['market_id'] == market_id and 0 <= (now-timestamp(snapshot['as_of'])).total_seconds() <= 30:
                if self._snapshot is None or timestamp(snapshot['as_of']) >= timestamp(self._snapshot['as_of']):
                    self._snapshot = deepcopy(snapshot)
                    self._forecast = deepcopy(prediction) if prediction and prediction['market_id'] == market_id else None
            self._touch()
            return True

    def snapshot(self):
        now = self.clock()
        with self._lock:
            market, price, quote, feature, saved = deepcopy((self._market, self._price, self._quote, self._snapshot, self._forecast))
            active = bool(market and timestamp(market['start']) <= now < timestamp(market['end']))
            if market:
                market['seconds_remaining'] = max(0, (timestamp(market['end'])-now).total_seconds())
                market['active'] = active
            feeds = {}
            missing = []
            if not active:
                missing.append('active_market')
            elif market.get('target_usd') is None:
                missing.append('price_to_beat')
            for name, observation in [('coinbase', price), ('polymarket', quote)]:
                age = (now-timestamp(observation['source_time'])).total_seconds() if observation and observation.get('source_time') else None
                match = name == 'coinbase' or bool(observation and observation.get('market_id') == (market or {}).get('id'))
                status = 'fresh' if age is not None and 0 <= age <= 30 and match and active else 'stale' if observation else 'missing'
                feeds[name+'_stream'] = {'source': name+'_stream', 'status': status,
                                        'last_data_at': (observation or {}).get('source_time'),
                                        'received_at': (observation or {}).get('received_at'),
                                        'age_seconds': age, 'market_match': match, 'reconnects': None}
                if observation:
                    observation['age_seconds'] = age
                    observation['status'] = status
                if status != 'fresh':
                    missing.append(name+'_price' if name == 'coinbase' else 'polymarket_quote')
            feature_fresh = feature and active and feature['market_id'] == market['id'] and 0 <= (now-timestamp(feature['as_of'])).total_seconds() <= 30
            if not feature_fresh:
                feature = saved = None
                missing.append('feature_snapshot')
            if saved and (not active or saved['market_id'] != market['id'] or not 0 <= (now-timestamp(saved['as_of'])).total_seconds() <= 30):
                saved = None
            estimate = None
            if feature and price and active:
                values = deepcopy(feature['values'])
                values.update(reference_price_usd=price['price_usd'], seconds_remaining=market['seconds_remaining'])
                quality = deepcopy(feature['quality'])
                quality['price']['status'] = feeds['coinbase_stream']['status']
                # Candle freshness advances even when no new persisted snapshot arrives.
                age = quality.get('candle_age_seconds')
                if age is not None and age + (now-timestamp(feature['as_of'])).total_seconds() >= 120:
                    quality['candle_status'] = 'missing_or_stale'
                probability, reason = baseline(values, quality)
                estimate = {'model_version': 'gaussian_distance_v1', 'market_id': market['id'],
                            'probability_up': probability, 'probability_down': None if probability is None else 1-probability,
                            'abstain_reason': reason, 'as_of': price['source_time'],
                            'snapshot_as_of': feature['as_of'], 'source': 'live_state_ram'}
            # Keep the diagnostic last price visible with its age; never expose it as a fresh estimate.
            return {**self.settings.public(), 'generated_at': now.isoformat(), 'updated_at': self._updated_at,
                    'revision': self._revision, 'storage_status': self._storage_status,
                    'market': market, 'coinbase': price, 'polymarket': quote if active else None,
                    'feature_snapshot': feature, 'forecast': saved,
                    'models': {saved['model_version']: saved} if saved else {}, 'live_estimate': estimate,
                    'trade_flow': None, 'order_book': None, 'derivatives': None,
                    'feeds': feeds, 'missing_data': missing + ['trade_flow', 'btc_order_book']}
