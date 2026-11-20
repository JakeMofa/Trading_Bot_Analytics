"""Explicit, finite PP two-leg rehearsal scope. No activation or lease renewal."""
import uuid
from datetime import datetime, timezone
from .cloud_origin_binding import TRIAL_ORIGIN, NEXT_TRIAL_ORIGIN, THIRD_TRIAL_ORIGIN, TRIAL_ORIGINS

NORMAL_LEASE_CAP_SECONDS = 4560
# Admission is within the final minute before the first quarter. B may wait
# almost another quarter when the first switch follows its boundary. Both
# outgoing pairs, B's original seal window and scheduling margin stay finite.
CYCLE_LEASE_CAP_SECONDS = 60 + 3600 + 900 + 1800 + 240
CYCLE_POLICY = 'two-official-markets-cycle'
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


def cycle_anchor(environ):
    policy = environ.get('TRADEBOT_PP_WINDOW_POLICY')
    anchor = environ.get('TRADEBOT_PP_CYCLE_INITIAL_A')
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
