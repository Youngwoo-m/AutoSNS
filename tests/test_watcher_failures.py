"""실제 운영·인증 없이 임시 로그에서 실패 사건을 검증한다."""
import datetime
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'ax-console' / 'app' / 'watcher.py'
SPEC = importlib.util.spec_from_file_location('watcher_failure_test_subject', SOURCE)
watcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watcher)


class WatcherFailuresTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        console = self.root / 'ax-console'
        self.agents = self.root / 'agents'
        self.agents.mkdir()
        catalog = console / 'config' / 'automations.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({'jobs': [{'job': 'claude.sample', 'account': 'personal',
                                                'channels': [['personal', 'tistory']]}]}))
        constants = {'ROOT': self.root, 'CONSOLE': console, 'AGENTS': self.agents,
                     'DIR': console / 'data' / 'incidents',
                     'STATE': console / 'data' / 'incidents' / 'state.json', 'CATALOG': catalog}
        p = patch.multiple(watcher, **constants)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(watcher, 'now', return_value=datetime.datetime(2026, 10, 30, 12, 23))
        p.start()
        self.addCleanup(p.stop)
        self.logs = self.root / 'personal' / 'claude-jobs' / 'logs'
        self.logs.mkdir(parents=True)
        for suffix in ['launchd.out.log', 'launchd.err.log']:
            (self.logs / f'sample.{suffix}').write_text('')
        script = self.logs.parent / 'run_claude_job.sh'
        script.write_text('#!/bin/bash\nLOG="$HERE/logs/$JOB.log"\n')
        pl = {'ProgramArguments': ['/bin/bash', str(script), 'sample'],
              'StandardOutPath': str(self.logs / 'sample.launchd.out.log'),
              'StandardErrorPath': str(self.logs / 'sample.launchd.err.log')}
        (self.agents / 'com.smuds.claude.sample.plist').write_bytes(plistlib.dumps(pl))
        self.internal = self.logs / 'sample.log'

    def test_discovers_wrapper_internal_log_when_job_argument_is_last(self):
        self.internal.write_text('')
        found = watcher.job_logs(watcher.plist('claude.sample'), 'claude.sample')
        self.assertIn(str(self.internal), found)

    def include_internal_log_in_catalog(self):
        # 파서 시험은 로그 탐색 기능과 독립적으로 같은 내부 로그를 읽는다.
        data = json.loads(watcher.CATALOG.read_text())
        data['jobs'][0]['logs'] = ['personal/claude-jobs/logs/sample.log']
        watcher.CATALOG.write_text(json.dumps(data))

    def test_first_scan_records_weekly_limit_at_wrapper_timestamp(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text(
            '===== [2026-10-30 12:00:00] sample 시작 (모델 sonnet) =====\n'
            "You've hit your weekly limit · resets 2pm (Asia/Seoul)\n")
        watcher.check_logs({}, first_run=True)
        incidents = watcher.incidents('open')
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]['job'], 'claude.sample')
        self.assertEqual(incidents[0]['severity'], 'error')
        self.assertEqual(incidents[0]['first'], '2026-10-30T12:00:00')

    def test_records_monthly_spend_limit_without_exit_code(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text(
            '===== [2026-10-30 06:00:00] sample 시작 (모델 opus) =====\n'
            "You've hit your monthly spend limit\n")
        self.assertEqual(watcher.check_logs({}, first_run=True), 1)
        incidents = watcher.incidents('open')
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]['severity'], 'error')
        self.assertEqual(incidents[0]['first'], '2026-10-30T06:00:00')

    def test_success_summary_without_failed_steps_is_not_an_incident(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text(
            '===== [2026-10-30 08:00:00] sample 시작 =====\n'
            '- 기록과 알림: 작업 기록 한 줄을 남겼고 카카오톡 알림도 보냈습니다. 실패한 단계는 없습니다.\n')
        self.assertEqual(watcher.check_logs({}, first_run=True), 0)
        self.assertEqual(watcher.incidents(), [])

    def test_error_after_no_failed_steps_summary_is_still_an_incident(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text(
            '===== [2026-10-30 08:00:00] sample 시작 =====\n'
            '- 기록과 알림: 작업 기록 한 줄을 남겼고 카카오톡 알림도 보냈습니다. '
            '실패한 단계는 없습니다. 하지만 Error: 후처리 연결이 끊겼습니다.\n')
        self.assertEqual(watcher.check_logs({}, first_run=True), 1)
        self.assertEqual(watcher.incidents('open')[0]['severity'], 'error')

    def test_incremental_scan_records_nonzero_exit_without_error_text(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text('===== [2026-10-30 08:00:00] sample 시작 =====\n')
        state = {}
        watcher.check_logs(state, first_run=True)
        with self.internal.open('a') as f:
            f.write('===== [2026-10-30 08:00:06] sample 끝 (코드 1) =====\n')
        self.assertEqual(watcher.check_logs(state, first_run=False), 1)
        incidents = watcher.incidents('open')
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]['first'], '2026-10-30T08:00:06')
        self.assertEqual(watcher.check_logs(state, first_run=False), 0)
        self.assertEqual(watcher.incidents('open')[0]['count'], 1)

    def test_first_scan_ignores_old_limit_and_success_exit(self):
        self.include_internal_log_in_catalog()
        self.internal.write_text(
            '===== [2026-10-28 08:00:00] sample 시작 =====\n'
            "You've hit your weekly limit · resets 2pm (Asia/Seoul)\n"
            '===== [2026-10-30 08:00:06] sample 끝 (코드 0) =====\n')
        self.assertEqual(watcher.check_logs({}, first_run=True), 0)
        self.assertEqual(watcher.incidents(), [])

    def test_existing_bracketed_error_log_still_records(self):
        path = self.logs / 'sample.launchd.err.log'
        path.write_text('[2026-10-30T08:00:00] AuthenticationError: fixture\n')
        self.assertEqual(watcher.check_logs({}, first_run=True), 1)
        self.assertEqual(watcher.incidents('open')[0]['first'], '2026-10-30T08:00:00')

    def test_new_internal_log_does_not_replay_old_failures_on_running_watcher(self):
        self.internal.write_text(
            '===== [2026-10-28 08:00:00] sample 시작 =====\n'
            "You've hit your weekly limit · resets 2pm (Asia/Seoul)\n"
            '===== [2026-10-30 08:00:00] sample 끝 (코드 0) =====\n')
        self.assertEqual(watcher.check_logs({'offsets': {}}, first_run=False), 0)
        self.assertEqual(watcher.incidents(), [])


if __name__ == '__main__':
    unittest.main()
