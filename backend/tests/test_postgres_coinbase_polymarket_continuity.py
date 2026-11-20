"""Generated Coinbase outage coverage with restricted PostgreSQL writes."""

import asyncio
from datetime import datetime, timedelta, timezone
import os
import unittest

import test_postgres_second_trial as restricted
import test_pp_initial_trial_drain as initial
from postgres.cloud_origin_binding import TRIAL_ORIGIN
from postgres.lifecycle import RotationPolicy
from postgres.live_contract import polymarket_bbo, polymarket_market
from postgres.live_diagnostics import LiveDiagnostic
from postgres.live_ingest import coinbase_session, polymarket_cycle
from postgres.live_state import LiveState
from postgres.live_supervisor import run_bounded
from postgres.store import StorageHold


class CoinbasePolymarketContinuity(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        roles = ('LIFECYCLE', 'APP', 'MIGRATOR')
        external = any(os.environ.get(f'TRADEBOT_TEST_{role}_DSN') for role in roles)
        cls.fixture_type = restricted.SecondTrialDSNTests if external else initial.InitialSealNative
        cls.fixture_type.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_type.tearDownClass()

    def setUp(self):
        self.fixture = self.fixture_type()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.fixture_on()

    def disable(self):
        return self.fixture.repo.disable_collector(TRIAL_ORIGIN)

    async def run_session(self, stop, coinbase, market, candles):
        return await run_bounded(
            self.fixture.store, None, stop, owner_check=lambda: True,
            disable_collector=self.disable, max_seconds=8, market_interval=1,
            coinbase=coinbase, market=market, candles=candles,
        )

    def check_stale_estimate(self, market_id, now):
        store = self.fixture.store
        observed = now + timedelta(seconds=35)
        state = LiveState(store.settings, clock=lambda: observed)
        state.discover(dict(
            id=market_id, start=(now - timedelta(seconds=10)).isoformat(),
            end=(now + timedelta(minutes=10)).isoformat(), target_usd='100000.123456',
        ))
        feature = dict(
            snapshot_id='generated-feature', market_id=market_id, as_of=observed.isoformat(),
            values={'target_usd': '100000', 'realized_volatility_15m': '0.01'},
            quality={'price': {'status': 'fresh'}, 'candle_status': 'fresh'},
        )
        price = store.current_price(observed)
        self.assertIsNotNone(price)
        self.assertTrue(state.publish(market_id, price, None, feature, None))
        view = state.snapshot()
        self.assertEqual(view['feeds']['coinbase_stream']['status'], 'stale')
        self.assertIsNone(view['live_estimate']['probability_up'])
        self.assertEqual(view['live_estimate']['abstain_reason'], 'reference_price_not_fresh')

    async def write_market_and_quote(self, store, client, stop, market_id, now):
        start = datetime.fromtimestamp(int(now.timestamp()) // 900 * 900, timezone.utc)
        end = start + timedelta(minutes=15)
        slug = f'generated-market-{market_id}'
        market = polymarket_market({
            'id': market_id, 'slug': slug, 'status': 'open',
            'assetPriceTerms': {
                'asset': {'symbol': 'BTC'}, 'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                'horizon': '15m', 'windowStart': start.isoformat(),
                'windowEnd': end.isoformat(), 'priceToBeat': '100000.123456',
            },
        }, now.isoformat())

        async def discover(_client, _now):
            return market

        async def fetch(_client, event):
            return polymarket_bbo({'marketData': {
                'marketSlug': slug, 'state': 'MARKET_STATE_OPEN',
                'bestBid': {'value': '0.4200'}, 'bestAsk': {'value': '0.4300'},
            }}, event, now.isoformat())

        quote = await polymarket_cycle(store, client, stop, now=now, discover=discover, fetch=fetch)
        self.assertIsNotNone(quote)
        with self.fixture.admin() as db:
            rows = db.execute(
                'SELECT generation_id,kind FROM raw.events '
                'WHERE origin_id=%s AND market_id=%s ORDER BY kind',
                (TRIAL_ORIGIN, market_id),
            ).fetchall()
        self.assertEqual([row['kind'] for row in rows], ['market', 'quote'])
        self.assertEqual(rows[0]['generation_id'], rows[1]['generation_id'])
        return rows[0]['generation_id']

    async def test_polymarket_writes_and_switch_continue_during_coinbase_retries(self):
        stop = asyncio.Event()
        fake_time = 0.0
        attempts = []
        delays = []
        still_waiting = asyncio.Event()
        written_generations = []
        fixture = self.fixture

        async def disconnected(source_stop):
            attempts.append(fake_time)
            if len(attempts) == 16:
                still_waiting.set()
                await source_stop.wait()
                return
            raise LiveDiagnostic('coinbase_stream', 'ws_closed_error')
            yield  # pragma: no cover

        async def backoff(_stop, delay):
            nonlocal fake_time
            delays.append(delay)
            fake_time += delay
            await asyncio.sleep(0)

        async def coinbase(store, source_stop):
            await coinbase_session(
                store, source_stop, source=disconnected, pause=backoff, clock=lambda: fake_time,
            )

        async def market(store, client, market_stop, *, now):
            await still_waiting.wait()
            market_id = f'generated-{len(written_generations)}'
            generation = await self.write_market_and_quote(store, client, market_stop, market_id, now)
            written_generations.append(generation)
            self.check_stale_estimate(market_id, now)
            if len(written_generations) == 1:
                rotated = await asyncio.to_thread(
                    fixture.repo.switch_if_due, TRIAL_ORIGIN, RotationPolicy(1),
                    require_live_lease=True,
                )
                self.assertEqual(rotated['status'], 'switched')
                self.assertEqual(rotated['sealed_generation_id'], fixture.anchor)
                fixture.children.append(rotated['generation_id'])
            else:
                market_stop.set()

        async def candles(*_args, **_kwargs):
            await stop.wait()

        self.assertEqual(await self.run_session(stop, coinbase, market, candles), 'stopped')
        self.assertEqual(written_generations, [fixture.anchor, fixture.children[-1]])
        self.assertEqual(len(attempts), 16)
        self.assertGreaterEqual(max(delays), 30)
        for t in attempts[1:]:
            self.assertLessEqual(sum(t - 60 < attempt <= t for attempt in attempts[1:]), 3)
        self.assertFalse(fixture.repo.collector_state(TRIAL_ORIGIN)['stored_enabled'])

    async def test_coinbase_storage_hold_still_forces_durable_off(self):
        stop = asyncio.Event()
        fixture = self.fixture

        def reject(_event):
            raise StorageHold('generated storage rejection')

        fixture.store.ingest = reject

        async def one_event(_stop):
            yield fixture.event(9876)

        async def coinbase(store, source_stop):
            await coinbase_session(store, source_stop, source=one_event)

        async def idle(*_args, **_kwargs):
            await stop.wait()

        with self.assertRaises(LiveDiagnostic) as stopped:
            await self.run_session(stop, coinbase, idle, idle)
        self.assertEqual(stopped.exception.code, 'coinbase_write.write_rejected')
        self.assertFalse(fixture.repo.collector_state(TRIAL_ORIGIN)['stored_enabled'])
