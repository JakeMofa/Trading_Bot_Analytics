"""Exercise the real Market dashboard and SSE with a controlled market clock."""
from datetime import timedelta
import importlib.util
from urllib.parse import parse_qs, urlsplit
import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'requires Playwright and Chromium')
class ModelReadoutBrowserTests(unittest.TestCase):
    def test_saved_abstention_survives_live_expiry_and_clears_on_rollover(self):
        import uvicorn
        from playwright.sync_api import expect, sync_playwright
        from postgres.api import create_app
        from postgres.config import Settings
        from postgres.live_state import LiveState
        from test_postgres_application import FakeStore, state_fixture

        _, clock, (market, price, quote, feature, forecast) = state_fixture()
        settings = Settings(data_mode='pp_live', origin_id='pp-live-readout-fixture')
        state = LiveState(settings, clock=lambda: clock[0])
        state.collector_status(True)
        state.discover(market)
        at = (clock[0] - timedelta(minutes=2)).isoformat()
        created = (clock[0] - timedelta(seconds=119)).isoformat()
        saved = dict(forecast, market_id=market['id'], origin_id=settings.origin_id,
                     prediction_id='fixture-prediction', snapshot_id='fixture-snapshot',
                     as_of=at, created_at=created, probability_up=None, probability_down=None,
                     abstain_reason='required_feature_missing')
        state.publish(market['id'], price, quote, feature, forecast, saved)

        received = clock[0].isoformat()
        state.display({'market':market, 'reference':{'event_id':'index-fixture', 'price_usd':'67900.50',
                       'source_time':received,'received_at':received}, 'quote':None,
                       'received':0,'saved':0,'duplicates':0,'started_at':received,'last_commit':None})
        state.publish_robinhood({'event_id':'rh-v1-fixture', 'price_usd':'68123.40', 'received_at':received,
                                'source_time':received, 'book_status':'two_sided',
                                'movement':{'delta_usd':'-0.000001200','previous_event_id':'rh-v1-earlier',
                                            'previous_received_at':(clock[0]-timedelta(seconds=1)).isoformat()}})
        app = create_app(settings, FakeStore(), state, refresh=False)
        with sync_playwright() as playwright:
            options = [os.environ.get('CHROME_BIN'), shutil.which('chromium'), shutil.which('google-chrome'),
                       '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                       playwright.chromium.executable_path]
            executable = next((item for item in options if item and Path(item).is_file()), None)
            if not executable:
                self.skipTest('requires an installed Chromium browser')
            browser = playwright.chromium.launch(executable_path=executable)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
                server = uvicorn.Server(uvicorn.Config(app, log_level='critical'))
                worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
                worker.start()
                try:
                    deadline = time.monotonic() + 5
                    while not server.started and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(server.started)
                    page = browser.new_page()
                    page.goto(f'http://127.0.0.1:{port}/dashboard', wait_until='domcontentloaded')
                    expect(page.locator('#forecast-up')).to_contain_text('UP')
                    expect(page.locator('#forecast-down')).to_contain_text('DOWN')
                    up, down = [page.locator('#forecast-'+side).evaluate(
                        '(node) => [getComputedStyle(node).fontSize,getComputedStyle(node).fontWeight, node.getBoundingClientRect().width]'
                    ) for side in ('up','down')]
                    self.assertEqual(up, down)
                    expect(page.locator('#saved-forecast-result')).to_have_text('Abstained · required feature missing')
                    expect(page.locator('#saved-forecast-state')).to_contain_text('Decision age 2m')
                    expect(page.locator('#saved-forecast-source')).to_be_hidden()
                    page.get_by_text('Decision inputs and provenance', exact=True).click()
                    expect(page.locator('#saved-forecast-source')).to_contain_text('Decision ' + at)
                    expect(page.locator('#saved-forecast-source')).to_contain_text('Recorded ' + created)
                    expect(page.locator('#saved-forecast-source')).to_contain_text('fixture-snapshot')
                    self.assertEqual(page.locator('#rolling-window').count(), 0)
                    market_card, forecast_card = [page.locator(selector).bounding_box()
                                             for selector in ('main .market', 'main .forecast')]
                    self.assertGreater(market_card['width'], 450)
                    self.assertEqual(market_card['y'], forecast_card['y'])
                    expect(page.locator('#ai-decision-buy')).to_be_hidden()
                    page.get_by_role('button', name='Models', exact=True).click()
                    expect(page.locator('#ai-decision-buy')).to_be_visible()
                    expect(page.locator('#ai-decision-buy')).to_have_text('Disabled')
                    page.get_by_role('button', name='Market', exact=True).click()
                    page.set_viewport_size({'width':390,'height':844})
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390)
                    cards = [page.locator('#'+selector).bounding_box()
                             for selector in ('venue-price','live-reference','robinhood-price')]
                    self.assertLess(cards[0]['y'], cards[1]['y'])
                    self.assertLess(cards[1]['y'], cards[2]['y'])
                    page.set_viewport_size({'width':1280,'height':720})

                    expect(page.locator('#live-reference')).to_contain_text('$')
                    expect(page.locator('#live-reference')).to_have_attribute('data-event-id', price['event_id'])
                    expect(page.locator('#venue-price')).to_have_text('$67,900.50')
                    expect(page.locator('#robinhood-price')).to_have_text('$68,123.40')
                    expect(page.locator('#robinhood-price')).to_have_attribute('data-event-id', 'rh-v1-fixture')
                    expect(page.locator('#robinhood-age')).to_contain_text('Recent')
                    expect(page.locator('#robinhood-movement')).to_have_text('Down $0.0000012 since previous poll')
                    state.display({'market':market, 'reference':None, 'quote':None, 'received':0,
                                   'saved':0,'duplicates':0,'started_at':received,'last_commit':None,
                                   'empty_book_at':received})
                    expect(page.locator('#market-quote')).to_contain_text('Polymarket US REST book was empty')
                    clock[0] += timedelta(seconds=31)
                    expect(page.locator('#robinhood-age')).to_contain_text('Stale')
                    expect(page.locator('#robinhood-movement')).to_have_text('Price change stale.')
                    state.publish_robinhood({'event_id':'rh-v1-crossed', 'price_usd':None,
                                             'received_at':clock[0].isoformat(), 'source_time':None,'book_status':'crossed'})
                    expect(page.locator('#robinhood-price')).to_have_text('—')
                    expect(page.locator('#robinhood-age')).to_contain_text('crossed book')
                    expect(page.locator('#forecast-up')).to_have_text('—')
                    expect(page.locator('#forecast-down')).to_have_text('—')
                    expect(page.locator('#forecast-state')).to_contain_text('reference price not fresh')
                    expect(page.locator('#saved-forecast-state')).to_contain_text('2m 31s ago')
                    state.collector_status(False)
                    expect(page.locator('#forecast-state')).to_contain_text('collector off')
                    next_market = dict(market, id='next-market')
                    state.discover(next_market)
                    state.display({'market':next_market, 'reference':None,'quote':None, 'received':0,
                                   'saved':0,'duplicates':0,'started_at':received,'last_commit':None})
                    expect(page.locator('#saved-forecast-result')).to_have_text('—')
                    expect(page.locator('#saved-forecast-source')).to_be_empty()
                    queries = []
                    def history_page(route):
                        query = parse_qs(urlsplit(route.request.url).query)
                        queries.append(query)
                        row = dict(saved, id=saved['prediction_id'], tier='authenticated_archive')
                        route.fulfill(json={'items': [row], 'next_cursor': 'fixture-next' if len(queries) == 1 else None,
                                            'coverage': {'complete': True}})

                    page.route('**/history/market-predictions?*', history_page)
                    page.get_by_role('button', name='History', exact=True).click()
                    page.locator('#history-market').fill(market['id'])
                    page.locator('#history-records').select_option('predictions')
                    page.get_by_role('button', name='Load predictions').click()
                    expect(page.locator('#event-rows tr')).to_have_attribute('data-prediction-id', saved['prediction_id'])
                    expect(page.locator('#event-rows')).to_contain_text('Verified archive')
                    expect(page.locator('#event-rows')).to_contain_text('required_feature_missing')
                    page.get_by_role('button', name='Next page').click()
                    expect(page.locator('#history-next')).to_be_disabled()
                    self.assertEqual(len(queries), 2)
                    self.assertEqual(queries[1].pop('cursor'), ['fixture-next'])
                    self.assertEqual(queries[0], queries[1])
                    self.assertEqual(queries[0]['market_id'], [market['id']])
                    page.close()
                finally:
                    browser.close()
                    server.should_exit = True
                    worker.join(5)
