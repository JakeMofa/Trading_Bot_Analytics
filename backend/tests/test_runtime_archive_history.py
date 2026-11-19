import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.runtime_history import RuntimeHistory, configured_history
from postgres.history import HistoryError
from postgres.config import Settings


class RuntimeArchiveHistoryTests(unittest.TestCase):
    def test_generation_binding_and_cleanup(self):
        repo, raw = Mock(), Mock()
        repo.generation.return_value = dict(origin_id='pp-live-pp', state='retired')
        factory = Mock(return_value=raw)
        reader = RuntimeHistory(repo,factory,origin_id='pp-live-pp')
        generation = '00000000-0000-0000-0000-000000000001'
        with patch('postgres.runtime_history.ArchiveHistory') as history:
            def fetch(*args, **kwargs):
                transport = history.call_args.args[1]
                transport.read_authenticated(transport._prefix+'fixture', max_bytes=1024, timeout_seconds=1)
                return {'rows':[]}
            history.return_value.read_generation.side_effect = fetch
            self.assertEqual(reader.read_generation(generation),{'rows':[]})
            self.assertEqual(history.call_args.args[1].generation_id,generation)
            raw.close.assert_called_once()
            history.return_value.read_generation.side_effect=HistoryError('corrupt','failed')
            with self.assertRaises(HistoryError):
                reader.read_generation(generation)
        self.assertEqual(raw.close.call_count,1)

    def test_wrong_origin_and_busy_do_not_open_cloud(self):
        repo, factory = Mock(), Mock()
        repo.generation.return_value = dict(origin_id='production',state='retired')
        reader = RuntimeHistory(repo,factory,origin_id='pp-live-pp')
        with self.assertRaises(HistoryError):
            reader.read_generation('00000000-0000-0000-0000-000000000001')
        factory.assert_not_called()
        reader._admission.acquire()
        with self.assertRaisesRegex(HistoryError,'already running'):
            reader.read_generation('00000000-0000-0000-0000-000000000001')
        reader._admission.release()

    def test_local_does_not_open_cloud_and_defaults_off(self):
        repo, factory = Mock(), Mock()
        repo.generation.return_value = dict(origin_id='pp-live-pp',state='sealed')
        with patch('postgres.runtime_history.ArchiveHistory'):
            RuntimeHistory(repo,factory,origin_id='pp-live-pp').read_generation('00000000-0000-0000-0000-000000000001')
        factory.assert_not_called()
        self.assertIsNone(configured_history(Settings(),Mock(),{}))
        with self.assertRaises(ValueError):
            configured_history(Settings(),Mock(),{'TRADEBOT_PP_ARCHIVE_HISTORY':'true'})

    def test_api_uses_configured_reader_and_reports_failed_retrieval(self):
        from fastapi.testclient import TestClient
        from postgres.api import create_app
        settings = Settings()
        reader = Mock()
        reader.read_generation.return_value = {'rows':[], 'provenance':{'tier':'authenticated_archive'}}
        with patch('postgres.runtime_history.configured_history',return_value=reader):
            app = create_app(settings,store=Mock(),refresh=False)
        client = TestClient(app)
        response = client.get('/history/archive/00000000-0000-0000-0000-000000000001')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['provenance']['tier'],'authenticated_archive')
        reader.read_generation.side_effect = HistoryError('archive_integrity','failed')
        response = client.get('/history/archive/00000000-0000-0000-0000-000000000001')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['detail']['code'],'archive_integrity')
