"""Opt-in, value-limited correlation events for the PP first-quote experiment."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone


def boundary_trace(stage, market=None, *, quote=None, **fields):
    if os.environ.get('TRADEBOT_PP_BOUNDARY_TRACE') != '1':
        return
    row = {'reader': 'canonical_rest', 'stage': stage, 'mono_ns': time.monotonic_ns(),
           'ts_utc': datetime.now(timezone.utc).isoformat(), **fields}
    if market:
        metadata = market.get('payload', {})
        row.update(market_id=market.get('market_id'), slug=metadata.get('slug'),
                   window_start=metadata.get('start'), window_end=metadata.get('end'))
    if quote:
        prices = quote.get('payload', {})
        row.update(event_id=quote.get('event_id'), received_at=quote.get('received_at'),
                   source_time=quote.get('source_time'), best_bid=prices.get('best_bid'),
                   best_ask=prices.get('best_ask'))
    logging.getLogger(__name__).warning('pp_boundary_trace %s', json.dumps(row, separators=(',', ':')))
