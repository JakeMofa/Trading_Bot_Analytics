"""Fail-closed isolated development configuration; no implicit live collection."""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = 'preprod'
    data_mode: str = 'generated'
    origin_id: str = 'generated-pp'
    dsn: str = ''
    outbox_max_pending: int = 10000

    def __post_init__(self):
        if self.environment != 'preprod':
            raise ValueError('only isolated preprod is qualified by this application')
        if self.data_mode not in ('generated', 'replay'):
            raise ValueError('live/production-preview modes are not qualified')
        if not self.origin_id or len(self.origin_id) > 128:
            raise ValueError('origin identity required')
        if not 10 <= self.outbox_max_pending <= 100000:
            raise ValueError('pending outbox bound must be 10..100000')

    @classmethod
    def from_env(cls):
        if os.getenv('TRADEBOT_COLLECTOR_ENABLED', 'false').lower() not in ('false', '0', 'off'):
            raise ValueError('real collector is unavailable and must remain OFF')
        dsn, path = os.getenv('TRADEBOT_DATABASE_DSN'), os.getenv('TRADEBOT_DATABASE_DSN_FILE')
        if dsn and path:
            raise ValueError('configure one database credential source')
        if path:
            dsn = Path(path).read_text().strip()
        return cls(os.getenv('TRADEBOT_ENVIRONMENT', 'preprod'), os.getenv('TRADEBOT_DATA_MODE', 'generated'),
                   os.getenv('TRADEBOT_ORIGIN_ID', 'generated-pp'), dsn or '',
                   int(os.getenv('TRADEBOT_OUTBOX_MAX_PENDING','10000')))

    def public(self):
        return {'environment': self.environment, 'data_mode': self.data_mode, 'origin_id': self.origin_id,
                'collector': {'enabled': False, 'running': False, 'error': None},
                'unsupported': ['real_collector', 'production_preview', 'ensemble', 'news', 'evaluation', 'paid_ai']}
