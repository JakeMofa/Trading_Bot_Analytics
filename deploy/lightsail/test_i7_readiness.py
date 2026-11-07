"""Capacity/collector readiness fails closed, independent of cached HTTP health."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('i7_readiness', Path(__file__).with_name('i7_readiness.py'))
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        service = {'ActiveState':'active', 'UnitFileState':'enabled', 'openai_off':True,
                   'retention_off':True, 'paid_credentials_absent':True, 'guard4096':True}
        self.snapshot = {'at':self.now.isoformat(), 'revision':readiness.EXPECTED_REVISION,
                         'tracked_clean':True,'original_helper_restored':True,'authorization_absent':True,
                         'services':{k:dict(service) for k in ('tradebot-api','tradebot-ensemble','tradebot-lifecycle')},
                         'storage':{'db_bytes':1024**3,'wal_bytes':0,'free_bytes':20*1024**3},
                         'endpoints':{'/health':{'status':'ok','collector_running':True,
                          'feeds':{k:{'status':'live','last_data_at':self.now.isoformat()} for k in ('coinbase_stream','polymarket_stream')}}}}
        self.budget = dict.fromkeys(readiness.BUDGET_FIELDS, 1024**2)
        self.budget['vm_qualified'] = True

    def test_complete_qualified_evidence_only_allows_review_not_execution(self):
        result = readiness.assess(self.snapshot,self.budget,self.now)
        self.assertEqual(result['status'],'READY_FOR_OPERATOR_REVIEW')
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['database_integrity'],'NOT_CHECKED')

    def test_bridge_requires_unexpired_policy_and_actual_process_value(self):
        self.snapshot['services']['tradebot-api'].update(guard4096=False,guard_mib=5120)
        self.snapshot['storage']['db_bytes']=4096*1024**2+1024
        self.assertIn('GUARD_CHANGED_OR_UNKNOWN',readiness.assess(self.snapshot,self.budget,self.now)['reasons'])
        policy={'status':'BRIDGE_ACTIVE','revision':readiness.EXPECTED_REVISION,'old_guard_mib':4096,
                'guard_mib':5120,'applied_at':self.now.isoformat(),
                'review_due_at':(self.now+timedelta(hours=24)).isoformat()}
        result=readiness.assess(self.snapshot,self.budget,self.now,policy)
        self.assertEqual(result['status'],'READY_FOR_OPERATOR_REVIEW')
        self.assertEqual(result['guard_bytes'],5120*1024**2)
        self.assertFalse(result['execution_authorized'])
        result=readiness.assess(self.snapshot,self.budget,self.now+timedelta(hours=24),policy)
        self.assertIn('INVALID_OR_OVERDUE_BRIDGE_POLICY',result['reasons'])
        policy['guard_mib']=6144
        self.assertIn('INVALID_OR_OVERDUE_BRIDGE_POLICY',readiness.assess(self.snapshot,self.budget,self.now,policy)['reasons'])

    def test_guard_reached_and_stopped_collector_rejected_despite_health_ok(self):
        self.snapshot['storage']['db_bytes'] = readiness.GUARD_BYTES
        self.snapshot['endpoints']['/health']['collector_running'] = False
        self.snapshot['endpoints']['/health']['feeds']['storage_guard'] = {'status':'limit_reached'}
        result = readiness.assess(self.snapshot,self.budget,self.now)
        self.assertEqual(result['status'],'STOP')
        self.assertTrue({'STORAGE_GUARD_REACHED','STORAGE_GUARD_LATCHED','COLLECTOR_NOT_RUNNING'} <= set(result['reasons']))

    def test_unknown_local_only_or_malformed_build_budget_rejected(self):
        for budget in (None,{},dict(self.budget,vm_qualified=False),dict(self.budget,index_growth_bytes=True),dict(self.budget,reserve_bytes=-1)):
            with self.subTest(budget=budget):
                self.assertIn('INDEX_BUILD_BUDGET_UNQUALIFIED',readiness.assess(self.snapshot,budget,self.now)['reasons'])

    def test_guard_budget_and_free_disk_are_separate_checks(self):
        self.snapshot['storage']['db_bytes'] = readiness.GUARD_BYTES - 1024
        self.snapshot['storage']['free_bytes'] = 1024
        reasons = readiness.assess(self.snapshot,self.budget,self.now)['reasons']
        self.assertIn('INSUFFICIENT_GUARD_HEADROOM',reasons)
        self.assertIn('INSUFFICIENT_FILESYSTEM_RESERVE',reasons)

    def test_stale_evidence_and_feed_cannot_be_reported_ready(self):
        reasons = readiness.assess(self.snapshot,self.budget,self.now+timedelta(minutes=6))['reasons']
        self.assertIn('STALE_OR_FUTURE_EVIDENCE',reasons)
        self.assertIn('FEED_NOT_FRESH_LIVE:coinbase_stream',reasons)

    def test_unsafe_service_flags_revision_or_unknown_storage_rejected(self):
        self.snapshot['services']['tradebot-api']['guard4096'] = False
        self.snapshot['services']['tradebot-ensemble']['paid_credentials_absent'] = False
        self.snapshot['revision'] = 'wrong'
        del self.snapshot['storage']['wal_bytes']
        reasons = readiness.assess(self.snapshot,self.budget,self.now)['reasons']
        self.assertIn('GUARD_CHANGED_OR_UNKNOWN',reasons)
        self.assertIn('UNSAFE_OR_UNKNOWN_FLAGS:tradebot-ensemble',reasons)
        self.assertIn('UNEXPECTED_REVISION',reasons)
        self.assertIn('UNKNOWN_STORAGE',reasons)

    def test_cli_cannot_execute_or_modify_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'snapshot.json';path.write_text(json.dumps(self.snapshot))
            before = path.read_bytes()
            result = subprocess.run([sys.executable,readiness.__file__,'--snapshot',str(path)],capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,2)
            self.assertEqual(json.loads(result.stdout)['status'],'STOP')
            self.assertEqual(path.read_bytes(),before)
            refused = subprocess.run([sys.executable,readiness.__file__,'--snapshot',str(path),'--execute'],capture_output=True,timeout=3)
            self.assertEqual(refused.returncode,2)


if __name__=='__main__':unittest.main()
