"""Generated PG17 failed-trial recovery qualification; no host/cloud access."""
from dataclasses import replace
import os
import shutil
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres import pp_failed_trial_drain as helper
import test_pp_initial_trial_drain as fixtures
from postgres.lifecycle import LifecycleHold
from postgres.archive_codec import ArchiveIntegrityError,ArchiveUnavailable,encoded
from postgres.cloud_origin_binding import NEXT_TRIAL_READER,cloud_binding

class Controls(unittest.TestCase):
    def test_exact_failed_scope_accepts_reviewed_ack_total_without_changing_worker_limits(self):
        target=helper.SealTarget(helper.FAILED_INITIAL_A,helper.FAILED_INITIAL_A,3,18930,20362,
                                'a'*40,str(uuid.uuid4()),'b'*40)
        target.validate()
        for change in ({'initial_a':str(uuid.uuid4())},{'generation':str(uuid.uuid4())},
                       {'outbox_count':64001},{'trial_source':'main'},{'writer_epoch':True}):
            with self.subTest(change=change),self.assertRaises((ValueError,LifecycleHold)):
                replace(target,**change).validate()
        from postgres.pp_sealed_archive import LIMITS
        from postgres.pp_retirement_verify import TwoMarketReadbackLimits
        self.assertEqual(LIMITS.max_rows,500)
        self.assertEqual((TwoMarketReadbackLimits().max_requests,TwoMarketReadbackLimits().max_seconds),(192,240))
        with patch('postgres.pp_failed_trial_drain.private_dsn') as secret:
            self.assertEqual(helper.main(['--generation',target.generation,'--initial-a',target.initial_a,
                '--writer-epoch','3','--raw-count','18930','--outbox-count','20362','--trial-source','a'*40,
                '--operation',target.operation,'--source','b'*40]),1)
            secret.assert_not_called()

