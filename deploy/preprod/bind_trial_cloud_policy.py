"""Render review-only trial Storage policy from exact public identity bindings.

No network, secret input, cloud call or migration application. Outputs create-only.
"""
import argparse
from pathlib import Path
import re
import uuid

TEMPLATE = Path(__file__).resolve().parents[2]/'supabase/review/pp_trial_20261119_01_storage.sql.in'


def render(*, writer_uid, writer_email, reader_uid, reader_email, policy_sha256):
    if (str(uuid.UUID(writer_uid)) != writer_uid or str(uuid.UUID(reader_uid)) != reader_uid
            or writer_uid == reader_uid or not re.fullmatch('[0-9a-f]{64}', policy_sha256)):
        raise ValueError('exact distinct reviewed UIDs/catalog hash required')
    for email in (writer_email, reader_email):
        if not re.fullmatch(r'[A-Za-z0-9._+@-]{3,254}', email) or email.count('@') != 1:
            raise ValueError('reviewed Auth emails required')
    if writer_email == reader_email: raise ValueError('separate machine identities required')
    values = dict(TRIAL_WRITER_UID=writer_uid,TRIAL_READER_UID=reader_uid,
        TRIAL_WRITER_EMAIL=writer_email,TRIAL_READER_EMAIL=reader_email,STORAGE_POLICY_SHA256=policy_sha256)
    source = TEMPLATE.read_text()
    for key, value in values.items(): source = source.replace('__'+key+'__',value)
    if re.search(r'__[A-Z_]+__',source): raise ValueError('unbound template marker')
    return source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('writer-uid','writer-email','reader-uid','reader-email','policy-sha256'):
        parser.add_argument('--'+arg,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); values=vars(args); path=values.pop('output')
    source=render(**values)
    with path.open('x') as output: output.write(source)


if __name__=='__main__': main()
