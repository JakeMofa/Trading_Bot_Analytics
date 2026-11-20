"""Run exact second-trial qualification in Linux CI's owned restricted-role DB.

The postgres-integration qualifier discovers test_postgres*.py and rejects any
skip. Its generated DSNs are required; never use a default/local user database.
"""
import os
from pathlib import Path
import shutil
import unittest
import test_pp_second_trial as qualification


class SecondTrialDSNTests(qualification.SecondTrialNative):
    @classmethod
    def setUpClass(cls):
        names=('LIFECYCLE','APP','MIGRATOR')
        if not all(os.environ.get('TRADEBOT_TEST_'+name+'_DSN') for name in names):
            raise unittest.SkipTest('requires owned generated PostgreSQL role DSNs')
        if (os.environ.get('TRADEBOT_DATA_MODE'),os.environ.get('TRADEBOT_ORIGIN_ID')) != ('generated','generated-pp'):
            raise unittest.SkipTest('requires dedicated generated CI harness')
        cls.lifecycle_dsn=os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']
        cls.app_dsn=os.environ['TRADEBOT_TEST_APP_DSN']
        cls.migrator_dsn=os.environ['TRADEBOT_TEST_MIGRATOR_DSN']
        psql=shutil.which('psql')
        if not psql:raise RuntimeError('psql required for real exact retirement issuer qualification')
        cls.bin=Path(psql).parent

    @classmethod
    def admin(cls,database='tradebot_pp'):
        if database!='tradebot_pp':raise ValueError('exact disposable PP database required')
        from postgres.connection import connect_migrator
        return connect_migrator(cls.migrator_dsn,environment='preprod')

    @classmethod
    def tearDownClass(cls):
        # The outer qualifier owns disposal; each test removes only its fixture.
        pass
