"""Offline point-in-time parity, including actual generated archive retirement."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveLimits, encoded, sha256, wire
from postgres.history import ArchiveHistory
from postgres.history_v2_envelope import CLOUD_COLUMNS, TABLE_KEYS
from postgres.contract import content_hash
from postgres.lifecycle import ArchiveWorker
from postgres.research_window import ResearchWindow
from postgres_lifecycle_fixtures import MemoryRepository, ImmutableMemoryTransport

ORIGIN = 'generated-lifecycle-unit'
START='2026-11-12T00:00:00+00:00'
END='2026-11-12T00:15:00+00:00'
CUTOFF='2026-11-12T00:05:00+00:00'
LABEL='2026-11-12T00:20:00+00:00'


def fixture():
    repo=MemoryRepository(); generation=repo.generation_id
    repo.rows=wire(repo.rows)
    for i,row in enumerate(repo.rows):
        row.update(source='polymarket_us',market_id='market',kind='quote',
                   source_time=f'2026-11-12T00:00:0{i}+00:00',
                   source_epoch=str(1794441600+i),price=None,
                   payload={'bid':'0.49000000000000000001','ask':None,'book':[]})
    repo.rows[0]['kind']='market'
    repo.rows[0]['payload']={'target':'100000.00000001','missing':None}
    repo.rows[3]['available_at']='2026-11-12T00:06:00+00:00' # delayed delivery
    repo.rows[4].update(kind='outcome',payload={'result':'UP'}) # never a predictor input
    repo.record['state']='collecting'
    records=[]
    def add(table,**values):
        payload={k:None for k in CLOUD_COLUMNS[table]}
        payload.update(origin_id=ORIGIN,content_hash='a'*64,**values)
        if table=='core.snapshot_evidence':
            payload['content_hash']=content_hash({k:payload[k] for k in CLOUD_COLUMNS[table]})
        row=dict(id=len(records)+1,origin_id=ORIGIN,generation_id=generation,entity_type=table,
                 entity_id=encoded([payload[k] for k in TABLE_KEYS[table]]).decode(),
                 content_hash=payload['content_hash'],payload=payload)
        records.append(row)
    for sid,available in [('s1',CUTOFF),('s2','2026-11-12T00:06:00+00:00')]:
        calculation={'market':{'target_usd':'100000.00000001','first_seen':START},'candle_inputs':[],'price':None}
        add('core.protected_evidence',evidence_id='e'+sid,generation_id=generation,source='calculation_inputs',
            event_id=sid,kind='feature_inputs',market_id='market',source_time=CUTOFF,
            source_epoch='1794441900',received_at=available,available_at=available,payload=calculation)
        add('core.feature_snapshots',snapshot_id=sid,market_id='market',as_of=CUTOFF,version=1 if sid=='s1' else 2,
            values_json={'target_usd':'100000.00000001','missing':None},quality_json={'late_join':True},
            evidence_json=calculation)
        add('core.snapshot_evidence',snapshot_id=sid,evidence_id='e'+sid)
        add('core.predictions',prediction_id='p'+sid,snapshot_id=sid,market_id='market',
            model_version='fixture',as_of=CUTOFF,created_at=available,seconds_remaining='600',
            probability_up='0.50000000000000000001',probability_down='0.49999999999999999999',
            assumptions_json={},payload={})
    add('core.protected_evidence',evidence_id='official',generation_id=generation,source='polymarket_us',
        event_id='o1',kind='outcome',market_id='market',source_time=LABEL,
        source_epoch='1794442800',received_at=LABEL,available_at=LABEL,payload={'data':{'result':'UP','final':'100001.00000001'},
            'provenance':{'data_mode':'generated'},'normalized':{'price':None,'size':None,'symbol':None}})
    add('core.outcomes',outcome_id='o1',market_id='market',evidence_id='official',result='UP',
        final='100001.00000001',source_time=LABEL,source_epoch='1794442800',confirmed_at=LABEL,
        available_at=LABEL,payload={'data':{'result':'UP','final':'100001.00000001'},
            'provenance':{'data_mode':'generated'}})
    source=Mock(origin_id=ORIGIN,generation_id=generation)
    source.read_revisions.side_effect=lambda ids,**kw:deepcopy([r for r in records if r['id'] in ids])
    transport=ImmutableMemoryTransport()
    reader=ResearchWindow(ArchiveHistory(repo,transport),source,origin_id=ORIGIN,generation_id=generation)
    return repo,transport,source,records,reader


def manifest(records):
    return [dict(id=r['id'],envelope_sha256=sha256(encoded(r))) for r in records]


def read(reader,records,**kwargs):
    options=dict(market_id='market',start=START,end=END,as_of=CUTOFF,labels_as_of=LABEL)
    options.update(kwargs)
    return reader.read(manifest(records),**options)


class ResearchWindowTests(unittest.TestCase):
    def test_exact_application_payloads_before_seal_and_after_retirement(self):
        repo,transport,source,records,reader=fixture()
        active=read(reader,records)
        repo.record['state']='sealed'
        sealed=read(reader,records)
        worker=ArchiveWorker(repo,transport,ArchiveLimits(max_rows=500))
        self.assertEqual(worker.archive_cycle(repo.generation_id)['status'],'archived')
        worker.retire_generated(repo.generation_id,qualification_enabled=True)
        self.assertEqual(repo.rows,[])
        retired=read(reader,records)
        for key in ('scope','inputs','saved_features','saved_forecasts','official_outcome_labels','links','coverage'):
            self.assertEqual(encoded(active[key]),encoded(sealed[key]))
            self.assertEqual(encoded(active[key]),encoded(retired[key]))
        self.assertEqual([r['event_id'] for r in retired['inputs']],['event-0000','event-0001','event-0002'])
        self.assertEqual([r['snapshot_id'] for r in retired['saved_features']],['s1'])
        self.assertEqual([r['prediction_id'] for r in retired['saved_forecasts']],['ps1'])
        self.assertEqual(retired['saved_features'][0]['values_json']['target_usd'],'100000.00000001')
        self.assertEqual(retired['official_outcome_labels'][0]['outcome_id'],'o1')
        self.assertEqual(retired['provenance']['raw_pages'][0]['tier'],'authenticated_archive')
        self.assertEqual(len(read(reader,records,labels_as_of=CUTOFF)['official_outcome_labels']),0)

    def test_no_invented_publication_time_or_broken_forecast_link(self):
        for mutate in (lambda rs:rs[0]['payload'].update(kind='other'),
                       lambda rs:rs[3]['payload'].update(snapshot_id='missing'),
                       lambda rs:rs[0]['payload'].update(payload={'changed':True}),
                       lambda rs:rs[2]['payload'].update(evidence_id='missing')):
            repo,transport,source,records,reader=fixture();mutate(records)
            with self.assertRaises(ArchiveIntegrityError):read(reader,records)

    def test_duplicate_foreign_missing_and_corrupt_rows_fail(self):
        for change in ('duplicate','foreign','missing','corrupt'):
            repo,transport,source,records,reader=fixture()
            if change=='duplicate':repo.rows.append(deepcopy(repo.rows[0]))
            if change=='foreign':repo.rows[0]['origin_id']='other'
            if change=='missing':source.read_revisions.side_effect=lambda *a,**kw:[]
            if change=='corrupt':
                source.read_revisions.side_effect=lambda *a,**kw: [dict(r,payload={}) for r in records]
            with self.assertRaises(ArchiveIntegrityError):read(reader,records)

    def test_future_forecast_and_labels_remain_separate_from_available_features(self):
        repo,transport,source,records,reader=fixture()
        records[3]['payload']['created_at']='2026-11-12T00:06:00+00:00'
        page=read(reader,records)
        self.assertEqual([r['snapshot_id'] for r in page['saved_features']],['s1'])
        self.assertEqual(page['saved_forecasts'],[])
        self.assertEqual(len(page['official_outcome_labels']),1)
        records[-2]['payload']['payload']['data']['result']='DOWN'
        with self.assertRaises(ArchiveIntegrityError):read(reader,records)

    def test_future_saved_calculation_inputs_never_look_available(self):
        for data in ({'market':{'first_seen':LABEL}},
                     {'price':{'source_time':LABEL}},
                     {'candle_inputs':[{'start':CUTOFF,'received_at':CUTOFF}]}):
            repo,transport,source,records,reader=fixture()
            records[0]['payload']['payload'].update(data)
            records[1]['payload']['evidence_json'].update(data)
            with self.assertRaises(ArchiveIntegrityError):read(reader,records)

    def test_outcome_requires_matching_ingestion_wrapper_and_identity(self):
        for mutate in (
                lambda proof, outcome: proof.update(payload={'result':'UP'}),
                lambda proof, outcome: proof['payload'].update(provenance=None),
                lambda proof, outcome: outcome['payload'].update(provenance={'data_mode':'other'}),
                lambda proof, outcome: outcome.update(final='100001.00000002'),
                lambda proof, outcome: proof.update(event_id='different-event')):
            repo,transport,source,records,reader=fixture()
            mutate(records[-2]['payload'],records[-1]['payload'])
            with self.assertRaises(ArchiveIntegrityError):read(reader,records)

    def test_limits_cutoff_and_deadline(self):
        repo,transport,source,records,reader=fixture()
        for kwargs in (dict(end=LABEL),dict(as_of=LABEL),dict(labels_as_of=START),dict(start=START[:-6])):
            with self.assertRaises((ArchiveLimit,ArchiveIntegrityError)):read(reader,records,**kwargs)
        reader.clock=Mock(side_effect=[0,20])
        with self.assertRaises(ArchiveLimit):read(reader,records)


import os
@unittest.skipUnless(os.environ.get('TRADEBOT_TEST_RESEARCH_DSN'), 'isolated generated PG DSN required')
class ResearchWindowPostgresTests(unittest.TestCase):
    def test_real_partition_drop_keeps_exact_research_payloads(self):
        import uuid
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from unittest.mock import patch
        from postgres.lifecycle import LifecycleRepository, RotationPolicy
        from postgres.history_v2_transport import HistoryV2PostgresTransport
        from datetime import datetime, timedelta, timezone
        dsn=os.environ['TRADEBOT_TEST_RESEARCH_DSN']
        # Environment variable is supplied only for a disposable Unix-socket DB.
        self.assertIn('host=/',dsn)
        def local():return psycopg.connect(dsn,row_factory=dict_row)
        with local() as db:
            identity=db.execute('SELECT current_database() db,current_user role').fetchone()
            self.assertEqual(identity['db'],'tradebot_pp')
        memory,objects,_,records,_=fixture()
        records = records[:-2]  # Outcome evidence below must come from actual ingestion.
        repo=LifecycleRepository(local)
        origin='generated-research-'+uuid.uuid4().hex
        initial=datetime(2026,11,12,tzinfo=timezone.utc)
        generation=str(repo.bootstrap(origin,now=initial)['generation_id'])
        with local() as db:
            db.execute("""INSERT INTO core.markets(origin_id,market_id,source,slug,duration,
                start_time,end_time,start_epoch,end_epoch,status,first_seen,last_seen,payload,content_hash)
                VALUES(%s,'market','polymarket_us',%s,900,%s,%s,1794441600,1794442500,
                'fixture',%s,%s,'{}',%s)""",(origin,origin,START,END,START,START,'a'*64))
            db.execute('INSERT INTO history_v2.markets SELECT * FROM core.markets WHERE origin_id=%s',(origin,))
            for row in memory.rows:
                row.update(origin_id=origin,generation_id=generation)
                columns=list(row)
                db.execute('INSERT INTO raw.events('+','.join(columns)+') VALUES('+','.join(['%s']*len(columns))+')',
                    [Jsonb(row[k]) if k=='payload' else row[k] for k in columns])
            for row in records:
                row.update(origin_id=origin,generation_id=generation)
                row['payload']['origin_id']=origin
                if row['entity_type']=='core.protected_evidence':row['payload']['generation_id']=generation
                if row['entity_type']=='core.snapshot_evidence':
                    row['content_hash']=row['payload']['content_hash']=content_hash({k:row['payload'][k] for k in CLOUD_COLUMNS[row['entity_type']]})
                row['entity_id']=encoded([row['payload'][k] for k in TABLE_KEYS[row['entity_type']]]).decode()
                row['id']=db.execute('''INSERT INTO ops.outbox(origin_id,generation_id,entity_type,
                    entity_id,content_hash,payload,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                    (origin,generation,row['entity_type'],row['entity_id'],row['content_hash'],Jsonb(row['payload']),CUTOFF)).fetchone()['id']
        from postgres.config import Settings
        from postgres.store import Store
        store = Store(Settings(origin_id=origin, dsn=dsn))
        received = '2026-11-12T00:19:00+00:00'
        provenance = {'data_mode':'generated','generator':'research_outcome_test',
                      'settlement_source':'synthetic_only'}
        store.ingest(dict(source='polymarket_us',event_id='ingested-outcome',kind='outcome',
            market_id='market',source_time=END,received_at=received,available_at=LABEL,
            payload={'result':'UP','final':'1.0000100000000000000000001E5'},
            provenance=provenance,raw_payload={'fixture':'captured official-shaped response'}))
        records = ArchiveWorker.structured_records(repo.outbox(generation, limit=50))
        self.assertEqual(len([r for r in records if r['entity_type']=='core.outcomes']), 1)
        with patch('postgres.history_v2_transport.PP_STRUCTURED_ORIGIN',origin):
            cloud=HistoryV2PostgresTransport(lambda **kw:local(),origin_id=origin,generation_id=generation,
                expected_database=identity['db'],expected_role=identity['role'],retain_revisions=True)
        # Native local history_v2 is the independently read-back structured tier.
        cloud.put_structured(records,timeout_seconds=4)
        class Revisions:
            origin_id=origin
            generation_id=generation
            def read_revisions(self,ids,**kwargs):
                selected=[r for r in records if r['id'] in ids]
                return cloud.read_structured_authenticated(selected,**kwargs)
        source=Revisions()
        reader=ResearchWindow(ArchiveHistory(repo,objects),source,origin_id=origin,generation_id=generation)
        active=read(reader,records)
        self.assertEqual(len(active['official_outcome_labels']),1)
        label=active['official_outcome_labels'][0]
        self.assertEqual(label['final'],'100001.00000000000000000001')
        self.assertEqual(label['payload']['data']['final'],'1.0000100000000000000000001E5')
        self.assertEqual(label['payload']['provenance'],provenance)
        self.assertEqual(read(reader,records,labels_as_of='2026-11-12T00:19:59.999999+00:00')['official_outcome_labels'],[])
        self.assertFalse(any(r['kind']=='outcome' for r in active['inputs']))
        switched=repo.switch_if_due(origin,RotationPolicy(qualified_size_bytes=1),now=initial+timedelta(hours=1))
        self.assertEqual(switched['status'],'switched')
        sealed=read(reader,records)
        objects.put_structured=cloud.put_structured
        objects.read_structured_authenticated=cloud.read_structured_authenticated
        worker=ArchiveWorker(repo,objects,ArchiveLimits(max_rows=500))
        self.assertEqual(worker.archive_cycle(generation)['status'],'archived')
        worker.retire_generated(generation,qualification_enabled=True)
        with local() as db:
            name='raw.events_g_'+generation.replace('-','')
            self.assertIsNone(db.execute('SELECT to_regclass(%s) relation',(name,)).fetchone()['relation'])
        retired=read(reader,records)
        for key in ('scope','inputs','saved_features','saved_forecasts','official_outcome_labels','links','coverage'):
            self.assertEqual(encoded(active[key]),encoded(sealed[key]))
            self.assertEqual(encoded(active[key]),encoded(retired[key]))
        self.assertEqual(retired['provenance']['raw_pages'][0]['tier'],'authenticated_archive')
        self.assertEqual(read(reader,records,labels_as_of='2026-11-12T00:19:59.999999+00:00')['official_outcome_labels'],[])
