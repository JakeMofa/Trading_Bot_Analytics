import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from recovery_release_evidence import attestation
from raw_generations import digest
class Tests(unittest.TestCase):
    def test_allowlist_preserves_checksums_and_strips_sensitive_fields(self):
        m={k:'a'*64 for k in ('source_sha256','source_schema_sha256','dependency_sha256')}
        m.update(format='AB72_SELECTED_RECOVERY_V1',source_integrity='ok',source_fk_violations=0,observations=1,stream_events=0,supporting_markets=1,snapshot_dependencies=1,prediction_dependencies=1,selected_serialized_bytes=42,
                 records=[{'dataset':'observations','key':'private-id','sha256':'b'*64}],source_path='/Users/private/source.db',source_binding={'main':[1,2,3]},unknown='SECRET')
        m['selection_sha256']=digest(m['records']);m['manifest_sha256']=digest(m)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'manifest.json';p.write_text(json.dumps(m));sha=hashlib.sha256(p.read_bytes()).hexdigest()
            q={'status':'PASS_ISOLATED_SELECTED_RECOVERY','manifest_file_sha256':sha,'manifest_sha256':m['manifest_sha256'],'production_authorized':False,'conflicts':0,'unverifiable_rows':0,'first_stage':{'synchronous':2},'retry_stage':{'changed_rows':0},'observations':1,'stream_events':0,'elapsed_seconds':1,'aggregate_peak_bytes':100,'rss_bytes':100,'linux_memory_limit_applied':False,'unknown':'SECRET'}
            proof=Path(root)/'proof.json';proof.write_text(json.dumps(q));qsha=hashlib.sha256(proof.read_bytes()).hexdigest();out=attestation(p,sha,proof,qsha)
            for secret in ('SECRET','/Users/private','private-id','source_binding'):self.assertNotIn(secret,json.dumps(out))
            self.assertEqual(out['exact_private_manifest_file_sha256'],sha);self.assertFalse(out['production_authorized'])
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):attestation(p,'0'*64,proof,qsha)

            q['retry_stage']['changed_rows']=1;proof.write_text(json.dumps(q))
            with self.assertRaisesRegex(ValueError,'stage verification'):attestation(p,sha,proof,hashlib.sha256(proof.read_bytes()).hexdigest())
