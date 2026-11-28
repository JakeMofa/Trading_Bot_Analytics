"""Reconstructible RAM view with publication-time market and source-age guards."""
import asyncio
from copy import deepcopy
from threading import RLock

from .calculation import baseline
from .domain import timestamp, utcnow, decimal_text
from .contract import source_timestamp


class LiveState:
    def __init__(self, settings, clock=utcnow):
        self.settings, self.clock = settings, clock
        self._lock = RLock()
        self._market = None
        self._price = None
        self.first_quote_signal = asyncio.Event()
        self._display = None
        self._archived = None
        self._quote = None
        self._snapshot = None
        self._forecast = None
        self._revision = 0
        self._updated_at = None
        self._storage_status = 'starting'
        self._collector = deepcopy(settings.public()['collector'])

    def display(self, packet):
        with self._lock:
            old = self._display
            first = packet['quote'] and (not old or not old['quote']
                                         or old['market']['id'] != packet['market']['id'])
            self._display = deepcopy(packet)
            if first:
                from .boundary_trace import boundary_trace
                boundary_trace('api_publication', reader='dashboard_live',
                               event_id=packet['quote']['event_id'], market_id=packet['market']['id'])
                signal = self.first_quote_signal
                self.first_quote_signal = asyncio.Event()
                signal.set()
            self._touch()

    def archive_count(self, started_at, count):
        with self._lock:
            self._archived = (started_at, count)

    def collector_status(self, enabled: bool | None):
        """A database lease is observable; process liveness is not visible here."""
        if self.settings.data_mode != 'pp_live':
            return
        value = {'enabled': enabled, 'running': None,
                 'error': None if enabled is not None else 'unavailable'}
        with self._lock:
            if value != self._collector:
                self._collector = value
                self._touch()

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

    def publish_price(self, price):
        """Gap-only Coinbase publication; never mutates an active-market bundle.

        Source spelling and exact decimals stay intact. Stale input may remain
        diagnostic, but reads cannot make it fresh or create a forecast.
        """
        now = self.clock()
        with self._lock:
            market = self._market
            if market and timestamp(market['start']) <= now < timestamp(market['end']):
                return False  # Discovery won the race; await atomic hydrate.
            try:
                if not price or price.get('origin') != self.settings.origin_id or price.get('source') != 'coinbase':
                    return False
                decimal_text(price['price_usd'],positive=True)
                cutoff = source_timestamp(now.isoformat())[1]
                source, received, available = (source_timestamp(price[key])[1]
                    for key in ('source_time','received_at','available_at'))
                if max(source,received,available) > cutoff:
                    return False
                if self._price is not None:
                    old = tuple(source_timestamp(self._price[key])[1] for key in ('source_time','received_at'))
                    if (source,received) <= old:
                        return False
            except (ValueError,TypeError,KeyError):
                return False
            self._price = deepcopy(price)
            self._touch()
            return True

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
            if quote and quote.get('market_id') == market_id:
                rest_book = self.settings.data_mode == 'pp_live'
                order_key = 'received_at' if rest_book else 'source_time'
                if (quote.get(order_key) and timestamp(quote['received_at']) <= now
                        and (not quote.get('source_time') or timestamp(quote['source_time']) <= now)
                        and (self._quote is None or timestamp(quote[order_key]) >= timestamp(self._quote[order_key]))):
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
            packet = self._display
            hydrated_quote_id = (quote or {}).get('event_id')
            reference = deepcopy((packet or {}).get('reference'))
            if reference:
                age = (now - timestamp(reference['source_time'])).total_seconds()
                reference['status'] = 'fresh' if 0 <= age <= 10 else 'stale'
            counters = None
            if packet:
                live = packet['market']
                archive = self._archived
                counters = {key: packet[key] for key in ('received', 'saved', 'duplicates', 'started_at', 'last_commit')}
                counters['archived'] = archive[1] if archive and archive[0] == packet['started_at'] else None
                if timestamp(live['start']) <= now < timestamp(live['end']):
                    if (market or {}).get('id') != live['id']:
                        quote = feature = saved = None
                    market = {**(market if market and market['id'] == live['id'] else {}), **live}
                    preview = packet['quote']
                    if preview and (not quote or timestamp(preview['received_at']) >= timestamp(quote['received_at'])):
                        quote = deepcopy(preview)
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
                rest_book = name == 'polymarket' and self.settings.data_mode == 'pp_live'
                observed_at = observation.get('received_at') if rest_book and observation else None
                freshness_at = observed_at or (observation.get('source_time') if observation else None)
                age = (now-timestamp(freshness_at)).total_seconds() if freshness_at else None
                match = name == 'coinbase' or bool(observation and observation.get('market_id') == (market or {}).get('id'))
                status = 'fresh' if age is not None and 0 <= age <= 30 and match and (name == 'coinbase' or active) else 'stale' if observation else 'missing'
                feed_name = 'coinbase_stream' if name == 'coinbase' else 'polymarket_rest' if rest_book else 'polymarket_stream'
                if (observation or {}).get('provenance', {}).get('feed') == 'polymarket_us_websocket':
                    feed_name = 'polymarket_stream'
                feeds[feed_name] = {'source': feed_name, 'status': status,
                                        'freshness_basis': 'received_at' if rest_book else 'source_time',
                                        'last_data_at': freshness_at,
                                        'received_at': (observation or {}).get('received_at'),
                                        'source_sample_at': (observation or {}).get('source_time') if rest_book else None,
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
            return {**self.settings.public(), 'collector': deepcopy(self._collector),
                    'polymarket_reference': reference, 'quote_counts': counters, 'database_quote_id': hydrated_quote_id, 'generated_at': now.isoformat(), 'updated_at': self._updated_at,
                    'revision': self._revision, 'storage_status': self._storage_status,
                    'market': market, 'coinbase': price, 'polymarket': quote if active else None,
                    'feature_snapshot': feature, 'forecast': saved,
                    'models': {saved['model_version']: saved} if saved else {}, 'live_estimate': estimate,
                    'trade_flow': None, 'order_book': None, 'derivatives': None,
                    'feeds': feeds, 'missing_data': missing + ['trade_flow', 'btc_order_book']}