class Native(unittest.TestCase):
    setUpClass=classmethod(fixtures.InitialSealNative.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.InitialSealNative.tearDownClass.__func__)
    admin=classmethod(fixtures.InitialSealNative.admin.__func__)
    fixture_on=fixtures.InitialSealNative.fixture_on
    cleanup=fixtures.InitialSealNative.cleanup
    evidence=fixtures.InitialSealNative.evidence

    @classmethod
    def setUpClass(cls):
        cls.external=all(os.environ.get('TRADEBOT_TEST_'+role+'_DSN')
                         for role in ('LIFECYCLE','APP','MIGRATOR','READER'))
        if cls.external:
            if (os.environ.get('TRADEBOT_DATA_MODE'),os.environ.get('TRADEBOT_ORIGIN_ID'))!=('generated','generated-pp'):
                raise RuntimeError('recovery tests require owned generated scope')
            cls.lifecycle_dsn=os.environ['TRADEBOT_TEST_LIFECYCLE_DSN']
            cls.app_dsn=os.environ['TRADEBOT_TEST_APP_DSN']
            cls.migrator_dsn=os.environ['TRADEBOT_TEST_MIGRATOR_DSN']
            cls.reader_dsn=os.environ['TRADEBOT_TEST_READER_DSN']
        else:
            fixtures.InitialSealNative.setUpClass.__func__(cls)
            cls.reader_dsn=f'host={cls.socket} user=tradebot_reader dbname=tradebot_pp'

    @classmethod
    def admin(cls,database='tradebot_pp'):
        if cls.external:
            if database!='tradebot_pp':raise ValueError('exact owned PP test database required')
            from postgres.connection import connect_migrator
            return connect_migrator(cls.migrator_dsn,environment='preprod')
        return fixtures.InitialSealNative.admin.__func__(cls,database)

    @classmethod
    def tearDownClass(cls):
        if not cls.external:fixtures.InitialSealNative.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.InitialSealNative.setUp(self)
        from postgres.pp_initial_trial_drain import seal_initial_a
        from postgres.pp_trial_prepare import prepare
        from postgres.pp_sealed_archive import cycle
        from postgres.config import Settings
        from postgres.store import Store
        from postgres.active_structured import ActiveStructuredWorker
        seal_initial_a(self.repo,self.target,execute=True);cycle(self.repo,self.raw,origin=fixtures.TRIAL_ORIGIN)
        self.origins.append(helper.ORIGIN);self.children.append(helper.FAILED_INITIAL_A)
        prepare(self.repo,helper.FAILED_INITIAL_A,'a'*40,execute=True,origin_id=helper.ORIGIN)
        self.failed_store=Store(Settings(environment='preprod',data_mode='pp_live',origin_id=helper.ORIGIN,dsn=self.app_dsn))
        with self.admin() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '1 minute' WHERE origin_id=%s",
                       (str(uuid.uuid4()),helper.ORIGIN))
        self.failed_store.ingest(self.event(81));self.repo.disable_collector(helper.ORIGIN)
        ActiveStructuredWorker(self.repo,self.raw,origin_id=helper.ORIGIN).cycle(helper.FAILED_INITIAL_A)
        self.target=helper.SealTarget(helper.FAILED_INITIAL_A,helper.FAILED_INITIAL_A,
            self.repo.collector_state(helper.ORIGIN)['epoch'],1,1,'a'*40,str(uuid.uuid4()),'b'*40)

    def test_seal_archive_exact_retry_and_independent_reader_preserve_old_and_failed_sources(self):
        from postgres.pp_sealed_archive import cycle
        from postgres.pp_retirement_verify import RetirementTransport
        from postgres.connection import connect
        before=self.evidence()
        result=helper.seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertFalse(result['retirement_authorized']);self.assertFalse(result['original_trial_satisfied'])
        self.assertEqual(result['status'],'sealed_for_failed_initial_trial_archive')
        self.assertEqual(helper.seal_failed_initial_a(self.repo,self.target,execute=True)['sealed_at'],result['sealed_at'])
        self.assertEqual(self.evidence(),before)
        self.raw.fail_get=True
        with self.assertRaises(ArchiveUnavailable):cycle(self.repo,self.raw,origin=helper.ORIGIN)
        self.raw.fail_get=False;self.assertEqual(cycle(self.repo,self.raw,origin=helper.ORIGIN)['status'],'archived')
        raw=self.raw;raw._reader=True;raw._origin_binding=cloud_binding(helper.ORIGIN)
        class Reader:
            expected_role=NEXT_TRIAL_READER
            origin_id=helper.ORIGIN
            generation_id=helper.FAILED_INITIAL_A
            def read_retirement_revisions(inner,records,*,max_bytes,timeout_seconds):
                rows=raw.read_structured_authenticated(records,max_bytes=max_bytes,timeout_seconds=timeout_seconds)
                return rows,max(len(encoded(rows)),len(encoded(records)))
        transport=RetirementTransport(raw,Reader(),origin_id=helper.ORIGIN,generation_id=helper.FAILED_INITIAL_A)
        reader=lambda:connect(self.reader_dsn,readonly=True)
        digest=self.repo.generation(helper.FAILED_INITIAL_A)['seal_hash']
        with patch('postgres.pp_retained_archive_audit.remote_preflight'):
            audit=helper.audit_failed_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
            self.assertEqual(audit['status'],'failed_initial_trial_archive_audit_verified')
            self.assertFalse(audit['original_trial_satisfied'])
            raw.corrupt_structured=True
            with self.assertRaises(ArchiveIntegrityError):
                helper.audit_failed_initial_a(reader,transport,self.target,seal_hash=digest,raw_objects=1,structured_pages=1)
        self.assertEqual(self.evidence(),before)
        with self.factory() as db:
            self.assertEqual(db.execute('SELECT count(*) AS n FROM archive.generations WHERE origin_id=%s',
                                        (helper.ORIGIN,)).fetchone()['n'],1)
        self.assertEqual(self.repo.collector_state(helper.ORIGIN)['generation_id'],helper.FAILED_INITIAL_A)
        self.assertEqual(self.repo.pending_outbox_limit,10000)
        with self.assertRaises(ValueError):self.failed_store.ingest(self.event(82))
        with self.assertRaises(LifecycleHold):
            helper.seal_failed_initial_a(self.repo,replace(self.target,operation=str(uuid.uuid4())),execute=True)

    def test_actual_20362_ack_total_seals_and_fully_reads_back_under_64mib(self):
        from postgres.active_structured import ActiveStructuredWorker
        from postgres.pp_sealed_archive import cycle
        from postgres.pp_retirement_verify import RetirementTransport
        from postgres.connection import connect
        # These generated revisions retain the real Store-created column/envelope
        # contract. Distinct synthetic symbols avoid conflicting mutable revisions.
        # Admit <=500 pending at once; total ACK history legitimately exceeds10000.
        inserted=0
        while inserted<20361:
            count=min(500,20361-inserted)
            with self.admin() as db:
                db.execute("""INSERT INTO ops.outbox
                    (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                    SELECT origin_id,generation_id,entity_type,
                      replace(entity_id,'BTC-USD','GENERATED-'||n),lpad(n::text,64,'0'),
                      payload||jsonb_build_object('symbol','GENERATED-'||n,'content_hash',lpad(n::text,64,'0')),
                      created_at
                    FROM (SELECT * FROM ops.outbox WHERE origin_id=%s ORDER BY id LIMIT 1) original
                    CROSS JOIN generate_series(%s::integer,%s::integer) n""",(helper.ORIGIN,inserted+1,inserted+count))
                self.assertEqual(db.execute('SELECT count(*) AS n FROM ops.outbox WHERE origin_id=%s '
                    'AND acknowledged_at IS NULL',(helper.ORIGIN,)).fetchone()['n'],count)
            result=ActiveStructuredWorker(self.repo,self.raw,origin_id=helper.ORIGIN).cycle(helper.FAILED_INITIAL_A)
            self.assertEqual(result['acknowledged'],count)
            inserted+=count
        with self.admin() as db:
            totals=db.execute('SELECT count(*) AS n,count(*) FILTER(WHERE acknowledged_at IS NULL) AS pending,'
                'sum(octet_length(row_to_json(o)::text)) AS bytes FROM ops.outbox o WHERE origin_id=%s',
                (helper.ORIGIN,)).fetchone()
        self.assertEqual((totals['n'],totals['pending']),(20362,0))
        self.assertLess(totals['bytes'],64*1024**2)
        self.assertEqual(self.repo.pending_outbox_limit,10000)
        target=replace(self.target,outbox_count=20362)
        before=self.evidence()
        helper.seal_failed_initial_a(self.repo,target,execute=True)
        self.assertEqual(cycle(self.repo,self.raw,origin=helper.ORIGIN)['status'],'archived')
        raw=self.raw;raw._reader=True;raw._origin_binding=cloud_binding(helper.ORIGIN)
        class Reader:
            expected_role=NEXT_TRIAL_READER
            origin_id=helper.ORIGIN
            generation_id=helper.FAILED_INITIAL_A
            def read_retirement_revisions(inner,records,*,max_bytes,timeout_seconds):
                rows=raw.read_structured_authenticated(records,max_bytes=max_bytes,timeout_seconds=timeout_seconds)
                return rows,len(encoded(rows))
        transport=RetirementTransport(raw,Reader(),origin_id=helper.ORIGIN,generation_id=helper.FAILED_INITIAL_A)
        reader=lambda:connect(self.reader_dsn,readonly=True)
        with patch('postgres.pp_retained_archive_audit.remote_preflight'):
            result=helper.audit_failed_initial_a(reader,transport,target,
                seal_hash=self.repo.generation(helper.FAILED_INITIAL_A)['seal_hash'],raw_objects=1,structured_pages=41)
        self.assertEqual(result['structured_count'],20362)
        self.assertEqual(result['inventory']['structured_pages_examined'],41)
        self.assertLess(result['bytes'],64*1024**2)
        self.assertEqual(self.evidence(),before)

    def test_partition_metadata_mismatch_holds_before_seal(self):
        from contextlib import contextmanager
        original = self.repo.transaction
        before = self.evidence()
        @contextmanager
        def transaction():
            with original() as db:
                class Connection:
                    def execute(inner, query, parameters=None):
                        cursor = db.execute(query, parameters)
                        if query.startswith('SELECT * FROM archive.generations WHERE origin_id='):
                            class ChangedRow:
                                def fetchone(self):
                                    row = cursor.fetchone()
                                    return dict(row, partition_name='events_g_' + '0' * 32)
                            return ChangedRow()
                        return cursor
                yield Connection()
        with patch.object(self.repo, 'transaction', transaction):
            with self.assertRaisesRegex(LifecycleHold, 'partition metadata'):
                helper.seal_failed_initial_a(self.repo, self.target, execute=True)
        self.assertEqual(self.evidence(), before)

    def test_another_pp_collector_blocks_recovery_seal(self):
        before=self.evidence()
        with self.admin() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()+interval '1 minute' WHERE origin_id='pp-live-pp'",
                       (str(uuid.uuid4()),))
        with self.assertRaisesRegex(LifecycleHold,'all PP collectors'):
            helper.seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.evidence(),before)
        self.assertEqual(self.repo.generation(helper.FAILED_INITIAL_A)['state'],'collecting')

    def test_bad_counts_source_and_pending_fail_without_seal(self):
        before=self.evidence()
        for change in ({'writer_epoch':99},{'raw_count':2},{'outbox_count':2},{'trial_source':'c'*40}):
            with self.subTest(change=change),self.assertRaises(LifecycleHold):
                helper.seal_failed_initial_a(self.repo,replace(self.target,**change),execute=True)
        self.assertEqual(self.evidence(),before)
        with self.admin() as db:db.execute('UPDATE ops.outbox SET acknowledged_at=NULL WHERE origin_id=%s',(helper.ORIGIN,))
        with self.assertRaisesRegex(LifecycleHold,'fully acknowledged'):
            helper.seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(helper.FAILED_INITIAL_A)['state'],'collecting')

    def test_checkpoint_rollback_and_expired_enabled_writer_preserve_raw(self):
        before=self.evidence()
        with patch.object(self.repo,'_checkpoint',side_effect=RuntimeError('journal failure')):
            with self.assertRaises(RuntimeError):helper.seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.evidence(),before)
        self.assertEqual(self.repo.collector_state(helper.ORIGIN)['epoch'],self.target.writer_epoch)
        with self.admin() as db:
            db.execute("UPDATE ops.writer_state SET collector_enabled=true,collector_session_id=%s,"
                       "collector_lease_expires_at=clock_timestamp()-interval '1 second' WHERE origin_id=%s",
                       (str(uuid.uuid4()),helper.ORIGIN))
        with self.assertRaisesRegex(LifecycleHold,'durably OFF'):
            helper.seal_failed_initial_a(self.repo,self.target,execute=True)
        self.assertEqual(self.repo.generation(helper.FAILED_INITIAL_A)['state'],'collecting')
