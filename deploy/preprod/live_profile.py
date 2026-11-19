"""Fail-closed comparison of a PP live trial with the qualified OFF profile.

The regular CD controller deliberately rejects this overlay. A separately
reviewed, bounded host action must validate both normalized Compose profiles
before changing any running service. Equality includes every other setting,
including disabled paid-AI/cloud/retirement flags and database isolation.
"""
from __future__ import annotations

from copy import deepcopy

from linux_actions import validate_config
from controller import require


LIVE_ORIGIN = 'pp-live-pp'


def validate_live_profile(base: dict, live: dict, source, image):
    validate_config(base, source, image)
    expected = deepcopy(base)
    for name in ('api', 'calculation', 'lifecycle'):
        expected['services'][name]['environment'].update(
            TRADEBOT_DATA_MODE='pp_live', TRADEBOT_ORIGIN_ID=LIVE_ORIGIN)
    expected['services']['lifecycle']['environment'].update(
        TRADEBOT_PP_LIVE_LIFECYCLE='true', TRADEBOT_PP_WINDOW_POLICY='two-official-markets')
    operator = expected['services']['operator']
    operator['environment'].update(TRADEBOT_PP_LIVE_CONTROL='true',
                                   TRADEBOT_APP_DSN_FILE='/run/secrets/app_dsn')
    target = operator['secrets'][0]['target']
    require(target in ('lifecycle_dsn', '/run/secrets/lifecycle_dsn'),
            'unreviewed_pp_operator_secret_shape')
    operator['secrets'].append({'source': 'app_dsn',
                                'target': '/run/secrets/app_dsn' if target.startswith('/') else 'app_dsn'})
    require(live == expected, 'unreviewed_pp_live_profile_difference')
    return live
