"""Fail-closed comparison of a PP live trial with the qualified OFF profile.

The regular CD controller deliberately rejects this overlay. A separately
reviewed, bounded host action must validate both normalized Compose profiles
before changing any running service. Equality includes every other setting,
including disabled paid-AI/cloud/retirement flags and database isolation.
"""
from __future__ import annotations

from copy import deepcopy

from linux_actions import (BOUNDARY_ORIGINS, DISPLAY_ORIGIN, DISPLAY_DIR, DISPLAY_KEYS, PREDICTION_READER_FILES, HISTORY_READER_FILES, RUNTIME_SECRETS, TRIAL_ORIGIN,
                           cycle_environment, live_origin, validate_config)
from controller import require


LIVE_ORIGIN = 'pp-live-pp'


def validate_live_profile(base: dict, live: dict, source, image, *, reader=False, initial_a=None, trial_origin=None, trial_reader=False):
    validate_config(base, source, image)
    origin=live_origin(trial_origin)
    require(not (trial_origin and reader),'trial_reader_requires_independent_profile')
    require(not trial_reader or (trial_origin not in (None,*BOUNDARY_ORIGINS) and not reader),'trial_reader_requires_exact_scope')
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
        if trial_origin==TRIAL_ORIGIN:
            operator['environment']['TRADEBOT_PP_COINBASE_TIMING']='true'
        if trial_origin in BOUNDARY_ORIGINS:
            operator['environment']['TRADEBOT_PP_BOUNDARY_TRACE']='1'
    for service in ('lifecycle', 'operator'):
        expected['services'][service]['environment'].update(cycle_environment(initial_a,trial_origin))
    target = operator['secrets'][0]['target']
    require(target in ('lifecycle_dsn', '/run/secrets/lifecycle_dsn'),
            'unreviewed_pp_operator_secret_shape')
    operator['secrets'].append({'source': 'app_dsn',
                                'target': '/run/secrets/app_dsn' if target.startswith('/') else 'app_dsn'})
    if trial_origin==DISPLAY_ORIGIN:
        for name in ('api','operator'):
            service=expected['services'][name]
            service['environment'].update(TRADEBOT_PP_QUOTE_DISPLAY='1',TRADEBOT_PP_BOUNDARY_TRACE='1')
            mount={'type':'bind','source':str(DISPLAY_DIR),'target':'/run/quote-display','bind':{}}
            actual_mounts=live['services'][name].get('volumes',[])
            if actual_mounts and actual_mounts[0].get('bind')=={'create_host_path':False}:
                mount['bind']={'create_host_path':False}
            if name=='operator':
                mount['read_only']=True
            service['volumes']=[mount]
        api=expected['services']['api']
        api['environment']['TRADEBOT_PP_PREDICTION_HISTORY']='true'
        for name,path in PREDICTION_READER_FILES.items():
            expected['secrets'][name]={'name':expected['name']+'_'+name,'file':str(path)}
            api['secrets'].append({'source':name,'target':('/run/secrets/' if target.startswith('/') else '')+name})
        operator['environment'].update(TRADEBOT_PP_ROBINHOOD_REFERENCE='1',
                                       ROBINHOOD_API_KEY_FILE='/run/secrets/robinhood_key_id',
                                       ROBINHOOD_PRIVATE_KEY_FILE='/run/secrets/robinhood_private_key',
                                       TRADEBOT_PP_COINBASE_TIMING='true',POLYMARKET_KEY_ID_FILE='/run/secrets/market_key_id',
                                       POLYMARKET_SECRET_KEY_FILE='/run/secrets/market_secret')
        for name in DISPLAY_KEYS:
            expected['secrets'][name]={'name':expected['name']+'_'+name,'file':str(RUNTIME_SECRETS/name)}
            operator['secrets'].append({'source':name,'target':('/run/secrets/' if target.startswith('/') else '')+name})
    if reader:
        api = expected['services']['api']
        api['environment']['TRADEBOT_PP_ARCHIVE_HISTORY'] = 'true'
        for name in HISTORY_READER_FILES:
            expected['secrets'][name] = {'name': expected['name']+'_'+name, 'file':str(RUNTIME_SECRETS/name)}
            api['secrets'].append({'source':name, 'target':('/run/secrets/' if target.startswith('/') else '')+name})
    if trial_reader:
        from trial_history_reader import TRIAL_HISTORY_READER_FILES,trial_history_reader_source
        api=expected['services']['api']
        api['environment']['TRADEBOT_PP_ARCHIVE_HISTORY']='true'
        for name in TRIAL_HISTORY_READER_FILES:
            expected['secrets'][name]={'name':expected['name']+'_'+name,'file':str(trial_history_reader_source(name))}
            api['secrets'].append({'source':name,'target':('/run/secrets/' if target.startswith('/') else '')+name})
    require(live == expected, 'unreviewed_pp_live_profile_difference')
    return live
