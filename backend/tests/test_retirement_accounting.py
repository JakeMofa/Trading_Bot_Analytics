"""Diagnostics cannot change authority, exception identity, or budget limits."""
import json
import io
import os
import unittest
from unittest.mock import patch
from contextlib import contextmanager, redirect_stdout

from postgres.archive_codec import ArchiveLimit, CycleBudget
from postgres.pp_retirement_verify import TwoMarketReadbackLimits
from postgres.retirement_accounting import accounted, bind_budget, measured_context, phase


class AccountingTests(unittest.TestCase):
    def test_retirement_reuse_requires_separate_exact_opt_in(self):
        from postgres.pp_retirement_verify import retirement_history_factory
        from postgres.pp_history_connection import PPHistoryConnectionFactory
        from postgres.pp_history_session import ReusablePPHistoryConnectionFactory
        from postgres.lifecycle import LifecycleHold
        for env in ({}, {'TRADEBOT_PP_REUSE_HISTORY_SESSION':'true'},
                    {'TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION':'false'}):
            self.assertIs(type(retirement_history_factory(env)),PPHistoryConnectionFactory)
        factory=retirement_history_factory({'TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION':'true'})
        self.assertIs(type(factory),ReusablePPHistoryConnectionFactory)
        factory.close()
        for value in ('TRUE','1','',True):
            with self.assertRaises(LifecycleHold):
                retirement_history_factory({'TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION':value})

    def test_trial06_permitted_retirement_requires_reuse_before_files_or_connections(self):
        from postgres import pp_retirement_verify
        from postgres.rehearsal_profile import CYCLE_POLICY, FIFTH_TRIAL_ORIGIN, SIXTH_TRIAL_ORIGIN

        sealed='00000000-0000-4000-8000-000000000001'
        argv=['verify','--sealed',sealed,'--collecting','00000000-0000-4000-8000-000000000002',
              '--seal-hash','a'*64,'--count','1','--two-market-window']
        environment=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
                         TRADEBOT_ORIGIN_ID=SIXTH_TRIAL_ORIGIN,TRADEBOT_PP_WINDOW_POLICY=CYCLE_POLICY,
                         TRADEBOT_PP_CYCLE_INITIAL_A=sealed)
        for origin,operation,opt_in,allowed in (
                (SIXTH_TRIAL_ORIGIN,'--retire-with-pp-permit','false',False),
                (SIXTH_TRIAL_ORIGIN,'--retire-with-pp-permit','TRUE',False),
                (SIXTH_TRIAL_ORIGIN,'--retire-with-pp-permit','true',True),
                (SIXTH_TRIAL_ORIGIN,'--inventory-only','false',True),
                (FIFTH_TRIAL_ORIGIN,'--retire-with-pp-permit','false',True)):
            env=environment|dict(TRADEBOT_ORIGIN_ID=origin,TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION=opt_in)
            with self.subTest(origin=origin,operation=operation,opt_in=opt_in), \
                    patch.dict(os.environ,env,clear=True), \
                    patch('sys.argv',argv+[operation]), \
                    patch.object(pp_retirement_verify,'require_trial_files',side_effect=AssertionError) as files, \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(pp_retirement_verify.main(),1)
                self.assertEqual(files.called,allowed)
                self.assertEqual(json.loads(output.getvalue())['reason'],'AssertionError' if allowed else 'lifecycle_hold')

    def test_connection_sqlstate_survives_sanitizing_factory(self):
        from postgres.pp_history_connection import PPHistoryConnectionFactory
        from postgres.archive_codec import ArchiveUnavailable
        import time
        class Failure(Exception):
            sqlstate='53300'
        @accounted
        def operation():
            with patch('psycopg.connect',side_effect=Failure('secret DSN server error')):
                PPHistoryConnectionFactory._open(b'password=secret',time.monotonic()+4)
        with self.assertRaises(ArchiveUnavailable) as caught:
            operation()
        report=caught.exception.retirement_accounting
        self.assertEqual((report['failed_phase'],report['sqlstate']),('history_connect','53300'))
        self.assertNotIn('secret',json.dumps(report))

    def test_nested_logical_charges_and_fixed_budget_failure_are_sanitized(self):
        secret = 'password=never-log-this payload-or-ticket'
        @accounted
        def operation():
            with CycleBudget(TwoMarketReadbackLimits(), clock=lambda:10) as budget:
                bind_budget(budget)
                with phase('structured_readback'):
                    with phase('history_exact_revisions'):
                        budget.request(123)
                        budget.account(7)
                    budget.deadline = 10
                    budget.check()
        with self.assertRaises(ArchiveLimit) as caught:
            operation()
        report=caught.exception.retirement_accounting
        self.assertEqual(report['failed_phase'],'structured_readback')
        self.assertEqual(report['exhausted_limit'],'seconds')
        self.assertEqual((report['requests'],report['logical_bytes']),(1,130))
        self.assertEqual(report['phases']['history_exact_revisions']['logical_bytes'],130)
        self.assertNotIn(secret,json.dumps(report))
        self.assertNotIn('cycle deadline reached',json.dumps(report))

    def test_sqlstate_and_failed_finish_are_observed_without_error_text(self):
        class DatabaseFailure(Exception):
            sqlstate='53300'
        failure=DatabaseFailure('sensitive server message')
        @contextmanager
        def transaction():
            yield 'db'
            raise failure
        @accounted
        def operation():
            with measured_context(transaction(),enter='local_open',finish='local_finish'):
                pass
        with self.assertRaises(DatabaseFailure) as caught:
            operation()
        self.assertIs(caught.exception,failure)
        report=failure.retirement_accounting
        self.assertEqual((report['failed_phase'],report['sqlstate']),('local_finish','53300'))
        self.assertNotIn('sensitive',json.dumps(report))

    def test_diagnostic_failure_does_not_replace_operation_exception_or_success(self):
        failure=RuntimeError('operation failure')
        @accounted
        def operation(fail):
            with patch('postgres.retirement_accounting.time.monotonic',side_effect=ValueError):
                # An invalid phase is a diagnostic bug, never authority.
                with phase('invalid-sensitive-input'):
                    if fail: raise failure
            return {'status':'diagnostic_only'}
        with self.assertRaises(RuntimeError) as caught:
            operation(True)
        self.assertIs(caught.exception,failure)
        self.assertTrue(operation(False)['phase_accounting']['diagnostics_unavailable'])
        self.assertEqual(operation(False)['phase_accounting']['phases'],{})
        self.assertIsNone(caught.exception.retirement_accounting['failed_phase'])

    def test_context_preserves_suppression_and_rollback(self):
        events=[]
        @contextmanager
        def transaction():
            try: yield None
            except ValueError: events.append('rollback')
        @accounted
        def operation():
            with measured_context(transaction(),enter='local_open',finish='local_finish'):
                raise ValueError('abort')
            return {'status':'readback_only'}
        result=operation()
        self.assertEqual(events,['rollback'])
        self.assertFalse(result['phase_accounting']['diagnostics_unavailable'])
