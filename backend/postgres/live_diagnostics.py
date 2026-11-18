"""Fixed, non-payload failure codes for the private PP collector operator."""
from __future__ import annotations

import asyncio

import httpx


OPERATIONS = frozenset({
    'ownership', 'session', 'coinbase_stream', 'coinbase_write',
    'coinbase_candles', 'coinbase_candle_write', 'coinbase_candle_loop',
    'polymarket_discovery', 'polymarket_market_write', 'polymarket_bbo',
    'polymarket_bbo_write', 'polymarket_loop',
})
CATEGORIES = frozenset({
    'timeout', 'transport', 'http_404', 'http_429', 'http_4xx', 'http_5xx',
    'http_unexpected',
    'invalid_or_unavailable', 'identity_mismatch', 'unexpected', 'ended',
    'lease_lost', 'deadline_reached', 'durable_off_unproven',
})


class CollectorHold(RuntimeError):
    """A collector session must stop and leave its durable writer OFF."""


class LiveDiagnostic(CollectorHold):
    def __init__(self, operation: str, category: str):
        if operation not in OPERATIONS or category not in CATEGORIES:
            raise ValueError('unreviewed collector diagnostic')
        self.code = operation + '.' + category
        super().__init__(self.code)


class SourceHTTPFailure(ValueError):
    """Provider status is reduced to an allowlisted category, never a body."""

    def __init__(self, status: int, message: str):
        self.category = ('http_429' if status == 429 else
                         'http_404' if status == 404 else
                         'http_5xx' if 500 <= status <= 599 else
                         'http_4xx' if 400 <= status <= 499 else 'http_unexpected')
        super().__init__(message)


class SourceTransportFailure(ValueError):
    def __init__(self, *, timeout: bool, message: str):
        self.category = 'timeout' if timeout else 'transport'
        super().__init__(message)


def diagnose(operation: str, error: Exception) -> LiveDiagnostic:
    """Classify types and fixed fields only; never copy exception text."""
    if isinstance(error, (SourceHTTPFailure, SourceTransportFailure)):
        category = error.category
    elif isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        category = 'timeout'
    elif isinstance(error, (httpx.TransportError, OSError)):
        category = 'transport'
    elif isinstance(error, ValueError):
        category = 'invalid_or_unavailable'
    else:
        category = 'unexpected'
    return LiveDiagnostic(operation, category)
