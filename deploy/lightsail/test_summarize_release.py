import unittest
import summarize_release as s
class Tests(unittest.TestCase):
    def test_only_known_metadata_survives(self):
        value=s.sanitize({'status':'STOP','release':'a'*40,'secret':'dummy-secret',
            'reason':'sensitive arbitrary text','allocation':{'headroom_mib':500,'payload':'private'},
            'checks':{'identity':{'private':'hidden'},'checks':[{'check':'quick_check','status':'PASS','payload':'hidden'}]}})
        self.assertNotIn('secret',value);self.assertNotIn('reason',value)
        self.assertEqual(value['allocation']['headroom_mib'],500)
        self.assertNotIn('payload',str(value));self.assertNotIn('identity',value['checks'])
    def test_arbitrary_status_cannot_be_success(self):self.assertNotIn('status',s.sanitize({'status':'secret text'}))
