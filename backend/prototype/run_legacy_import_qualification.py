"""One supervised generated structured-count qualification, no production paths."""
import argparse
import json
import os
import shutil
from pathlib import Path
import tempfile
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_application_qualification import supervise


def main():
    started=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    args=parser.parse_args()
    report=Path(args.report)
    if (not report.name.startswith('ab-import-') or report.exists() or report.is_symlink()
        or Path('/opt/tradebot') in report.resolve().parents):
        raise ValueError('fresh generated import report required')
    workspace=Path(tempfile.mkdtemp(prefix='generated-ab-import-work-'))
    if shutil.disk_usage(workspace).free < 12*1024**3:
        workspace.rmdir()
        raise RuntimeError('2GiB workspace plus 10GiB free-space floor unavailable')
    if sys.platform=='linux':
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0])*1024 < 1152*1024**2:
            workspace.rmdir()
            raise RuntimeError('1.125GiB available RAM prerequisite')
    source=Path(__file__).resolve().parents[2]
    manifest=source/'AB_CANDIDATE_MANIFEST.json'
    source_bytes=0
    if manifest.exists():
        from build_ab_candidate import verify_export
        verified=verify_export(source,os.environ.get('AB_IMPORT_SOURCE_SHA'),repo=os.environ.get('AB_SOURCE_REPOSITORY'))
        source_bytes=64*1024+manifest.stat().st_blocks*512+sum((source/p).stat().st_blocks*512 for p in verified['files'])
    os.environ.update(AB_PROFILE_STARTED=str(started),AB_IMPORT_WORKSPACE=str(workspace),
                      AB_IMPORT_SOURCE_BYTES=str(source_bytes),AB_IMPORT_PROGRESS=str(report.with_suffix('.progress.json')))
    command=[sys.executable,str(Path(__file__).with_name('qualify_legacy_import.py')),'--report',str(report)]
    code=supervise(command,report,seconds=180)
    progress=report.with_suffix('.progress.json')
    if code and progress.exists():
        try:
            value=json.loads(report.read_text());value['last_progress']=json.loads(progress.read_text());report.write_text(json.dumps(value))
        except (ValueError,OSError):pass
    if not any(workspace.iterdir()):workspace.rmdir()
    else:
        # A killed/reaped run is a failure, not successful cleanup. Keep bounded
        # generated evidence rather than extending the original deadline.
        print(json.dumps({'retained_generated_workspace':str(workspace)}),flush=True)
    return code

if __name__=='__main__':raise SystemExit(main())
