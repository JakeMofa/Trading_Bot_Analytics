"""Optional reference transport degradation preserves PM, exact writes and lease."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from postgres.live_diagnostics import LiveDiagnostic,SourceHTTPFailure
from postgres.live_ingest import coinbase_candle_cycle
from postgres.store import CandleRevisionConflict, IdentityConflict, StorageHold
from postgres.live_supervisor import run_bounded

class Store:
 def __init__(self):
  self.settings=SimpleNamespace(environment='preprod',data_mode='pp_live',origin_id='pp-live-fixture');self.enabled=True;self.stops=0;self.saved=[]
 def collector_enabled(self):return self.enabled
 def disable(self):self.enabled=False;self.stops+=1;return False
 def ingest(self,event):self.saved.append(event)

class CandleDegraded(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,fetch,*,write=None,pause=None,max_seconds=1):
  self.store=Store();self.stop=asyncio.Event();self.pm=0
  if write:self.store.ingest=write
  async def market(*args,**kwargs):self.pm+=1
  async def stream(store,stop):await stop.wait()
  async def candles(store,client,stop,**kwargs):return await coinbase_candle_cycle(store,client,stop,fetch=fetch,**kwargs)
  async with httpx.AsyncClient() as client:
   with patch('postgres.live_supervisor._pause_or_stop',pause or self.normal_pause):
    return await run_bounded(self.store,client,self.stop,owner_check=lambda:True,disable_collector=self.store.disable,max_seconds=max_seconds,market=market,coinbase=stream,candles=candles)
 async def normal_pause(self,stop,seconds):await stop.wait()
 async def test_multiple_transient_cycles_keep_pm_progress_then_exact_recovery(self):
  errors=[httpx.ReadTimeout('private'),httpx.ConnectError('private'),SourceHTTPFailure(429,'private'),SourceHTTPFailure(503,'private')];calls=[];cadences=[]
  async def fetch(*args):
   calls.append(self.pm)
   if errors:raise errors.pop(0)
   return [{'source':'coinbase','kind':'candle','payload':{'exact':'100.000000000000000001'}}]
  async def pause(stop,seconds):
   if seconds==60:
    cadences.append(seconds)
    if len(cadences)==5:stop.set()
    await asyncio.sleep(.001)
   else:await asyncio.sleep(.0001)
  with self.assertLogs('postgres.live_supervisor',level='WARNING') as logs:
   self.assertEqual(await self.run_case(fetch,pause=pause),'stopped')
  self.assertEqual(len(logs.output),5)
  self.assertTrue(all('pp_candles_unavailable reason=coinbase_candles.' in line for line in logs.output[:4]))
  self.assertIn('pp_candles_cycle_recovered unavailable_cycles=4',logs.output[-1])
  self.assertNotIn('private',' '.join(logs.output));self.assertNotIn('100.000000000000000001',' '.join(logs.output))
  self.assertEqual(cadences,[60]*5);self.assertEqual(len(calls),5);self.assertGreater(calls[-1],calls[0]);self.assertEqual(len(self.store.saved),1);self.assertEqual(self.store.saved[0]['payload']['exact'],'100.000000000000000001');self.assertEqual(self.store.stops,1)
 async def test_auth_missing_malformed_and_protocol_errors_are_fatal(self):
  for error,category in [(SourceHTTPFailure(401,'private'),'http_4xx'),(SourceHTTPFailure(404,'private'),'http_404'),(ValueError('private malformed'),'invalid_or_unavailable')]:
   async def fetch(*args):raise error
   with self.subTest(category=category),self.assertRaises(LiveDiagnostic) as caught:await self.run_case(fetch)
   self.assertEqual(caught.exception.code,'coinbase_candles.'+category);self.assertEqual(self.store.stops,1);self.assertEqual(self.store.saved,[])
 async def test_write_timeout_and_write_rejection_are_fatal(self):
  for error,category in [(TimeoutError('private'),'timeout'),(IdentityConflict('private'),'invalid_or_unavailable'),(StorageHold('private'),'write_rejected')]:
   async def fetch(*args):return [{'kind':'candle'}]
   def write(event):raise error
   with self.subTest(category=category),self.assertRaises(LiveDiagnostic) as caught:await self.run_case(fetch,write=write)
   self.assertEqual(caught.exception.code,'coinbase_candle_write.'+category);self.assertEqual(self.store.stops,1)
 async def test_candle_revision_preserves_polymarket_and_later_candle(self):
  revised={'event_id':'revised'}
  new={'event_id':'new'}
  async def fetch(*args):return [revised,new]
  def write(event):
   if event==revised:raise CandleRevisionConflict('private revised body')
   self.store.saved.append(event)
  async def pause(stop,seconds):
   if seconds==5 and self.store.saved:stop.set()
   await asyncio.sleep(.001)
  with self.assertLogs('postgres.live_ingest',level='WARNING') as logs:
   self.assertEqual(await self.run_case(fetch,write=write,pause=pause),'stopped')
  self.assertEqual(self.store.saved,[new])
  self.assertGreaterEqual(self.pm,2)
  self.assertIn('pp_candle_revisions_rejected count=1',logs.output[0])
  self.assertNotIn('private',' '.join(logs.output))
 async def test_explicit_off_interrupts_normal_cadence_wait(self):
  async def fetch(*args):raise httpx.ConnectError('private')
  async def pause(stop,seconds):
   if seconds==60:stop.set()
   await stop.wait()
  self.assertEqual(await asyncio.wait_for(self.run_case(fetch,pause=pause),.5),'stopped');self.assertEqual(self.store.stops,1)
 async def test_session_deadline_interrupts_degraded_candle_wait(self):
  async def fetch(*args):raise httpx.ReadTimeout('private')
  with self.assertRaises(LiveDiagnostic) as caught:await self.run_case(fetch,max_seconds=.03)
  self.assertEqual(caught.exception.code,'session.deadline_reached');self.assertEqual(self.store.stops,1)
 async def test_unclassified_exception_is_not_retried(self):
  async def broken(*args):raise RuntimeError('private')
  with self.assertRaises(LiveDiagnostic) as caught:await self.run_case(broken)
  self.assertEqual(caught.exception.code,'coinbase_candles.unexpected');self.assertEqual(self.store.stops,1)
