"""Generated actual-schema/count/fanout fixture from bounded read-only size evidence.

No database copies, network calls or real source bodies. Historical and stopped
legacy fixtures are generated independently. Mean sizes plus3% and one observed
maximum per table model recorded shape; not full raw-volume or venue proof.
"""
import json,math,sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from raw_generations import canonical

COUNTS={'markets':1826,'candles':58812,'reference_prices':18692,'runs':49260,'feed_health':4,
        'feature_snapshots':18289,'predictions':27743,'historical_market_prices':12694,
        'historical_backfill_chunks':90,'news_events':28,'schema_migrations':1,
        'prediction_context_links':20,'news':0,'current_decisions':832,'ai_suggestions':1277,
        'cloud_sync_state':7,'cloud_lifecycle_state':1}
SIZE={'markets':(8062485,4999),'candles':(7470082,130),'reference_prices':(6168101,333),
      'runs':(5825208,1398),'feature_snapshots':(45250265,2526),'predictions':(15952800,679),
      'historical_market_prices':(899188,71),'historical_backfill_chunks':(103898,1427),
      'news_events':(11682,474),'current_decisions':(184461,273),'ai_suggestions':(217660,239)}
META=[41]+[200000+i for i in range(1,18268)]
PRICES=['7']+['legacy-'+str(i) for i in range(1,17924)]
MISSING_META=META[:6755];MISSING_PRICES=PRICES[:6493]

