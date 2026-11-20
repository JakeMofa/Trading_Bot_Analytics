"""Generated-only CI partition and bounded sanitized timeout evidence."""
from collections import Counter
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('qualification_partitions',HERE/'qualify_postgres.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)


def case(module,name):
    cls=type(name,(unittest.TestCase,),{'__module__':module,'runTest':lambda self:None})
    return cls()


def ids(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from ids(item)
        else:yield item.id()


class PartitionTests(unittest.TestCase):
    def test_only_exact_recovery_module_moves_with_no_lost_or_duplicated_tests(self):
        before=unittest.TestSuite([case('test_postgres_application','App'),unittest.TestSuite([
            case(q.FAILED_RECOVERY_MODULE,'RecoveryA'),case(q.FAILED_RECOVERY_MODULE,'RecoveryB'),
            case(q.FAILED_RECOVERY_MODULE+'_extra','Neighbor')])])
        expected=Counter(ids(before))
        parts=q.partition_application_tests(before)
        self.assertEqual(parts['application_lifecycle'].countTestCases(),2)
        self.assertEqual(parts['failed_trial_recovery'].countTestCases(),2)
        combined=Counter(ids(parts['application_lifecycle']))+Counter(ids(parts['failed_trial_recovery']))
        self.assertEqual(combined,expected)
        self.assertTrue(all(name.startswith(q.FAILED_RECOVERY_MODULE+'.') for name in ids(parts['failed_trial_recovery'])))

    def test_empty_missing_or_malformed_phases_are_not_silently_qualified(self):
        for suite in (unittest.TestSuite(),unittest.TestSuite([case('test_postgres_application','App')]),
                      unittest.TestSuite([case(q.FAILED_RECOVERY_MODULE,'Recovery')])):
            with self.assertRaises(RuntimeError):q.partition_application_tests(suite)
        with self.assertRaises(RuntimeError):q.partition_application_tests([object()])

    def test_recovery_import_failure_is_routed_and_reported_without_disappearing(self):
        missing='test_postgres_missing_recovery_fixture_8b4fb'
        loader=unittest.TestLoader();failed=loader.loadTestsFromName(missing)
        self.assertEqual(len(loader.errors),1)
        suite=unittest.TestSuite([case('test_postgres_application','App'),failed])
        with patch.object(q,'FAILED_RECOVERY_MODULE',missing):
            parts=q.partition_application_tests(suite)
        self.assertEqual(parts['failed_trial_recovery'].countTestCases(),1)
        result=unittest.TestResult();parts['failed_trial_recovery'].run(result)
        self.assertEqual(len(result.errors),1)
        self.assertIn(missing,result.errors[0][1])

    def test_phase_bounds_and_child_code_keep_skip_rejection_and_global_deadline(self):
        self.assertEqual(q.APPLICATION_TEST_PHASES,(('application_lifecycle',180),('failed_trial_recovery',90)))
        for phase,_ in q.APPLICATION_TEST_PHASES:
            code=q.application_test_code(phase)
            compile(code,'<child>','exec')
            self.assertIn('test_postgres*.py',code)
            self.assertIn('partition_application_tests',code)
            self.assertIn('not r.skipped and r.testsRun',code)
        with self.assertRaises(ValueError):q.application_test_code('unreviewed')


class TimeoutEvidenceTests(unittest.TestCase):
    def exercise(self,kill):
        child=Mock(pid=12345,returncode=None)
        output='x'*60000+'\nregistered-password postgresql://user:unregistered-password@host/db\n'
        output+='test_actual_20362_ack_total (test_postgres_failed_trial_drain.Native) ... '
        count=[0]
        def communicate(*,timeout=None):
            count[0]+=1
            if count[0]==1 or (kill and count[0]==2):raise subprocess.TimeoutExpired('qualification-child',timeout)
            child.returncode=-9 if kill else -15
            return '',output
        child.communicate.side_effect=communicate
        stream=io.StringIO()
        with patch.object(q,'DEADLINE',115),patch.object(q,'PHASE','failed_trial_recovery'), \
             patch.object(q,'REDACTIONS',['registered-password']),patch.object(q.time,'monotonic',return_value=100), \
             patch.object(q.subprocess,'Popen',return_value=child) as opened,patch.object(q.os,'killpg') as killed, \
             contextlib.redirect_stderr(stream):
            with self.assertRaisesRegex(RuntimeError,'terminated and reaped'):
                q.command(['python','-c','generated-fixture'],timeout=180)
        text=stream.getvalue()
        self.assertNotIn('registered-password',text)
        self.assertNotIn('unregistered-password',text)
        self.assertNotIn('postgresql://',text)
        self.assertIn('[REDACTED_DSN]',text)
        self.assertIn('test_actual_20362_ack_total',text)
        self.assertLess(len(text),51000)
        record=json.loads(text.splitlines()[-1])
        self.assertEqual(record,dict(phase='failed_trial_recovery',reason='child_deadline',budget_seconds=15,
            elapsed_seconds=0,term_requested=True,kill_requested=kill,reaped=True))
        self.assertEqual(child.communicate.call_args_list[0].kwargs,{'timeout':15})
        self.assertTrue(opened.call_args.kwargs['start_new_session'])
        self.assertEqual(killed.call_args_list[0].args,(12345,signal.SIGTERM))
        if kill:self.assertEqual(killed.call_args_list[1].args,(12345,signal.SIGKILL))

    def test_term_timeout_preserves_sanitized_partial_test_name_and_reap_status(self):self.exercise(False)
    def test_kill_fallback_also_preserves_sanitized_partial_output(self):self.exercise(True)


if __name__=='__main__':unittest.main()
