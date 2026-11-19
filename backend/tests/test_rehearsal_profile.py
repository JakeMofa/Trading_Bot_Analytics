"""Finite explicit cycle scope, isolated from ordinary admission."""
import asyncio
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.rehearsal_profile import cycle_anchor, lease_cap, CYCLE_POLICY
from postgres.operator_session import OperatorSession
from postgres.lifecycle import LifecycleRepository, LifecycleHold
from postgres.lifecycle_worker import configuration

A=str(uuid.uuid4())
ENV=dict(TRADEBOT_ENVIRONMENT='preprod',TRADEBOT_DATA_MODE='pp_live',
    TRADEBOT_ORIGIN_ID='pp-live-pp',TRADEBOT_PP_WINDOW_POLICY=CYCLE_POLICY,
    TRADEBOT_PP_CYCLE_INITIAL_A=A,TRADEBOT_PP_LIVE_LIFECYCLE='true')

class ProfileTests(unittest.TestCase):
    def test_exact_scope_and_normal_cap_unchanged(self):
        self.assertEqual(cycle_anchor(ENV),A)
        self.assertEqual(lease_cap(),4560)
        self.assertEqual(lease_cap(A),6600)
        self.assertEqual(configuration(ENV)['rehearsal_anchor'],A)
        for change in ({'TRADEBOT_ENVIRONMENT':'production'},
                       {'TRADEBOT_DATA_MODE':'generated'},
                       {'TRADEBOT_ORIGIN_ID':'pp-live-other'},
                       {'TRADEBOT_PP_CYCLE_INITIAL_A':'bad'},
                       {'TRADEBOT_PP_WINDOW_POLICY':'two-official-markets'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                cycle_anchor({**ENV,**change})
        with self.assertRaises(ValueError):
            cycle_anchor({k:v for k,v in ENV.items() if k!='TRADEBOT_PP_CYCLE_INITIAL_A'})

    def test_lease_rejects_wrong_cycle_before_database(self):
        repo=LifecycleRepository(lambda:self.fail('opened database'))
        for origin,generation,seconds,anchor in (
            ('pp-live-pp',A,6600,None),('pp-live-other',A,6600,A),
            ('pp-live-pp',str(uuid.uuid4()),6600,A),
            ('pp-live-pp',A,6601,A),('pp-live-pp',A,900,A)):
            with self.subTest(seconds=seconds), self.assertRaises(LifecycleHold):
                repo.enable_collector(origin,session_id=str(uuid.uuid4()),
                    expected_generation_id=generation,max_seconds=seconds,rehearsal_anchor=anchor)

class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cycle_is_explicit_finite_and_does_not_renew(self):
        entered=asyncio.Event()
        calls=[]
        async def run(stop,seconds):
            calls.append(seconds)
            entered.set()
            await stop.wait()
        control=OperatorSession(run,lambda:{'collector_enabled':False},rehearsal_anchor=A)
        for seconds in (900,4560,6601,True):
            with self.assertRaises(ValueError): await control.start(max_seconds=seconds)
        await control.start(max_seconds=6600)
        await entered.wait()
        self.assertEqual(calls,[6600])
        await control.stop()
        normal=OperatorSession(run,lambda:{'collector_enabled':False})
        with self.assertRaises(ValueError):await normal.start(max_seconds=6600)

class ChainTests(unittest.TestCase):
    def test_exact_two_switch_chain_and_terminal_fresh_a(self):
        from datetime import datetime, timedelta, timezone
        start=datetime(2026,11,19,tzinfo=timezone.utc)
        ids=[A,str(uuid.uuid4()),str(uuid.uuid4())]
        rows=[dict(generation_id=g,slot=slot,created_at=start+timedelta(minutes=i*30),
                   started_at=start+timedelta(minutes=i*30),
                   sealed_at=start+timedelta(minutes=(i+1)*30),
                   state='retired' if i==0 else 'sealed' if i==1 else 'collecting')
              for i,(g,slot) in enumerate(zip(ids,('A','B','A')))]
        class Result:
            def __init__(self,rows):self.rows=rows
            def fetchone(self):return self.rows[0]
            def fetchall(self):return self.rows
        class Connection:
            def __init__(self,chain):self.chain=chain
            def execute(self,sql,args):return Result([rows[0]] if 'generation_id=%s' in sql else self.chain)
        for count in (1,2,3):
            self.assertEqual(LifecycleRepository._rehearsal_phase(Connection(rows[:count]),
                'pp-live-pp',A,rows[count-1]),count-1)
        for bad in (rows[::-1],rows[:2]+[{**rows[2],'slot':'B'}],
                    [{**rows[0],'state':'verified'},*rows[1:]],
                    [rows[0],{**rows[1],'started_at':start},rows[2]]):
            with self.assertRaises(LifecycleHold):
                LifecycleRepository._rehearsal_phase(Connection(bad),'pp-live-pp',A,rows[2])


class AlignmentTests(unittest.TestCase):
    def test_last_minute_gate_preserves_second_alignment_and_reserve(self):
        from datetime import datetime, timezone
        from postgres.rehearsal_profile import require_cycle_alignment
        for text,seconds in [('2026-11-19T12:14:00+00:00',60),
                             ('2026-11-19T12:14:59.999999+00:00',0.000001)]:
            self.assertAlmostEqual(require_cycle_alignment(datetime.fromisoformat(text)),seconds)
        for text in ('2026-11-19T12:13:59.999999+00:00','2026-11-19T12:15:00+00:00',
                     '2026-11-19T12:15:00.000001+00:00'):
            with self.assertRaises(ValueError):require_cycle_alignment(datetime.fromisoformat(text))


class ApiTests(unittest.TestCase):
    def test_ordinary_route_keeps_cap_and_cycle_requires_exact_explicit_budget(self):
        from fastapi.testclient import TestClient
        from postgres.operator_api import create_operator_app
        class Session:
            def __init__(self):self.calls=[]
            def state(self):return {'process_running':False}
            async def start(self,*,max_seconds):
                self.calls.append(max_seconds)
                return {'process_running':True}
            async def stop(self):return {'process_running':False}
        session=Session();token='fixture-'+'x'*32
        headers={'Authorization':'Bearer '+token}
        normal=TestClient(create_operator_app(object(),origin_id='pp-live-pp',token=token,session=session))
        self.assertEqual(normal.post('/collector/on?max_seconds=6600',headers=headers).status_code,422)
        cycle=TestClient(create_operator_app(object(),origin_id='pp-live-pp',token=token,session=session,
            max_session_seconds=6600,required_session_seconds=6600))
        self.assertEqual(cycle.post('/collector/on?max_seconds=6600').status_code,401)
        for query in ('','?max_seconds=4560','?max_seconds=6601'):
            self.assertEqual(cycle.post('/collector/on'+query,headers=headers).status_code,422)
        self.assertEqual(session.calls,[])
        self.assertEqual(cycle.post('/collector/on?max_seconds=6600',headers=headers).status_code,202)
        self.assertEqual(session.calls,[6600])
