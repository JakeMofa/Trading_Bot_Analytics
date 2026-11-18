"""Generated fault tests for restoring the exact PP runtime before migration."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller as c
import linux_actions as a


IMAGE='sha256:'+'a'*64
PG_ID='f'*64
IDS={service:str(index+1)*64 for index,service in enumerate(a.SERVICES)}
SCHEMA={'count':2,'digest':'a'*32}


class DockerBudget:
    def __init__(self):
        self.calls=[]
        self.running={cid:False for cid in IDS.values()}
        self.policy={cid:'no' for cid in IDS.values()}
        self.fail_start=False

    def timeout(self,maximum=None):
        return 100 if maximum is None else min(100,maximum)

    def run(self,args,**kwargs):
        self.calls.append(args)
        if args[:2]==['docker','update']:
            policy=args[2].split('=',1)[1]
            for cid in args[3:]:self.policy[cid]=policy
        elif args[:2]==['docker','start']:
            for cid in args[2:]:
                self.running[cid]=True
                if self.fail_start:raise c.DeploymentHold('simulated_partial_start')
        elif args[:2]==['docker','stop']:
            for cid in args[4:]:self.running[cid]=False
        return b''


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder=Path(self.temp.name)
        self.context=c.Context(c.Request('a'*40,'b'*64,'c'*64),folder,folder,IMAGE,
                               failed_stage='migrate',migration_started=True)
        self.actions=a.LinuxActions()
        self.actions.pg_id=PG_ID
        self.actions.pg_volume=a.PG_VOLUME
        self.actions.fence_started=True
        self.actions.fence_completed=True
        self.budget=DockerBudget()
        self.rows={service:self.row(service) for service in a.SERVICES}
        self.actions.prior_runtime={'ids':IDS,'rows':deepcopy(self.rows),'image':IMAGE,
                                    'pg_id':PG_ID,'pg_volume':a.PG_VOLUME,'schema':SCHEMA}

    @staticmethod
    def row(service):
        return {'Id':IDS[service],'Image':IMAGE,'Config':{'Cmd':a.COMMANDS[service],
                'Labels':{'com.docker.compose.project':a.PROJECT,'com.docker.compose.service':service},
                'Env':['TRADEBOT_COLLECTOR_ENABLED=false','ENABLE_LOCAL_RETENTION=false',
                       'ENABLE_OPENAI_ANALYST=false']},
                'Mounts':[{'Destination':'/run/secrets/app_dsn','Source':'/etc/tradebot/pp-runtime/app_dsn','RW':False}],
                'HostConfig':{'Memory':a.MEMORY[service]*1024**2,'RestartPolicy':{'Name':'unless-stopped'}},
                'NetworkSettings':{'Networks':{a.NETWORK:{}}},
                'State':{'Running':True,'Health':{'Status':'healthy'}}}

    def ids(self,context,budget,services,all=False):
        return [IDS[services[0]]]

    def inspect(self,budget,ids):
        service=next(name for name,cid in IDS.items() if cid==ids[0])
        row=deepcopy(self.rows[service])
        row['State']['Running']=self.budget.running[ids[0]]
        row['HostConfig']['RestartPolicy']['Name']=self.budget.policy[ids[0]]
        return [row]

    def runtime(self,context,budget):
        self.assertEqual(context.image,IMAGE)
        self.assertTrue(all(self.budget.running.values()))
        self.assertTrue(all(value=='unless-stopped' for value in self.budget.policy.values()))

    def recover(self):
        with patch.object(self.actions,'_ids',side_effect=self.ids), \
             patch.object(self.actions,'_inspect',side_effect=self.inspect), \
             patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_schema_ledger',return_value=SCHEMA), \
             patch.object(self.actions,'_runtime',side_effect=self.runtime), \
             patch.object(self.actions,'_host_api'),patch.object(self.actions,'_host_operator'):
            return self.actions.recover(self.context,self.budget)

    def test_inventory_failure_restores_exact_prior_containers_and_reports_failed_release(self):
        result=self.recover()
        self.assertEqual(result['strategy'],'prior_runtime_restored_pre_migration')
        self.assertEqual(result['prior_image_id'],IMAGE)
        self.assertEqual(result['prior_container_ids'],IDS)
        self.assertFalse(result['database_restored'])
        self.assertEqual(self.budget.calls[0],['docker','update','--restart=unless-stopped',*IDS.values()])
        self.assertEqual(self.budget.calls[1],['docker','start',*IDS.values()])
        self.assertFalse(any('compose' in args or 'migrate' in args for args in self.budget.calls))

    def test_partial_restart_is_fenced_and_never_claimed_as_recovery(self):
        self.budget.fail_start=True
        with self.assertRaisesRegex(c.DeploymentHold,'simulated_partial_start'):
            self.recover()
        self.assertFalse(any(self.budget.running.values()))
        self.assertTrue(all(value=='no' for value in self.budget.policy.values()))

    def test_changed_prior_container_blocks_start(self):
        self.rows['api']['Config']['Env'].append('TRADEBOT_COLLECTOR_ENABLED=true')
        with self.assertRaisesRegex(c.DeploymentHold,'prior_stopped_container_changed'):
            self.recover()
        self.assertEqual(self.budget.calls,[])

    def test_changed_schema_blocks_start(self):
        with patch.object(self.actions,'_ids',side_effect=self.ids), \
             patch.object(self.actions,'_inspect',side_effect=self.inspect), \
             patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_schema_ledger',return_value={'count':3,'digest':'b'*32}):
            with self.assertRaisesRegex(c.DeploymentHold,'pre_migration_database_changed'):
                self.actions.recover(self.context,self.budget)
        self.assertEqual(self.budget.calls,[])

    def test_changed_postgres_identity_blocks_start(self):
        def changed(context,budget):self.actions.pg_id='e'*64
        with patch.object(self.actions,'_ids',side_effect=self.ids), \
             patch.object(self.actions,'_inspect',side_effect=self.inspect), \
             patch.object(self.actions,'_postgres',side_effect=changed), \
             patch.object(self.actions,'_schema_ledger',return_value=SCHEMA):
            with self.assertRaisesRegex(c.DeploymentHold,'pre_migration_database_changed'):
                self.actions.recover(self.context,self.budget)
        self.assertEqual(self.budget.calls,[])

    def test_marker_or_attempted_oneoff_forbids_prior_restore(self):
        marker=self.context.staging/'migration-oneoff-attempted.json'
        marker.write_text('{}')
        with self.assertRaisesRegex(c.DeploymentHold,'pre_migration_restore_not_proven'):
            self.actions._restore_prior_before_migration(self.context,self.budget)
        marker.unlink()
        self.actions.migration_oneoff_attempted=True
        with patch.object(self.actions,'_cleanup_oneoffs'),patch.object(self.actions,'_fence'), \
             patch.object(self.actions,'_postgres'),patch.object(self.actions,'_inventory',return_value={}):
            result=self.actions.recover(self.context,self.budget)
        self.assertEqual(result['strategy'],'stop_candidate_keep_database')
        self.assertEqual(self.budget.calls,[])

    def test_first_migration_oneoff_writes_durable_marker_before_docker_run(self):
        seen=[]
        def run(args,**kwargs):
            seen.append((self.context.staging/'migration-oneoff-attempted.json').exists())
            return b''
        with patch.object(self.actions,'_cleanup_oneoffs'):
            self.actions._oneoff(self.context,self.budget,'migrate',compose=lambda args,timeout:run(args))
        marker=self.context.staging/'migration-oneoff-attempted.json'
        self.assertEqual(seen,[True])
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode),0o600)
        self.assertEqual(json.loads(marker.read_text())['attempt_id'],self.actions.attempt_id)
        self.assertTrue(self.actions.migration_oneoff_attempted)

    def test_inventory_failure_precedes_oneoff_and_keeps_restore_eligible(self):
        actions=a.LinuxActions()
        def capture(context,budget):actions.prior_runtime=self.actions.prior_runtime
        with patch.object(actions,'_capture_prior_runtime',side_effect=capture), \
             patch.object(actions,'_fence'), \
             patch.object(actions,'_inventory',side_effect=c.DeploymentHold('inventory_exceeds_generated_bound')), \
             patch.object(actions,'_oneoff') as oneoff:
            with self.assertRaisesRegex(c.DeploymentHold,'inventory_exceeds_generated_bound'):
                actions.migrate(self.context,self.budget)
        self.assertTrue(actions.fence_started and actions.fence_completed)
        self.assertFalse(actions.migration_oneoff_attempted)
        self.assertFalse((self.context.staging/'migration-oneoff-attempted.json').exists())
        oneoff.assert_not_called()

    def test_first_install_has_no_prior_runtime_and_can_reach_migration(self):
        actions=a.LinuxActions()
        actions.pg_id=PG_ID;actions.pg_volume=a.PG_VOLUME
        with patch.object(actions,'_ids',return_value=[]),patch.object(actions,'_inspect') as inspect:
            actions._capture_prior_runtime(self.context,self.budget)
        inspect.assert_not_called()
        self.assertIsNone(actions.prior_runtime)

    def test_partial_prior_runtime_fails_before_fence(self):
        actions=a.LinuxActions()
        actions.pg_id=PG_ID;actions.pg_volume=a.PG_VOLUME
        def partial(context,budget,services,all=False):
            return [IDS[services[0]]] if services[0]=='api' else []
        with patch.object(actions,'_ids',side_effect=partial),patch.object(actions,'_fence') as fence:
            with self.assertRaisesRegex(c.DeploymentHold,'prior_runtime_missing_or_ambiguous'):
                actions.migrate(self.context,self.budget)
        fence.assert_not_called()
        self.assertFalse(actions.fence_started)


if __name__=='__main__':unittest.main()
