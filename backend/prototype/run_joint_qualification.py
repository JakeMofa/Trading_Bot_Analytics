"""Whole-family180s envelope for the generated joint HTTP/SSE/reuse suite."""
import argparse,json,os,sys,tempfile,time
from pathlib import Path
from run_application_qualification import supervise

if __name__=='__main__':
    started=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',required=True)
    args=parser.parse_args();report=Path(args.report)
    if report.exists() or report.is_symlink() or not report.name.startswith('ab-joint-'):
        raise ValueError('fresh joint report required')
    workspace=Path(tempfile.mkdtemp(prefix='ab-joint-work-'))
    os.environ.update(AB_PROFILE_STARTED=str(started),AB_JOINT_WORKSPACE=str(workspace),AB_JOINT_REPORT_PATH=str(report))
    command=[sys.executable,'-m','unittest','discover','-s','backend/tests','-p','test_ab_complete_handoff.py','-v']
    code=supervise(command,report,180)
    value=json.loads(report.read_text())
    if not any(workspace.iterdir()):workspace.rmdir()
    else:value['retained_generated_workspace']=str(workspace);code=1
    value['whole_suite_elapsed_seconds']=time.monotonic()-started
    value['root_suite_exit_code']=code
    manifest=Path(__file__).resolve().parents[2]/'AB_CANDIDATE_MANIFEST.json'
    if manifest.exists():value['source_sha']=json.loads(manifest.read_text())['source_sha']
    if code or value['whole_suite_elapsed_seconds']>180:value['status']='FAIL';code=1
    report.write_text(json.dumps(value,sort_keys=True)+'\n')
    raise SystemExit(code)
