"""Build a deterministic, standard-library-only archive probe zipapp."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZipInfo

BACKEND = Path(__file__).resolve().parent
FILES = {
    '__main__.py': 'prototype/archive_probe/__main__.py',
    **{name+'.py': 'app/'+name+'.py' for name in
       ('retention_recovery', 'retention', 'retention_timestamp_guards')},
}


def build(output):
    with ZipFile(output, 'x') as bundle:
        for name, source in FILES.items():
            bundle.writestr(ZipInfo(name), (BACKEND/source).read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
