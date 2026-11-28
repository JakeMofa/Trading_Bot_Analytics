"""Market/time history across real attached and retired PostgreSQL generations."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
import uuid
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits
from postgres.calculation import calculate, baseline
from postgres.config import Settings
from postgres.connection import connect
from postgres.history import HistoryError
from postgres.ingestion import generated_events
from postgres.lifecycle import ArchiveWorker, LifecycleRepository, RotationPolicy
from postgres.market_history import MarketHistory, Window, merge
from postgres.store import Store
from postgres_lifecycle_fixtures import ImmutableMemoryTransport
import test_pp_initial_trial_drain as fixture


class Objects(ImmutableMemoryTransport):
    def close(self):
        pass


class MarketHistoryNative(unittest.TestCase):
    # Share the existing disposable PG17 foundation and migration setup only.
    setUpClass = classmethod(fixture.InitialSealNative.setUpClass.__func__)
    tearDownClass = classmethod(fixture.InitialSealNative.tearDownClass.__func__)
    admin = classmethod(fixture.InitialSealNative.admin.__func__)

    def test_point_in_time_baseline_survives_rotation_and_real_drop(self):
        now = datetime(2026,11,12,12,5,tzinfo=timezone.utc)
        origin = 'generated-market-history-'+uuid.uuid4().hex
        repo = LifecycleRepository(lambda:connect(self.lifecycle_dsn))
        first = repo.bootstrap(origin, now=now-timedelta(minutes=5))['generation_id']
        store = Store(Settings(origin_id=origin,dsn=self.app_dsn))
        market, _, *remaining = generated_events(now)
        # Current-market identity and old candles in A; newest candles, price
        # and quote in B. As-observed time is distinct from candle start.
        venue_reference = dict(remaining[-2], source='polymarket_us', event_id='index-price')
        events = [market, *remaining, venue_reference]
        for row in events[:9]:
            row['received_at'] = (now-timedelta(seconds=2)).isoformat()
            store.ingest(row)
        second = repo.switch_if_due(origin,RotationPolicy(1),now=now-timedelta(seconds=1))
        self.assertEqual(second['status'],'switched')
        for row in events[9:]:
            store.ingest(row)
        late = dict(events[-1], event_id='late', available_at=(now+timedelta(seconds=1)).isoformat())
        store.ingest(late)
        window = Window(market['market_id'], now-timedelta(minutes=5), now+timedelta(seconds=1), now)
        objects = Objects()
        reader = MarketHistory(store, lambda:objects)
        def all_rows():
            result, cursor = [], None
            for _ in range(40):
                page = reader.read(window,cursor,5)
                self.assertTrue(page['coverage']['complete'])
                result.extend(page['items'])
                cursor = page['next_cursor']
                if not cursor:
                    return result
            self.fail('cursor did not finish')

        def replay(rows):
            saved = next(r for r in rows if r['kind']=='market')
            market = dict(saved['payload']['data'], id=saved['market_id'], first_seen=saved['received_at'])
            reference = next(r for r in rows if r['source']=='coinbase' and r['kind']=='price')
            price = dict(reference, origin=reference['origin_id'], price_usd=reference['price'])
            candles = [dict(r['payload']['data'], **{k:r[k] for k in ('source','symbol','received_at')},
                           start=r['source_time']) for r in rows if r['kind']=='candle']
            values, quality, _ = calculate(market,price,candles,now)
            return values, baseline(values,quality)

        attached = all_rows()
        identities = [(r['source'],r['event_id']) for r in attached]
        self.assertEqual(identities,sorted(set(identities)))
        self.assertEqual(len(attached),len(events))
        features, prediction = replay(attached)
        self.assertEqual(features['distance_usd'],'25.0000000000000000000')
        self.assertIsNotNone(prediction[0])
        worker = ArchiveWorker(repo,objects,ArchiveLimits(max_rows=500))
        self.assertEqual(worker.archive_cycle(first)['status'], 'archived')
        self.assertEqual(attached,all_rows())
        worker.retire_generated(first,qualification_enabled=True)
        retired = all_rows()
        self.assertEqual({r['tier'] for r in retired},{'authenticated_archive','local_postgres'})
        self.assertEqual([{k:v for k,v in r.items() if k!='tier'} for r in attached],
                         [{k:v for k,v in r.items() if k!='tier'} for r in retired])
        self.assertEqual(replay(retired),(features,prediction))
        missing = MarketHistory(store).read(window,None,500)
        self.assertFalse(missing['coverage']['complete'])
        self.assertEqual(missing['coverage']['missing_generations'],[first])
        page = reader.read(window,None,1)
        with self.assertRaises(HistoryError):
            reader.read(Window('other',window.start,window.end,window.as_of),page['next_cursor'],1)
        key = next(iter(objects.objects))
        objects.objects[key] = b'invalid object'
        with self.assertRaises(ArchiveIntegrityError):
            reader.read(window,None,500)

    def test_five_hundred_rows_before_and_after_both_retire(self):
        now = datetime(2026,11,12,13,5,tzinfo=timezone.utc)
        origin = 'generated-market-page-'+uuid.uuid4().hex
        repo = LifecycleRepository(lambda:connect(self.lifecycle_dsn))
        old_a = repo.bootstrap(origin, now=now-timedelta(minutes=4))['generation_id']
        store = Store(Settings(origin_id=origin,dsn=self.app_dsn))
        market, *others = generated_events(now)
        market.update(received_at=(now-timedelta(minutes=3)).isoformat())
        store.ingest(market)
        objects = Objects()
        worker = ArchiveWorker(repo,objects,ArchiveLimits(max_rows=500))
        reader = MarketHistory(store,lambda:objects)
        for i in range(500):
            if i == 250:
                b = repo.switch_if_due(origin,RotationPolicy(1),now=now)
                self.assertEqual(b['status'],'switched')
            stamp = (now+timedelta(milliseconds=i-250)).isoformat()
            store.ingest(dict(others[-1],event_id=f'quote-{i:03}',source_time=stamp,received_at=stamp))
        window = Window(market['market_id'],now-timedelta(seconds=1),now+timedelta(seconds=1),now+timedelta(seconds=1))
        def timed_page():
            start = time.perf_counter()
            result = reader.read(window,None,500)
            elapsed = time.perf_counter()-start
            self.assertTrue(result['coverage']['complete'])
            self.assertIsNone(result['next_cursor'])
            self.assertEqual([r['event_id'] for r in result['items']],[f'quote-{i:03}' for i in range(500)])
            return elapsed, [(r['event_id'],r['content_hash'],r['payload']) for r in result['items']]
        hot, expected = timed_page()
        for gen in (old_a,b['generation_id']):
            if gen != old_a:
                repo.switch_if_due(origin,RotationPolicy(1),now=window.end+timedelta(seconds=1))
            self.assertEqual(worker.archive_cycle(gen)['status'],'archived')
            self.assertEqual(timed_page()[1],expected)
            worker.retire_generated(gen,qualification_enabled=True)
        cold, observed = timed_page()
        self.assertEqual(observed,expected)
        print(f'local_pg17_generated_500_page hot_seconds={hot:.4f} verified_fixture_seconds={cold:.4f}')


class MarketPageBounds(unittest.TestCase):
    def test_keyset_frontier_duplicate_integrity_and_filter_only_progress(self):
        def row(id_, digest='a'):
            return {'source':'polymarket_us','event_id':id_,'content_hash':digest}
        a, b, c = [row(id_) for id_ in ('A','B','C')]
        items, cursor = merge([([a,b,c],None),([a],['polymarket_us','A'])],limit=3,scope='x')
        self.assertEqual(items,[a])
        self.assertTrue(cursor)
        self.assertTrue(merge([([],['polymarket_us','B']),([c],None)],limit=3,scope='x')[1])
        with self.assertRaises(ArchiveIntegrityError):
            merge([([a],None),([row('A','b')],None)],limit=3,scope='x')
