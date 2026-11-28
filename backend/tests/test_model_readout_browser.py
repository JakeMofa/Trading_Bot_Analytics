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
                    expect(page.locator('#saved-forecast-result')).to_have_text('Abstained · required feature missing')
                    expect(page.locator('#saved-forecast-state')).to_contain_text('Decision ' + at)
                    expect(page.locator('#saved-forecast-state')).to_contain_text('Saved ' + created)
                    expect(page.locator('#saved-forecast-source')).to_contain_text('fixture-snapshot')
                    expect(page.locator('#ai-decision-buy')).to_have_text('Disabled')

                    clock[0] += timedelta(seconds=31)
                    expect(page.locator('#forecast-up')).to_have_text('—')
                    expect(page.locator('#forecast-state')).to_contain_text('reference price not fresh')
                    expect(page.locator('#saved-forecast-state')).to_contain_text('2m 31s ago')
                    state.collector_status(False)
                    expect(page.locator('#forecast-state')).to_contain_text('collector off')
                    state.discover(dict(market, id='next-market'))
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
