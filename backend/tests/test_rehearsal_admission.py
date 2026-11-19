"""Exact schedule evidence for the currently unsupported second PP switch."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio
import sys
import unittest
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.rehearsal_admission import Market, plan
from postgres.operator_session import OperatorSession

START=datetime(2026,11,19,12,tzinfo=timezone.utc)
IDS=tuple(str(UUID(int=i)) for i in (1,2,3))


def fixture(start=START, reserves=(1800,1800)):
    boundary=START if start==START else START+timedelta(seconds=900)
    a_seal=boundary+timedelta(seconds=1800)
    b_seal=a_seal+timedelta(seconds=1800)
    pairs=tuple(tuple(Market(f'venue-{i+j}',boundary+timedelta(seconds=(i+j)*900),
                         boundary+timedelta(seconds=(i+j+1)*900)) for j in range(2)) for i in (0,2))
    return dict(origin_id='pp-live-pp',session_start=start,lease_expires_at=start+timedelta(seconds=4560),
        generations=(('A',IDS[0]),('B',IDS[1]),('A',IDS[2])),markets=pairs,
        seals=(a_seal,b_seal),readback_seconds=reserves)


class RehearsalAdmissionTests(unittest.TestCase):
    def test_full_seal_windows_exceed_cap_even_when_aligned(self):
        result=plan(**fixture())
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(result['lease_margin_seconds'],-840)
        self.assertEqual(result['legs'][0]['seal_deadline'],(START+timedelta(seconds=3600)).isoformat())
        self.assertEqual(result['legs'][1]['seal_deadline'],(START+timedelta(seconds=5400)).isoformat())
        self.assertIn('old_A_retirement_not_proved_before_fresh_A_allocation',result['reasons'])

    def test_midmarket_wait_is_exact_and_consumes_lease(self):
        result=plan(**fixture(start=START+timedelta(microseconds=1)))
        self.assertEqual(result['legs'][0]['first_market_start'],(START+timedelta(seconds=900)).isoformat())
        self.assertAlmostEqual(result['lease_margin_seconds'],-1739.999999)

    def test_short_planned_readback_still_cannot_enable_existing_B_profile(self):
        result=plan(**fixture(reserves=(240,240)))
        self.assertEqual(result['reasons'],['current_market_pair_profile_does_not_rotate_B'])
        self.assertFalse(result['executable'])
        self.assertEqual(result['lease_margin_seconds'],720)
        self.assertNotEqual(result['legs'][0]['sealed_generation'],result['legs'][1]['collecting_generation'])

    def test_lease_equality_cannot_admit_commit(self):
        options=fixture(reserves=(240,240))
        options['lease_expires_at']=START+timedelta(seconds=3840)
        self.assertIn('lease_expires_before_second_leg_commit_and_observation',plan(**options)['reasons'])

    def test_invalid_slots_uuid_boundaries_pairs_and_policy_fail(self):
        changes=[dict(generations=(('A',IDS[0]),('B',IDS[1]),('A',IDS[0]))),
                 dict(generations=(('A',IDS[0]),('A',IDS[1]),('B',IDS[2]))),
                 dict(readback_seconds=(1801,240)),dict(readback_seconds=(True,240)),
                 dict(lease_expires_at=START+timedelta(seconds=4561)),dict(origin_id='production')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):plan(**(fixture()|change))
        options=fixture()
        pairs=list(options['markets']); first=list(pairs[0])
        first[0]=Market('invalid',START+timedelta(microseconds=1),START+timedelta(seconds=900,microseconds=1))
        pairs[0]=tuple(first)
        with self.assertRaises(ValueError):plan(**(options|dict(markets=tuple(pairs))))

    def test_actual_operator_contract_rejects_longer_lease_without_start(self):
        calls=[]
        async def run(*args):calls.append(args)
        session=OperatorSession(run,lambda: {'collector_enabled':False})
        with self.assertRaises(ValueError):asyncio.run(session.start(max_seconds=4561))
        self.assertEqual(calls,[])
