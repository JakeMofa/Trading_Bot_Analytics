"""Build the reviewed SQLite timestamp validator; never run at app startup.

Use CI's Linux artifact for the existing VM: no compiler/install on production.
The extension calls SQLite through its ABI table, without linking a second SQLite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def build(output):
    source=Path(__file__).parent/'native/retention_time.c'
    compiler=shutil.which('cc')
    if not compiler:raise RuntimeError('C compiler required on build host only')
    if output.name!='_retention_time.so' or output.exists() or output.with_suffix('.json').exists():
        raise ValueError('output must be a new _retention_time.so with a new manifest')
    output.parent.mkdir(parents=True,exist_ok=True)
    flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared']
    if sys.platform=='darwin':
        includes=next((p for p in (Path('/opt/homebrew/opt/sqlite/include'),Path('/usr/local/opt/sqlite/include')) if (p/'sqlite3ext.h').is_file()),None)
        if includes is None:raise RuntimeError('extension-capable SQLite headers required on macOS build host')
        flags+=['-I'+str(includes)]
    subprocess.run([compiler,*flags,str(source),'-o',str(output)],check=True,timeout=30)
    output.chmod(0o644)
    proof={'format':1,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
           'binary_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    manifest=output.with_suffix('.json');manifest.write_text(json.dumps(proof,sort_keys=True)+'\n');manifest.chmod(0o644)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.output)))
