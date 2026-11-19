"""PP20 forward procedure must preserve stopped profile and historical data."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller as c
import linux_actions as a
import pp20_forward_bootstrap as f
from test_linux_actions import inspected


class ForwardGuards(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(f,'prior_state',return_value={})
        patcher.start();self.addCleanup(patcher.stop)

    def rows(self):
        rows={name:inspected(name) for name in a.SERVICES}
        for index,(name,row) in enumerate(rows.items()):
            row['Id']=str(index+1)*64;row['Image']=f.FAILED_IMAGE
            row['State']['Running']=False;row['State']['OOMKilled']=False
            row['HostConfig']['RestartPolicy']['Name']='no'
            row['Config']['Labels']['com.docker.compose.oneoff']='False'
            row['Config']['Env']=[v for v in row['Config']['Env'] if not v.startswith('TRADEBOT_GENERATED_LOCAL_STORAGE=')]
        return rows

    def test_only_exact_stopped_default_off_profile_is_accepted(self):
        rows=self.rows();f.stopped_profile(rows)
        changes=[('running',lambda r:r['api']['State'].update(Running=True)),
                 ('image',lambda r:r['api'].update(Image='sha256:'+'a'*64)),
                 ('restart',lambda r:r['lifecycle']['HostConfig']['RestartPolicy'].update(Name='unless-stopped')),
                 ('live',lambda r:r['api']['Config']['Env'].append('TRADEBOT_PP_LIVE_CONTROL=true')),
                 ('secret',lambda r:r['api']['Mounts'][0].update(Source='/other/secret')),
                 ('network',lambda r:r['calculation']['NetworkSettings']['Networks'].update(egress={})),
                 ('origin',lambda r:r['lifecycle']['Config']['Env'].append('TRADEBOT_ORIGIN_ID=pp-live-pp')),
                 ('duplicate',lambda r:r['api'].update(Id=r['lifecycle']['Id'])),
                 ('oneoff',lambda r:r['api']['Config']['Labels'].update({'com.docker.compose.oneoff':'True'}))]
        for name,change in changes:
            with self.subTest(name=name):
                bad=deepcopy(rows);change(bad)
                with self.assertRaises(c.DeploymentHold):f.stopped_profile(bad)

    def test_preservation_pins_old_raw_and_generated_source_but_all_live_ack_metadata(self):
        calls=[]
        def query(actions,budget,table,where='true',expression='to_jsonb(t)'):
            calls.append((table,where,expression));return {'count':1,'digest':'a'*64}
        with patch.object(f,'fingerprint',side_effect=query):
            f.preserved_state(None,None,10000,'2026-11-19 11:00:00.000000+00')
        self.assertIn(('ops.outbox',"origin_id='generated-pp' AND id<=10000","to_jsonb(t)-'acknowledged_at'"),calls)
        self.assertIn(('ops.outbox',"origin_id='pp-live-pp'",'to_jsonb(t)'),calls)
        self.assertIn(('raw.events',"received_at<='2026-11-19 11:00:00.000000+00'::timestamptz",'to_jsonb(t)'),calls)
        self.assertIn(('core.outcomes','true','to_jsonb(t)'),calls)
        with self.assertRaises(c.DeploymentHold):f.preserved_state(None,None,1,"x';DELETE FROM raw.events;")

    def test_migration4_cannot_start_services_after_changed_source(self):
        actions=Mock();actions._json=json.loads
        actions.build.return_value='sha256:'+'a'*64
        actions._inventory.side_effect=[{'raw.events':{'count':28411}}, {'raw.events':{'count':28410}}]
        actions._oneoff.return_value=json.dumps({'environment':'preprod','operation':'migrate','result':[4]})
        with tempfile.TemporaryDirectory() as folder,patch.object(f,'preserved_state',return_value={}):
            p=Path(folder);context=c.Context(c.Request('a'*40,'b'*64,f.CONTROLLER),p,p)
            with self.assertRaisesRegex(c.DeploymentHold,'migration_changed_existing_evidence'):
                f.forward(actions,context,None,{},10000,'2026-11-19 11:00:00+00')
        actions.start.assert_not_called();actions.smoke.assert_not_called()

    def test_live_ack_or_outcome_change_after_bootstrap_stops_before_smoke(self):
        actions=Mock();actions._json=json.loads
        actions.build.return_value='sha256:'+'a'*64
        actions._inventory.return_value={'raw.events':{'count':28411}}
        actions._oneoff.return_value=json.dumps({'environment':'preprod','operation':'migrate','result':[4]})
        before={'ops.outbox':{'digest':'a'*64}}
        with tempfile.TemporaryDirectory() as folder,patch.object(f,'preserved_state',side_effect=[before,before,{'ops.outbox':{'digest':'b'*64}}]):
            p=Path(folder);context=c.Context(c.Request('a'*40,'b'*64,f.CONTROLLER),p,p)
            with self.assertRaisesRegex(c.DeploymentHold,'forward_preservation_failed'):
                f.forward(actions,context,None,before,10000,'2026-11-19 11:00:00+00')
        actions.start.assert_called_once();actions.smoke.assert_not_called()

    def test_empty_or_other_migration_result_cannot_bootstrap(self):
        for result in ([],[3],[3,4]):
            actions=Mock();actions._json=json.loads;actions.build.return_value='sha256:'+'a'*64
            actions._oneoff.return_value=json.dumps({'environment':'preprod','operation':'migrate','result':result})
            with tempfile.TemporaryDirectory() as folder,patch.object(f,'preserved_state',return_value={}):
                p=Path(folder);context=c.Context(c.Request('a'*40,'b'*64,f.CONTROLLER),p,p)
                with self.assertRaisesRegex(c.DeploymentHold,'forward_migration4_not_proven'):
                    f.forward(actions,context,None,{},10000,'2026-11-19 11:00:00+00')
            actions.start.assert_not_called()


if __name__=='__main__':unittest.main()
