"""Explicit, finite PP two-leg rehearsal scope. No activation or lease renewal."""
import uuid
from datetime import datetime, timezone
from .cloud_origin_binding import (BOUNDARY_ORIGIN, TRIAL_ORIGIN, NEXT_TRIAL_ORIGIN, THIRD_TRIAL_ORIGIN,
                                   FOURTH_TRIAL_ORIGIN, FIFTH_TRIAL_ORIGIN, SIXTH_TRIAL_ORIGIN,
                                   SEVENTH_TRIAL_ORIGIN, TRIAL_ORIGINS)

NORMAL_LEASE_CAP_SECONDS = 4560
# Admission is within the final minute before the first quarter. B may wait
# almost another quarter when the first switch follows its boundary. Both
# outgoing pairs, B's original seal window and scheduling margin stay finite.
CYCLE_LEASE_CAP_SECONDS = 60 + 3600 + 900 + 1800 + 240
CYCLE_POLICY = 'two-official-markets-cycle'
ELAPSED_CYCLE_POLICY = 'elapsed-30m-cycle'
ELAPSED_CYCLE_SECONDS = 1800
BOUNDARY_POLICY = 'boundary-diagnostic-v1'
BOUNDARY_LEASE_SECONDS = 4100
BOUNDARY_SMOKE_ORIGIN = 'pp-live-pp-smoke-20261125-01'
BOUNDARY_SMOKE_LEASE_SECONDS = 540
BOUNDARY_ORIGINS = frozenset({BOUNDARY_ORIGIN, BOUNDARY_SMOKE_ORIGIN})


def boundary_lease_seconds(origin):
    return BOUNDARY_SMOKE_LEASE_SECONDS if origin == BOUNDARY_SMOKE_ORIGIN else BOUNDARY_LEASE_SECONDS

TRIAL_PREPARATION_CHECKPOINT = 'trial:initial-a-prepare-v1'
# One reviewed trial namespace in the SAME environment database, not a wildcard.
CYCLE_ORIGINS = frozenset({'pp-live-pp', *TRIAL_ORIGINS})


def canonical_anchor(value):
    try:
        valid = isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValueError('canonical initial A generation UUID required')
    return value


def elapsed_cycle_seconds(environ):
    origin = environ.get('TRADEBOT_ORIGIN_ID')
    policy = environ.get('TRADEBOT_PP_WINDOW_POLICY')
    raw = environ.get('TRADEBOT_PP_ELAPSED_CYCLE_SECONDS')
    if policy == 'bounded-size-cycle' or environ.get('TRADEBOT_PP_SIZE_CYCLE_BYTES') is not None:
        raise ValueError('live size-cycle policy is not available')
    if origin != SEVENTH_TRIAL_ORIGIN:
        if policy == ELAPSED_CYCLE_POLICY or raw is not None:
            raise ValueError('elapsed cycle requires the exact seventh PP trial')
        return None
    if (policy != ELAPSED_CYCLE_POLICY or raw != str(ELAPSED_CYCLE_SECONDS)
            or environ.get('TRADEBOT_ENVIRONMENT') != 'preprod'
            or environ.get('TRADEBOT_DATA_MODE') != 'pp_live'):
        raise ValueError('seventh trial requires its exact elapsed-cycle profile')
    return ELAPSED_CYCLE_SECONDS


def elapsed_cycle_binding(origin, window_seconds):
    if origin == SEVENTH_TRIAL_ORIGIN:
        if type(window_seconds) is not int or window_seconds != ELAPSED_CYCLE_SECONDS:
            raise ValueError('seventh trial elapsed window mismatch')
        return {'profile': ELAPSED_CYCLE_POLICY, 'window_seconds': window_seconds}
    if window_seconds is not None:
        raise ValueError('elapsed cycle requires the exact seventh PP trial')
    return {}


def cycle_anchor(environ):
    policy = environ.get('TRADEBOT_PP_WINDOW_POLICY')
    anchor = environ.get('TRADEBOT_PP_CYCLE_INITIAL_A')
    if environ.get('TRADEBOT_ORIGIN_ID') in BOUNDARY_ORIGINS or policy == BOUNDARY_POLICY:
        boundary_anchor(environ)
        return None
    if elapsed_cycle_seconds(environ) is not None:
        return canonical_anchor(anchor)
    if policy != CYCLE_POLICY:
        if environ.get('TRADEBOT_ORIGIN_ID') in TRIAL_ORIGINS:
            raise ValueError('exact trial origin requires explicit two-leg cycle profile')
        if anchor is not None:
            raise ValueError('cycle identity requires explicit cycle profile')
        return None
    if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod'
            or environ.get('TRADEBOT_DATA_MODE') != 'pp_live'
            or environ.get('TRADEBOT_ORIGIN_ID') not in CYCLE_ORIGINS):
        raise ValueError('two-leg rehearsal requires isolated PP live scope')
    return canonical_anchor(anchor)


def boundary_anchor(environ):
    if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod'
            or environ.get('TRADEBOT_DATA_MODE') != 'pp_live'
            or environ.get('TRADEBOT_ORIGIN_ID') not in BOUNDARY_ORIGINS
            or environ.get('TRADEBOT_PP_WINDOW_POLICY') != BOUNDARY_POLICY
            or environ.get('TRADEBOT_PP_CYCLE_INITIAL_A') is not None
            or environ.get('TRADEBOT_PP_ELAPSED_CYCLE_SECONDS') is not None
            or environ.get('TRADEBOT_PP_SIZE_CYCLE_BYTES') is not None):
        raise ValueError('exact PP boundary profile required')
    return canonical_anchor(environ.get('TRADEBOT_PP_BOUNDARY_INITIAL_A'))


def lease_cap(anchor=None):
    if anchor is None:
        return NORMAL_LEASE_CAP_SECONDS
    canonical_anchor(anchor)
    return CYCLE_LEASE_CAP_SECONDS


def require_cycle_alignment(admitted_at):
    """Validate the actual DB lease admission, never a host/proposed clock.

    Strictly before the quarter: equality has no activation/commit runway.
    Rejection runs inside the admission transaction and rolls back ON.
    """
    if not isinstance(admitted_at, datetime) or admitted_at.tzinfo is None:
        raise ValueError('aware database admission timestamp required')
    instant=admitted_at.astimezone(timezone.utc)
    elapsed=((instant.minute % 15)*60+instant.second)*1000000+instant.microsecond
    remaining=900000000-elapsed
    if not 0 < remaining <= 60000000:
        raise ValueError('two-leg admission requires final 60 seconds before UTC quarter')
    return remaining / 1000000
