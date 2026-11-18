"""Generated runtime acceptance must distinguish rollover from a missing chart."""
import time
import unittest
from unittest.mock import Mock, patch

from postgres.acceptance import current_chart


class ChartAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.old={'event_id':'price-old','kind':'price','price':'100.1'}
        self.new={'event_id':'price-new','kind':'price','price':'100.2'}
        self.state={'market':{'id':'market-old'}}
        self.worker=Mock()
        self.worker.calculate_once.return_value='snapshot-new'
        self.store=Mock()
        self.store.ingest.return_value={'duplicate':False}

    @staticmethod
    def client(*charts):
        client=Mock()
        client.get.side_effect=[Mock(**{'json.return_value':chart}) for chart in charts]
        return client

    def test_rollover_seeds_new_current_market_and_requires_its_price(self):
        client=self.client({'market':{'id':'market-new'},'points':[]},
                           {'market':{'id':'market-new'},'points':[{'price_usd':'100.2'}]})
        with patch('postgres.acceptance.generated_events',return_value=[self.new]) as generated:
            state,price,extra=current_chart(client,self.store,self.worker,self.state,self.old,
                                            time.monotonic()+10,lambda event:{'market':{'id':'market-new'}})
        self.assertEqual(state['market']['id'],'market-new')
        self.assertIs(price,self.new)
        self.assertEqual(len(extra),1)
        generated.assert_called_once()
        self.worker.discover_once.assert_called_once()
        self.worker.calculate_once.assert_called_once()

    def test_empty_same_market_is_a_failure_without_reseeding(self):
        client=self.client({'market':{'id':'market-old'},'points':[]})
        with patch('postgres.acceptance.generated_events') as generated:
            with self.assertRaisesRegex(AssertionError,'bounded chart missing current input'):
                current_chart(client,self.store,self.worker,self.state,self.old,time.monotonic()+10,Mock())
        generated.assert_not_called()
        self.store.ingest.assert_not_called()

    def test_rollover_with_wrong_price_still_fails(self):
        client=self.client({'market':{'id':'market-new'},'points':[]},
                           {'market':{'id':'market-new'},'points':[{'price_usd':'999'}]})
        with patch('postgres.acceptance.generated_events',return_value=[self.new]):
            with self.assertRaisesRegex(AssertionError,'bounded chart missing current input'):
                current_chart(client,self.store,self.worker,self.state,self.old,time.monotonic()+10,
                              lambda event:{'market':{'id':'market-new'}})


if __name__=='__main__':
    unittest.main()
