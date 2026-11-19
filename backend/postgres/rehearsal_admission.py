"""Offline A -> B -> fresh A planning. No database, routes or activation.

The existing market-pair profile cannot perform the second switch. A timing
fit is evidence for a separately reviewed continuation, never admission to run.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

LEASE_CAP_SECONDS = 4560  # Existing OperatorSession/enable_collector contract.
SEAL_WINDOW_SECONDS = 1800  # Existing bound_seal_window; never extended here.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('offset-aware datetime required')
    return value.astimezone(timezone.utc)


def micros(value):
    delta = utc(value) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


@dataclass(frozen=True)
class Market:
    market_id: str
    start: datetime
    end: datetime
    source: str = 'polymarket_us'
    duration: int = 900

    def validate(self):
        if (not isinstance(self.market_id, str) or not 1 <= len(self.market_id) <= 256
                or self.source != 'polymarket_us' or type(self.duration) is not int
                or self.duration != 900 or micros(self.start) % 900000000
                or utc(self.end) - utc(self.start) != timedelta(seconds=900)):
            raise ValueError('explicit official 15-minute market identity/boundary required')


def plan(*, origin_id, session_start, lease_expires_at, generations, markets,
         seals, readback_seconds=(1800, 1800), fresh_a_observation_seconds=1):
    """Validate an explicit proposed schedule; return current-profile HOLD.

    generations is exactly ((A,old_uuid),(B,b_uuid),(A,fresh_uuid)); future UUIDs
    are proposed identities, not proof of allocated partitions. markets is two
    ordered pairs of captured venue metadata; quote receipt proof remains a
    runtime requirement. seals is the two proposed actual switch instants.
    Readback reserves include archive/drain/proof/permit/commit, not only HTTP.
    """
    start, expires = utc(session_start), utc(lease_expires_at)
    if (origin_id != 'pp-live-pp'
            or not start < expires <= start + timedelta(seconds=LEASE_CAP_SECONDS)
            or not isinstance(generations, tuple) or len(generations) != 3):
        raise ValueError('bounded existing lease and exact A/B/A generations required')
    ids = []
    for item, slot in zip(generations, ('A', 'B', 'A')):
        if not isinstance(item, tuple) or len(item) != 2 or item[0] != slot:
            raise ValueError('explicit A/B/fresh-A slot order required')
        value = item[1]
        try:
            valid = isinstance(value, str) and str(uuid.UUID(value)) == value
        except (ValueError, AttributeError):
            valid = False
        if not valid or value in ids:
            raise ValueError('three distinct canonical generation UUIDs required')
        ids.append(value)
    if (not isinstance(markets, tuple) or len(markets) != 2
            or not isinstance(seals, tuple) or len(seals) != 2
            or not isinstance(readback_seconds, tuple) or len(readback_seconds) != 2
            or type(fresh_a_observation_seconds) is not int
            or not 1 <= fresh_a_observation_seconds <= 900):
        raise ValueError('two exact market pairs/seals and bounded observation required')
    seal_times = tuple(map(utc, seals))
    if not start < seal_times[0] < seal_times[1]:
        raise ValueError('ordered future seals required')
    seen_markets = set()
    legs = []
    collecting_at = start
    for index, (pair, seal, reserve) in enumerate(zip(markets, seal_times, readback_seconds)):
        if (not isinstance(pair, tuple) or len(pair) != 2
                or type(reserve) is not int or not 1 <= reserve <= SEAL_WINDOW_SECONDS):
            raise ValueError('two complete markets and unchanged seal-window reserve required')
        for market in pair:
            if not isinstance(market, Market):
                raise ValueError('captured official market metadata required')
            market.validate()
            if market.market_id in seen_markets:
                raise ValueError('four distinct official market identities required')
            seen_markets.add(market.market_id)
        boundary = EPOCH + timedelta(microseconds=((micros(collecting_at)+899999999)//900000000)*900000000)
        if (utc(pair[0].start) != boundary or utc(pair[1].start) != utc(pair[0].end)
                or seal < utc(pair[1].end)):
            raise ValueError('each generation needs its next two full contiguous official markets')
        deadline = seal + timedelta(seconds=SEAL_WINDOW_SECONDS)
        finish = seal + timedelta(seconds=reserve)
        legs.append(dict(sealed_slot=generations[index][0], sealed_generation=ids[index],
            collecting_slot=generations[index+1][0], collecting_generation=ids[index+1],
            markets=[m.market_id for m in pair], first_market_start=boundary.isoformat(),
            second_market_end=utc(pair[1].end).isoformat(), sealed_at=seal.isoformat(),
            seal_deadline=deadline.isoformat(), planned_readback_commit=finish.isoformat()))
        collecting_at = seal
    finishes = [seal + timedelta(seconds=reserve) for seal, reserve in zip(seal_times, readback_seconds)]
    required_until = max(finishes[1],seal_times[1]+timedelta(seconds=fresh_a_observation_seconds))
    reasons = ['current_market_pair_profile_does_not_rotate_B']
    if finishes[0] >= seal_times[1]:
        reasons.append('old_A_retirement_not_proved_before_fresh_A_allocation')
    # Lease validity is strict > database clock at commit; equality cannot pass.
    if required_until >= expires:
        reasons.append('lease_expires_before_second_leg_commit_and_observation')
    return dict(status='HOLD', executable=False, origin_id=origin_id, reasons=reasons,
        lease_cap_seconds=LEASE_CAP_SECONDS, lease_expires_at=expires.isoformat(),
        required_lease_valid_past=required_until.isoformat(),
        lease_margin_seconds=(expires-required_until).total_seconds(), legs=legs,
        coverage='schedule_only_not_observed',
        continuation='separately_review_second_rotation_and_exact_retirement_proof; no_lease_renewal_implied')
