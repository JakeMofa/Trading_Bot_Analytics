from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from cases import match_cases
from collector import connect, normalize, save_market
from features import initialize


def raw(id, start, end, status, final=None):
    return {'id': id, 'slug': 'cpc-' + id, 'status': status,
            'assetPriceTerms': {'asset': {'symbol': 'btc'},
              'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN', 'horizon': '15m',
              'windowStart': start, 'windowEnd': end,
              'priceToBeat': {'value': '100'},
              'settlementPrice': {'value': final} if final else None}}


VALUES = {'distance_pct': '0.02', 'realized_volatility_15m': '0.001',
          'return_5m': '0.002', 'seconds_remaining': 300}
QUALITY = {'price': {'status': 'fresh'}, 'candle_status': 'fresh'}


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize(self.db)

    def tearDown(self): self.db.close()

    def add(self, id, start, end, seen, as_of):
        with self.db:
            save_market(self.db, normalize(raw(id, start, end, 'MARKET_STATUS_OPEN')), seen)
            self.db.execute('''INSERT INTO feature_snapshots
              (market_id,as_of,version,values_json,quality_json,evidence_json)
              VALUES(?,?,?,?,?,?)''', (id, as_of, 1, json.dumps(VALUES), json.dumps(QUALITY), '{}'))
        return self.db.execute('SELECT id FROM feature_snapshots WHERE market_id=?', (id,)).fetchone()[0]

    def test_known_outcome_only_one_snapshot_per_market(self):
        self.add('prior', '2026-09-30T01:00:00Z', '2026-09-30T01:15:00Z',
                 '2026-09-30T01:00:30Z', '2026-09-30T01:05:00Z')
        with self.db:
            self.db.execute('''INSERT INTO feature_snapshots
              (market_id,as_of,version,values_json,quality_json,evidence_json)
              VALUES(?,?,?,?,?,?)''', ('prior', '2026-09-30T01:08:00Z', 1,
                        json.dumps(VALUES), json.dumps(QUALITY), '{}'))
            save_market(self.db, normalize(raw('prior', '2026-09-30T01:00:00Z',
              '2026-09-30T01:15:00Z', 'MARKET_STATUS_RESOLVED', '101')),
              '2026-09-30T01:20:00Z')
        target = self.add('current', '2026-09-30T01:30:00Z',
                 '2026-09-30T01:45:00Z', '2026-09-30T01:30:10Z',
                 '2026-09-30T01:35:00Z')
        result = match_cases(self.db, target)
        self.assertEqual(result['eligible_markets'], 1)
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(result['matches'][0]['outcome'], 'UP')
        self.assertEqual(result['matches'][0]['outcome_known_at'], '2026-09-30T01:20:00Z')

    def test_future_result_is_excluded_even_if_current_market_row_resolved(self):
        self.add('prior', '2026-09-30T01:00:00Z', '2026-09-30T01:15:00Z',
                 '2026-09-30T01:00:30Z', '2026-09-30T01:05:00Z')
        target = self.add('current', '2026-09-30T01:30:00Z',
                 '2026-09-30T01:45:00Z', '2026-09-30T01:30:10Z',
                 '2026-09-30T01:35:00Z')
        with self.db:
            save_market(self.db, normalize(raw('prior', '2026-09-30T01:00:00Z',
              '2026-09-30T01:15:00Z', 'MARKET_STATUS_RESOLVED', '101')),
              '2026-09-30T01:40:00Z')
        self.assertEqual(match_cases(self.db, target)['eligible_markets'], 0)


if __name__ == '__main__': unittest.main()
