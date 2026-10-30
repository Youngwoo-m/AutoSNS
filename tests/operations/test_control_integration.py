"""임시 원본 루트에서 별도 프로세스의 계정 잠금 공유를 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from common.shared.axlock import AxLock, LockPaths


PROBE = '''
import json, sys
from common.shared.axlock import AxLock, LockPaths, Timeout
lock = AxLock(LockPaths.from_root(sys.argv[1]), process_probe=lambda _: False)
try:
    with lock.hold([sys.argv[2]], job='child-lock-probe', wait=0):
        print(json.dumps({'acquired': True}))
except Timeout:
    print(json.dumps({'acquired': False}))
'''


class CrossProcessControlTests(unittest.TestCase):
    def test_dept_aliases_contend_across_processes_and_personal_is_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = AxLock(LockPaths.from_root(root), process_probe=lambda _: False)

            def acquired(resource):
                result = subprocess.run(
                    [sys.executable, '-c', PROBE, str(root), resource],
                    cwd=Path(__file__).resolve().parents[2],
                    capture_output=True, text=True, timeout=10, check=True,
                )
                self.assertEqual(result.stderr, '')
                return json.loads(result.stdout)['acquired']

            with lock.hold(['profile:naver'], job='parent-lock-probe', wait=0):
                self.assertFalse(acquired('profile:tiktok'))
                self.assertFalse(acquired('profile:youtube-dept'))
                self.assertTrue(acquired('profile:tistory'))
            self.assertTrue(acquired('profile:tiktok'))
