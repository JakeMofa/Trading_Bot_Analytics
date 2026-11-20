"""Actual CLI HOLD protocol, sanitized diagnostics, no connections or credentials."""
import contextlib,io,json,math,sys,unittest
from unittest.mock import patch
from postgres.archive_codec import ArchiveLimit
from postgres import pp_retirement_verify as verify
class RetirementFailureDiagnostics(unittest.TestCase):
 def accounting(self):
  return dict(elapsed_seconds=239.9,remaining_seconds=0,requests=97,logical_bytes=123456,failed_phase='history_projections',sqlstate='57014',exhausted_limit='seconds',diagnostics_unavailable=False,nested_phase_totals_overlap=True,phases=dict(history_projections=dict(calls=2,seconds=44.5,max_seconds=30.1,requests=2,logical_bytes=1234)))
 def test_actual_cli_hold_includes_stage_and_preserves_numeric_accounting(self):
  error=ArchiveLimit('private SQL/password must not appear');error.retirement_accounting=self.accounting()
  args=['pp_retirement_verify','--sealed','11111111-1111-4111-8111-111111111111','--collecting','22222222-2222-4222-8222-222222222222','--seal-hash','a'*64,'--count','1','--retire-with-pp-permit']
  with patch.object(sys,'argv',args),patch.object(verify.Target,'validate',side_effect=error),contextlib.redirect_stdout(io.StringIO()) as output:
   self.assertEqual(verify.main(),1)
  value=json.loads(output.getvalue());self.assertEqual((value['stage'],value['reason']),('pp_retirement_verify','archive_limit'))
  self.assertEqual(value['phase_accounting'],self.accounting());self.assertIsNone(value['retirement_authorized']);self.assertEqual(value['partition_outcome'],'inspect_generation_and_ticket');self.assertNotIn('private',output.getvalue())
 def test_untrusted_exception_code_message_and_diagnostic_fields_do_not_escape(self):
  secret='postgresql://user:SECRET@host raw SQL'
  error=ValueError(secret);error.code=secret;accounting=self.accounting();accounting.update(sqlstate=secret,failed_phase=secret,exhausted_limit=secret,raw=secret)
  accounting['phases']['history_projections']['SQL']=secret;accounting['phases'][secret]={'seconds':1}
  error.retirement_accounting=accounting
  value=verify.retirement_failure(error);self.assertEqual(value['reason'],'ValueError');self.assertNotIn(secret,json.dumps(value))
  self.assertIsNone(value['phase_accounting']['sqlstate']);self.assertEqual(set(value['phase_accounting']['phases']),{'history_projections'})
 def test_invalid_numeric_and_boolean_shapes_are_unavailable_not_printed(self):
  value=self.accounting();value.update(elapsed_seconds=math.nan,remaining_seconds=math.inf,requests=True,logical_bytes=-1,diagnostics_unavailable='false')
  value['phases']['history_projections'].update(calls=1.5,seconds=math.nan,logical_bytes='SECRET')
  safe=verify.sanitize_phase_accounting(value);json.dumps(safe,allow_nan=False)
  self.assertTrue(safe['diagnostics_unavailable'])
  for key in ('elapsed_seconds','remaining_seconds','requests','logical_bytes'):self.assertIsNone(safe[key])
  self.assertIsNone(safe['phases']['history_projections']['calls'])
 def test_public_archive_code_is_not_replaceable_by_instance_message(self):
  error=ArchiveLimit('SECRET');error.code='secret_instance_code'
  self.assertEqual(verify.retirement_failure(error)['reason'],'archive_limit')
  self.assertFalse(verify.retirement_failure(error)['retirement_authorized'])
  self.assertIsNone(verify.retirement_failure(error,retirement_requested=True)['retirement_authorized'])

 def test_returned_inventory_hold_has_stage_without_changing_late_outcomes(self):
  result=verify.public_retirement_result(dict(status='HOLD',retirement_authorized=False,inventory=dict(fit='exceeds_limits'),phase_accounting=self.accounting()))
  self.assertEqual((result['stage'],result['reason']),('pp_retirement_verify','inventory_exceeds_limits'));self.assertFalse(result['retirement_authorized'])
  late=dict(status='retired_pp_after_operation_deadline',retirement_authorized=True,operation_deadline_met=False)
  self.assertIs(verify.public_retirement_result(late,retirement_requested=True),late)

 def test_indexed_retirement_lookup_is_exact_trial_only(self):
  from postgres.cloud_origin_binding import THIRD_TRIAL_ORIGIN
  from postgres.lifecycle import LifecycleHold
  flag='TRADEBOT_PP_RETIREMENT_INDEXED_LATEST_RECEIPTS'
  self.assertFalse(verify.retirement_indexed_latest({},THIRD_TRIAL_ORIGIN))
  self.assertTrue(verify.retirement_indexed_latest({flag:'true'},THIRD_TRIAL_ORIGIN))
  with self.assertRaises(LifecycleHold):
   verify.retirement_indexed_latest({flag:'true'},verify.ORIGIN)
  with self.assertRaises(LifecycleHold):
   verify.retirement_indexed_latest({flag:'TRUE'},THIRD_TRIAL_ORIGIN)
