"""Read-only Chrome observation via a pinned Benchmark loopback tunnel.

Run before the requested quarter. The output contains bounded observations
of DOM paint and normal API hydration for matching against the canonical log.
The browser checks shown text and samples after two animation frames.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time


ORIGIN = 'pp-live-pp-display-20261127-02'
PAINT_OBSERVER = """
() => {
  const quote = document.querySelector('#market-quote');
  const slug = document.querySelector('#market-slug');
  window.benchmarkPaints = {};
  let lastId = null;
  new MutationObserver(() => {
    const id = quote.dataset.eventId;
    if (!id || id === lastId) return;
    lastId = id;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (quote.dataset.eventId !== id || !quote.getClientRects().length) return;
      const market = slug.textContent;
      if (!(market in window.benchmarkPaints) && Object.keys(window.benchmarkPaints).length < 6) {
        window.benchmarkPaints[market] = {
          event_id: id, browser_utc_ms: Date.now(),
          bid: document.querySelector('#market-up').textContent,
          offer: document.querySelector('#market-down').textContent,
          quote: quote.textContent
        };
      }
    }));
  }).observe(quote, {attributes:true, attributeFilter:['data-event-id']});
}
"""


def clock_sample(before, after, state):
    generated = datetime.fromisoformat(state['generated_at']).timestamp() * 1000
    return {'min_offset_ms': generated-after, 'max_offset_ms': generated-before}


def sample_market(windows, state):
    market = state.get('market') or {}
    slug = market.get('slug')
    if not market.get('active') or not slug or (slug not in windows and len(windows) >= 6):
        return
    window = windows.setdefault(slug, {'start': market['start'], 'id': market['id'],
                                       'polled_live_events': [], 'database_observations': {}})
    quote = state.get('polymarket') or {}
    event_id = quote.get('event_id')
    if (quote.get('market_id') == market['id'] and event_id
            and event_id not in window['polled_live_events'] and len(window['polled_live_events']) < 16):
        window['polled_live_events'].append(event_id)
    hydrated = state.get('database_quote_id')
    if hydrated and hydrated in window['polled_live_events']:
        window['database_observations'].setdefault(hydrated, state['generated_at'])


async def observe(args):
    import httpx
    from playwright.async_api import async_playwright
    base = f'http://127.0.0.1:{args.port}'
    samples = []
    windows = {}
    async with httpx.AsyncClient(base_url=base, timeout=3, trust_env=False) as client:
        async def read():
            before = time.time_ns()/1e6
            response = await client.get('/state/current')
            after = time.time_ns()/1e6
            response.raise_for_status()
            state = response.json()
            if state.get('origin_id') != ORIGIN or state.get('data_mode') != 'pp_live':
                raise ValueError('unexpected dashboard origin')
            return state, clock_sample(before, after, state)

        await read()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=args.chrome)
            try:
                page = await browser.new_page()
                await page.goto(base+'/dashboard', wait_until='domcontentloaded')
                await page.locator('#market-quote').wait_for(state='attached')
                await page.evaluate(PAINT_OBSERVER)
                if time.time() >= args.boundary:
                    raise ValueError('browser did not start before rollover')
                flags = set()
                while time.time() < args.boundary + 905:
                    state, offset = await read()
                    if len(samples) < 4 or time.time() >= args.boundary+895:
                        samples.append(offset)
                    sample_market(windows, state)
                    flags.add(state.get('collector',{}).get('enabled'))
                    await asyncio.sleep(.25 if args.boundary-1 < time.time() < args.boundary+90 else 2)
                return {'boundary_utc':datetime.fromtimestamp(args.boundary,timezone.utc).isoformat(),
                        'origin_id':ORIGIN, 'collector_enabled_observations':list(flags),
                        'clock_offset_bounds_ms':samples, 'state_samples':windows,
                        'browser_observations':await page.evaluate('() => window.benchmarkPaints')}
            finally:
                await browser.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--boundary', required=True, type=int, help='UTC Unix time of the target quarter')
    parser.add_argument('--chrome', help='optional operator workstation Chrome executable')
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    if not 1 <= args.port <= 65535 or args.boundary%900 or not 5 <= args.boundary-time.time() <= 300:
        parser.error('expected a loopback port and an upcoming quarter within five minutes')
    with os.fdopen(os.open(args.output, os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as output:
        json.dump(asyncio.run(observe(args)),output,indent=2,allow_nan=False)
        output.write('\n')


if __name__ == '__main__':
    main()
