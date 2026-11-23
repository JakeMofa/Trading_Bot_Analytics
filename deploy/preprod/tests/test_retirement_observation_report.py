import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retirement_observation_report import build


def utc(second):
    return f'2026-11-23T00:00:{second:02d}+00:00'


def snapshot(second, quotes, *, fresh=False):
    old = {'slot': 'A', 'generation_id': 'original', 'state': 'retired' if fresh else 'verified',
           'retired_at': utc(18) if fresh else None, 'relation_exists': not fresh,
           'partition_attached': not fresh}
    b = {'slot': 'B', 'generation_id': 'next', 'partition_attached': True,
         'polymarket_quotes': {'rows': quotes}}
    generations = [old, b]
    if fresh:
        generations.append({'slot': 'A', 'generation_id': 'fresh', 'partition_attached': True,
                            'started_at': utc(23), 'polymarket_quotes': {'rows': 1}})
    return {'origin_id': 'trial', 'at_utc': utc(second), 'generations': generations,
            'writer': {'generation_id': 'fresh' if fresh else 'next'}}


class VerificationProof(unittest.TestCase):
    def test_bounds_and_fresh_a(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            attempt = {'started_at': utc(0), 'sealed': 'original', 'collecting': 'next'}
            inventory = {**attempt, 'inventory': {'raw_objects': 3, 'structured_pages_examined': 4}}
            receipt = {**attempt, 'status': 'retired_pp', 'retirement_authorized': True,
                       'phase_accounting': {'elapsed_seconds': 15, 'phases': {
                           'raw_local_compare': {'calls': 3}, 'structured_compare': {'calls': 4}}}}
            for name, data in [('attempt-1', attempt), ('inventory-1', inventory), ('retire-1', receipt)]:
                (directory / (name + '.json')).write_text(json.dumps(data))
            rows = [snapshot(1,1), snapshot(6,5), snapshot(14,8), snapshot(19,17),
                    snapshot(26,17,fresh=True)]
            (directory / 'live-db.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result = build(directory, 'trial', utc(20))
            self.assertEqual(result['b_quote_count_increase'], 3)
            self.assertEqual(result['fresh_a_after_removal']['persisted_polymarket_quotes'], 1)
            (directory/'retire-1.json').unlink()
            receipt.update(status='HOLD',retirement_authorized=None)
            receipt['phase_accounting']['failed_phase'] = 'structured_compare'
            (directory/'retire-1-failure.json').write_text(json.dumps(receipt))
            result = build(directory, 'trial', utc(35))
            self.assertEqual(result['structured_pages_compared'], 3)
            self.assertIsNone(result['b_quote_count_increase'])
            self.assertIsNone(result['fresh_a_after_removal'])
