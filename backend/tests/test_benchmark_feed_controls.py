import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres import feed_controls as controls
from postgres.operator_api import create_operator_app

TOKEN='generated-private-operator-fixture-key-only'


class FeedControlTests(unittest.TestCase):
    def setUp(self):
        self.store=SimpleNamespace(origin=controls.ORIGIN,settings=SimpleNamespace(environment='preprod',data_mode='pp_live'))
        self.client=TestClient(create_operator_app(MagicMock(),origin_id=controls.ORIGIN,token=TOKEN,feed_store=self.store))
        self.full={'Authorization':'Bearer '+TOKEN}
        self.grant={'Authorization':'Bearer '+self.client.post('/collector/feeds/session',headers=self.full).json()['access_token']}

    def test_grant_does_not_authorize_global_on_off_or_new_grants(self):
        for path in ('/collector/off','/collector/feeds/session'):
            self.assertEqual(self.client.post(path,headers=self.grant).status_code,401)
        self.assertEqual(self.client.get('/collector/feeds',headers=self.full).status_code,401)
        self.assertEqual(self.client.get('/collector/feeds',headers={**self.grant,'Origin':'https://untrusted.example'}).status_code,403)
        self.assertEqual(self.client.post('/collector/feeds/session',headers={**self.full,'Origin':'http://127.0.0.1:18433'}).status_code,403)
        minted=controls.mint(TOKEN,1600000000)
        self.assertFalse(controls.verify(TOKEN,'Bearer '+minted['access_token'],1600001800))

    def test_one_feed_request_exact_shape_and_conflict(self):
        with patch.object(controls,'set_desired',return_value={'enabled':False,'revision':1,'components':{}}) as write:
            args={'json':{'enabled':False,'revision':0},'headers':self.grant}
            self.assertEqual(self.client.put('/collector/feeds/robinhood',**args).status_code,200)
            write.assert_called_once_with(self.store,'robinhood',False,0)
            self.assertEqual(self.client.put('/collector/feeds/all',**args).status_code,404)
            self.assertEqual(self.client.put('/collector/feeds/coinbase',json={'enabled':'false','revision':0},headers=self.grant).status_code,422)
            write.side_effect=controls.RevisionConflict()
            self.assertEqual(self.client.put('/collector/feeds/robinhood',**args).status_code,409)

    def test_stale_process_cannot_mark_resumed_feed_running(self):
        base={'session':'new','enabled':True}
        rows=[dict(base,worker='feed_desired:coinbase',cursor={'enabled':False,'revision':2}),
              dict(base,worker='feed_actual:coinbase_stream',cursor={'session':'old','state':'running'})]
        state=controls._state(rows)
        self.assertFalse(state['coinbase']['enabled'])
        self.assertEqual(state['coinbase']['components'],{'coinbase_stream':'unknown','coinbase_candles':'unknown'})
        self.assertTrue(state['robinhood']['enabled'])


class FeedBrowserTests(unittest.TestCase):
    def test_private_controls_change_only_chosen_feed(self):
        import importlib.util
        import os
        import shutil
        if not importlib.util.find_spec('playwright'):
            self.skipTest('requires Playwright and Chromium')
        from playwright.sync_api import sync_playwright, expect
        from postgres.config import Settings
        from postgres.live_state import LiveState
        from test_postgres_application import state_fixture
        _, clock, (market,price,quote,feature,forecast)=state_fixture()
        state=LiveState(Settings(data_mode='pp_live',origin_id=controls.ORIGIN), clock=lambda:clock[0])
        state.collector_status(True)
        state.discover(market)
        state.publish(market['id'],price,quote,feature,forecast)
        state.feed_controls={feed:{'enabled':True,'revision':0,'components':{part:'running' for part in parts}}
                             for feed,parts in controls.COMPONENTS.items()}
        commands=[]
        html=(Path(__file__).resolve().parents[1]/'postgres/dashboard.html').read_text()
        grant=controls.mint(TOKEN)['access_token']
        with sync_playwright() as playwright:
            candidates=(os.getenv('CHROME_BIN'),shutil.which('chromium'),shutil.which('google-chrome'),
                        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',playwright.chromium.executable_path)
            browser_bin=next((x for x in candidates if x and Path(x).is_file()),None)
            if not browser_bin:
                self.skipTest('requires installed Chromium')
            browser=playwright.chromium.launch(executable_path=browser_bin)
            page=browser.new_page()
            page.add_init_script("""window.EventSource=class {
                constructor(){window.fixtureStream=this;} addEventListener(){} close(){}
            };""")
            def respond(route):
                from urllib.parse import urlsplit
                path=urlsplit(route.request.url).path
                if path=='/dashboard':
                    return route.fulfill(body=html,content_type='text/html')
                if path.startswith('/collector/feeds/'):
                    headers={'Access-Control-Allow-Origin':'http://127.0.0.1:18433',
                             'Access-Control-Allow-Headers':'Content-Type, Authorization','Access-Control-Allow-Methods':'PUT'}
                    if route.request.method=='OPTIONS':
                        return route.fulfill(status=204,headers=headers)
                    feed=path.split('/')[-1]
                    cmd=route.request.post_data_json
                    commands.append((feed,cmd,route.request.headers.get('authorization')))
                    state.feed_controls[feed]={'enabled':cmd['enabled'],'revision':cmd['revision']+1,
                        'components':{p:('running' if cmd['enabled'] else 'paused') for p in controls.COMPONENTS[feed]}}
                    return route.fulfill(json={'origin':controls.ORIGIN,'feed':feed,**state.feed_controls[feed]},headers=headers)
                if path=='/state/current':
                    return route.fulfill(json=state.snapshot())
                return route.fulfill(json={})
            page.route('**/*',respond)
            try:
                page.goto('http://127.0.0.1:18433/dashboard#feed_session='+grant)
                update=lambda:page.evaluate('(s)=>window.fixtureStream.onmessage({data:JSON.stringify(s)})',state.snapshot())
                page.wait_for_function('typeof window.fixtureStream?.onmessage==="function"')
                update()
                self.assertEqual(page.url,'http://127.0.0.1:18433/dashboard')
                for feed,title in [('robinhood','Robinhood'),('coinbase','Coinbase'),('polymarket','Polymarket')]:
                    page.get_by_role('button',name='Pause '+title,exact=True).click()
                    expect(page.locator('#feed-controls-message')).to_have_text(title+' pause request saved.')
                    update()
                    self.assertEqual([k for k,v in state.feed_controls.items() if not v['enabled']],[feed])
                    if feed in ('coinbase','polymarket'):
                        expect(page.locator('#forecast-up')).to_have_text('—')
                        expect(page.locator('#forecast-state')).to_contain_text(feed+' paused')
                    page.get_by_role('button',name='Resume '+title,exact=True).click()
                    expect(page.locator('#feed-controls-message')).to_have_text(title+' resume request saved.')
                    update()
                self.assertEqual(len(commands),6)
                self.assertTrue(all(a=='Bearer '+grant for _,_,a in commands))
                page.reload()
                page.wait_for_function('typeof window.fixtureStream?.onmessage==="function"')
                update()
                expect(page.get_by_role('button',name='Pause Robinhood')).to_be_disabled()
            finally:
                browser.close()
