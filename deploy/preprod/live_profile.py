"""Fail-closed comparison of a PP live trial with the qualified OFF profile.

The regular CD controller deliberately rejects this overlay. A separately
reviewed, bounded host action must validate both normalized Compose profiles
before changing any running service. Equality includes every other setting,
including disabled paid-AI/cloud/retirement flags and database isolation.
"""
from __future__ import annotations

from copy import deepcopy

from linux_actions import validate_config, HISTORY_READER_FILES, RUNTIME_SECRETS, cycle_environment, live_origin
from controller import require


LIVE_ORIGIN = 'pp-live-pp'


def validate_live_profile(base: dict, live: dict, source, image, *, reader=False, initial_a=None, trial_origin=None, trial_reader=False):
    validate_config(base, source, image)
    origin=live_origin(trial_origin)
    require(not (trial_origin and reader),'trial_reader_requires_independent_profile')
    require(not trial_reader or (trial_origin is not None and not reader),'trial_reader_requires_exact_scope')
    expected = deepcopy(base)
    for name in ('api', 'calculation', 'lifecycle'):
        expected['services'][name]['environment'].update(
            TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID=origin)
    expected['services']['lifecycle']['environment'].update(
        TRADEBOT_PP_LIVE_LIFECYCLE='true', TRADEBOT_PP_WINDOW_POLICY='two-official-markets',
        TRADEBOT_GENERATED_LOCAL_STORAGE='false')
    operator = expected['services']['operator']
    operator['environment'].update(TRADEBOT_PP_LIVE_CONTROL='true',
                                   TRADEBOT_APP_DSN_FILE='/run/secrets/app_dsn')
    if trial_origin:
        operator['environment']['TRADEBOT_ORIGIN_ID']=origin
    for service in ('lifecycle', 'operator'):
        expected['services'][service]['environment'].update(cycle_environment(initial_a,trial_origin))
    target = operator['secrets'][0]['target']
    require(target in ('lifecycle_dsn', '/run/secrets/lifecycle_dsn'),
            'unreviewed_pp_operator_secret_shape')
    operator['secrets'].append({'source': 'app_dsn',
                                'target': '/run/secrets/app_dsn' if target.startswith('/') else 'app_dsn'})
    if reader:
        api = expected['services']['api']
        api['environment']['TRADEBOT_PP_ARCHIVE_HISTORY'] = 'true'
        for name in HISTORY_READER_FILES:
            expected['secrets'][name] = {'name': expected['name']+'_'+name, 'file':str(RUNTIME_SECRETS/name)}
            api['secrets'].append({'source':name, 'target':('/run/secrets/' if target.startswith('/') else '')+name})
    if trial_reader:
        from trial_history_reader import TRIAL_HISTORY_READER_FILES
        api=expected['services']['api']
        api['environment']['TRADEBOT_PP_ARCHIVE_HISTORY']='true'
        for name in TRIAL_HISTORY_READER_FILES:
            expected['secrets'][name]={'name':expected['name']+'_'+name,'file':str(RUNTIME_SECRETS/name)}
            api['secrets'].append({'source':name,'target':('/run/secrets/' if target.startswith('/') else '')+name})
    require(live == expected, 'unreviewed_pp_live_profile_difference')
    return live
