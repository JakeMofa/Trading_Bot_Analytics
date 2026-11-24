"""Generated socket-only PG17 rehearsal. The destination version catalog is a fixture."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import secrets
import threading
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveLimits, encoded, sha256
from postgres.connection import connect
from postgres.lifecycle import ArchiveWorker, LifecycleRepository
from postgres.pp_retirement_verify import Target
from postgres.retirement_shadow import JOURNAL_DDL, verify_shadow
import test_pp_initial_trial_drain as cluster
import test_postgres_lifecycle_integration as lifecycle
from postgres_lifecycle_fixtures import ImmutableMemoryTransport


class FixtureDestination(ImmutableMemoryTransport):
    def pin_shadow_versions(self):
        return nullcontext(self)

    def version(self, batch):
        if batch.startswith('raw.events:'):
            if batch != 'raw.events:000000000000' or len(self.objects) != 1:
                raise ArchiveIntegrityError('fixture requires one exact raw manifest')
            return sha256(next(iter(self.objects.values())))
        _, after, last = batch.split(':')
        records = sorted((r for r in self.structured.values() if int(after) < r['id'] <= int(last)),
                         key=lambda r: r['id'])
        return sha256(encoded(records))


class ShadowNative(unittest.TestCase):
    # Reuse the suite's disposable socket-only cluster, migrations and generated insert.
    admin = cluster.InitialSealNative.__dict__['admin']
    tearDownClass = cluster.InitialSealNative.__dict__['tearDownClass']
    insert = lifecycle.PostgreSQLLifecycleIntegration.insert

    @classmethod
    def setUpClass(cls):
        cluster.InitialSealNative.setUpClass.__func__(cls)
        with cls.admin() as db:
            db.execute("CREATE SCHEMA shadow_qualification")
            db.execute(JOURNAL_DDL)

    def setUp(self):
        self.journal_key = secrets.token_bytes(32)
        self.origin = 'generated-shadow-' + uuid.uuid4().hex
        self.factory = lambda: connect(self.lifecycle_dsn)
        self.app_factory = lambda: connect(self.app_dsn)
        self.repo = LifecycleRepository(self.factory)
        start = datetime.now(timezone.utc) - timedelta(hours=73)
        sealed = self.repo.bootstrap(self.origin, start)['generation_id']
        self.insert(1)
        with self.app_factory() as db:
            db.execute("""INSERT INTO ops.outbox
                (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                SELECT %s,%s,'fixture',i::text,repeat('1',64),jsonb_build_object('id',i),now()
                FROM generate_series(1,56) AS i""", (self.origin, sealed))
        active = self.repo.switch_if_due(self.origin)['generation_id']
        self.transport = FixtureDestination()
        self.transport.origin_id = self.origin
        self.transport.generation_id = sealed
        worker = ArchiveWorker(self.repo, self.transport, ArchiveLimits(max_rows=100))
        self.assertEqual(worker.archive_cycle(sealed)['status'], 'archived')
        self.target = Target(sealed, active, self.repo.generation(sealed)['seal_hash'], 1)
        self.limits = ArchiveLimits(max_rows=1, max_requests=100)

    def read(self, cap):
        return verify_shadow(self.repo, self.transport, self.admin, self.target,
                             source='b'*40, limits=self.limits, batch_budget=cap, journal_key=self.journal_key)

    def test_resume_with_opposite_slot_committing_and_ambiguous_attempt(self):
        # Independent writer commits while the verifier holds the sealed generation.
        start = threading.Event()
        finished = threading.Event()
        errors = []
        def writer():
            try:
                if not start.wait(5):
                    raise TimeoutError('verifier did not reach final raw read')
                self.insert(120)
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=writer)
        thread.start()
        original = self.transport.read_authenticated
        def overlap(*args, **kw):
            start.set()
            self.assertTrue(finished.wait(5))
            return original(*args, **kw)
        self.transport.read_authenticated = overlap
        structured_read = self.transport.read_structured_authenticated
        reads = 0
        def interrupt_before_page_55(*args, **kw):
            nonlocal reads
            reads += 1
            if reads == 55:
                raise KeyboardInterrupt("forced worker interruption")
            return structured_read(*args, **kw)
        self.transport.read_structured_authenticated = interrupt_before_page_55
        with self.assertRaises(KeyboardInterrupt):
            self.read(100)
        self.transport.read_structured_authenticated = structured_read
        thread.join(5)
        self.assertFalse(errors)
        paused = self.read(1)
        self.assertEqual((paused['status'], paused['reused_batches'], paused['fresh_batches']),
                         ('shadow_paused', 55, 1))
        self.assertEqual(self.repo.generation(self.target.sealed)['state'], 'verified')
        with self.app_factory() as db:
            count = db.execute('SELECT count(*) n FROM raw.events WHERE generation_id=%s',
                               (self.target.collecting,)).fetchone()['n']
        self.assertEqual(count, 1)
        done = self.read(2)
        self.assertEqual((done['status'], done['reused_batches'], done['fresh_batches']),
                         ('shadow_complete', 56, 1))
        self.assertFalse(done['retirement_authorized'])
        row = next(iter(self.transport.structured.values()))
        row['payload'] = {'privileged_mutation': True}
        with self.assertRaisesRegex(ArchiveIntegrityError, 'version or source changed'):
            self.read(2)
        with self.admin() as db:
            db.execute("UPDATE archive.generations SET sealed_at=now()-interval '31 minutes' WHERE generation_id=%s",
                       (self.target.sealed,))
        with self.assertRaises(ArchiveLimit):
            self.read(2)

    def test_changed_previously_reused_version_during_final_reconciliation(self):
        self.read(55)
        original = self.transport.read_structured_authenticated
        def change_prior_object(*args, **kw):
            key = next(iter(self.transport.objects))
            self.transport.objects[key] += b'changed'
            return original(*args, **kw)
        self.transport.read_structured_authenticated = change_prior_object
        with self.assertRaisesRegex(ArchiveIntegrityError, 'during reconciliation'):
            self.read(2)
        self.assertEqual(self.repo.generation(self.target.sealed)['state'], 'verified')

    def test_journal_admin_cannot_forge_previously_checked_raw_batch(self):
        saved = self.read(1)
        with self.admin() as db:
            db.execute("UPDATE shadow_qualification.verified_batches SET proof=%s WHERE scope=%s",
                       ('0'*64, saved['scope']))
        with self.assertRaisesRegex(ArchiveIntegrityError, 'journal signature'):
            self.read(2)
