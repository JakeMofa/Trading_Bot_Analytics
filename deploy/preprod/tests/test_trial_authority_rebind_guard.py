"""Pending public metadata blocks admission; recovery stays permit-free."""
import hashlib,json,sys,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import transition_control as gate
from controller import DeploymentHold
class RebindGuardTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.marker=Path(self.tmp.name)/'pending.json'
  p=patch.object(gate,'TRIAL_AUTHORITY_REBIND_PENDING',self.marker);p.start();self.addCleanup(p.stop)
 def test_absence_is_default_and_marker_bytes_never_read(self):
  gate.require_no_trial_authority_rebind()
  for raw in (b'',b'{partial',b'{}',b'REQUIRED_REVIEW'):
   self.marker.write_bytes(raw)
   with patch.object(Path,'read_bytes',side_effect=AssertionError('never read marker')):
    with self.assertRaisesRegex(DeploymentHold,'^trial_authority_rebind_pending$'):gate.require_no_trial_authority_rebind()
   self.marker.unlink()
 def test_symlink_broken_symlink_directory_and_unreadable_marker_hold(self):
  target=Path(self.tmp.name)/'target';target.write_text('public metadata')
  for destination in (target,Path(self.tmp.name)/'missing'):
   self.marker.symlink_to(destination)
   with self.assertRaisesRegex(DeploymentHold,'trial_authority_rebind_pending'):gate.require_no_trial_authority_rebind()
   self.marker.unlink()
  self.marker.mkdir()
  with self.assertRaises(DeploymentHold):gate.require_no_trial_authority_rebind()
  self.marker.rmdir();self.marker.write_text('public');self.marker.chmod(0)
  with self.assertRaises(DeploymentHold):gate.require_no_trial_authority_rebind()
 def test_metadata_error_fails_closed_without_error_details(self):
  with patch.object(Path,'lstat',side_effect=PermissionError('SECRET filesystem details')):
   with self.assertRaisesRegex(DeploymentHold,'^trial_authority_rebind_pending$'):gate.require_no_trial_authority_rebind()
 def test_enter_and_on_hold_before_authority_journal_or_runtime(self):
  self.marker.write_bytes(b'{interrupted transaction')
  request=gate.TransitionRequest('enter','a'*40,'b'*64,'c'*64,'sha256:'+'d'*64)
  with patch.object(gate.HostBinding,'from_marker',return_value=SimpleNamespace(validate=lambda:None)),patch.object(gate,'_secure_file') as secure,patch.object(gate,'_candidate') as candidate,patch.object(gate,'_consume') as consume,patch.object(gate,'_read_active') as read,patch.object(gate,'_atomic_json') as write:
   with self.assertRaisesRegex(DeploymentHold,'trial_authority_rebind_pending'):gate.transition(request,Path('/trusted/controller.pyz'))
   with self.assertRaisesRegex(DeploymentHold,'trial_authority_rebind_pending'):gate.session('session-v1 on 60',Path('/trusted/controller.pyz'))
   for mocked in (secure,candidate,consume,read,write):mocked.assert_not_called()
 def test_off_and_idempotent_leave_work_while_marker_exists(self):
  self.marker.write_bytes(b'{both authorities already replaced but not committed')
  digest=hashlib.sha256(b'controller').hexdigest()
  request=gate.TransitionRequest('leave','a'*40,'b'*64,digest,'sha256:'+'c'*64)
  active={**request.bindings(), 'state':'ready_off','nonce':str(uuid.uuid4()),'version':1}
  context=SimpleNamespace(source=Path('/reviewed/source'),image=request.image_id)
  actions=SimpleNamespace(_runtime=lambda *a:None,_host_api=lambda:None,_host_operator=lambda:None)
  with patch.object(gate.HostBinding,'from_marker',return_value=SimpleNamespace(validate=lambda:None)),patch.object(gate,'_secure_file',return_value=(b'controller',None)),patch.object(gate,'_candidate',return_value=context),patch.object(gate,'_image_binding',return_value=actions),patch.object(gate,'_owned_runtime'),patch.object(gate,'_read_active',side_effect=lambda:dict(active)),patch.object(gate,'RUNTIME_SECRETS',Path(self.tmp.name)/'no-secrets'),patch.object(gate,'_prove_off') as off,patch.object(gate,'_consume') as consume:
   self.assertEqual(gate.session('session-v1 off',Path('/trusted/controller.pyz'))['gate'],'PP_LIVE_OFF');off.assert_called_once()
   active['state']='generated_restored'
   self.assertEqual(gate.transition(request,Path('/trusted/controller.pyz'))['gate'],'PP_GENERATED_RESTORED')
   consume.assert_not_called()
