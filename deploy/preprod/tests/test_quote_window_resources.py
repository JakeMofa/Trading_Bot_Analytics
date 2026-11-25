from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quote_window_resources import backlog, build_report, collect, instant, interval, profile_report


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


class QuoteWindowResourcesTest(unittest.TestCase):
    def test_device_interval_cpu_pressure_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'sys/kernel/random').mkdir(parents=True)
            (root/'sys/kernel/random/boot_id').write_text('test-id')
            (root/'meminfo').write_text('MemAvailable:   1024 kB\n')
            (root/'vmstat').write_text('pswpin 2\npswpout 3\n')
            (root/'pressure').mkdir()
            (root/'stat').write_text('cpu 2 0 8 90 0 0 0 0 30 10\n')
            (root/'diskstats').write_text('8 0 sda 4 0 9 0 0 0 30 0 0 12 0\n8 1 sda1 0 0 80 0 0 0 99 0 0 3 0\n')
            (root/'pressure/memory').write_text('full avg10=0.02 total=5\n')
            a = collect(root, '8:0')
            (root/'stat').write_text('cpu 4 0 8 97 1 0 0 0 30 10\n')
            (root/'diskstats').write_text('8 0 sda 4 0 10 0 0 0 32 0 0 14 0\n')
            (root/'pressure/memory').write_text('full avg10=0.02 total=10005\n')
            b = collect(root,'8:0')
            b['monotonic_ns']=a['monotonic_ns']+1_000_000_000
            timing=interval(a,b)
            self.assertEqual(a['mem_available_kib'],1024)
            self.assertEqual(timing['cpu_busy_pct'],20.)
            self.assertEqual(timing['cpu_iowait_pct'],10.)
            self.assertEqual(timing['memory_full_stall_pct'],1.)
            self.assertEqual(timing['disk_read_bytes'],512)
            self.assertEqual(timing['disk_write_bytes'],1024)
            self.assertIsNone(timing['io_some_stall_pct'])
            self.assertEqual(timing['pswpin'],0)
            b['counters']['pswpin']=0
            self.assertIsNone(interval(a,b)['pswpin'])
            b['boot_id']='different-boot'
            self.assertEqual(interval(a,b),{})

    def test_join_does_not_backfill_future_or_stale_or_cross_origin(self):
        boundary=1_800_000_000
        obs={'at_utc':utc(boundary+4),'origin_id':'example','generations':[{'pending':2,'oldest_pending_at':utc(boundary+1)}]}
        samples=[{'at_utc':utc(boundary+n),'monotonic_ns':n*1_000_000_000,'mem_available_kib':1000,
                  'boot_id':'boot','device':'1:2','counters':{}} for n in (2,5,65)]
        boundaries=[{'window_start':utc(boundary+i*900)} for i in range(4)]
        boundaries[0]['dashboard_first_utc'] = utc(boundary+6)
        result=build_report(samples,[obs,dict(obs,origin_id='other')],boundaries,'example')
        points=result['windows'][0]['samples']
        self.assertIsNone(points[0]['archive'])
        self.assertEqual(points[1]['archive'],{'pending':2,'oldest_pending_seconds_at_observation':3.,'sample_age_seconds':1.})
        self.assertIsNone(points[2]['archive'])
        self.assertEqual(result['windows'][3]['samples'],[])
        wait = result['windows'][0]['during_wait_for_dashboard']
        self.assertEqual(wait['covered_seconds'],3.)
        self.assertEqual(wait['samples_in_span'],2)
        self.assertIsNone(wait['pswpin'])
        self.assertIsNone(result['windows'][1]['during_wait_for_dashboard'])
        one = build_report(samples, [obs], boundaries[:1], 'example')
        self.assertEqual(len(one['windows']), 1)
        self.assertEqual(one['windows'][0]['during_wait_for_dashboard'], wait)
        self.assertRaises(ValueError, build_report, samples,[obs],boundaries[:3],'example')
        benchmark = {'runs':[{'mode':'cold','started_at_utc':utc(boundary+1),'ended_at_utc':utc(boundary+10)}]}
        stats = profile_report(samples, benchmark)[0]['resources']
        self.assertEqual(stats['covered_seconds'],3.)
        self.assertIsNone(stats['max_observed_pending'])
        self.assertRaises(ValueError, instant, '2026-09-29T00:00:00')

    def test_missing_oldest_is_unknown_not_zero(self):
        info={'origin_id':'example','at_utc':utc(10),'generations':[{'pending':2},{'pending':4,'oldest_pending_at':utc(6)}]}
        self.assertEqual(backlog(info,10,'example'),{'pending':6,'oldest_pending_seconds_at_observation':None,'sample_age_seconds':0})
        self.assertIsNone(backlog(dict(info,generations=[]),10,'example'))


if __name__ == '__main__':
    unittest.main()
