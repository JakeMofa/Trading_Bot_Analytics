"""Native bounded revision selection with an occupied retained history."""
from copy import deepcopy
import unittest
import uuid

import test_sync_barriers_pg as fixture
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded, sha256
from postgres.cloud_origin_binding import TRIAL_ORIGIN


class RevisionSelectionPG(unittest.TestCase):
    # Reuse only the disposable Unix-socket fixture, not its inherited test cases.
    setUpClass = classmethod(fixture.SyncBarriersPG.setUpClass.__func__)
    tearDownClass = classmethod(fixture.SyncBarriersPG.tearDownClass.__func__)
    admin = classmethod(fixture.SyncBarriersPG.admin.__func__)
    reset = fixture.SyncBarriersPG.reset
    connected = fixture.SyncBarriersPG.connected
    transport = fixture.SyncBarriersPG.transport
    setUp = fixture.SyncBarriersPG.setUp

    def seed(self):
        generation = str(uuid.uuid4())
        template = fixture.page(generation)[1]  # Fifty revisions of one mutable entity.
        records = []
        for outbox_id in range(54537, 54587):
            record = deepcopy(template)
            record['id'] = outbox_id
            records.append(record)
        with self.admin() as db:
            # Real receipts, FK and envelope-hash trigger remain enabled. Retained
            # rows deliberately need not decode: they must never be selected.
            db.execute('''INSERT INTO history_v2.structured_receipts
                SELECT %s,%s,i,'retained','retained',repeat('a',64),repeat('b',64),
                    encode(sha256(convert_to('retained','UTF8')),'hex')
                FROM generate_series(1,6000) i''', (TRIAL_ORIGIN, generation))
            db.execute('''INSERT INTO history_v2.structured_revision_payloads
                SELECT origin_id,generation_id,outbox_id,convert_to('retained','UTF8')
                FROM history_v2.structured_receipts''')
            for scoped_generation in (generation, str(uuid.uuid4())):
                with db.cursor() as cursor:
                    cursor.executemany('''INSERT INTO history_v2.structured_receipts
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', [
                        (TRIAL_ORIGIN, scoped_generation, r['id'], r['entity_type'], r['entity_id'],
                         r['content_hash'], sha256(encoded(r['payload'])), sha256(encoded(r)))
                        for r in records])
                    cursor.executemany('''INSERT INTO history_v2.structured_revision_payloads
                        VALUES (%s,%s,%s,%s)''', [
                        (TRIAL_ORIGIN, scoped_generation, r['id'], encoded(r)) for r in records])
            db.execute('ANALYZE history_v2.structured_receipts')
            db.execute('ANALYZE history_v2.structured_revision_payloads')
        return generation, records

    def test_selected_fifty_remain_exact_and_plan_work_is_bounded(self):
        generation, records = self.seed()
        ids = [r['id'] for r in records]
        captured = []
        with self.connected() as db:
            transport = self.transport(db, generation)
            class Capture:
                def execute(self, statement, values):
                    captured.append((statement, values))
                    return db.execute(statement, values)
            self.assertEqual(transport._read_revisions(Capture(), ids, 256 * 1024), records)
            statement, values = captured[0]
            plan = db.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + statement, values).fetchone()['QUERY PLAN'][0]['Plan']
        scans = []
        def visit(node):
            if node.get('Relation Name') in ('structured_receipts', 'structured_revision_payloads'):
                scans.append(node)
            for child in node.get('Plans', []):
                visit(child)
        visit(plan)
        self.assertEqual({node['Relation Name'] for node in scans},
                         {'structured_receipts', 'structured_revision_payloads'})
        for relation in ('structured_receipts', 'structured_revision_payloads'):
            examined = sum((node['Actual Rows'] + node.get('Rows Removed by Filter', 0)) * node['Actual Loops']
                           for node in scans if node['Relation Name'] == relation)
            self.assertLessEqual(examined, 100, (relation, plan))

    def test_missing_selected_revision_fails_despite_other_generation_copy(self):
        generation, records = self.seed()
        with self.admin() as db:
            db.execute('''DELETE FROM history_v2.structured_revision_payloads
                WHERE origin_id=%s AND generation_id=%s AND outbox_id=%s''',
                (TRIAL_ORIGIN, generation, records[17]['id']))
        with self.connected() as db:
            with self.assertRaises(ArchiveIntegrityError):
                self.transport(db, generation)._read_revisions(db, [r['id'] for r in records], 256 * 1024)

    def test_aggregate_metadata_suppresses_all_variable_fields_before_fetch(self):
        generation, records = self.seed()
        ids = [r['id'] for r in records]
        bound = 256 * 1024
        # Each selected receipt fits; their combined text exceeds the bound.
        with self.admin() as db:
            db.execute('''UPDATE history_v2.structured_receipts SET entity_id=repeat('x',6000)
                WHERE origin_id=%s AND generation_id=%s AND outbox_id=ANY(%s::bigint[])''',
                (TRIAL_ORIGIN, generation, ids))
        with self.connected() as db:
            transport = self.transport(db, generation)
            rows = transport._revision_cursor(db, ids, bound).fetchall()
            self.assertEqual([row['outbox_id'] for row in rows], ids)
            for row in rows:
                self.assertLess(row['total'], bound)
                self.assertGreater(row['metadata_total'], bound)
                for field in ('envelope', 'entity_type', 'entity_id', 'content_hash', 'payload_hash', 'envelope_hash'):
                    self.assertIsNone(row[field], field)
            with self.assertRaises(ArchiveLimit):
                transport._decode_revisions(rows, ids, bound)


if __name__ == '__main__':
    unittest.main()
