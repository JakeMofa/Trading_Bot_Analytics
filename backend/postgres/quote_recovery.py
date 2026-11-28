"""Bounded REST recovery for a quiet Polymarket US market subscription."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time

from .domain import timestamp
from .live_contract import QuoteContractError
from .live_diagnostics import SourceHTTPFailure, SourceTransportFailure, diagnose


QUIET_AFTER = timedelta(seconds=30)
PROBE_INTERVAL = 30
MAX_BACKOFF = 60
REQUEST_DEADLINE = 5


@dataclass(frozen=True)
class QuoteFeedSnapshot:
    market: dict | None
    last_ws_at: datetime | None = None
    ws_revision: int = 0
    paused: bool = False


@dataclass(frozen=True)
class RecoveredQuote:
    market_id: str
    checked_at: datetime
    quote: dict | None  # None is a confirmed empty book.


def _market_window(market):
    return (market['market_id'], timestamp(market['payload']['start']),
            timestamp(market['payload']['end']))


class QuietQuoteRecovery:
    def __init__(self, snapshot, fetch, publish, *, on_failure=None,
                 clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
                 request_deadline=REQUEST_DEADLINE):
        self.snapshot = snapshot
        self.fetch = fetch
        self.publish = publish
        self.on_failure = on_failure
        self.clock = clock
        self.monotonic = monotonic
        self.request_deadline = request_deadline
        self._in_flight = False
        self._next_probe = float('-inf')
        self._delay = PROBE_INTERVAL

    async def check(self):
        if self._in_flight or self.monotonic() < self._next_probe:
            return
        before = self.snapshot()
        if before.market is None or before.paused:
            return
        market_id, start, end = _market_window(before.market)
        now = self.clock()
        if not start <= now < end or now - max(start, before.last_ws_at or start) < QUIET_AFTER:
            return

        self._in_flight = True
        try:
            async with asyncio.timeout(self.request_deadline):
                quote = await self.fetch(before.market)
            if quote is not None and quote['market_id'] != market_id:
                raise QuoteContractError('identity_mismatch', 'REST quote market identity mismatch')
        except (TimeoutError, SourceHTTPFailure, SourceTransportFailure, QuoteContractError) as error:
            self._next_probe = self.monotonic() + self._delay
            self._delay = min(self._delay * 2, MAX_BACKOFF)
            if self.on_failure is not None:
                self.on_failure(diagnose('polymarket_bbo', error).code)
            return
        finally:
            self._in_flight = False

        self._delay = PROBE_INTERVAL
        self._next_probe = self.monotonic() + self._delay
        after = self.snapshot()
        checked_at = self.clock()
        if (after.paused or after.market is None
                or _market_window(after.market) != (market_id, start, end)
                or not start <= checked_at < end
                or after.ws_revision != before.ws_revision):
            return
        # Publication is synchronous so the guard and handoff to the writer
        # cannot interleave with a WebSocket update or a feed control change.
        self.publish(RecoveredQuote(market_id, checked_at, quote))
