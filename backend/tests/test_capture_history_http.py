"""Network-free executable PP capture controls and real in-process API routes."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend')); sys.path.insert(0, str(ROOT/'backend/tests'))
sys.path.insert(0, str(ROOT/'deploy/preprod'))
from fastapi.testclient import TestClient
from postgres.api import create_app
from postgres.config import Settings
from postgres.archive_codec import ArchiveLimits
from postgres.lifecycle import ArchiveWorker
from test_research_window import fixture
import capture_history_http as probe

SHA = 'd2ca040bb11b70c1a809e6b056ca7ebb1c6c8d05'
IDS = {'1': str(uuid.UUID(int=1)), '2': str(uuid.UUID(int=2))}


def response(route, body):
    wire = json.dumps(body).encode()
    return dict(route=route, body=body, observed_at=probe.utc(), completed_at=probe.utc(),
        status_code=200, elapsed_seconds=0, body_base64=base64.b64encode(wire).decode(),
        body_sha256=hashlib.sha256(wire).hexdigest())


class FixtureHTTP:
    def __init__(self, client, origin): self.client, self.origin = client, origin
    def get(self, route, *, sse=False):
        if route in ('/state/current', '/events'):
            return response(route, dict(environment='preprod', data_mode='pp_live', origin_id=probe.ORIGIN,
                generated_at='2026-11-19T10:00:00+00:00', market=None, forecast=None,
                collector={'enabled':False}))
        result = self.client.get(route)
        if result.status_code != 200: raise ValueError('fixture HTTP failure')
        body = result.json()
        # The real HTTP route is exercised on isolated generated records only.
        # Adapt just the fixture origin; no real endpoint is contacted.
        if route.startswith('/history/archive/'):
            body['provenance']['origin_id'] = probe.ORIGIN
            for row in body['rows']: row['origin_id'] = probe.ORIGIN
        if route.startswith('/history/predictions'): body['origin_id'] = probe.ORIGIN
        return response(route, body)


def captures():
    result = []
    for ordinal, generation in IDS.items():
        with patch('postgres_lifecycle_fixtures.uuid.uuid4', return_value=uuid.UUID(generation)):
            repo, transport, source, records, reader = fixture()
        repo.record['state'] = 'sealed'
        class Store:
            def verify(self): pass
            def predictions(self, limit):
                return [{'id':'fixture-forecast', 'market_id':'market', 'as_of':'2026-11-12T00:05:00Z',
                         'probability_up':'0.50000000000000000001', 'abstain_reason':None}]
            def chart(self): return {'status':'missing', 'market':None, 'points':[]}
        with TestClient(create_app(Settings(), Store(), history=reader.raw, refresh=False)) as client:
            adapter = FixtureHTTP(client, probe.ORIGIN)
            result.append(probe.collect(adapter, generation, 'retained', expected=IDS, source_sha=SHA))
            worker = ArchiveWorker(repo, transport, ArchiveLimits(max_rows=500))
            assert worker.archive_cycle(generation)['status'] == 'archived'
            worker.retire_generated(generation, qualification_enabled=True)
            result.append(probe.collect(adapter, generation, 'retired', expected=IDS, source_sha=SHA))
    return result


class CaptureHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.captures = captures()

    def test_create_only_pair_binding_and_exact_readonly_compare(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            probe.bind(path, 1, IDS['1']); probe.bind(path, 2, IDS['2'])
            with self.assertRaises((ValueError, FileExistsError)): probe.bind(path, 1, IDS['1'])
            result = probe.compare(path, self.captures)
            self.assertEqual(result['result'], 'INCOMPLETE')
            self.assertEqual(len(result['windows']), 2)
            self.assertTrue(all(window['row_count'] == 5 for window in result['windows']))
            self.assertIn('historical_context_outcomes_unsupported', result['missing_evidence'])
            self.assertEqual(self.captures[0]['rows'][0]['source_epoch'], '1794441600')
            self.assertEqual(self.captures[1]['responses'][-1]['body']['provenance']['tier'], 'authenticated_archive')

    def test_mismatches_and_tampered_captured_bytes_block(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); probe.bind(path, 1, IDS['1']); probe.bind(path, 2, IDS['2'])
            for mutation in (
                lambda c: c[1]['rows'][0].update(source_epoch='1794441600.000000001'),
                lambda c: c[1].update(operator_declared_source_sha='a'*40),
                lambda c: c[1]['responses'][0].update(body_sha256='a'*64),
                lambda c: c[1]['responses'][2]['body']['items'][0].update(probability_up='0.5'),
                lambda c: c[1].update(expected_generations={'1':IDS['2']}),
            ):
                candidate=deepcopy(self.captures); mutation(candidate)
                with self.assertRaises(ValueError): probe.compare(path, candidate)

    def test_wrong_phase_origin_paging_and_float_epoch_fail(self):
        base=self.captures[0]['responses']
        class Replay:
            def get(self, route, **kwargs): return deepcopy(base.pop(0))
        for mutate in (
            lambda rs: rs[0]['body'].update(origin_id='production'),
            lambda rs: rs[-1]['body']['provenance'].update(state='collecting'),
            lambda rs: rs[-1]['body'].update(complete=False),
            lambda rs: rs[-1]['body']['rows'][0].update(source_epoch=1794441600.0),
            lambda rs: rs[-1]['body']['rows'].append(deepcopy(rs[-1]['body']['rows'][0])),
        ):
            base=deepcopy(self.captures[0]['responses']); mutate(base)
            with self.assertRaises(ValueError): probe.collect(Replay(), IDS['1'], 'retained', expected=IDS, source_sha=SHA)

    def test_loopback_only_no_redirect_proxy_or_credentials(self):
        for url in ('http://example.com', 'https://127.0.0.1', 'http://127.0.0.1/path',
                    'http://user:secret@127.0.0.1', 'http://127.0.0.1?token=x', 'http://192.168.1.1'):
            with self.assertRaises(ValueError): probe.LoopbackHTTP(url)
        probe.LoopbackHTTP('http://127.0.0.1:8080'); probe.LoopbackHTTP('http://[::1]:8080')

    def test_socket_get_byte_deadline_and_sse_controls_without_network(self):
        class Reply(io.BytesIO):
            status=200
            def getheader(self, name): return 'text/event-stream'
        class Connection:
            sock=None
            def __init__(self,*a,**kw): self.timeout=kw['timeout']
            def request(self, method, route, headers): self.method=method; assert method=='GET'
            def getresponse(self): return Reply(b'data: {"origin_id":"pp-live-pp"}\n\n')
            def close(self): pass
        with patch.object(probe.http.client, 'HTTPConnection', Connection):
            client=probe.LoopbackHTTP('http://127.0.0.1:8080')
            self.assertEqual(client.get('/events',sse=True)['body']['origin_id'],probe.ORIGIN)
            with self.assertRaises(ValueError): probe.LoopbackHTTP('http://127.0.0.1',max_bytes=1).get('/events',sse=True)
            client.deadline=0
            with self.assertRaises(ValueError): client.get('/state/current')

    def test_pagination_full_rows_and_explicit_page_limit(self):
        responses = deepcopy(self.captures[0]['responses'])
        page = responses.pop()['body']
        rows = page['rows']
        first = deepcopy(page)
        first.update(rows=rows[:2], complete=False)
        cursor = 'v1.'+base64.urlsafe_b64encode(json.dumps([IDS['1'],rows[1]['source'],rows[1]['event_id']]).encode()).decode().rstrip('=')
        first['next_cursor'] = cursor
        last = deepcopy(page); last['rows'] = rows[2:]
        class Replay:
            def __init__(self): self.items=deepcopy(responses)+[response('/page1',first),response('/page2',last)]
            def get(self,route,**kwargs):
                item=self.items.pop(0); item['route']=route; return item
        captured=probe.collect(Replay(),IDS['1'],'retained',expected=IDS,source_sha=SHA)
        self.assertEqual(captured['rows'],rows)
        self.assertEqual(captured['row_count'],5)
        with self.assertRaises(ValueError):
            probe.collect(Replay(),IDS['1'],'retained',expected=IDS,source_sha=SHA,max_pages=1)

    def test_absolute_header_deadline_shuts_down_only_request_socket(self):
        shutdown=threading.Event()
        class Socket:
            def shutdown(self,how): shutdown.set()
        class Connection:
            sock=Socket()
            def __init__(self,*a,**kw): pass
            def request(self,*a,**kw): pass
            def getresponse(self):
                if not shutdown.wait(1): raise AssertionError('absolute timeout failed')
                raise TimeoutError('fixture header read interrupted')
            def close(self): pass
        with patch.object(probe.http.client,'HTTPConnection',Connection):
            client=probe.LoopbackHTTP('http://127.0.0.1',request_seconds=0.01,total_seconds=0.02)
            with self.assertRaises(TimeoutError): client.get('/state/current')
        self.assertTrue(shutdown.is_set())

    def test_cli_failure_retains_prior_responses_without_running_host_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); binding=path/'bindings'; probe.bind(binding,1,IDS['1'])
            output=path/'failed.json'
            class Broken:
                def __init__(self,*a,**kw): self.count=0
                def get(self,route,**kw):
                    self.count+=1
                    if self.count>1: raise TimeoutError('fixture only')
                    return deepcopy(CaptureHTTPTests.captures[0]['responses'][0])
            args=['capture_history_http.py','capture','--binding-dir',str(binding),'--ordinal','1',
                '--phase','retained','--base-url','http://127.0.0.1:8080',
                '--source-sha',SHA,'--output',str(output)]
            with patch.object(probe,'LoopbackHTTP',Broken),patch.object(sys,'argv',args):
                self.assertEqual(probe.main(),1)
            failed=json.loads(output.read_text())
            self.assertEqual(failed['result'],'FAIL')
            self.assertEqual(len(failed['responses']),1)
            self.assertEqual(failed['failure_type'],'TimeoutError')

    def test_unknown_second_uuid_is_explicit_and_cannot_compare_early(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); probe.bind(path, 1, IDS['1'])
            self.assertEqual(probe.bindings(path), {'1':IDS['1']})
            with self.assertRaises(ValueError): probe.compare(path, self.captures)
            with self.assertRaises(ValueError): probe.bind(path,2,IDS['1'])


class TrialOriginCaptureTests(unittest.TestCase):
    def test_exact_origin_binding_disallows_reusing_legacy_capture_directory(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            probe.bind(directory, 1, IDS['1'], origin=probe.TRIAL_ORIGIN)
            self.assertEqual(probe.bindings(directory, origin=probe.TRIAL_ORIGIN), {'1': IDS['1']})
            with self.assertRaisesRegex(ValueError, 'binding mismatch'):
                probe.bindings(directory)
            with self.assertRaisesRegex(ValueError, 'exact PP capture origin'):
                probe.bindings(directory, origin='pp-live-pp-trial-unqualified')
            state = dict(environment='preprod', data_mode='pp_live', origin_id=probe.TRIAL_ORIGIN,
                         generated_at='2026-11-19T00:00:00+00:00')
            probe.validate_state(state, origin=probe.TRIAL_ORIGIN)
            with self.assertRaisesRegex(ValueError, 'origin mismatch'):
                probe.validate_state(state)


if __name__=='__main__': unittest.main()
