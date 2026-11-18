"""Fail-closed PP-only Compose profile for one supervised structured-history call.

The normal deployment profile remains unchanged. This profile never authorizes
continuous cloud sync, raw retirement, or a persistent root lifecycle service.
"""
from __future__ import annotations

from copy import deepcopy

from controller import require
from linux_actions import PROJECT, validate_config
from live_profile import validate_live_profile

CLOUD_FILES = {
    'pp_history_dsn': '/etc/tradebot/cloud/pp_history_dsn',
    'pp_history_ca': '/etc/tradebot/cloud/pp_history_ca',
}
EGRESS = 'structured_probe_egress'
OFF = {
    'TRADEBOT_COLLECTOR_ENABLED': 'false',
    'TRADEBOT_CLOUD_ENABLED': 'false',
    'TRADEBOT_RETIREMENT_ENABLED': 'false',
    'ENABLE_SUPABASE_SYNC': 'false',
    'ENABLE_LOCAL_RETENTION': 'false',
    'ENABLE_OPENAI_ANALYST': 'false',
}


def validate_probe_profile(base: dict, live: dict, probe: dict, source, image):
    """Compare every normalized field; allow only the reviewed one-shot service."""
    validate_config(base, source, image)
    validate_live_profile(base, live, source, image)
    require(set(probe.get('networks', {})) == set(live['networks']) | {EGRESS},
            'unexpected_probe_network')
    network = probe['networks'][EGRESS]
    require(network == {'name': PROJECT + '_' + EGRESS,
                        'driver': 'bridge', 'ipam': {}},
            'unsafe_probe_egress')
    require(set(probe.get('secrets', {})) == set(live['secrets']) | set(CLOUD_FILES),
            'unexpected_probe_secret')
    for name, path in CLOUD_FILES.items():
        require(probe['secrets'][name] == {'name': PROJECT + '_' + name,
                                         'file': path}, 'unsafe_probe_secret_path')

    expected = deepcopy(live)
    expected['networks'][EGRESS] = deepcopy(network)
    for name in CLOUD_FILES:
        expected['secrets'][name] = deepcopy(probe['secrets'][name])
    service = deepcopy(base['services']['lifecycle'])
    service['command'] = ['python', '-m', 'postgres.pp_structured_probe']
    service['user'] = '0:0'
    service['restart'] = 'no'
    service['profiles'] = ['structured_probe']
    service['environment'].update(
        TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID='pp-live-pp',
        TRADEBOT_PP_HISTORY_DSN_FILE='/run/secrets/pp_history_dsn',
        TRADEBOT_PP_HISTORY_CA_FILE='/run/secrets/pp_history_ca',
        TRADEBOT_PP_STRUCTURED_ONE_SHOT='true', **OFF)
    service['secrets'].extend([
        {'source': name, 'target': '/run/secrets/' + name}
        for name in CLOUD_FILES
    ])
    service['networks'][EGRESS] = None
    expected['services']['structured_probe'] = service
    require(probe == expected, 'unreviewed_probe_profile_difference')
    return probe
