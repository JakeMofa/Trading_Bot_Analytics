import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import ai_advisor2


class OpenAIPhase0Tests(unittest.TestCase):
    def test_ai_is_off_without_explicit_opt_in(self):
        with patch.dict(os.environ, {'ENABLE_OPENAI_ANALYST': 'false',
                                     'OPENAI_API_KEY': 'test-key'}, clear=False), \
             patch('ai_advisor2._env_file_values', return_value={}), \
             patch('ai_advisor2.urllib.request.urlopen') as urlopen:
            self.assertFalse(ai_advisor2.is_enabled())
            self.assertIsNone(ai_advisor2.ai_suggest('test'))
            urlopen.assert_not_called()

    def test_hold_seconds_is_preserved_by_parser(self):
        parsed = ai_advisor2._parsed_result({
            'action': 'HOLD',
            'confidence': 0.6,
            'explanation': 'Wait for confirmation',
            'hold_seconds': 120,
        })
        self.assertEqual(parsed['hold_seconds'], 120)
        self.assertEqual(parsed['action'], 'HOLD')
        self.assertEqual(parsed['confidence'], 0.6)


if __name__ == '__main__':
    unittest.main()