def populate(path,missing,guard):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
    from test_ab_application import legacy,T,iso
    import historical,history_batch,news,run_ensemble_agent,cloud_memory,cloud_lifecycle
    legacy(path)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        historical.initialize(db);history_batch.initialize_batch(db);news.initialize(db);run_ensemble_agent.ensure_ai_schema(db);cloud_lifecycle.initialize_lifecycle_state(db)
        db.execute('CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY,source TEXT,headline TEXT,link TEXT,publication_time TEXT,first_seen_time TEXT,delay_seconds REAL,freshness_category TEXT)')
        def cols(table):return tuple(x[1] for x in db.execute('PRAGMA table_info('+table+')'))
        def insert(table,row):db.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        def pad(table,row,field,i):
            if table not in SIZE:return row
            total,maximum=SIZE[table];goal=maximum if i==1 else min(maximum,math.ceil(total/COUNTS[table]*1.03))
            extra=goal-len(canonical(tuple(row.values())).encode())
            if extra>0:row[field]+=' '*extra
            return row
        market_ids=['m']+['fixture-market-'+str(i) for i in range(1,1826)]
        source_market=dict(db.execute('SELECT * FROM markets WHERE id=\'m\'').fetchone())
        seed_obs=dict(db.execute('SELECT * FROM observations WHERE id=41').fetchone());seed_tick=dict(db.execute('SELECT * FROM stream_events').fetchone())
        seed_snap=dict(db.execute('SELECT * FROM feature_snapshots').fetchone());seed_pred=dict(db.execute('SELECT * FROM predictions').fetchone());seed_link=dict(db.execute('SELECT * FROM prediction_context_links').fetchone())
        with db:
            for i in range(1,len(market_ids)):
                row={**source_market,'id':market_ids[i],'slug':market_ids[i]};insert('markets',pad('markets',row,'raw_json',i))
            if missing:
                db.execute('DELETE FROM observations WHERE id=41');db.execute('DELETE FROM stream_events')
            for i,key in enumerate(META):
                if i==0 and not missing:continue
                if missing and i<6755:continue
                row={**seed_obs,'id':key,'market_id':market_ids[i%len(market_ids)],'received_at':iso(T+timedelta(microseconds=i))}
                row['payload']+=' '*max(0,4140-len(canonical(tuple(row.values())).encode()));insert('observations',row)
                if i%1000==0:guard()
            for i,key in enumerate(PRICES):
                if i==0 and not missing:continue
                if missing and i<6493:continue
                row={**seed_tick,'event_id':key,'received_at':iso(T+timedelta(microseconds=i)),'source_time':iso(T+timedelta(microseconds=i))}
                row['payload']+=' '*max(0,640-len(canonical(tuple(row.values())).encode()));insert('stream_events',row)
                if i%1000==0:guard()
            insert('stream_events',{**seed_tick,'event_id':'current-only','received_at':iso(T+timedelta(seconds=1)),'source_time':iso(T+timedelta(seconds=1))})
            snapshots={}
            for sid in range(1,18290):
                idx=(sid-1)%len(META);pi=min(idx,len(PRICES)-1);asof=T+timedelta(microseconds=sid)
                evidence=json.loads(seed_snap['evidence_json']);values=json.loads(seed_snap['values_json']);quality=json.loads(seed_snap['quality_json'])
                evidence['metadata_observation_id']=META[idx];evidence['metadata_received_at']=iso(T+timedelta(microseconds=idx))
                evidence['price']['input_id']=PRICES[pi];evidence['price']['source_time']=iso(T+timedelta(microseconds=pi))
                quality['price']=dict(evidence['price']);quality['price']['age_seconds']=(asof-(T+timedelta(microseconds=pi))).total_seconds()
                values['seconds_remaining']=(T+timedelta(minutes=15)-asof).total_seconds()
                row={**seed_snap,'id':sid,'market_id':market_ids[idx%len(market_ids)],'as_of':iso(asof),'values_json':json.dumps(values),'quality_json':json.dumps(quality),'evidence_json':json.dumps(evidence)}
                pad('feature_snapshots',row,'quality_json',sid);snapshots[sid]=(row['market_id'],row['as_of'])
                if sid==1:db.execute('UPDATE feature_snapshots SET market_id=?,as_of=?,values_json=?,quality_json=?,evidence_json=? WHERE id=1',tuple(row[k] for k in ('market_id','as_of','values_json','quality_json','evidence_json')))
                else:insert('feature_snapshots',row)
                if sid%1000==0:guard()
            selected_ids=[i for i in snapshots if (i-1)%18268<6755];selected_set=set(selected_ids);unselected=[i for i in snapshots if i not in selected_set]
            plan=[(i,0) for i in selected_ids[:6745]]+[(i,0) for i in unselected]+[(i,1) for i in unselected[:9485]]
            if len(plan)!=27743:raise ValueError('generated prediction cardinality')
            for pid,(sid,model) in enumerate(plan,1):
                market,at=snapshots[sid];row={**seed_pred,'id':pid,'snapshot_id':sid,'market_id':market,'as_of':at,'model_version':'generated-'+str(model)}
                pad('predictions',row,'assumptions_json',pid)
                if pid==1:db.execute('UPDATE predictions SET model_version=?,as_of=?,assumptions_json=? WHERE id=1',(row['model_version'],at,row['assumptions_json']))
                else:insert('predictions',row)
                if pid%1000==0:guard()
            for table,n in (('candles',58812),('reference_prices',18692)):
                current=db.execute('SELECT count(*) FROM '+table).fetchone()[0];earliest=db.execute('SELECT min(time) FROM candles').fetchone()[0]
                for i in range(1,n-current+1):
                    if table=='candles':
                        row=dict(zip(cols(table),('coinbase','BTC-USD',60,earliest-i*60,'12340.00','12340.00','12340.00','12340.00','1.00000001',iso(T))))
                        extra=math.ceil(SIZE[table][0]/n*1.03)-len(canonical(tuple(row.values())).encode())
                        if extra>0:row['volume']+='0'*extra
                    else:row={'received_at':iso(T+timedelta(microseconds=i)),'source_time':iso(T),'source':'coinbase','price':'12341.000000000000001','payload':'{}'};row=pad(table,row,'payload',i)
                    insert(table,row)
                    if i%1000==0:guard()
            for i in range(1,49261):
                row={'id':i,'received_at':iso(T),'source':'generated_fixture','success':0,'detail':'synthetic log; no operation performed'};insert('runs',pad('runs',row,'detail',i))
                if i%1000==0:guard()
            for i in range(12694):
                row={'market_id':market_ids[i%len(market_ids)],'source_time':int(T.timestamp())+i//len(market_ids),'long_price':'0.55','short_price':'0.45','retrieved_at':iso(T+timedelta(seconds=10))};insert('historical_market_prices',row)
            for i in range(90):
                row={'window_start':iso(T-timedelta(hours=8*(i+1))),'window_end':iso(T-timedelta(hours=8*i)),'attempted_at':iso(T),'result_json':'{"generated_only":true}'};insert('historical_backfill_chunks',pad('historical_backfill_chunks',row,'result_json',i+1))
            for i in range(1,29):
                row=dict(zip(cols('news_events'),(i,'generated_only',str(i),'https://fixture.invalid/'+str(i),'Generated Bitcoin '+str(i),iso(T),iso(T),iso(T),'[]','BTC')));insert('news_events',pad('news_events',row,'categories_json',i))
            for i in range(91,98):insert('observations',{'id':i,'market_id':'m','received_at':iso(T),'source_time':iso(T),'kind':'resolution','payload':'{}'})
            for i in range(2,21):insert('prediction_context_links',{**seed_link,'id':i,'prediction_id':i,'outcome_observation_id':90+(i-1)%8})
            for i in range(832):
                row={k:None for k in cols('current_decisions')};row.update(market_id=market_ids[i],snapshot_id=i+1,decision_action='HOLD',decision_summary='generated archived state',updated_at=iso(T));insert('current_decisions',pad('current_decisions',row,'decision_summary',i+1))
            for i in range(1277):
                row={k:None for k in cols('ai_suggestions')};row.update(id=i+1,snapshot_id=i+1,market_id=market_ids[i%len(market_ids)],ai_action='HOLD',ai_explanation='generated archived state; no AI call',created_at=iso(T));insert('ai_suggestions',pad('ai_suggestions',row,'ai_explanation',i+1))
            feed_cols=cols('feed_health')
            for i in range(4):
                row={k:None for k in feed_cols};row[feed_cols[0]]='generated-'+str(i)
                if 'status' in row:row['status']='unavailable'
                if 'updated_at' in row:row['updated_at']=iso(T)
                # Use declared nonnull defaults for counters,never a healthy receipt.
                for col in db.execute('PRAGMA table_info(feed_health)'):
                    if col[3] and row[col[1]] is None:row[col[1]]=0 if col[2]=='INTEGER' else 'unavailable'
                insert('feed_health',row)
            for name in ('markets','feature_snapshots','predictions','candles','reference_prices','news_events'):
                cloud_memory._save_checkpoint(db,name,status='pending',rows_added=0)
        if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('generated source foreign keys')
        actual={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in COUNTS}
        if actual!=COUNTS:raise ValueError('generated structured counts differ: '+repr(actual))
        return {'source_counts':actual,'missing':missing,'selected_metadata':len(META),'selected_stream':len(PRICES)}
