"""Generated local backup recovery checks; no database, cloud or VM access."""
from contextlib import redirect_stdout
from copy import deepcopy
import gzip
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import (ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable,
    ArchiveLimits, encoded, manifest_set_hash, pack_chunk, row_cursor, sha256)
from postgres.raw_backup_verify import RecoveryLimits, main, verify_backup

ORIGIN = 'pp-live-pp'
GENERATION = '00000000-0000-4000-8000-000000000001'


def event(index):
    return dict(origin_id=ORIGIN, generation_id=GENERATION, source='coinbase',
        event_id=f'event-{index:08d}', source_time='2026-11-19T10:00:00.123456789+00:00',
        received_at='2026-11-19T10:00:01+00:00', available_at='2026-11-19T10:00:01+00:00',
        payload={'price':'100.000000000000000000001', 'missing':None,
                 'private_fixture_text':'do-not-print-recovered-payload'})


class RawBackupVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='raw-backup-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base/'backup'
        self.root.mkdir()
        self.path = self.base/'inventory.json'
        self.rows = [event(index) for index in range(3)]
        self.build([self.rows[:2], self.rows[2:]])

    def build(self, chunks):
        manifests, after = [], None
        for index, rows in enumerate(chunks):
            blob, manifest = pack_chunk(rows, origin_id=ORIGIN, generation_id=GENERATION,
                                        after=after, limits=ArchiveLimits())
            manifest['manifest_id'] = f'raw.events:{index:012d}'
            manifest['object_key'] = f'raw-v1/{sha256(ORIGIN.encode())}/{GENERATION}/{manifest["sha256"]}.jsonl.gz'
            path = self.root/manifest['object_key']; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            manifests.append(manifest); after = manifest['coverage']['last']
        self.inventory = dict(generation=dict(origin_id=ORIGIN, generation_id=GENERATION,
            seal_count=sum(m['row_count'] for m in manifests), seal_hash=manifest_set_hash(manifests)),
            manifests=manifests)
        self.write_inventory()

    def write_inventory(self, *, reseal=False):
        if reseal:
            self.inventory['generation']['seal_hash'] = manifest_set_hash(self.inventory['manifests'])
        self.path.write_bytes(encoded(self.inventory))
        self.digest = sha256(self.path.read_bytes())

    def verify(self, **kwargs):
        values = dict(expected_inventory_sha256=self.digest, backup_root=self.root,
                      origin_id=ORIGIN, generation_id=GENERATION)
        values.update(kwargs)
        return verify_backup(self.path, **values)

    def replace_raw(self, index, transform):
        manifest = self.inventory['manifests'][index]
        raw = transform(gzip.decompress((self.root/manifest['object_key']).read_bytes()))
        blob = gzip.compress(raw, mtime=0)
        manifest['sha256'] = sha256(blob); manifest['byte_count'] = len(blob)
        manifest['coverage']['decoded_bytes'] = len(raw)
        manifest['coverage']['decoded_sha256'] = sha256(raw)
        manifest['object_key'] = f'raw-v1/{sha256(ORIGIN.encode())}/{GENERATION}/{manifest["sha256"]}.jsonl.gz'
        (self.root/manifest['object_key']).write_bytes(blob)
        self.write_inventory(reseal=True)

    def test_exact_multichunk_recovery_reports_only_aggregate_evidence(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.verify()
        self.assertEqual((result['objects'], result['rows']), (2, 3))
        self.assertEqual(result['recovered_rows_sha256'], sha256(b''.join(encoded(r)+b'\n' for r in self.rows)))
        self.assertEqual(result['recovered_identity_sha256'], sha256(encoded([row_cursor(r) for r in self.rows])))
        self.assertEqual(result['coverage'], 'complete_generation_conditional_on_trusted_inventory')
        self.assertFalse(result['retirement_authority']); self.assertFalse(result['network_used'])
        self.assertFalse(result['data_written']); self.assertFalse(result['official_settlement'])
        self.assertNotIn('payload', result)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_codec_page_boundary_and_empty_generation(self):
        rows = [event(index) for index in range(501)]
        self.build([rows[:500], rows[500:]])
        self.assertEqual(self.verify()['rows'], 501)
        self.build([[]])
        result = self.verify()
        self.assertEqual(result['rows'], 0)
        self.assertEqual(result['recovered_rows_sha256'], sha256(b''))
        self.assertEqual(result['recovered_identity_sha256'], sha256(b'[]'))

    def test_external_digest_and_exact_scope_are_mandatory(self):
        for kwargs in (dict(expected_inventory_sha256='a'*64), dict(expected_inventory_sha256=''),
                       dict(origin_id='prod-live'), dict(generation_id=GENERATION.upper()),
                       dict(generation_id='00000000-0000-4000-8000-000000000002')):
            # This fixture's UUID has no alphabetic digits, so use a malformed
            # canonical spelling rather than an unchanged uppercase value.
            if kwargs.get('generation_id') == GENERATION:
                kwargs['generation_id'] = '{'+GENERATION+'}'
            with self.subTest(kwargs=kwargs), self.assertRaises(ArchiveIntegrityError):
                self.verify(**kwargs)

    def test_missing_final_object_and_truncated_or_corrupt_bytes_fail_closed(self):
        path = self.root/self.inventory['manifests'][-1]['object_key']
        original = path.read_bytes(); path.unlink()
        with self.assertRaises(ArchiveUnavailable): self.verify()
        path.write_bytes(original[:-1])
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        path.write_bytes(bytes([original[0]^1])+original[1:])
        with self.assertRaises(ArchiveIntegrityError): self.verify()

    def test_changed_decoded_hash_header_or_origin_is_rejected(self):
        original = deepcopy(self.inventory)
        self.inventory['manifests'][0]['coverage']['decoded_sha256'] = 'a'*64
        self.write_inventory(reseal=True)
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        self.inventory = deepcopy(original); self.write_inventory()
        def wrong_header(raw):
            lines = raw.splitlines(); header=json.loads(lines[0]); header['origin_id']='prod-live'
            return encoded(header)+b'\n'+b'\n'.join(lines[1:])+b'\n'
        self.replace_raw(0, wrong_header)
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        self.build([self.rows[:2], self.rows[2:]])
        def wrong_row(raw):
            lines = raw.splitlines(); row=json.loads(lines[1]); row['origin_id']='prod-live'
            lines[1]=encoded(row); return b'\n'.join(lines)+b'\n'
        self.replace_raw(0, wrong_row)
        with self.assertRaises(ArchiveIntegrityError): self.verify()

    def test_catalog_gap_overlap_count_and_hash_changes_are_rejected_before_object_io(self):
        original = deepcopy(self.inventory)
        for mutate in (lambda x:x['manifests'].pop(),
                       lambda x:x['manifests'][1]['coverage'].update(after=None),
                       lambda x:x['manifests'][1]['coverage'].update(first=['coinbase','event-00000001']),
                       lambda x:x['generation'].update(seal_count=4),
                       lambda x:x['generation'].update(seal_hash='a'*64)):
            self.inventory=deepcopy(original); mutate(self.inventory); self.write_inventory()
            with patch('postgres.raw_backup_verify.unpack_chunk') as decode:
                with self.assertRaises(ArchiveIntegrityError): self.verify()
                decode.assert_not_called()

    def test_unsafe_paths_symlinks_hardlinks_and_special_files_are_rejected(self):
        original=deepcopy(self.inventory)
        for key in ('../outside', '/outside', 'raw-v1/../outside', 'raw-v1\\outside'):
            self.inventory=deepcopy(original); self.inventory['manifests'][0]['object_key']=key
            self.write_inventory()
            with self.assertRaises(ArchiveIntegrityError): self.verify()
        self.inventory=original; self.write_inventory()
        target=self.root/self.inventory['manifests'][0]['object_key']
        outside=self.base/'outside'; outside.write_bytes(target.read_bytes()); target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(ArchiveUnavailable): self.verify()
        target.unlink(); os.link(outside,target)
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        target.unlink(); os.mkfifo(target)
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        target.unlink(); target.write_bytes(outside.read_bytes())
        directory=self.root/'raw-v1'; moved=self.root/'moved'; directory.rename(moved); directory.symlink_to(moved)
        with self.assertRaises(ArchiveUnavailable): self.verify()
        alias=self.base/'alias'; alias.symlink_to(self.root)
        with self.assertRaises(ArchiveUnavailable): self.verify(backup_root=alias)
        with self.assertRaises(ArchiveIntegrityError): self.verify(backup_root=self.root/'..'/'backup')

    def test_inventory_duplicate_fields_and_symlink_are_rejected(self):
        raw=self.path.read_bytes()
        self.path.write_bytes(b'{"generation":{},"generation":{},"manifests":[]}')
        self.digest=sha256(self.path.read_bytes())
        with self.assertRaises(ArchiveIntegrityError): self.verify()
        self.path.unlink(); other=self.base/'real-inventory'; other.write_bytes(raw); self.path.symlink_to(other)
        with self.assertRaises(ArchiveUnavailable): self.verify(expected_inventory_sha256=sha256(raw))

    def test_aggregate_budgets_and_decode_deadline_do_not_return_partial_success(self):
        compressed=sum(m['byte_count'] for m in self.inventory['manifests'])
        decoded=sum(m['coverage']['decoded_bytes'] for m in self.inventory['manifests'])
        for limits in (RecoveryLimits(max_compressed_bytes=compressed-1), RecoveryLimits(max_decoded_bytes=decoded-1)):
            with self.assertRaises(ArchiveLimit): self.verify(limits=limits)
        from postgres import raw_backup_verify as subject
        clock=[0]; original=subject.unpack_chunk
        def late(*args, **kwargs):
            result=original(*args, **kwargs); clock[0]=60; return result
        with patch.object(subject,'unpack_chunk',side_effect=late):
            with self.assertRaises(ArchiveLimit): self.verify(clock=lambda:clock[0])

    def test_file_change_during_read_is_rejected(self):
        original=os.fstat; calls=[0]
        def changed(descriptor):
            result=original(descriptor); calls[0]+=1
            if calls[0]==4:
                values={name:getattr(result,name) for name in ('st_mode','st_nlink','st_size','st_dev','st_ino','st_mtime_ns','st_ctime_ns')}
                values['st_mtime_ns']+=1
                return SimpleNamespace(**values)
            return result
        with patch('postgres.raw_backup_verify.os.fstat',side_effect=changed):
            with self.assertRaises(ArchiveIntegrityError): self.verify()

    def test_cli_prints_no_payload_and_sanitizes_failure(self):
        arguments=['--inventory',str(self.path),'--expected-inventory-sha256',self.digest,
                   '--backup-root',str(self.root),'--origin-id',ORIGIN,'--generation-id',GENERATION]
        output=io.StringIO()
        with redirect_stdout(output): self.assertEqual(main(arguments),0)
        self.assertNotIn('do-not-print',output.getvalue()); self.assertNotIn('event-',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['rows'],3)
        (self.root/self.inventory['manifests'][-1]['object_key']).unlink()
        output=io.StringIO()
        with redirect_stdout(output): self.assertEqual(main(arguments),1)
        self.assertEqual(json.loads(output.getvalue()),{'status':'hold','code':'archive_unavailable'})
        self.assertNotIn(str(self.root),output.getvalue())


if __name__=='__main__':
    unittest.main()
