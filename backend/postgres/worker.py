"""Independent discovery and one serial calculation loop; no feed/network calls."""
import argparse
import asyncio
import logging

from .calculation import calculate, forecast
from .config import Settings
from .domain import utcnow
from .store import PublicationRejected, Store

LOG = logging.getLogger(__name__)


class CalculationWorker:
    def __init__(self, store, clock=utcnow):
        self.store, self.clock = store, clock
        self.market = None

    def discover_once(self):
        self.market = self.store.active_market(self.clock())

    def calculate_once(self):
        market = self.market
        if not market:
            return None
        at = self.clock()
        price,candles = self.store.inputs(market['id'],at)
        result = calculate(market,price,candles,at)
        if result is None:
            return None
        values,quality,evidence = result
        snapshot = {'market_id':market['id'],'as_of':at.isoformat(),'values':values,'quality':quality,'evidence':evidence}
        prediction = forecast(market,snapshot,self.clock())
        if not prediction or (self.market or {}).get('id') != market['id']:
            return None
        try:
            return self.store.save_calculation(market,snapshot,prediction,self.clock())
        except PublicationRejected:
            return None

    async def run(self):
        async def discover():
            while True:
                try:
                    await asyncio.to_thread(self.discover_once)
                except Exception as error:
                    self.market = None
                    LOG.warning('discovery unavailable: %s',type(error).__name__)
                await asyncio.sleep(0.5)
        async def calculate_serially():
            while True:
                try:
                    await asyncio.to_thread(self.calculate_once)
                except Exception as error:
                    LOG.warning('calculation unavailable: %s',type(error).__name__)
                await asyncio.sleep(5)
        # A blocked calculation cannot delay discovery. Only one calculation is ever outstanding.
        async with asyncio.TaskGroup() as group:
            group.create_task(discover())
            group.create_task(calculate_serially())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    store = Store(Settings.from_env())
    store.verify()
    worker = CalculationWorker(store)
    if args.once:
        worker.discover_once()
        print('calculated' if worker.calculate_once() else 'no_publishable_market')
    else:
        asyncio.run(worker.run())


if __name__ == '__main__':
    main()
