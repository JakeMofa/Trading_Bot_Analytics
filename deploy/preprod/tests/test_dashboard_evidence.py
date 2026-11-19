"""Offline evidence fixtures, including regressions the ID-only observer misses."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dashboard_evidence as audit

BASE = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)


def record(tick, *, market='A', generation='old', abstain=False):
    at = BASE + timedelta(seconds=tick)
    feature_at = (at-timedelta(seconds=2)).isoformat()
    forecast = dict(prediction_id='p'+str(tick), snapshot_id='f'+str(tick), market_id=market,
                    as_of=feature_at, probability_up=None if abstain else '0.600000000000000001',
                    probability_down=None if abstain else '0.399999999999999999',
                    abstain_reason='completed_candles_missing_or_stale' if abstain else None)
    state = dict(environment='preprod', data_mode='pp_live', origin_id='pp-live-pp',
                 generated_at=at.isoformat(), market=dict(id=market, start=BASE.isoformat(),
                 end=(BASE+timedelta(minutes=15)).isoformat(), active=True),
                 coinbase=dict(source_time=(at-timedelta(seconds=1)).isoformat(), generation_id=generation),
                 feature_snapshot=dict(snapshot_id='f'+str(tick),market_id=market,as_of=feature_at,
                 quality=dict(price=dict(source_time=(at-timedelta(seconds=3)).isoformat(),status='fresh'),
                              candle_status='missing_or_stale' if abstain else 'fresh',candle_age_seconds=4)),
                 forecast=forecast, live_estimate=dict(forecast,as_of=(at-timedelta(seconds=1)).isoformat(),snapshot_as_of=feature_at))
    return audit.capture('/state/current',state,at=at.isoformat(),source_sha='fixture-sha',latency_ms=1,monotonic_seconds=tick)


def generations():
    return [dict(writer=dict(at_utc=(BASE+timedelta(seconds=t)).isoformat(),generation_id=g))
            for t,g in [(6,'old'),(9,'new')]]


class DashboardEvidenceTests(unittest.TestCase):
    def test_numeric_pass_is_separate_from_ids_and_boundary_has_bracket(self):
        result = audit.summarize([record(5),record(10,generation='new'),record(15,generation='new')],generations())
        self.assertEqual(result['numeric_forecast_result'],'PASS')
        self.assertEqual(result['distinct_active_numeric_saved_predictions'],3)
        self.assertIsNone(result['switches'][0]['exact_switch_timestamp'])
        self.assertTrue(result['switches'][0]['numeric_on_both_sides'])
        self.assertEqual(result['observations'][0]['saved']['probability_up'],'0.600000000000000001')

    def test_truthful_abstain_integrity_pass_but_numeric_incomplete(self):
        result = audit.summarize([record(5,abstain=True),record(10,abstain=True)],generations())
        self.assertEqual(result['integrity_result'],'PASS')
        self.assertEqual(result['numeric_forecast_result'],'INCOMPLETE')
        self.assertEqual(result['classifications']['saved'],{'truthful_abstain':2})
        self.assertEqual(result['distinct_active_numeric_saved_predictions'],0)

    def test_prior_market_ids_do_not_count(self):
        r=record(5);r['state']['forecast']['market_id']='prior'
        result=audit.summarize([r],generations())
        self.assertEqual(result['integrity_result'],'FAIL')
        self.assertEqual(result['distinct_active_numeric_saved_predictions'],0)
        self.assertIn('prior_or_unbound_market',result['observations'][0]['saved']['issues'])

    def test_bad_timestamps_feature_binding_and_input_ages(self):
        for mutate,issue in [
            (lambda s:s['forecast'].update(as_of=(BASE-timedelta(seconds=40)).isoformat()),'forecast_stale_or_time_missing'),
            (lambda s:s['forecast'].update(snapshot_id='old'),'saved_prediction_snapshot_binding_missing'),
            (lambda s:s['feature_snapshot']['quality']['price'].update(source_time=(BASE-timedelta(minutes=2)).isoformat()),'saved_input_price_stale_or_missing'),
            (lambda s:s['market'].update(end=BASE.isoformat()),'market_not_active_at_observation'),
            (lambda s:s['forecast'].update(as_of=(BASE+timedelta(minutes=1)).isoformat()),'forecast_stale_or_time_missing')]:
            r=record(5);mutate(r['state'])
            result=audit.summarize([r],generations())
            self.assertEqual(result['integrity_result'],'FAIL')
            self.assertIn(issue,result['observations'][0]['saved']['issues'])

    def test_live_dashboard_ten_second_limit_distinct_from_saved(self):
        r=record(20);r['state']['coinbase']['source_time']=BASE.isoformat();r['state']['live_estimate']['as_of']=BASE.isoformat()
        result=audit.summarize([r],generations())
        self.assertEqual(result['observations'][0]['saved']['classification'],'active_numeric')
        self.assertEqual(result['observations'][0]['live']['classification'],'dashboard_suppressed_numeric')
        self.assertEqual(result['failures'],[])

    def test_live_asof_must_match_captured_tick_not_just_be_recent(self):
        r=record(20);r['state']['live_estimate']['as_of']=BASE.isoformat()
        result=audit.summarize([r])
        self.assertIn('live_tick_time_mismatch',result['observations'][0]['live']['issues'])
        self.assertEqual(result['observations'][0]['live']['classification'],'stale_or_unbound')

    def test_malformed_probability_and_conflicting_abstain(self):
        for value,reason in [('NaN',None),('1.1',None),(True,None),('0.6','stale')]:
            r=record(5);r['state']['forecast'].update(probability_up=value,abstain_reason=reason)
            self.assertEqual(audit.summarize([r])['observations'][0]['saved']['classification'],'invalid')

    def test_legacy_ids_and_nonempty_history_not_proof(self):
        result=audit.summarize([dict(at=BASE.isoformat(),prediction_id='p'),
                                dict(endpoint='/history/predictions?limit=5',history=[{'id':'p'}])])
        self.assertEqual(result['numeric_forecast_result'],'INCOMPLETE')
        self.assertEqual(result['samples'],0)

    def test_missing_switch_side_and_stale_generated_at_fail_closed(self):
        result=audit.summarize([record(10)],generations())
        self.assertEqual(result['integrity_result'],'INCOMPLETE')
        r=record(5);r['state']['generated_at']=(BASE-timedelta(minutes=2)).isoformat()
        self.assertIn('cross_host_clock_or_delivery_not_qualified',audit.summarize([r])['missing_evidence'])
        r=record(5,abstain=True);r['state']['forecast']['probability_down']='0.4'
        self.assertEqual(audit.summarize([r])['observations'][0]['saved']['classification'],'stale_or_unbound')

    def test_cross_host_clock_skew_not_forecast_input_age(self):
        rows=[record(5),record(10,generation='new'),record(15,generation='new')]
        for row in rows:
            row['at']=(audit.instant(row['at'])-timedelta(milliseconds=65)).isoformat()
        result=audit.summarize(rows,generations())
        self.assertEqual(result['numeric_forecast_result'],'PASS')
        self.assertEqual(result['observations'][0]['live']['input_price_age_seconds'],1)
        self.assertAlmostEqual(result['observations'][0]['operator_minus_server_generated_seconds'],-0.065)
        self.assertFalse(result['clock_evidence']['synchronized_wall_clocks_proven'])
        rows[0]['at']=(BASE+timedelta(seconds=30)).isoformat()
        self.assertIn('cross_host_clock_or_delivery_not_qualified',audit.summarize(rows,generations())['missing_evidence'])

    def test_missing_server_timestamp_does_not_use_operator_clock(self):
        row=record(5);row['state']['generated_at']=None
        result=audit.summarize([row],generations())
        self.assertIn('state_generated_time_missing_or_invalid',result['failures'])
        self.assertEqual(result['observations'][0]['live']['classification'],'stale_or_unbound')

    def test_stale_source_truthful_abstain_not_numeric_failure(self):
        row=record(50,abstain=True)
        row['state']['coinbase']['source_time']=BASE.isoformat()
        row['state']['live_estimate']['as_of']=BASE.isoformat()
        row['state']['live_estimate']['abstain_reason']='reference_price_not_fresh'
        result=audit.summarize([row])
        self.assertEqual(result['observations'][0]['live']['classification'],'truthful_abstain')
        self.assertEqual(result['failures'],[])
        self.assertEqual(result['numeric_forecast_result'],'INCOMPLETE')
        row['state']['live_estimate'].update(probability_up='0.6',probability_down='0.4',abstain_reason=None)
        self.assertEqual(audit.summarize([row])['observations'][0]['live']['classification'],'stale_or_unbound')

    def test_market_rollover_with_explicit_missing_market_gap(self):
        before=record(5);gap=record(10);gap['state'].update(market=None,forecast=None,live_estimate=None)
        after=record(15,market='B')
        result=audit.summarize([before,gap,after])
        self.assertEqual(len(result['market_transitions']),1)
        self.assertEqual(result['market_transitions'][0]['intervening_missing_market_samples'],1)
        self.assertEqual(result['market_transitions'][0]['before']['market_id'],'A')
        self.assertEqual(result['market_transitions'][0]['after']['market_id'],'B')

    def test_capture_allowlist_no_headers_or_secret_nested_price(self):
        r=record(5);state=deepcopy(r['state']);state['headers']={'Authorization':'secret'}
        state['feature_snapshot']['quality']['price']['secret']='secret'
        capture=audit.capture('/events',state,at=r['at'],source_sha='s',latency_ms=1,monotonic_seconds=1)
        self.assertNotIn('secret',json.dumps(capture))

    def test_cli_roundtrip_decimal_candle_and_create_only_output(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'states.jsonl';gen=folder/'gen.jsonl';out=folder/'result.json'
            rows=[record(5),record(10,generation='new'),record(15,generation='new')]
            for row in rows:row['state']['feature_snapshot']['quality']['candle_age_seconds']=4.5
            source.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            gen.write_text(''.join(json.dumps(r)+'\n' for r in generations()))
            command=[sys.executable,audit.__file__,'--input',str(source),'--generations',str(gen),'--output',str(out)]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(out.read_text())['numeric_forecast_result'],'PASS')
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
