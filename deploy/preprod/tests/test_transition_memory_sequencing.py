"""Transition admission and recovery faults; no host or cloud operations."""
import json,sys,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1])]
from controller import DeploymentHold
from linux_actions import LinuxActions
from live_transition import LiveTransition
import transition_control as gate
from test_live_transition import Actions,Budget

class MemorySequencingTests(unittest.TestCase):
 def component(self):
  actions=Actions();context=SimpleNamespace(source=Path('/reviewed/source'),image='sha256:'+'a'*64)
  live=LiveTransition(actions,context,Budget(actions))
  live._profile=lambda **_:actions.calls.append('profile')
  return actions,context,live
 def test_ordinary_deploy_still_checks_full_one_gib_and_disk(self):
  with patch.object(LinuxActions,'_host_identity'),patch('linux_actions.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3)),patch('linux_actions.Path.read_text',return_value='MemAvailable: 1048575 kB'):
   with self.assertRaisesRegex(DeploymentHold,'insufficient_host_headroom'):LinuxActions._host()
   LinuxActions._transition_host()
  with patch.object(LinuxActions,'_host_identity'),patch('linux_actions.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3-1)):
   with self.assertRaisesRegex(DeploymentHold,'insufficient_host_headroom'):LinuxActions._transition_host()
  with patch.object(LinuxActions,'_host_identity'),patch('linux_actions.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3)),patch('linux_actions.Path.read_text',return_value='MemAvailable: 1048576 kB'):
   LinuxActions._host()
 def test_low_memory_is_recoverable_only_after_owned_services_stop(self):
  actions,_,live=self.component()
  def headroom():
   actions.calls.append('headroom')
   if actions.running:raise DeploymentHold('insufficient_host_headroom')
  actions._host_headroom=headroom
  self.assertEqual(live.enter()['gate'],'PP_LIVE_READY_OFF')
  stop=next(i for i,v in enumerate(actions.calls) if isinstance(v,tuple) and v[0]=='base' and v[1][0]=='stop')
  self.assertLess(actions.calls.index('writers_off'),stop);self.assertLess(stop,actions.calls.index('headroom'))
 def test_malformed_ownership_and_duplicate_service_never_quiesce(self):
  for bad in ('foreign','duplicate'):
   actions,_,live=self.component();original=actions._inspect
   def inspect(budget,ids):
    rows=original(budget,ids)
    if bad=='foreign':rows[0]['Image']='sha256:'+'f'*64
    else:rows[1]['Config']['Labels']['com.docker.compose.service']='api'
    return rows
   actions._inspect=inspect
   with self.assertRaisesRegex(DeploymentHold,'foreign_runtime_blocks_transition'):live.enter()
   self.assertFalse(any(isinstance(v,tuple) and v[0]=='base' and v[1][0]=='stop' for v in actions.calls))
 def test_nonoff_session_or_lease_never_quiesces(self):
  actions,_,live=self.component();actions._reader_sql=lambda *_:'1'
  with self.assertRaisesRegex(DeploymentHold,'pp_live_durable_off_unproven'):live.enter()
  self.assertFalse(any(isinstance(v,tuple) and v[0]=='base' and v[1][0]=='stop' for v in actions.calls))
 def test_remaining_low_memory_holds_with_off_and_stopped_apps(self):
  actions,_,live=self.component()
  actions._host_headroom=lambda:(_ for _ in ()).throw(DeploymentHold('insufficient_host_headroom'))
  with self.assertRaisesRegex(DeploymentHold,'insufficient_host_headroom'):live.leave()
  self.assertFalse(actions.running);self.assertEqual(live.phase,'generated_headroom')
  self.assertIn('writers_off',actions.calls)
  self.assertFalse(any(isinstance(v,tuple) and 'up' in v[1] for v in actions.calls))
 def test_partial_stop_or_identity_replacement_does_not_start(self):
  actions,_,live=self.component();original=actions._compose
  def stop(*args,**kwargs):
   value=original(*args,**kwargs)
   if args[2][0]=='stop':raise DeploymentHold('child_deadline_exceeded')
   return value
  actions._compose=stop
  with self.assertRaisesRegex(DeploymentHold,'child_deadline_exceeded'):live.enter()
  self.assertFalse(actions.running)
  self.assertFalse(any(isinstance(v,tuple) and 'up' in v[1] for v in actions.calls))
 def run_outer(self,code,always=False,preflight=False,partial_stop=False):
  actions,context,_=self.component();request=gate.TransitionRequest('enter','a'*40,'b'*64,__import__('hashlib').sha256(b'controller').hexdigest(),context.image)
  context.request=SimpleNamespace(source_sha=request.source_sha);active={};budgets=[];headroom_calls=[]
  def headroom():
   headroom_calls.append(actions.running)
   if len(headroom_calls)==1 or always:raise DeploymentHold(code)
  actions._host_headroom=headroom
  if preflight:actions._host_api=lambda:(_ for _ in ()).throw(DeploymentHold('host_api_wrong_state'))
  if partial_stop:
   headroom_calls.append(False)  # Do not fail the subsequent recovery headroom.
   original_compose=actions._compose;stops=[]
   def compose(*args,**kwargs):
    value=original_compose(*args,**kwargs)
    if args[2][0]=='stop':
     stops.append(True)
     if len(stops)==1:raise DeploymentHold('child_deadline_exceeded')
    return value
   actions._compose=compose
  def budget(seconds):budgets.append(seconds);return Budget(actions)
  def write(_path,value,**_):active.clear();active.update(value)
  with patch.object(gate.HostBinding,'from_marker',return_value=SimpleNamespace(validate=lambda:None)),patch.object(gate,'_secure_file',return_value=(b'controller',None)),patch.object(gate,'_candidate',return_value=context),patch.object(gate,'_image_binding',return_value=actions),patch.object(gate,'_consume',return_value=str(uuid.uuid4())) as consume,patch.object(gate,'_atomic_json',side_effect=write),patch.object(gate,'ACTIVE',Path('/nonexistent-transition-memory-test')),patch.object(gate,'Budget',side_effect=budget),patch('live_transition.validate_live_profile'):
   result=gate.transition(request,Path('/trusted/controller.pyz'))
  return result,active,actions,budgets,headroom_calls,consume
 def test_interrupt_uses_exactly_one_fresh_180_second_recovery(self):
  result,active,actions,budgets,headroom,consume=self.run_outer('operator_connection_interrupted')
  self.assertEqual(budgets,[600,180]);consume.assert_called_once();self.assertEqual(headroom,[False,False])
  self.assertEqual(result['reason'],'pp_live_entry_failed_generated_restored');self.assertEqual(active['state'],'generated_restored')
  self.assertEqual(result['entry_failure'],dict(phase='live_headroom',reason='operator_connection_interrupted'))
  starts=[v for v in actions.calls if isinstance(v,tuple) and v[0]=='base' and 'up' in v[1]]
  self.assertEqual(len(starts),1)
 def test_initial_fixed_code_survives_and_sql_details_never_escape(self):
  result,active,*_=self.run_outer('insufficient_host_headroom')
  self.assertEqual(active['entry_failure']['reason'],'insufficient_host_headroom')
  result,active,*_=self.run_outer('postgresql://user:SECRET@example SQL DETAILS')
  self.assertEqual(result['entry_failure']['reason'],'transition_action_failed');self.assertNotIn('SECRET',json.dumps([result,active]))

 def test_recovery_still_low_holds_off_without_false_restored_journal(self):
  result,active,actions,budgets,_,consume=self.run_outer('insufficient_host_headroom',always=True)
  self.assertEqual(budgets,[600,180]);consume.assert_called_once();self.assertFalse(actions.running)
  self.assertEqual(result['reason'],'pp_live_entry_recovery_unproven');self.assertEqual(active['state'],'recovery_unproven')
  self.assertEqual(active['entry_failure'],dict(phase='live_headroom',reason='insufficient_host_headroom'))
  self.assertEqual(active['recovery_failure'],dict(phase='generated_headroom',reason='insufficient_host_headroom'))
  self.assertFalse(any(isinstance(v,tuple) and 'up' in v[1] for v in actions.calls))
 def test_prepare_and_live_start_each_need_full_quiescent_headroom(self):
  actions,context,_=self.component()
  live=LiveTransition(actions,context,Budget(actions),initial_a=str(uuid.uuid4()),trial_origin='pp-live-pp-trial-20261119-06')
  live._profile=lambda **_:None;events=[]
  live._prepare_trial=lambda:events.append('prepare')
  live._check_live_off=lambda:events.append('ready_off')
  def headroom():
   self.assertFalse(actions.running);events.append('headroom')
   if len(events)>1:raise DeploymentHold('insufficient_host_headroom')
  actions._host_headroom=headroom
  with self.assertRaisesRegex(DeploymentHold,'insufficient_host_headroom'):live.enter()
  self.assertEqual(events,['headroom','prepare','headroom'])
  self.assertFalse(any(isinstance(v,tuple) and v[0]=='live' and 'up' in v[1] for v in actions.calls))

 def test_recovery_reaps_registered_prepare_before_owned_services(self):
  actions,_,live=self.component();pending=[True];original=actions._inspect
  def inspect(budget,ids):
   rows=original(budget,ids)
   if pending[0]:rows[0]['Config']['Labels']['com.docker.compose.oneoff']='True'
   return rows
  actions._inspect=inspect
  def cleanup(*_):actions.calls.append('cleanup_registered_prepare');pending[0]=False
  actions._cleanup_oneoffs=cleanup
  self.assertEqual(live.leave()['gate'],'PP_GENERATED_RESTORED')
  off=next(i for i,v in enumerate(actions.calls) if isinstance(v,tuple) and '--stop-collector' in v[1])
  self.assertLess(actions.calls.index('cleanup_registered_prepare'),off)

 def test_preflight_failure_never_recovers_or_quiesces(self):
  result,active,actions,budgets,headroom,consume=self.run_outer('unused',preflight=True)
  self.assertEqual(budgets,[600]);consume.assert_called_once();self.assertTrue(actions.running)
  self.assertEqual(result['reason'],'pp_live_entry_preflight_failed');self.assertFalse(result['recovery_attempted'])
  self.assertEqual(result['recovery'],'not_performed');self.assertEqual(active['state'],'recovery_unproven')
  self.assertEqual(active['entry_failure'],dict(phase='generated_preflight',reason='host_api_wrong_state'))
  self.assertNotIn('cleanup_oneoffs',actions.calls);self.assertEqual(headroom,[])
  self.assertFalse(any(isinstance(v,tuple) and ('stop' in v[1] or 'up' in v[1] or '--stop-collector' in v[1]) for v in actions.calls))
 def test_partial_stop_attempt_gets_one_full_recovery(self):
  result,active,actions,budgets,_,_=self.run_outer('unused',partial_stop=True)
  self.assertEqual(budgets,[600,180]);self.assertTrue(result['recovery_attempted']);self.assertEqual(active['state'],'generated_restored')
  self.assertEqual(active['entry_failure'],dict(phase='quiesce',reason='child_deadline_exceeded'))
  self.assertEqual(len([v for v in actions.calls if isinstance(v,tuple) and v[0]=='base' and 'up' in v[1]]),1)
