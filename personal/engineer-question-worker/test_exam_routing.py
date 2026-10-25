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

if __name__ == '__main__':
    unittest.main()
