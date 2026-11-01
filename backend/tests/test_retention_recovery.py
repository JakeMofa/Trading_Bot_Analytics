from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from cloud_memory import build_archive
import retention_recovery as recovery

STAMP='2026-10-01T00:00:00.000000+00:00'


class RecoveryProofTests(unittest.TestCase):
    def archive(self,dataset,rows):
        raw,compressed,sha=build_archive(dataset,rows)
        lo,hi=rows[0],rows[-1]
        manifest={'source':'polymarket' if dataset=='observations' else 'coinbase',
            'bucket':'market-raw','object_path':'generated-only/'+dataset,'verified_at':STAMP,
            'started_at':lo['received_at'],'ended_at':hi['received_at'],
            'event_count':len(rows),'compressed_bytes':len(compressed),'sha256':sha,
            'first_source_id':lo.get('id'),'last_source_id':hi.get('id'),
            'metadata':{'dataset':dataset,'verification':'authenticated_readback_sha256',
                'first_source_key':json.dumps([lo.get('source'),lo.get('event_id')]),
                'last_source_key':json.dumps([hi.get('source'),hi.get('event_id')])}}
        return manifest,compressed

    def test_original_json_text_and_exact_decimal_strings_reconstruct(self):
        for dataset in ('observations','stream_events'):
            row=({'id':7,'market_id':'m','received_at':STAMP,'source_time':None,'kind':'book',
                  'payload':'{ "price": "123.00000001", "quantity": 1.25 }'} if dataset=='observations' else
                 {'source':'coinbase','event_id':'0007','received_at':STAMP,'source_time':STAMP,
                  'price':'123.00000001','size':'0.1000','side':None,'payload':'{ "x": true }'})
            m,b=self.archive(dataset,[row]);proof,found=recovery.verify_archive(m,b,{recovery.identity(dataset,row)})
            saved=recovery.build_manifest(dataset,[row],[(proof,found)])
            self.assertEqual(saved['records'][0],row)
            result=recovery.reconstruct_in_memory(saved)
            self.assertTrue(result['raw_columns_exact']);self.assertFalse(result['full_database_backup'])

    def test_raw_number_precision_loss_or_boolean_change_is_rejected(self):
        row={'id':1,'market_id':'m','received_at':STAMP,'source_time':None,'kind':'book',
             'payload':'{"x":0.100000000000000001}'}
        m,b=self.archive('observations',[row]);proof,found=recovery.verify_archive(m,b,{(1,)})
        with self.assertRaises(recovery.RecoveryError):recovery.build_manifest('observations',[row],[(proof,found)])
        row['payload']='{"x":true}';m,b=self.archive('observations',[row]);proof,found=recovery.verify_archive(m,b,{(1,)})
        row['payload']='{"x":1}'
        with self.assertRaises(recovery.RecoveryError):recovery.build_manifest('observations',[row],[(proof,found)])

    def test_size_checksum_count_boundaries_and_missing_coverage_fail_closed(self):
        row={'id':1,'market_id':'m','received_at':STAMP,'source_time':None,'kind':'book','payload':'{}'}
        m,b=self.archive('observations',[row])
        for change in ({'sha256':'0'*64},{'compressed_bytes':len(b)+1},{'event_count':2},{'last_source_id':2}):
            bad={**m,**change}
            with self.subTest(change=change),self.assertRaises(recovery.RecoveryError):recovery.verify_archive(bad,b,{(1,)})
        proof,found=recovery.verify_archive(m,b,set())
        with self.assertRaises(recovery.RecoveryError):recovery.build_manifest('observations',[row],[(proof,found)])

    def test_json_string_payload_is_compared_as_a_string(self):
        row={'id':1,'market_id':'m','received_at':STAMP,'source_time':None,'kind':'book','payload':'"{}"'}
        m,b=self.archive('observations',[row]);proof,found=recovery.verify_archive(m,b,{(1,)})
        saved=recovery.build_manifest('observations',[row],[(proof,found)])
        self.assertEqual(saved['records'][0]['payload'],'"{}"')


if __name__=='__main__':unittest.main()
