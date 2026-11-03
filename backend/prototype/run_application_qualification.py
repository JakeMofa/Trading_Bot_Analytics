"""Hard180s process-family envelope for one generated ApplicationStore trial."""
import argparse,json,os,signal,subprocess,sys,time,math
from pathlib import Path

def supervise(command,report,seconds=180):
    started=float(os.environ.get('AB_PROFILE_STARTED',time.monotonic()));env=dict(os.environ,AB_PROFILE_STARTED=str(started))
    remaining=started+seconds-time.monotonic()
    if not math.isfinite(started) or remaining<=0 or started>time.monotonic():
        Path(report).write_text(json.dumps({'status':'FAIL','error':'original budget expired before launch'}));return 1
    child=subprocess.Popen(command,env=env,start_new_session=True)
    try:
        code=child.wait(timeout=max(0,started+seconds-time.monotonic()))
        if not Path(report).exists():
            Path(report).write_text(json.dumps({'status':'FAIL','error':'qualification exited without report','exit_code':code}))
        return code
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL);child.wait()
        Path(report).write_text(json.dumps({'status':'FAIL','error':'absolute whole-operation deadline','elapsed_seconds':time.monotonic()-started}))
        return 1
    except BaseException:
        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL)
        child.wait();raise
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sha',required=True);parser.add_argument('--workspace',required=True);parser.add_argument('--report',required=True)
    a=parser.parse_args()
    from qualify_application import validate_workspace
    validate_workspace(a.workspace,a.report)
    command=[sys.executable,str(Path(__file__).with_name('qualify_application.py')),'--sha',a.sha,'--workspace',a.workspace,'--report',a.report]
    raise SystemExit(supervise(command,a.report))
