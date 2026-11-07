"""Real ApplicationStore bootstrap from independent generated history + capsule."""
from contextlib import closing
import hashlib,json,sqlite3,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import ApplicationStore,legacy,T,iso,timedelta,Stop
import test_selected_recovery as selected_tests
from selected_recovery import verify,stage,file_binding
from recovery_capsule import RecoveryCapsule,export_stream
from raw_generations import canonical,digest
from migration_budget import MigrationBudget
import features

class Tests(unittest.TestCase):
    def test_capsule_tampering_and_expired_deadline_hold_before_activation(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);_,cap,_,stream,_=self.fixture(root)
            args=dict(manifest_sha256=cap.proof['manifest_file_sha256'],dependency_sha256=cap.proof['dependency_sha256'],stream_sha256=cap.proof['stream_sha256'])
            with self.assertRaises(TimeoutError):RecoveryCapsule(root/'manifest.json',root/'dependencies.json',stream,deadline=time.monotonic()-1,**args)
            with stream.open('ab') as f:f.write(b'{}\n')
            with self.assertRaises((Stop,KeyError)):RecoveryCapsule(root/'manifest.json',root/'dependencies.json',stream,deadline=time.monotonic()+15,**args)

    def fixture(self,root,live_name='generated-legacy-live.db',deadline=None,metadata_id=41):
        historical,deps=selected_tests.Tests().fixture(root)
        live=root/live_name;expected=legacy(live)
        if metadata_id!=41:
            for path in (historical,live):
                with closing(sqlite3.connect(path)) as db,db:
                    db.execute('UPDATE observations SET id=? WHERE id=41',(metadata_id,))
                    e=json.loads(db.execute('SELECT evidence_json FROM feature_snapshots').fetchone()[0]);e['metadata_observation_id']=metadata_id
                    db.execute('UPDATE feature_snapshots SET evidence_json=?',(json.dumps(e),))
            expected[2]['metadata_observation_id']=metadata_id
        with closing(sqlite3.connect(live)) as db,db:
            db.execute('DELETE FROM observations WHERE id=?',(metadata_id,));db.execute('DELETE FROM stream_events')
        d=json.loads(deps.read_text());d['missing_observations']=[metadata_id];d['snapshots'][0][4]=metadata_id;d['legacy_binding']=file_binding(live);deps.write_text(json.dumps(d))
        deadline=deadline or time.monotonic()+15;v=verify(historical,deps,hashlib.sha256(historical.read_bytes()).hexdigest(),hashlib.sha256(deps.read_bytes()).hexdigest(),deadline)
        target=root/'generated-ab-recovery-selected';target.mkdir(mode=0o700);stage(target,v,deadline)
        manifest=root/'manifest.json';manifest.write_text(json.dumps(v[0]));msha=hashlib.sha256(manifest.read_bytes()).hexdigest()
        lines=[(canonical(dict(dataset=t,key=k,row=r,sha256=digest(r)))+'\n').encode() for (t,k),r in sorted(v[1].items())]
        streamsha=hashlib.sha256(b''.join(lines)).hexdigest();stream=root/'selected.jsonl'
        export_stream(target/'staged-core.db',manifest,msha,stream,streamsha,deadline)
        self.assertFalse(export_stream(target/'staged-core.db',manifest,msha,stream,streamsha,deadline)['changed'])
        cap=RecoveryCapsule(manifest,deps,stream,manifest_sha256=msha,dependency_sha256=hashlib.sha256(deps.read_bytes()).hexdigest(),stream_sha256=streamsha,deadline=deadline)
        return live,cap,expected,stream,deadline
    def test_actual_bootstrap_features_history_new_ack_and_restart(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,expected,stream,deadline=self.fixture(root)
            before=hashlib.sha256(live.read_bytes()).hexdigest();work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap,migration_budget=MigrationBudget(deadline=deadline))
            with closing(store.connection()) as db:
                self.assertEqual(features.calculate(db,'m',T+timedelta(seconds=1)),expected)
                self.assertEqual(db.execute('SELECT id,snapshot_id FROM predictions').fetchone(),(1,1))
                db.save_stream_event(dict(source='coinbase',event_id='new',received_at=iso(T+timedelta(seconds=2)),source_time=iso(T+timedelta(seconds=2)),price='12342.000000000001',size='1',side='buy',payload='{}'))
                self.assertEqual(features.calculate(db,'m',T+timedelta(seconds=3))[0]['reference_price_usd'],'12342.000000000001')
            with closing(store.worker_connection('history')) as db:
                self.assertEqual(db.execute("SELECT price FROM stream_events WHERE source='coinbase' AND event_id='7'").fetchone()[0],'12341.000000000000001')
            store.close()
            with self.assertRaisesRegex(Stop,'proof binding'):ApplicationStore(work,live,routing=True,fresh_b=True)
            reopened=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap,migration_budget=MigrationBudget(deadline=time.monotonic()+15))
            self.assertEqual(reopened.protocol.core.execute("SELECT count(*) FROM events WHERE status='committed'").fetchone()[0],1);reopened.close()
            self.assertEqual(hashlib.sha256(live.read_bytes()).hexdigest(),before)
    def test_recovered_price_corruption_fails_read_and_startup(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
            with store.protocol.core:
                row=json.loads(store.protocol.core.native.execute('SELECT record FROM ab_legacy_stream_pins').fetchone()[0]);row['price']='9'
                store.protocol.core.native.execute('UPDATE ab_legacy_stream_pins SET record=?',(canonical(row),))
            with closing(store.connection()) as db:
                with self.assertRaises(sqlite3.OperationalError):db.execute("SELECT price FROM stream_events WHERE event_id='7'").fetchall()
            store.close()
            with self.assertRaisesRegex(ValueError,'protected legacy price'):ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
    def test_incomplete_bootstrap_rolls_back_proof_and_retries_exactly(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            def fail(point):
                if point=='migration_before_commit':raise RuntimeError('generated cutover interruption')
            with self.assertRaisesRegex(RuntimeError,'interruption'):ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap,fault=fail)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap);store.close()

    def test_v2_writer_cannot_modify_new_recovery_core(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap);store.close()
            with closing(sqlite3.connect(work/'core.db')) as db:
                db.create_function('ab72_writer_enabled',0,lambda:1);db.create_function('ab72_layout_version',0,lambda:2)
                with self.assertRaises(sqlite3.DatabaseError):db.execute("UPDATE predictions SET model_version='old-writer'")

    def test_actual_runtime_loads_explicit_proof_and_preserves_default_hold(self):
        from storage_runtime import configured_runtime
        from test_ab_runtime import environment
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,stream,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            env=environment(work);env.update(SQLITE_DB_PATH=str(live),AB_STARTUP_MODE='fresh-b',
                AB_RECOVERY_MANIFEST=str(root/'manifest.json'),AB_RECOVERY_DEPENDENCIES=str(root/'dependencies.json'),AB_RECOVERY_STREAM=str(stream),
                AB_RECOVERY_MANIFEST_SHA256=cap.proof['manifest_file_sha256'],AB_RECOVERY_DEPENDENCY_SHA256=cap.proof['dependency_sha256'],AB_RECOVERY_STREAM_SHA256=cap.proof['stream_sha256'])
            runtime=configured_runtime(env)
            try:
                runtime.open('collector')
                with closing(runtime.connection()) as db:self.assertEqual(db.execute('SELECT id FROM observations WHERE id=41').fetchone()[0],41)
            finally:runtime.close()
            del env['AB_RECOVERY_STREAM_SHA256']
            with self.assertRaisesRegex(RuntimeError,'complete explicit'):configured_runtime(env)
    def test_recovered_sparse_id_is_reserved_and_capsule_drift_holds(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root,metadata_id=1000);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
            with closing(store.connection()) as db:eid=db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{},iso(T))
            self.assertGreater(eid,1000);store.close()
            with closing(sqlite3.connect(live)) as db,db:db.execute("UPDATE markets SET target='0'")
            with self.assertRaisesRegex(Stop,'legacy binding changed'):ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
    def test_recovered_metadata_late_corruption_blocks_read(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
            try:
                with store.protocol.core:store.protocol.core.native.execute("UPDATE observations SET payload='{}' WHERE id=41")
                with closing(store.connection()) as db:
                    with self.assertRaises(sqlite3.OperationalError):db.execute('SELECT payload FROM observations WHERE id=41').fetchall()
            finally:store.close()

    def test_logical_admission_prevents_restart_budget_overflow(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as folder:
            root=Path(folder);live,cap,_,_,_=self.fixture(root);work=root/'generated-ab-core';work.mkdir(mode=0o700)
            store=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=cap)
            try:
                core=store.protocol.core.native
                initial=tuple(core.execute('SELECT row_count,logical_bytes FROM ab_core_audit_budget').fetchone())
                with core:core.execute('UPDATE ab_core_audit_budget SET row_limit=row_count+1')
                with closing(store.connection()) as db:
                    args=(iso(T),iso(T),'coinbase','1.0000000001','{}')
                    with db:db.execute('INSERT INTO reference_prices(received_at,source_time,source,price,payload) VALUES(?,?,?,?,?)',args)
                    self.assertEqual(core.execute('SELECT row_count FROM ab_core_audit_budget').fetchone()[0],initial[0]+1)
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'logical admission'):
                        with db:db.execute('INSERT INTO reference_prices(received_at,source_time,source,price,payload) VALUES(?,?,?,?,?)',args)
                    self.assertEqual(core.execute('SELECT count(*) FROM reference_prices').fetchone()[0],1)
            finally:store.close()
