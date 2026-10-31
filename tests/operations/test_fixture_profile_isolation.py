"""관문 fixture는 사용자 브라우저와 격리하되 파일 잠금은 실제로 사용한다."""
import unittest
from unittest.mock import patch

from tests.operations import test_publication_gate as gate
from common.shared import axlock


class FixtureProfileIsolationTests(unittest.TestCase):
    def test_fixture_never_probes_host_processes_and_keeps_real_flock(self):
        fixture = gate.GateFixture(methodName='test_plan_read_preserves_bytes')
        self.addCleanup(fixture.doCleanups)
        with patch.object(axlock.subprocess, 'run',
                          side_effect=AssertionError('host process probe escaped fixture')):
            fixture.setUp()
            permit = fixture.ready()
            self.assertIsNotNone(permit)
            competitor = gate.AxLock(fixture.store.locks.paths, process_probe=lambda resource: False)
            with fixture.store.locks.hold(['profile:tistory'], job='fixture-owner', wait=0):
                with self.assertRaises(axlock.Timeout):
                    with competitor.hold(['profile:tistory'], job='fixture-contender', wait=0):
                        self.fail('competing fixture acquired an already held profile')
