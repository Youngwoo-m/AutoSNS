import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class ExamRoutingTest(unittest.TestCase):
    def config(self, *args):
        run = subprocess.run([sys.executable, str(ROOT/'queue.py'), *args, 'config'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_civil_requests_and_answers_are_separate_from_default_survey(self):
        survey = self.config()
        civil = self.config('--exam', 'civil')
        self.assertEqual(survey['form'], 'engineer-questions')
        self.assertEqual(civil['form'], 'civil-engineer-questions')
        self.assertNotEqual(survey['state'], civil['state'])
        self.assertTrue(civil['published'].endswith('/civil-questions/published.json'))
        self.assertTrue(survey['published'].endswith('/questions/published.json'))
    def test_building_has_own_form_state_and_list(self):
        building = self.config('--exam', 'building')
        self.assertEqual(building['form'], 'building-engineer-questions')
        self.assertTrue(building['state'].endswith('building-state.json'))
        self.assertTrue(building['published'].endswith('/building-questions/published.json'))
    def test_safety_has_own_form_state_and_list(self):
        safety = self.config('--exam', 'safety')
        self.assertEqual(safety['exam'], '건설안전기술사')
        self.assertEqual(safety['form'], 'safety-engineer-questions')
        self.assertTrue(safety['state'].endswith('safety-state.json'))
        self.assertTrue(safety['published'].endswith('/safety-questions/published.json'))

if __name__ == '__main__':
    unittest.main()
