import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
import maintenance_host as h

class AdapterTests(unittest.TestCase):
    def host(self,root):return h.Host(SimpleNamespace(ROOT=Path(root),reviewed_run=Mock(return_value='')), 'b'*40,Path('bundle'))
    def test_reserve_amendment_is_maintenance_only(self):
        self.assertEqual(h.POLICY['headroom_mib'],128)
        self.assertEqual(h.POLICY['ceiling_mib'],5120)
        self.assertEqual(h.rv.POLICY['storage_reserve_mb'],512)
        self.assertEqual(h.rv.POLICY['storage_ceiling_mb'],5120)

    def test_allocation_counts_physical_main_and_wal(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'data';p.mkdir();(p/'btc_intelligence.db').write_bytes(b'x'*100);(p/'btc_intelligence.db-wal').write_bytes(b'x'*50)
            self.assertEqual(self.host(root).allocation(1)['physical_mib'],150/1048576)
    def test_command_reserves_reaping_and_never_exceeds_caller_budget(self):
        host=self.host('/tmp');host.stop('tradebot-api',30)
        self.assertEqual(host.cd.reviewed_run.call_args.kwargs['timeout'],20)
        with self.assertRaises(h.rv.Stop):host.start('tradebot-api',10)
    def test_helper_code_restoration_continues_after_one_failure(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);doc={'helpers':{},'original_helpers':{}}
            for name in h.FILES:
                target=p/name;target.write_text('new');doc['helpers'][name]=h.rv.sha(target)
                original=p/('saved-'+name);original.write_text('original')
                doc['original_helpers'][name]={'path':str(original),'sha256':h.rv.sha(original),'mode':0o700}
            doc['helpers']['deploy.py']='mismatch'
            host=self.host(root);host.doc=doc
            with patch.object(h,'__file__',str(p/'maintenance_host.py')):
                with self.assertRaises(h.controller.Stop):host.restore_helpers()
            self.assertEqual((p/'smoke.py').read_text(),'original')
            self.assertEqual((p/'deploy.py').read_text(),'new')
    def test_monitor_partial_failure_still_attempts_every_restore(self):
        host=self.host('/tmp');host.monitors={'timer':'active','monitor':'active'}
        host.start=Mock(side_effect=[RuntimeError(),None])
        with self.assertRaises(h.controller.Stop):host.restore_monitor(None,50)
        self.assertEqual(host.start.call_count,2)
    def test_verification_child_timeout_reaps_without_other_process_signals(self):
        host=self.host('/tmp');child=Mock();child.communicate.side_effect=TimeoutError()
        with patch.object(h.subprocess,'Popen',return_value=child),patch.object(host,'reap_owned_child') as reap:
            with self.assertRaises(TimeoutError):host.verify(10,30)
            reap.assert_called_once_with(10)
    def test_workflow_routes_and_interruption_sum(self):
        p=Path(__file__).resolve().parents[2]
        self.assertIn('timeout-minutes: 50',(p/'.github/workflows/deploy-tradebot.yml').read_text())
        self.assertEqual(h.controller.OTHER+h.controller.VERIFY+h.controller.REAP+h.controller.RECOVERY,h.controller.INTERRUPTION)

    def test_resumed_collection_uses_ceiling_not_quiescent_reserve(self):
        from datetime import datetime,timezone,timedelta
        import json
        now=datetime.now(timezone.utc);t=now.isoformat();host=self.host('/tmp')
        host.allocation=Mock(return_value={'physical_mib':5000,'headroom_mib':120})
        state={'market':{'id':'m','slug':'m','start':(now-timedelta(seconds=5)).isoformat(),'end':(now+timedelta(minutes=5)).isoformat()},'coinbase':{'source_time':t,'received_at':t},'polymarket':{'slug':'m','source_time':t,'received_at':t}}
        health={'collector':{'running':True},'feeds':{n:{'status':'live'} for n in ('coinbase_stream','polymarket_stream')}}
        with patch.object(h.rv,'fetch',side_effect=[health,state]),patch.object(h.rv,'owned_process',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'coinbase_persisted':t,'polymarket_persisted':t}))):
            host.collection_probe()
