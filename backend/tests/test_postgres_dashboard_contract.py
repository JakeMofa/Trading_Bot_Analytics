"""Execute the PP chart summary with the actual bounded-history API contract."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'requires Node.js for dashboard JavaScript')
class ChartSummaryContractTests(unittest.TestCase):
    def test_truncated_history_warns_and_complete_history_does_not(self):
        source = (Path(__file__).resolve().parents[1] / 'postgres/dashboard.html').read_text()
        function = re.search(r'    function updateChartSummary\(\) \{.*?\n    \}', source, re.S).group()
        script = '''
const summaries = [];
let chartData;
const set = (key, value) => summaries.push({key, value});
const money = value => value;
const serverNowMs = () => null;
const localTime = value => value;
''' + function + '''
for (const truncated of [true, false]) {
  chartData = {status:'ok', tier:'local', bounded_input_limit:5000, truncated,
    market:{id:'fixture'}, points:[{at:'2026-11-19T12:05:00Z',price_usd:'100025.1234567890123456789'}]};
  updateChartSummary();
}
chartData = {status:'missing', market:null, points:[]};
updateChartSummary();
process.stdout.write(JSON.stringify(summaries));
'''
        result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True,
                                text=True, check=True, timeout=10)
        summaries = json.loads(result.stdout)
        self.assertTrue(all(item['key'] == 'chart-summary' for item in summaries))
        self.assertIn('earlier ticks outside query limit', summaries[0]['value'])
        self.assertNotIn('earlier ticks outside query limit', summaries[1]['value'])
        self.assertEqual(summaries[2]['value'], 'No stream ticks saved for this market yet.')

    def test_hidden_history_is_idle_and_delayed_results_are_discarded(self):
        source = (Path(__file__).resolve().parents[1] / 'postgres/dashboard.html').read_text()
        scheduler = source[source.index('    const viewRequests'):source.index('    function refreshView')]
        details = source[source.index('    async function refreshDetails'):source.index('    function renderModels')]
        script = """
const assert = require('node:assert/strict');
let currentPage='market';
const document={hidden:false}, paths=[], resolved=[], rendered=[];
const getJSON=(path,signal)=>new Promise(resolve=>{paths.push(path);resolved.push(resolve)});
const renderPredictions=items=>rendered.push(items);
const set=()=>{};
""" + scheduler + details + """
(async()=>{
  await refreshDetails();
  assert.deepEqual(paths,[]);
  currentPage='history';
  const first=refreshDetails();
  await refreshDetails();
  assert.deepEqual(paths,['/history/predictions?limit=100']);
  cancelRequest('details');
  currentPage='market';
  resolved.shift()({items:['stale']});
  await first;
  assert.deepEqual(rendered,[]);
  assert.equal(paths.length,1);
  currentPage='history';document.hidden=true;
  await refreshDetails();
  assert.equal(paths.length,1);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        subprocess.run([shutil.which('node'), '-e', script], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
