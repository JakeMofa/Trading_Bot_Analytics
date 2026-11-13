"""Acknowledged PostgreSQL writes and bounded local reads.

Every acknowledgement follows transaction commit. Duplicate immutable identities
compare content; mutable projections only advance from newer source evidence.
No remote retrieval, SQLite fallback, implicit migration, or DDL occurs here.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from .domain import bound, canonical, decimal_text, digest, json_value, timestamp, utcnow


class IdentityConflict(ValueError):
    pass


class PublicationRejected(ValueError):
    pass


class StorageHold(RuntimeError):
    pass


class Store:
    def __init__(self, settings):
        self.settings = settings
        self.origin = settings.origin_id

    def connection(self, readonly=False):
        from .connection import connect
        return connect(self.settings.dsn, environment=self.settings.environment, readonly=readonly)

    def verify(self):
        from .migrate import validate_schema
        with self.connection(True) as db:
            validate_schema(db, self.settings.environment)

    @staticmethod
    def _insert(db, table, record, keys, immutable=True):
        from psycopg import sql
        from psycopg.types.json import Jsonb
        schema, name = table.split('.')
        values = [Jsonb(value) if isinstance(value, (dict, list)) else value for value in record.values()]
        query = sql.SQL('INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING RETURNING *').format(
            sql.Identifier(schema), sql.Identifier(name), sql.SQL(',').join(map(sql.Identifier, record)),
            sql.SQL(',').join(sql.Placeholder() for _ in record), sql.SQL(',').join(map(sql.Identifier, keys)))
        result = db.execute(query, values).fetchone()
        if result is None:
            result = db.execute(sql.SQL('SELECT * FROM {}.{} WHERE {}').format(sql.Identifier(schema), sql.Identifier(name),
                sql.SQL(' AND ').join(sql.SQL('{} = %s').format(sql.Identifier(key)) for key in keys)),
                [record[key] for key in keys]).fetchone()
            if immutable and result.get('content_hash') != record.get('content_hash'):
                raise IdentityConflict(f'conflicting immutable identity in {table}')
        return result

    def _outbox(self, db, table, row, keys, generation_id=None):
        from psycopg.types.json import Jsonb
        db.execute('''INSERT INTO ops.outbox(origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(origin_id,entity_type,entity_id,content_hash) DO NOTHING''',
                   (self.origin, generation_id, table, canonical([row[key] for key in keys]), row['content_hash'],
                    Jsonb(json_value(row)), utcnow()))

    def _admit(self, db, reserve):
        # Serialize admission across ingestion and calculation. Lifecycle acknowledgements
        # only reduce backlog, so they do not need this lock. A hold never deletes evidence.
        key = int(digest(['outbox-admission',self.origin])[:15],16)
        db.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
        maximum = self.settings.outbox_max_pending
        count = db.execute('''SELECT count(*) AS count FROM (SELECT 1 FROM ops.outbox WHERE origin_id=%s
            AND acknowledged_at IS NULL LIMIT %s) pending''',(self.origin,maximum+1)).fetchone()['count']
        if count+reserve > maximum:
            raise StorageHold('pending outbox bound reached; preserve local evidence until verified sync')

    def ingest(self, event):
        """Persist one normalized generated/replay event and derived projections."""
        from .contract import source_timestamp
        from psycopg.types.json import Jsonb
        event = dict(event)
        if event.get('provenance', {}).get('data_mode') != self.settings.data_mode:
            raise ValueError('input provenance data_mode does not match isolated runtime')
        if event.get('origin_id', self.origin) != self.origin:
            raise ValueError('input origin mismatch')
        for key in ('source', 'event_id', 'kind', 'received_at', 'payload'):
            if key not in event:
                raise ValueError(f'missing {key}')
        for key in ('source','event_id'):
            if not str(event[key]):
                raise ValueError(f'empty {key}')
            event[key] = str(event[key])
        if event['kind'] not in ('market', 'price', 'candle', 'quote', 'outcome'):
            raise ValueError('unsupported event kind')
        source_time = event.get('source_time')
        original, epoch = source_timestamp(source_time) if source_time is not None else (None, None)
        received = timestamp(event['received_at'])
        available = timestamp(event.get('available_at', event['received_at']))
        if available < received:
            raise ValueError('availability cannot precede receipt')
        if event.get('price') is not None:
            decimal_text(event['price'], positive=True)
        if event.get('size') is not None:
            decimal_text(event['size'])
            if Decimal(event['size']) < 0:
                raise ValueError('size cannot be negative')
        if event['kind'] == 'quote':
            for key in ('up_probability','down_probability','best_bid','best_ask'):
                value = event['payload'].get(key)
                if value is not None and not 0 <= Decimal(decimal_text(value)) <= 1:
                    raise ValueError('quote outside unit interval')
        payload = {'data': event['payload'], 'provenance': event['provenance']}
        immutable = {key: event.get(key) for key in ('source', 'event_id', 'kind', 'market_id', 'symbol', 'source_time', 'price', 'size', 'payload', 'raw_payload', 'provenance')}
        content_hash = digest(immutable)
        with self.connection() as db:
            writer = db.execute('''SELECT w.generation_id,g.state FROM ops.writer_state w
              JOIN archive.generations g USING(origin_id,generation_id)
              WHERE w.origin_id=%s FOR SHARE OF w''', (self.origin,)).fetchone()
            if not writer or writer['state'] != 'collecting':
                raise ValueError('explicit lifecycle bootstrap required before ingestion')
            generation_id = writer['generation_id']
            prior = db.execute('SELECT generation_id,content_hash FROM ops.dedup WHERE origin_id=%s AND source=%s AND event_id=%s',
                               (self.origin, event['source'], event['event_id'])).fetchone()
            if prior:
                if prior['content_hash'] != content_hash:
                    raise IdentityConflict('conflicting source event identity')
                acknowledgement = {'origin_id': self.origin, 'event_id': event['event_id'],
                                   'generation_id': prior['generation_id'], 'content_hash': content_hash, 'duplicate': True}
            else:
                self._admit(db,2 if event['kind']=='outcome' else 1)
                if event['kind'] == 'market':
                    self._market(db, event, payload, received, generation_id)
                record = dict(generation_id=generation_id, origin_id=self.origin, source=event['source'],
                              event_id=str(event['event_id']), kind=event['kind'], market_id=event.get('market_id'),
                              symbol=event.get('symbol'), source_time=original, source_epoch=epoch,
                              received_at=received, available_at=available, price=event.get('price'), size=event.get('size'),
                              payload=payload, raw_payload=event.get('raw_payload'), content_hash=content_hash)
                self._insert(db, 'raw.events', record, ('generation_id','origin_id','source','event_id'))
                # Race losers compare the winning immutable identity, rolling back all their projections.
                self._insert(db, 'ops.dedup', dict(origin_id=self.origin, source=event['source'], event_id=str(event['event_id']),
                             generation_id=generation_id, content_hash=content_hash, expires_at=received+timedelta(days=30)),
                             ('origin_id','source','event_id'))
                if event['kind'] == 'price':
                    if epoch is None or event.get('price') is None or not event.get('symbol'):
                        raise ValueError('price requires source time, price and symbol')
                    row = {key: record[key] for key in ('origin_id','source','symbol','event_id','generation_id','source_time','source_epoch','received_at','available_at','price','size','payload','content_hash')}
                    inserted = db.execute('''INSERT INTO core.current_prices(origin_id,source,symbol,event_id,generation_id,
                      source_time,source_epoch,received_at,available_at,price,size,payload,content_hash)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT(origin_id,source,symbol) DO UPDATE SET event_id=EXCLUDED.event_id,
                      generation_id=EXCLUDED.generation_id,source_time=EXCLUDED.source_time,source_epoch=EXCLUDED.source_epoch,
                      received_at=EXCLUDED.received_at,available_at=EXCLUDED.available_at,price=EXCLUDED.price,size=EXCLUDED.size,
                      payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash
                      WHERE EXCLUDED.source_epoch > core.current_prices.source_epoch
                         OR (EXCLUDED.source_epoch = core.current_prices.source_epoch AND EXCLUDED.received_at > core.current_prices.received_at)
                      RETURNING *''', [Jsonb(value) if isinstance(value, dict) else value for value in row.values()]).fetchone()
                    if inserted:
                        self._outbox(db, 'core.current_prices', inserted, ('origin_id','source','symbol'), generation_id)
                elif event['kind'] == 'candle':
                    self._candle(db, event, payload, received, generation_id)
                elif event['kind'] == 'outcome':
                    protected = self._protect(db, record)
                    data = event['payload']
                    outcome = dict(origin_id=self.origin, outcome_id=event['event_id'], market_id=event['market_id'],
                                   evidence_id=protected['evidence_id'], result=data['result'], final=data.get('final'),
                                   source_time=original, source_epoch=epoch, confirmed_at=received, available_at=available,
                                   payload=payload, content_hash=content_hash)
                    if outcome['final'] is not None:
                        decimal_text(outcome['final'])
                    outcome = self._insert(db, 'core.outcomes', outcome, ('origin_id','outcome_id'))
                    self._outbox(db, 'core.outcomes', outcome, ('origin_id','outcome_id'), generation_id)
                acknowledgement = {'origin_id': self.origin, 'event_id': event['event_id'],
                                   'generation_id': generation_id, 'content_hash': content_hash, 'duplicate': False}
        return acknowledgement

    def _market(self, db, event, payload, received, generation_id):
        from .contract import source_timestamp
        from psycopg.types.json import Jsonb
        data = event['payload']
        start, start_epoch = source_timestamp(data['start'])
        end, end_epoch = source_timestamp(data['end'])
        if end_epoch-start_epoch != 900 or data.get('duration', 900) != 900:
            raise ValueError('only exact 15-minute markets supported')
        if data.get('target_usd') is not None:
            decimal_text(data['target_usd'], positive=True)
        row = dict(origin_id=self.origin, market_id=event['market_id'], source=event['source'], slug=data['slug'],
                   duration=900, start_time=start, end_time=end, start_epoch=start_epoch, end_epoch=end_epoch,
                   target=data.get('target_usd'), final=None, result=None, status=data['status'],
                   index_symbol=data.get('index_symbol'), rules=data.get('rules'), first_seen=received,last_seen=received,
                   payload=payload, content_hash=digest(data))
        existing = self._insert(db, 'core.markets', row, ('origin_id','market_id'), immutable=False)
        if existing['content_hash'] != row['content_hash']:
            # Markets are mutable metadata projections; immutable raw events retain each revision.
            if received >= existing['last_seen']:
                existing = db.execute('''UPDATE core.markets SET slug=%s,target=%s,status=%s,index_symbol=%s,rules=%s,
                    last_seen=%s,payload=%s,content_hash=%s WHERE origin_id=%s AND market_id=%s
                    AND start_epoch=%s AND end_epoch=%s RETURNING *''',
                    (row['slug'],row['target'],row['status'],row['index_symbol'],row['rules'],received,Jsonb(payload),
                     row['content_hash'],self.origin,event['market_id'],start_epoch,end_epoch)).fetchone()
                if not existing:
                    raise IdentityConflict('market boundaries cannot be revised under the same identity')
        self._outbox(db, 'core.markets', existing, ('origin_id','market_id'), generation_id)

    def _candle(self, db, event, payload, received, generation_id):
        data = event['payload']
        row = dict(origin_id=self.origin, source=event['source'], symbol=event['symbol'], granularity=data['granularity'],
                   time=data['time'], **{key: decimal_text(data[key]) if data.get(key) is not None else None for key in ('low','high','open','close','volume')},
                   first_seen=received, payload=payload, content_hash=digest(data))
        if row['granularity'] != 60 or row['time'] % 60:
            raise ValueError('candles require aligned 60-second boundaries')
        # Revisions require a later explicit importer; do not overwrite forecast evidence silently.
        row = self._insert(db, 'core.candles', row, ('origin_id','source','symbol','granularity','time'))
        self._outbox(db, 'core.candles', row, ('origin_id','source','symbol','granularity','time'), generation_id)

    def _protect(self, db, raw):
        generation = raw.get('generation_id')
        if generation:
            row = db.execute('SELECT state FROM archive.generations WHERE origin_id=%s AND generation_id=%s FOR SHARE',
                             (self.origin,generation)).fetchone()
            if not row or row['state'] == 'retired':
                raise PublicationRejected('input generation retired; retry using protected evidence')
        evidence = {key: raw.get(key) for key in ('origin_id','generation_id','source','event_id','kind','market_id',
                                                 'source_time','source_epoch','received_at','available_at','payload','raw_payload','content_hash')}
        if 'price' in raw:
            # Protected schema has no price/size columns: keep their exact values in its envelope.
            evidence['payload'] = {**raw['payload'],'normalized':json_value({key:raw.get(key) for key in ('price','size','symbol')})}
        evidence['evidence_id'] = digest([self.origin,raw['source'],raw['event_id'],raw['content_hash']])
        evidence = self._insert(db, 'core.protected_evidence', evidence, ('origin_id','evidence_id'))
        self._outbox(db, 'core.protected_evidence', evidence, ('origin_id','evidence_id'), generation)
        return evidence

    @staticmethod
    def _market_view(row):
        if not row:
            return None
        return json_value({'id': row['market_id'], 'origin': row['origin_id'], 'slug': row['slug'], 'start': row['start_time'],
                           'end': row['end_time'], 'target_usd': row['target'], 'status': row['status'],
                           'first_seen': row['first_seen'], 'provenance': row['payload'].get('provenance', {})})

    def _active(self, db, now):
        epoch = Decimal(str(timestamp(now).timestamp()))
        return db.execute('''SELECT * FROM core.markets WHERE origin_id=%s AND duration=900
            AND start_epoch<=%s AND end_epoch>%s AND first_seen<=%s AND last_seen<=%s
            AND status IN ('MARKET_STATUS_OPEN','open') ORDER BY start_epoch DESC,market_id LIMIT 1''',
            (self.origin,epoch,epoch,now,now)).fetchone()

    def active_market(self, now=None):
        with self.connection(True) as db:
            return self._market_view(self._active(db, timestamp(now or utcnow())))

    @staticmethod
    def _price_view(row):
        return json_value({'origin':row['origin_id'], 'source':row['source'], 'event_id':row['event_id'],
                          'generation_id':row['generation_id'],'source_time':row['source_time'], 'received_at':row['received_at'],
                          'available_at':row['available_at'],'price_usd':row['price'],'size_btc':row['size'],
                          'content_hash':row['content_hash'],'provenance':row['payload'].get('provenance',{})}) if row else None

    def inputs(self, market_id, now=None):
        now = timestamp(now or utcnow())
        wanted = int(now.timestamp())//60*60-60
        with self.connection(True) as db:
            price = db.execute('''SELECT * FROM core.current_prices WHERE origin_id=%s AND source='coinbase' AND symbol='BTC-USD'
              AND source_epoch<=%s AND available_at<=%s''', (self.origin,Decimal(str(now.timestamp())),now)).fetchone()
            candles = db.execute('''SELECT * FROM core.candles WHERE origin_id=%s AND source='coinbase' AND symbol='BTC-USD'
              AND granularity=60 AND time BETWEEN %s AND %s AND first_seen<=%s ORDER BY time LIMIT 17''',
              (self.origin,wanted-16*60,wanted,now)).fetchall()
        return self._price_view(price), [json_value({'origin':row['origin_id'],'source':row['source'],'symbol':row['symbol'],
                    'granularity':row['granularity'],'start':datetime.fromtimestamp(row['time'],timezone.utc),
                    'close':row['close'],'volume':row['volume'],'received_at':row['first_seen'],'content_hash':row['content_hash'],
                    'provenance':row['payload'].get('provenance',{})}) for row in candles]

    def save_calculation(self, market, snapshot, prediction, now=None):
        from .contract import source_timestamp
        from psycopg.types.json import Jsonb
        now = timestamp(now or utcnow())
        if (not prediction or not 0 <= (now-timestamp(snapshot['as_of'])).total_seconds() <= 30
                or prediction['market_id'] != market['id'] or snapshot['market_id'] != market['id']):
            raise PublicationRejected('stale or expired calculation')
        snapshot_id = digest([self.origin,market['id'],snapshot['as_of'],1])
        with self.connection() as db:
            existing = db.execute('''SELECT f.content_hash AS feature_hash,p.content_hash AS prediction_hash
                FROM core.feature_snapshots f JOIN core.predictions p USING(origin_id,snapshot_id)
                WHERE f.origin_id=%s AND f.snapshot_id=%s AND p.model_version=%s''',
                (self.origin,snapshot_id,prediction['model_version'])).fetchone()
            if existing:
                if existing['feature_hash'] != digest(snapshot) or existing['prediction_hash'] != digest(prediction):
                    raise IdentityConflict('conflicting calculation identity')
                return snapshot_id
            writer=db.execute('''SELECT w.generation_id,g.state FROM ops.writer_state w
                JOIN archive.generations g USING(origin_id,generation_id) WHERE w.origin_id=%s FOR SHARE OF w''',
                (self.origin,)).fetchone()
            if not writer or writer['state']!='collecting':
                raise PublicationRejected('no collecting generation for structured acknowledgement')
            output_generation=writer['generation_id']
            self._admit(db,6)
            active = self._active(db,now)
            if not active or active['market_id'] != market['id']:
                raise PublicationRejected('market changed during calculation')
            evidences = []
            price = snapshot['evidence'].get('price', {})
            if price.get('input_id'):
                evidence_id=digest([self.origin,price['source'],price['input_id'],price['content_hash']])
                protected=db.execute('''SELECT * FROM core.protected_evidence WHERE origin_id=%s AND evidence_id=%s''',
                    (self.origin,evidence_id)).fetchone()
                if protected:
                    evidences.append(protected)
                else:
                    raw = db.execute('''SELECT * FROM raw.events WHERE generation_id=%s AND origin_id=%s AND source=%s AND event_id=%s''',
                        (price['generation_id'],self.origin,price['source'],price['input_id'])).fetchone()
                    if not raw:
                        raise PublicationRejected('raw price evidence unavailable')
                    evidences.append(self._protect(db,raw))
            # Persist full calculation input envelope, including exact metadata and candle versions.
            envelope = dict(origin_id=self.origin,generation_id=output_generation,source='calculation_inputs',event_id=snapshot_id,kind='feature_inputs',
                            market_id=market['id'],source_time=snapshot['as_of'],source_epoch=source_timestamp(snapshot['as_of'])[1],
                            received_at=now,available_at=now,payload=snapshot['evidence'],raw_payload=None,content_hash=digest(snapshot['evidence']))
            evidences.append(self._protect(db,envelope))
            row = dict(origin_id=self.origin,snapshot_id=snapshot_id,market_id=market['id'],as_of=timestamp(snapshot['as_of']),version=1,
                       values_json=snapshot['values'],quality_json=snapshot['quality'],evidence_json=snapshot['evidence'],content_hash=digest(snapshot))
            row = self._insert(db,'core.feature_snapshots',row,('origin_id','snapshot_id'))
            self._outbox(db,'core.feature_snapshots',row,('origin_id','snapshot_id'),output_generation)
            for evidence in evidences:
                db.execute('''INSERT INTO core.snapshot_evidence(origin_id,snapshot_id,evidence_id) VALUES(%s,%s,%s)
                  ON CONFLICT DO NOTHING''',(self.origin,snapshot_id,evidence['evidence_id']))
                # FK edges have a stable lossless outbox envelope too.
                edge = dict(origin_id=self.origin,snapshot_id=snapshot_id,evidence_id=evidence['evidence_id'])
                edge['content_hash'] = digest(edge)
                self._outbox(db,'core.snapshot_evidence',edge,('origin_id','snapshot_id','evidence_id'),output_generation)
            row = dict(origin_id=self.origin,prediction_id=digest([snapshot_id,prediction['model_version']]),snapshot_id=snapshot_id,
                       market_id=market['id'],model_version=prediction['model_version'],as_of=timestamp(prediction['as_of']),created_at=now,
                       seconds_remaining=prediction['seconds_remaining'],probability_up=prediction['probability_up'],probability_down=prediction['probability_down'],
                       abstain_reason=prediction['abstain_reason'],assumptions_json=prediction['assumptions'],payload={'experimental':True},
                       content_hash=digest(prediction))
            row = self._insert(db,'core.predictions',row,('origin_id','prediction_id'))
            self._outbox(db,'core.predictions',row,('origin_id','prediction_id'),output_generation)
            db.execute('''INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at) VALUES(%s,'calculation',%s,%s)
                ON CONFLICT(origin_id,worker) DO UPDATE SET cursor=EXCLUDED.cursor,updated_at=EXCLUDED.updated_at''',
                (self.origin,Jsonb({'snapshot_id':snapshot_id,'market_id':market['id'],'as_of':snapshot['as_of']}),now))
        return snapshot_id

    def hydrate(self, market_id, now=None):
        now = timestamp(now or utcnow())
        price,_ = self.inputs(market_id,now)
        with self.connection(True) as db:
            feature = db.execute('''SELECT * FROM core.feature_snapshots WHERE origin_id=%s AND market_id=%s AND as_of<=%s
                ORDER BY as_of DESC LIMIT 1''',(self.origin,market_id,now)).fetchone()
            prediction = db.execute('''SELECT * FROM core.predictions WHERE origin_id=%s AND market_id=%s AND as_of<=%s
                ORDER BY as_of DESC LIMIT 1''',(self.origin,market_id,now)).fetchone()
            quote = db.execute('''SELECT * FROM raw.events WHERE origin_id=%s AND market_id=%s AND source='polymarket_us'
                AND kind='quote' AND available_at<=%s AND source_epoch<=%s ORDER BY source_epoch DESC LIMIT 1''',
                (self.origin,market_id,now,Decimal(str(now.timestamp())))).fetchone()
        feature = json_value({'snapshot_id':feature['snapshot_id'],'market_id':market_id,'as_of':feature['as_of'],
                              'values':feature['values_json'],'quality':feature['quality_json']}) if feature else None
        quote = json_value({**quote['payload']['data'],'market_id':market_id,'source_time':quote['source_time'],
                            'received_at':quote['received_at'],'provenance':quote['payload'].get('provenance',{})}) if quote else None
        prediction = json_value(prediction) if prediction else None
        return price,quote,feature,prediction

    def predictions(self, limit=100):
        with self.connection(True) as db:
            return json_value(db.execute('''SELECT prediction_id AS id,market_id,model_version,as_of,created_at,
               seconds_remaining,probability_up,probability_down,abstain_reason FROM core.predictions
               WHERE origin_id=%s ORDER BY as_of DESC LIMIT %s''',(self.origin,bound(limit))).fetchall())

    def chart(self, now=None):
        now = timestamp(now or utcnow())
        with self.connection(True) as db:
            row = self._active(db,now)
            if not row:
                return {'status':'missing','market':None,'points':[]}
            points = db.execute('''SELECT source_time,source_epoch,price FROM raw.events WHERE origin_id=%s AND source='coinbase'
                AND kind='price' AND symbol='BTC-USD' AND source_epoch>=%s AND source_epoch<%s AND available_at<=%s
                ORDER BY source_epoch DESC LIMIT 5000''',(self.origin,row['start_epoch'],row['end_epoch'],now)).fetchall()
        buckets = {}
        for point in reversed(points):
            buckets[int(point['source_epoch'])//5] = {'at':point['source_time'],'price_usd':str(point['price'])}
        return {'status':'ok','market':self._market_view(row),'points':list(buckets.values()),'tier':'local',
                'bounded_input_limit':5000,'truncated':len(points)==5000}
