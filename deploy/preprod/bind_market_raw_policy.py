"""Render a reviewed PP Storage policy; never connect to or modify Supabase.

The rendered SQL is a one-use migration candidate. The operator must separately
verify the selected project and current bucket/policy state before applying it.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import uuid


PROJECT_REF = 'xttdqeimdujweijxcuro'
BUCKET = 'market-raw'
TEMPLATE = Path(__file__).resolve().parents[2] / 'supabase/review/pp_market_raw_storage_policies.sql.in'
TEMPLATE_SHA256 = '5abe6f03ee330e1f9e9f35488f5f1c21d02d0874296b1d6128f039a1c248337e'
READBACK_PATCH = Path(__file__).resolve().parents[2] / 'supabase/review/pp_market_raw_readback_legacy_patch.sql.in'
READBACK_PATCH_SHA256 = 'fcad352555f110a4c0adeca6f77a99fda310f7216c28743dc904491fb0be7002'
UID_MARKER = '__PP_STORAGE_AUTH_UID__'
EMAIL_MARKER = '__PP_STORAGE_AUTH_EMAIL__'
POLICY_HASH_MARKER = '__EXPECTED_POLICY_SHA256__'
EMAIL = re.compile(r'[a-z0-9._+\-]+@[a-z0-9.\-]+\Z')


def render(uid: str, email: str, *, project_ref: str, bucket: str,
           template: bytes | None = None) -> bytes:
    if project_ref != PROJECT_REF or bucket != BUCKET:
        raise ValueError('unreviewed Supabase project or bucket')
    try:
        parsed = uuid.UUID(uid)
    except (ValueError, AttributeError, TypeError):
        raise ValueError('canonical reviewed Auth UID required') from None
    if str(parsed) != uid or parsed.version != 4:
        raise ValueError('canonical reviewed Auth UID required')
    if not isinstance(email, str) or len(email) > 254 or not EMAIL.fullmatch(email):
        raise ValueError('reviewed machine email required')
    source = TEMPLATE.read_bytes() if template is None else template
    if hashlib.sha256(source).hexdigest() != TEMPLATE_SHA256:
        raise ValueError('reviewed policy template changed')
    text = source.decode('ascii')
    if text.count(UID_MARKER) != 4 or text.count(EMAIL_MARKER) != 1:
        raise ValueError('reviewed policy bindings changed')
    result = text.replace(UID_MARKER, uid).replace(EMAIL_MARKER, email)
    if '__PP_STORAGE_' in result:
        raise ValueError('unbound policy marker remains')
    return result.encode('ascii')


def render_rollback(uid: str, email: str, *, project_ref: str, bucket: str) -> bytes:
    """Fail closed unless the two reviewed policies still bind the same UID.

    This revokes only policy grants. It never deletes a Storage object or an
    Auth user, and it requires a separately reviewed migration application.
    """
    render(uid, email, project_ref=project_ref, bucket=bucket)
    return f"""-- REVIEWED POLICY-ONLY ROLLBACK. Objects and Auth user remain.
BEGIN;
DO $preflight$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM storage.buckets
                 WHERE id='market-raw' AND public=false) THEN
    RAISE EXCEPTION 'private market-raw bucket binding changed';
  END IF;
  IF (SELECT count(*) FROM pg_policies
      WHERE schemaname='storage' AND tablename='objects') <> 2 OR
     NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage'
                 AND tablename='objects' AND policyname='tradebot_pp_raw_upload'
                 AND cmd='INSERT' AND roles::text[]=ARRAY['authenticated']::text[]
                 AND with_check LIKE '%{uid}%'
                 AND with_check LIKE '%storage.object.upload%') OR
     NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage'
                 AND tablename='objects' AND policyname='tradebot_pp_raw_readback'
                 AND cmd='SELECT' AND roles::text[]=ARRAY['authenticated']::text[]
                 AND qual LIKE '%{uid}%'
                 AND qual LIKE '%storage.object.get_authenticated%') THEN
    RAISE EXCEPTION 'reviewed PP Storage policy set changed; manual review required';
  END IF;
END $preflight$;
DROP POLICY tradebot_pp_raw_upload ON storage.objects;
DROP POLICY tradebot_pp_raw_readback ON storage.objects;
COMMIT;
""".encode('ascii')


def render_readback_patch(uid: str, email: str, *, project_ref: str, bucket: str,
                          expected_policy_sha256: str,
                          template: bytes | None = None) -> bytes:
    """Render one reviewed, catalog-hash-bound readback-only amendment."""
    render(uid, email, project_ref=project_ref, bucket=bucket)
    if (not isinstance(expected_policy_sha256, str) or
            not re.fullmatch(r'[0-9a-f]{64}', expected_policy_sha256) or
            expected_policy_sha256 == '0' * 64):
        raise ValueError('fresh reviewed policy catalog SHA-256 required')
    source = READBACK_PATCH.read_bytes() if template is None else template
    if hashlib.sha256(source).hexdigest() != READBACK_PATCH_SHA256:
        raise ValueError('reviewed readback patch template changed')
    text = source.decode('ascii')
    if (text.count(UID_MARKER) != 6 or text.count(EMAIL_MARKER) != 1 or
            text.count(POLICY_HASH_MARKER) != 2):
        raise ValueError('readback patch bindings changed')
    result = (text.replace(UID_MARKER, uid).replace(EMAIL_MARKER, email)
              .replace(POLICY_HASH_MARKER, expected_policy_sha256))
    if '__PP_STORAGE_' in result or POLICY_HASH_MARKER in result:
        raise ValueError('unbound policy marker remains')
    return result.encode('ascii')


def write_new(path: Path, sql: bytes) -> str:
    """Create a private, non-overwriting candidate file and return its digest."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(sql)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(sql).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--project-ref', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('apply', 'rollback', 'readback-patch'),
                        default='apply')
    parser.add_argument('--expected-policy-sha256')
    args = parser.parse_args()
    if args.mode == 'readback-patch':
        sql = render_readback_patch(
            args.uid, args.email, project_ref=args.project_ref, bucket=args.bucket,
            expected_policy_sha256=args.expected_policy_sha256)
    else:
        if args.expected_policy_sha256 is not None:
            parser.error('--expected-policy-sha256 is only for readback-patch')
        renderer = render if args.mode == 'apply' else render_rollback
        sql = renderer(args.uid, args.email, project_ref=args.project_ref,
                       bucket=args.bucket)
    digest = write_new(args.output, sql)
    print(f'policy candidate rendered; SHA-256 {digest}; no Supabase changes')


if __name__ == '__main__':
    main()
