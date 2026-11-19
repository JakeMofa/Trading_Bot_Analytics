"""Two independent #185 generated windows and actual FastAPI HTTP contracts."""
from copy import deepcopy
from pathlib import Path
import json
import re
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
sys.path.insert(0, str(ROOT / 'deploy/preprod'))
from fastapi.testclient import TestClient
from postgres.api import create_app
from postgres.config import Settings
from postgres.archive_codec import ArchiveLimits
from postgres.lifecycle import ArchiveWorker
from test_research_window import fixture, read, ORIGIN
import history_parity_evidence as parity

GOLDEN = ROOT / 'backend/tests/fixtures/history_parity_two_generations.json'


def generated_bundle():
    bundle = {'source_sha': 'd2ca040bb11b70c1a809e6b056ca7ebb1c6c8d05', 'windows': []}
    # Isolated model fixtures: no writer, operator authority or native DROP proof.
    for n in (1, 2):
        generation = str(uuid.UUID(int=n))
        with patch('postgres_lifecycle_fixtures.uuid.uuid4', return_value=uuid.UUID(generation)):
            repo, transport, source, records, reader = fixture()
        window = dict(origin_id=ORIGIN, generation_id=generation, phases={})
        for phase in parity.PHASES:
            if phase == 'sealed': repo.record['state'] = 'sealed'
            if phase == 'retired':
                worker = ArchiveWorker(repo, transport, ArchiveLimits(max_rows=500))
                assert worker.archive_cycle(generation)['status'] == 'archived'
                worker.retire_generated(generation, qualification_enabled=True)
                assert repo.rows == []
            research = read(reader, records)
            class Store:
                def verify(self): pass  # Explicit generated HTTP store; no database.
                def predictions(self, limit):
                    return [dict(id=f['prediction_id'], **{key: f.get(key) for key in parity.PREDICTION})
                            for f in research['saved_forecasts']][:limit]
                def chart(self):
                    # This is the actual missing-current-market HTTP contract.
                    return dict(status='missing', market=None, points=[])
            with TestClient(create_app(Settings(origin_id=ORIGIN), Store(), history=reader.raw, refresh=False)) as client:
                responses = {}
                for route in ('/history/predictions?limit=500', '/history/coinbase-chart', '/history/context'):
                    response = client.get(route)
                    responses[route] = dict(status_code=response.status_code, body=response.json())
            window['phases'][phase] = dict(research=research, http=responses,
                research_artifact=f'generated/{generation}/{phase}/research.json',
                http_artifact=f'generated/{generation}/{phase}/http.json')
        bundle['windows'].append(window)
    return json.loads(json.dumps(bundle))


class HistoryParityEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = generated_bundle()

    def test_exact_two_generation_http_and_research_fixture_matches_golden(self):
        def comparable_generated_capture(bundle):
            # Compressed bytes can differ across Python/zlib builds. Preserve
            # the real hashes in the actual capture/report; normalize only this
            # synthetic golden comparison's raw transport object hashes. Exact
            # decoded input strings, envelope hashes and every saved link remain.
            result = deepcopy(bundle)
            for window in result['windows']:
                for phase in window['phases'].values():
                    for page in phase['research']['provenance']['raw_pages']:
                        self.assertTrue(all(re.fullmatch('[0-9a-f]{64}', value)
                                            for value in page['sha256']))
                        page['sha256'] = ['<runtime-compressed-object-sha256>' for _ in page['sha256']]
            return result
        self.assertEqual(comparable_generated_capture(self.bundle),
                         comparable_generated_capture(json.loads(GOLDEN.read_text())))
        result = parity.audit(self.bundle)
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(len(result['windows']), 2)
        for window in result['windows']:
            hashes = {p['research_sha256'] for p in window['phases'].values()}
            self.assertEqual(len(hashes), 1)
            self.assertTrue(all(p['context_status'] == 'unsupported' for p in window['phases'].values()))
        self.assertIn('feature or forecast recomputation', result['not_proven'])

    def test_changed_exact_value_timestamp_missing_and_duplicate_http_fail(self):
        for mutation in (
            lambda p: p['research']['inputs'][0]['payload'].update(target='100000.000000010'),
            lambda p: p['research']['inputs'][0].update(source_epoch='1794441600.000000001'),
            lambda p: p['http']['/history/predictions?limit=500']['body'].update(items=[]),
            lambda p: p['http']['/history/predictions?limit=500']['body']['items'].extend(
                deepcopy(p['http']['/history/predictions?limit=500']['body']['items'])),
            lambda p: p['http']['/history/predictions?limit=500']['body']['items'][0].update(probability_up='0.5'),
        ):
            bundle = deepcopy(self.bundle)
            mutation(bundle['windows'][1]['phases']['retired'])
            self.assertEqual(parity.audit(bundle)['result'], 'FAIL')

    def test_missing_labels_are_incomplete_and_never_synthesized(self):
        bundle = deepcopy(self.bundle)
        for phase in bundle['windows'][0]['phases'].values(): phase['research']['official_outcome_labels'] = []
        result = parity.audit(bundle)
        self.assertEqual(result['result'], 'INCOMPLETE')
        self.assertIn('official_outcome_labels_missing', result['missing_evidence'])

    def test_identity_source_phase_and_float_guards(self):
        for mutate in (
            lambda b: b.update(source_sha='d2ca040'),
            lambda b: b['windows'].pop(),
            lambda b: b['windows'][1].update(generation_id=b['windows'][0]['generation_id']),
            lambda b: b['windows'][0]['phases'].pop('sealed'),
            lambda b: b['windows'][0]['phases']['sealed'].update(latency=0.1),
        ):
            bundle = deepcopy(self.bundle); mutate(bundle)
            with self.assertRaises(ValueError): parity.audit(bundle)

    def test_cli_creates_report_once_without_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'report.json'
            command = [sys.executable, str(ROOT/'deploy/preprod/history_parity_evidence.py'),
                       '--input', str(GOLDEN), '--output', str(target)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(target.read_text())['result'], 'PASS')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == '__main__': unittest.main()
