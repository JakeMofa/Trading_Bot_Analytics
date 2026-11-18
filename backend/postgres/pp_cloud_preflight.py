"""Read-only PP cloud binding preflight; never starts a sync worker.

The Storage Auth files are produced by the separate operator provisioner.
The structured PostgreSQL credential is a different identity and remains
unusable while tradebot_pp_history is NOLOGIN. This module reads no file data,
opens no network connection, and intentionally has no enable path.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat


EXPECTED_FILES = {
    'storage_api_key': '/run/secrets/pp_storage_api_key',
    'storage_auth_email': '/run/secrets/supabase_auth_email',
    'storage_auth_password': '/run/secrets/supabase_auth_password',
    'storage_auth_uid': '/run/secrets/supabase_auth_uid',
    'structured_dsn': '/run/secrets/pp_history_dsn',
    'local_lifecycle_dsn': '/run/secrets/lifecycle_dsn',
}
FILE_ENV = {
    'storage_api_key': 'TRADEBOT_PP_STORAGE_API_KEY_FILE',
    'storage_auth_email': 'TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE',
    'storage_auth_password': 'TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE',
    'storage_auth_uid': 'TRADEBOT_PP_STORAGE_AUTH_UID_FILE',
    'structured_dsn': 'TRADEBOT_PP_HISTORY_DSN_FILE',
    'local_lifecycle_dsn': 'TRADEBOT_DATABASE_DSN_FILE',
}
OFF_FLAGS = ('ENABLE_SUPABASE_SYNC', 'ENABLE_LOCAL_RETENTION',
             'ENABLE_OPENAI_ANALYST', 'TRADEBOT_CLOUD_ENABLED',
             'TRADEBOT_RETIREMENT_ENABLED')
HOLDS = ('structured_role_login_unqualified',
         'structured_receipts_grants_unqualified',
         'cloud_worker_not_wired', 'retirement_off')


@dataclass(frozen=True)
class PPCloudBinding:
    files: dict[str, Path]

    @classmethod
    def from_environment(cls, environ: dict[str, str]) -> 'PPCloudBinding':
        if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or
                environ.get('TRADEBOT_DATA_MODE') != 'pp_live' or
                environ.get('TRADEBOT_ORIGIN_ID') != 'pp-live-pp'):
            raise ValueError('exact PP live identity required')
        if any(environ.get(flag, 'false').lower() not in ('false', '0', 'off')
               for flag in OFF_FLAGS):
            raise ValueError('cloud, retirement and paid AI must remain OFF')
        files = {}
        for purpose, expected in EXPECTED_FILES.items():
            if environ.get(FILE_ENV[purpose]) != expected:
                raise ValueError('exact and independent PP secret paths required')
            files[purpose] = Path(expected)
        return cls(files)

    def check_file_metadata(self) -> None:
        """Check mounted-file safety without reading credentials or identifiers."""
        identities = set()
        for path in self.files.values():
            try:
                info = path.lstat()
            except OSError:
                raise ValueError('PP binding file unavailable') from None
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    info.st_uid not in (0, os.geteuid()) or
                    info.st_mode & 0o077 or not 1 <= info.st_size <= 4096):
                raise ValueError('unsafe PP binding file')
            identity = (info.st_dev, info.st_ino)
            if identity in identities:
                raise ValueError('PP binding files must be independent')
            identities.add(identity)


def main() -> int:
    try:
        binding = PPCloudBinding.from_environment(os.environ)
        binding.check_file_metadata()
    except ValueError:
        print(json.dumps({'status': 'STOP', 'reason': 'pp_cloud_binding_invalid'}))
        return 1
    print(json.dumps({'status': 'STOP', 'environment': 'preprod',
                      'origin_id': 'pp-live-pp', 'files_private': True,
                      'holds': HOLDS}))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
