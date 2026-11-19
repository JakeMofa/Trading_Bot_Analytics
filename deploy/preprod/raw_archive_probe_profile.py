"""Exact default-OFF Compose profile for one PP sealed-generation archive cycle."""
from __future__ import annotations

from copy import deepcopy

from controller import require
from linux_actions import PROJECT, validate_config
from live_profile import validate_live_profile
from structured_probe_profile import LOCAL_STAGED, OFF


CLOUD_FILES = {
    'pp_history_dsn': '/etc/tradebot/cloud/pp_history_dsn',
    'pp_history_ca': '/etc/tradebot/cloud/pp_history_ca',
    'pp_storage_api_key': '/etc/tradebot/cloud/pp_storage_api_key',
    'supabase_auth_email': '/etc/tradebot/cloud/supabase_auth_email',
    'supabase_auth_password': '/etc/tradebot/cloud/supabase_auth_password',
    'supabase_auth_uid': '/etc/tradebot/cloud/supabase_auth_uid',
}
EGRESS = 'raw_archive_probe_egress'


def validate_raw_archive_profile(base: dict, live: dict, probe: dict, source, image):
    validate_config(base, source, image)
    validate_live_profile(base, live, source, image)
    require(set(probe.get('networks', {})) == set(live['networks']) | {EGRESS},
            'unexpected_raw_archive_network')
    network = probe['networks'][EGRESS]
    require(network == {'name': PROJECT + '_' + EGRESS,
                        'driver': 'bridge', 'ipam': {}},
            'unsafe_raw_archive_egress')
    require(set(probe.get('secrets', {})) == set(live['secrets']) | set(CLOUD_FILES) | {'probe_local_dsn'},
            'unexpected_raw_archive_secret')
    for name, path in CLOUD_FILES.items():
        require(probe['secrets'][name] == {'name': PROJECT + '_' + name,
                                         'file': path}, 'unsafe_raw_archive_secret_path')
    require(probe['secrets']['probe_local_dsn'] ==
            {'name': PROJECT + '_probe_local_dsn', 'file': LOCAL_STAGED},
            'unsafe_raw_archive_local_secret_path')

    expected = deepcopy(live)
    expected['networks'][EGRESS] = deepcopy(network)
    for name in (*CLOUD_FILES, 'probe_local_dsn'):
        expected['secrets'][name] = deepcopy(probe['secrets'][name])
    service = deepcopy(base['services']['lifecycle'])
    # Generated-only local storage is absent (default OFF) in cloud probes.
    service['environment'].pop('TRADEBOT_GENERATED_LOCAL_STORAGE',None)
    service['command'] = ['python', '-m', 'postgres.pp_raw_archive_probe']
    service['user'] = '0:0'
    service['restart'] = 'no'
    service['profiles'] = ['raw_archive_probe']
    service['environment'].update(
        TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID='pp-live-pp',
        TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT='true',
        TRADEBOT_PP_HISTORY_DSN_FILE='/run/secrets/pp_history_dsn',
        TRADEBOT_PP_HISTORY_CA_FILE='/run/secrets/pp_history_ca',
        TRADEBOT_PP_STORAGE_API_KEY_FILE='/run/secrets/pp_storage_api_key',
        TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE='/run/secrets/supabase_auth_email',
        TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE='/run/secrets/supabase_auth_password',
        TRADEBOT_PP_STORAGE_AUTH_UID_FILE='/run/secrets/supabase_auth_uid', **OFF)
    service['secrets'] = [
        {'source': 'probe_local_dsn', 'target': '/run/secrets/lifecycle_dsn'},
        *({'source': name, 'target': '/run/secrets/' + name}
          for name in CLOUD_FILES),
    ]
    service['networks'][EGRESS] = None
    expected['services']['raw_archive_probe'] = service
    require(probe == expected, 'unreviewed_raw_archive_profile_difference')
    return probe


def validate_recurring_profile(validated_probe, actual):
    """Reuse the checked raw worker boundary, subtract both history credentials."""
    expected = deepcopy(validated_probe)
    service = expected['services'].pop('raw_archive_probe')
    for name in ('pp_history_dsn', 'pp_history_ca'):
        del expected['secrets'][name]
        service['secrets'] = [item for item in service['secrets'] if item['source'] != name]
    for key in ('TRADEBOT_PP_HISTORY_CA_FILE', 'TRADEBOT_PP_HISTORY_DSN_FILE',
                'TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT'):
        del service['environment'][key]
    service['environment']['TRADEBOT_PP_SEALED_ARCHIVE'] = 'true'
    service['command'] = ['python', '-m', 'postgres.pp_sealed_archive', '--execute']
    service['profiles'] = ['sealed_archive']
    expected['services']['sealed_archive'] = service
    require(actual == expected, 'unreviewed_recurring_archive_profile_difference')
