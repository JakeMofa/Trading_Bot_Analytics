import sys,tempfile,unittest,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from raw_generations import Store,iso,COLUMNS
from feature_inputs import project,cycle
import features
T=datetime(2026,1,1,tzinfo=timezone.utc)

class Tests(unittest.TestCase):
    def test_existing_feature_engine_matches_flat_history_and_pins_evidence(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            s=Store(f);market={'id':'m','duration':900,'start':iso(T+timedelta(hours=71,minutes=59)),'end':iso(T+timedelta(hours=72,minutes=14)),'first_seen':iso(T)};s.set_market(market)
            row={'market_id':'m','received_at':iso(T),'source_time':iso(T),'kind':'metadata','payload':'{"assetPriceTerms":{"priceToBeat":{"value":"12340.00000001"}}}'}
            metadata=s.save('observations','metadata',row)
            for i,(receipt,source,price) in enumerate([(T+timedelta(hours=71,minutes=59),T+timedelta(hours=71,minutes=59),'12341.000000000000001'),(T+timedelta(hours=72,seconds=1),T+timedelta(hours=72,seconds=1),'12342.000000000000001'),(T+timedelta(hours=72,seconds=2),T+timedelta(hours=75),'999999')]):
                s.save('stream_events','coinbase:'+str(i),{'source':'coinbase','event_id':str(i),'received_at':iso(receipt),'source_time':iso(source),'price':price,'size':'1','side':'buy','payload':'{"venue":"coinbase"}'})
            asof=T+timedelta(hours=72,seconds=3)
            with s.core:
                wanted=int(asof.timestamp())//60*60-60
                for k in range(17):
                    price=str(12300+(k%3)*10);time=wanted-k*60
                    s.core.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',('coinbase','BTC-USD',60,time,price,price,price,price,'1',iso(datetime.fromtimestamp(time+60,timezone.utc))))
            db,refs,_=project(s,'m',asof);projected=features.calculate(db,'m',asof)
            # Generated flat reference contains all rows, including future-source
            # data; real version2 SQL must produce identical values/quality/IDs.
            db.execute('PRAGMA query_only=OFF');db.execute('DELETE FROM stream_events');db.execute('DELETE FROM observations')
            for dataset in COLUMNS:
                rows=s.history(dataset,T,asof)
                db.executemany('INSERT INTO '+dataset+' VALUES('+','.join('?' for _ in COLUMNS[dataset])+')',[tuple(r[c] for c in COLUMNS[dataset]) for r in rows])
            db.commit();reference=features.calculate(db,'m',asof);db.close()
            self.assertEqual(projected,reference);self.assertEqual(projected[2]['price']['input_id'],'1')
            with ThreadPoolExecutor(max_workers=1) as worker:r=worker.submit(cycle,s,'m',asof).result()
            self.assertIsNotNone(r['prediction']);self.assertIsNone(r['abstain_reason']);self.assertEqual(r['result'],reference)
            self.assertEqual(r['generation_refs']['metadata']['id'],metadata)
            self.assertEqual(s.core.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],1)
            self.assertEqual(s.core.execute('SELECT COUNT(*) FROM predictions').fetchone()[0],1)
            self.assertEqual(s.core.execute('PRAGMA foreign_key_check').fetchall(),[])
            # Metadata auto-pinning and selected price evidence both durable.
            self.assertEqual(s.core.execute('SELECT COUNT(*) FROM required_evidence').fetchone()[0],2)
            s.close();s=Store(f)
            self.assertEqual(s.core.execute('SELECT COUNT(*) FROM prediction_details').fetchone()[0],1);s.close()
