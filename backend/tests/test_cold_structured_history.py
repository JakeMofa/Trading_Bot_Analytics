"""Generated-only cold history query qualification; no cloud/network access."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable, encoded, sha256
from postgres.cold_structured_history import ColdStructuredHistory, MAX_BYTES, ORIGIN
from postgres.history_v2_envelope import CLOUD_COLUMNS, TABLE_KEYS

GENERATION='00000000-0000-4000-8000-000000000001'


def envelope(index):
    table='core.predictions'
    payload={key:None for key in CLOUD_COLUMNS[table]}
    payload.update(origin_id=ORIGIN, prediction_id='p'+str(index), snapshot_id='s'+str(index),
                   market_id='market',model_version='gaussian_distance_v1',
                   as_of='2026-11-19T10:00:00+00:00', created_at='2026-11-19T10:00:00+00:00',
                   probability_up='0.50000000000000000001',probability_down='0.49999999999999999999',
                   content_hash='a'*64)
    return dict(id=index,origin_id=ORIGIN,generation_id=GENERATION,entity_type=table,
                entity_id=encoded([payload[k] for k in TABLE_KEYS[table]]).decode(),
                content_hash='a'*64,payload=payload)


def setup(count=51, clock=lambda:0):
    rows=[envelope(i) for i in range(1,count+1)]
    source=Mock(origin_id=ORIGIN,generation_id=GENERATION)
    source.read_revisions.side_effect=lambda ids,**kw:deepcopy([r for r in rows if r['id'] in ids])
    reader=ColdStructuredHistory(source,origin_id=ORIGIN,generation_id=GENERATION,clock=clock)
    manifest=[dict(id=r['id'],envelope_sha256=sha256(encoded(r))) for r in rows]
    return reader,source,rows,manifest


class ColdHistoryTests(unittest.TestCase):
    def test_pages_exact_identity_bytes_decimal_and_coverage(self):
        reader,source,rows,manifest=setup()
        page=reader.read_page(manifest,entity_type='core.predictions',market_id='market')
        self.assertEqual(page['rows'],rows[:50])
        self.assertFalse(page['coverage']['end_of_reviewed_manifest'])
        final=reader.read_page(manifest,entity_type='core.predictions',market_id='market',cursor=page['next_cursor'])
        self.assertEqual(final['rows'],rows[50:]);self.assertTrue(final['coverage']['end_of_reviewed_manifest'])
        self.assertEqual(final['coverage']['whole_market_coverage'],'not_established')
        self.assertFalse(final['provenance']['retirement_authority'])
        self.assertEqual(source.method_calls[0].kwargs,dict(max_bytes=MAX_BYTES,timeout_seconds=4))
        self.assertEqual([c[0] for c in source.method_calls],['read_revisions','read_revisions'])

    def test_origin_generation_market_entity_and_manifest_hash_guard(self):
        for mutate in [lambda r:r.update(origin_id='production'),lambda r:r.update(generation_id='other'),
                       lambda r:r['payload'].update(market_id='other'),
                       lambda r:r.update(entity_type='core.outcomes'),
                       lambda r:r['payload'].update(probability_up='0.50')]:
            reader,source,rows,manifest=setup(1);mutate(rows[0])
            with self.assertRaises(ArchiveIntegrityError):reader.read_page(manifest,entity_type='core.predictions',market_id='market')
        reader,source,rows,manifest=setup(1)
        with self.assertRaises(ValueError):ColdStructuredHistory(source,origin_id='prod',generation_id=GENERATION)

    def test_missing_and_reordered_rows_never_empty_success(self):
        for rows in ([],[envelope(2),envelope(1)]):
            reader,source,_,manifest=setup(2);source.read_revisions.side_effect=None;source.read_revisions.return_value=rows
            with self.assertRaises(ArchiveIntegrityError):reader.read_page(manifest,entity_type='core.predictions',market_id='market')

    def test_scope_cursor_cannot_be_reused_for_other_origin_or_market(self):
        reader,source,rows,manifest=setup();first=reader.read_page(manifest,entity_type='core.predictions',market_id='market')
        with self.assertRaises(ArchiveIntegrityError):reader.read_page(manifest,entity_type='core.predictions',market_id='other',cursor=first['next_cursor'])
        with self.assertRaises(ArchiveIntegrityError):reader.read_page(manifest[:-1],entity_type='core.predictions',market_id='market',cursor=first['next_cursor'])

    def test_deadline_size_and_network_failure_remain_explicit(self):
        ticks=iter([0,4]);reader,source,rows,manifest=setup(1,clock=lambda:next(ticks))
        with self.assertRaises(ArchiveLimit):reader.read_page(manifest,entity_type='core.predictions',market_id='market')
        reader,source,rows,manifest=setup(1);rows[0]['payload']['payload']={'large':'x'*MAX_BYTES}
        with self.assertRaises(ArchiveLimit):reader.read_page(manifest,entity_type='core.predictions',market_id='market')
        reader,source,rows,manifest=setup(1);source.read_revisions.side_effect=OSError('sensitive details')
        with self.assertRaisesRegex(ArchiveUnavailable,'cold structured source unavailable'):
            reader.read_page(manifest,entity_type='core.predictions',market_id='market')

    def test_manifest_validation_and_no_work_on_invalid_request(self):
        reader,source,rows,manifest=setup(1)
        for bad in ([],[manifest[0],manifest[0]],[dict(id=True,envelope_sha256='a'*64)]):
            with self.assertRaises((ArchiveLimit,ArchiveIntegrityError)):reader.read_page(bad,entity_type='core.predictions',market_id='market')
        source.read_revisions.assert_not_called()


if __name__=='__main__':unittest.main()
