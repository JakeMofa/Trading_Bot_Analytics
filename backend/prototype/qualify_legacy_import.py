"""One full structured/fanout/capsule bootstrap, generated only, original host caps."""
import hashlib,json,os,resource,shutil,sqlite3,sys,tempfile,time
from contextlib import closing
from datetime import timedelta
from pathlib import Path
BOOT=float(os.environ.get('AB_PROFILE_STARTED',time.monotonic()))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_ab_application import T,iso
from application_store import ApplicationStore
from migration_budget import MigrationBudget
from bootstrap_fixture import populate,COUNTS,MISSING_META,MISSING_PRICES
from selected_recovery import verify,stage,file_binding,sha_file
from recovery_capsule import RecoveryCapsule,export_stream
from allocation_measurement import measure
from raw_generations import canonical,digest
import features

def digest_table(db,table):
    h=hashlib.sha256()
    for row in db.execute('SELECT * FROM "'+table+'" ORDER BY rowid'):
        b=canonical(tuple(row)).encode();h.update(len(b).to_bytes(8,'big'));h.update(b)
    return h.hexdigest()

def qualify():
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    root=Path(tempfile.mkdtemp(prefix='generated-ab-full-bootstrap-',dir=os.environ.get('AB_IMPORT_WORKSPACE')))
    result={'status':'FAIL','source_sha':os.environ.get('AB_IMPORT_SOURCE_SHA'),
            'scope':'full recorded structured counts and selected fanout; not full raw volume/production proof',
            'limits':{'workspace_bytes':2*1024**3,'audit_bytes':256*1024**2,'rows':250000,'work_seconds':170,'total_seconds':180,'linux_address_space_bytes':512*1024**2},'counts':COUNTS}
    owner=None;last=0.;progress_at=0.;code_bytes=int(os.environ.get('AB_IMPORT_SOURCE_BYTES','0'))
    def guard(force=False):
        nonlocal last,progress_at
        now=time.monotonic()
        if now>=BOOT+170:raise TimeoutError('original full bootstrap work deadline')
        if not force and now-last<.05:return
        last=now;allocation=measure(root,require_family=sys.platform=='linux');used=code_bytes+allocation['sampled_total_bytes']
        result['sampled_allocated_peak_bytes']=max(used,result.get('sampled_allocated_peak_bytes',0))
        result['unlinked_temp_peak_bytes']=max(allocation['unlinked_regular_bytes'],result.get('unlinked_temp_peak_bytes',0));result['allocation_scope']=allocation['owner_scope']
        if used>2*1024**3:raise RuntimeError('original whole-workspace allocation bound')
        if os.environ.get('AB_IMPORT_PROGRESS') and now-progress_at>=1:
            progress_at=now;Path(os.environ['AB_IMPORT_PROGRESS']).write_text(json.dumps({'phase':result.get('phase'),'elapsed_seconds':now-BOOT,'sampled_allocated_peak_bytes':result['sampled_allocated_peak_bytes']}))
    try:
        historical=root/'generated-legacy-historical.db';live=root/'generated-legacy-live.db'
        result['phase']='historical_fixture';populate(historical,False,guard)
        result['phase']='stopped_legacy_fixture';populate(live,True,guard);guard(True)
        with closing(sqlite3.connect(live)) as db:
            expected={table:digest_table(db,table) for table in COUNTS}
            mids=set(MISSING_META);pids=set(MISSING_PRICES);refs=[]
            for sid,version,market,at,ev,vs in db.execute('SELECT id,version,market_id,as_of,evidence_json,values_json FROM feature_snapshots'):
                guard();e=json.loads(ev);v=json.loads(vs);p=e['price']
                if e['metadata_observation_id'] in mids or str(p['input_id']) in pids:refs.append([sid,version,market,at,e['metadata_observation_id'],e['metadata_received_at'],v.get('target_usd'),str(p['input_id']),p['source_time'],v.get('reference_price_usd')])
            selected={r[0] for r in refs};preds=[list(r) for r in db.execute('SELECT id,snapshot_id,market_id FROM predictions') if r[1] in selected]
        deps={'format':'AB72_SELECTED_DEPENDENCIES_V1','legacy_binding':file_binding(live),'missing_observations':MISSING_META,'missing_stream_events':MISSING_PRICES,'snapshots':refs,'predictions':preds}
        depfile=root/'dependencies.json';depfile.write_text(canonical(deps));dsha=hashlib.sha256(depfile.read_bytes()).hexdigest()
        result['phase']='source_verification'
        verified=verify(historical,depfile,sha_file(historical,guard),dsha,BOOT+170,guard)
        selected_root=root/'generated-ab-recovery-selected';selected_root.mkdir(mode=0o700);stage(selected_root,verified,BOOT+170,guard=guard)
        mf=root/'selected-manifest.json';mf.write_text(canonical(verified[0]));msha=hashlib.sha256(mf.read_bytes()).hexdigest()
        stream=root/'selected.jsonl';h=hashlib.sha256()
        for (table,key),row in sorted(verified[1].items()):h.update((canonical(dict(dataset=table,key=key,row=row,sha256=digest(row)))+'\n').encode())
        streamsha=h.hexdigest();export_stream(selected_root/'staged-core.db',mf,msha,stream,streamsha,BOOT+170)
        # Discard the verifier's duplicate decoded bodies before opening the runtime.
        del verified
        capsule=RecoveryCapsule(mf,depfile,stream,manifest_sha256=msha,dependency_sha256=dsha,stream_sha256=streamsha,deadline=BOOT+170)
        result.update(preparation_seconds=time.monotonic()-BOOT,selected_rows=capsule.proof['selected_rows'],snapshot_dependencies=len(refs),prediction_dependencies=len(preds));guard(True)
        work=root/'generated-ab-core';work.mkdir(mode=0o700);budget=MigrationBudget(row_limit=250000,byte_limit=256*1024**2,deadline=BOOT+170)
        result['phase']='application_bootstrap';before=time.monotonic();owner=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=capsule,migration_budget=budget,measurement=guard)
        result['constructor_seconds']=time.monotonic()-before;result['import_metrics']=owner.import_metrics;result['logical_admission']=owner.core_logical_metrics;result['protocol_peak_bytes']=owner.protocol.peak;guard(True)
        result['phase']='exact_structured_readback';core=owner.protocol.core.native
        for table,count in COUNTS.items():
            guard()
            if core.execute('SELECT count(*) FROM '+table).fetchone()[0]!=count or digest_table(core,table)!=expected[table]:raise RuntimeError('exact structured identity/count: '+table)
        if core.execute('SELECT count(*) FROM ab_legacy_stream_pins').fetchone()[0]!=17925:raise RuntimeError('price reference coverage')
        if core.execute('SELECT count(*) FROM ab_legacy_pins').fetchone()[0]!=18276:raise RuntimeError('metadata/outcome coverage')
        result['phase']='historical_feature_readback'
        with closing(sqlite3.connect(historical.resolve().as_uri()+'?mode=ro',uri=True)) as source:
            source.row_factory=sqlite3.Row
            expected_feature=features.calculate(source,'m',T+timedelta(seconds=2))
        with closing(owner.worker_connection('history')) as reader:
            if features.calculate(reader,'m',T+timedelta(seconds=2))!=expected_feature:raise RuntimeError('historical feature/prediction input equivalence')
            if reader.execute('SELECT count(*) FROM predictions').fetchone()[0]!=27743:raise RuntimeError('real history path')
        owner.close();owner=None;guard(True)
        result['phase']='restart_audit';before=time.monotonic();owner=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=capsule,migration_budget=MigrationBudget(row_limit=250000,byte_limit=256*1024**2,deadline=BOOT+170),measurement=guard)
        result['restart_audit_seconds']=time.monotonic()-before;guard(True)
        with closing(owner.connection()) as db:
            eid=db.save_observation('m',iso(T+timedelta(seconds=3)),'book',{},iso(T))
            if eid<=218267:raise RuntimeError('sparse legacy/recovery ID collision')
        result['new_acknowledged_id']=eid
        owner.close();owner=None;before=time.monotonic()
        owner=ApplicationStore(work,live,routing=True,fresh_b=True,recovery=capsule,migration_budget=MigrationBudget(row_limit=250000,byte_limit=256*1024**2,deadline=BOOT+170),measurement=guard)
        result['after_ack_restart_seconds']=time.monotonic()-before
        if owner.protocol.core.execute("SELECT count(*) FROM events WHERE id=? AND status='committed'",(eid,)).fetchone()[0]!=1:raise RuntimeError('forward recovery lost new acknowledgement')
        result['legacy_unchanged']=file_binding(live)==deps['legacy_binding']
        if not result['legacy_unchanged']:raise RuntimeError('legacy changed')
        result['status']='PASS_GENERATED_FULL_BOOTSTRAP'
    except Exception as error:result.update(error_type=type(error).__name__,error=str(error))
    finally:
        if owner:owner.close()
        result['phase']='cleanup'
        result['elapsed_before_cleanup_seconds']=time.monotonic()-BOOT
        try:
            if sys.platform=='linux':
                from qualify_application import fixture_owners
                if fixture_owners(root):raise RuntimeError('full bootstrap fixture handles remain')
            shutil.rmtree(root)
        except Exception as error:result.update(status='FAIL',cleanup_error_type=type(error).__name__,cleanup_error=str(error),retained_generated_workspace=str(root))
        result['elapsed_including_cleanup_seconds']=time.monotonic()-BOOT
        result['rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        if result['elapsed_including_cleanup_seconds']>180:result['status']='FAIL'
    return result

if __name__=='__main__':
    r=qualify()
    if len(sys.argv)==3 and sys.argv[1]=='--report':
        with open(sys.argv[2],'x') as f:json.dump(r,f,sort_keys=True)
    print(json.dumps(r,sort_keys=True));raise SystemExit(0 if r['status']=='PASS_GENERATED_FULL_BOOTSTRAP' else 1)
