"""owner 분기 제거 시 legacy 실행/개인 fallback이 재발하는 fixture 시험."""
import ast
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from common.operations.models import Registry, Connection
from common.operations.runtime_models import ExecutionPolicy
from common.operations.runtime_store import RuntimeStore
from common.operations import entrypoints

ROOT = Path(__file__).resolve().parents[2]


def functions(path, names, namespace):
    """legacy module top-level/import를 실행하지 않고 실제 함수 본문만 로드한다."""
    tree = ast.parse((ROOT / path).read_text())
    nodes = [x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), namespace)
    return namespace


class OwnerFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RuntimeStore(self.root / 'runtime')
        self.store.initialize()
        self.key = ('personal', 'blogger', 'publish')
        self.job = dict(owner_account_id='personal', execution_owner='managed', executor_id='fixture',
                        schedule_owner='console', enabled=True, policy_revision='p', connection_id='target')
        self.registry = Registry('fixture', {'personal': {}}, {}, {},
            {'target': Connection('target', 'personal', 'blogger', enabled=True)}, {'fixture': self.job}, {'p': {}}, {})
        executor = ExecutorSpec('fixture', ('fixture',), ('submit',), '/usr/bin/python3', Path('/tmp'),
                                'tests.fixture', ('submit',), ())
        self.catalog = ExecutionCatalog({'fixture': executor}, {
            'console.fixture': {'job_ids': ['fixture'], 'source': 'console', 'legacy_allowed': True}})
        self.services = dict(registry=self.registry, catalog=self.catalog, store=self.store, policy=ExecutionPolicy(),
            action_routes={self.key: dict(job_ids=('fixture',), caller_id='console.fixture',
                managed_eligible=True, inventory_complete=True)},
            request=dict(job_id='fixture', scheduled_at_utc='2026-10-30T01:00:00Z', phase='submit',
                         source='console', request_kind='new_publication', mode='dry'))

    def route(self, services=None, key=None):
        return entrypoints.route_legacy_action(key or self.key, services=services or self.services)

    def test_managed_console_does_not_spawn_or_write_done(self):
        ns = dict(threading=threading, LOCK=threading.Lock(), ROOT=self.root, RUNS=self.root / 'runs',
            CONSOLE=self.root, Path=Path, json=json, subprocess=subprocess,
            route_console_action=lambda task, **kw: self.route(),
            now=lambda: __import__('datetime').datetime(2026, 10, 30, 10),
            find_action=lambda *args: {'cmd': ['/forbidden'], 'label': 'fixture'},
            run_publish=lambda *args: self.fail('managed publish가 legacy로 진입'))
        tasks = [dict(id='t', account='personal', channel='blogger', action='publish', status='scheduled', title='fixture')]
        ns.update(load=lambda: [dict(x) for x in tasks], save=lambda value: tasks.__setitem__(slice(None), value))
        functions('ax-console/app/server.py', {'run_task', '_record_managed_task'}, ns)
        with patch('subprocess.run', side_effect=AssertionError('managed subprocess 금지')) as spawn:
            result = ns['run_task']('t')
            again = ns['run_task']('t')
        self.assertEqual(spawn.call_count, 0)
        self.assertEqual(tasks[0]['status'], 'queued')
        self.assertEqual(tasks[0]['run_id'], result['run_id'])
        self.assertEqual(result['run_id'], again['run_id'])
        self.assertFalse((self.root / 'runs').exists())
        self.assertEqual(len(self.store.list_runs()), 1)

    def test_direct_publish_cli_is_fenced(self):
        ns = dict(sys=sys, os=__import__('os'), json=json,
            route_legacy_action=lambda key, **kw: self.route(), ADAPTERS={'blogger': lambda *a: self.fail('legacy 실행')})
        functions('ax-console/app/publishers.py', {'main'}, ns)
        with patch.object(sys, 'argv', ['publishers.py', '/missing', 'personal', 'blogger']), contextlib.redirect_stdout(io.StringIO()) as out:
            ns['main']()
        self.assertEqual(json.loads(out.getvalue())['status'], 'queued')
        self.assertEqual(len(self.store.list_runs()), 1)

    def test_wrapper_preserves_first_axlock_line(self):
        # 운영 wrapper는 실행하지 않는다. 동일한 axlock→owner guard→본문 구조만 fixture로 검증한다.
        script = self.root / 'wrapper.sh'
        marker = self.root / 'legacy'
        script.write_text('#!/bin/sh\n[ -z "$AX_LOCKED" ] && exec env AX_LOCKED=1 "$0" "$@"\n'
            + f'"{sys.executable}" "$1" || exit $?\nprintf legacy >> "{marker}"\n')
        script.chmod(0o700)
        guard = self.root / 'guard.py'
        guard.write_text('import sys\nsys.path.insert(0, ' + repr(str(ROOT)) + ')\n'
            'from common.operations.legacy_fences import guard_legacy_action\n'
            'guard_legacy_action(("invalid", "blogger", "publish"))\n')
        done = subprocess.run([str(script), str(guard)], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse(marker.exists())
        paths = ['personal/claude-jobs/run_claude_job.sh', 'dept/naver-blog-auto/run_geoai.sh',
            'dept/naver-blog-auto/run_geoai_evening.sh', 'dept/naver-blog-auto/run_jobs.sh',
            'dept/youtube-shorts-auto/run_tiktok_queue.sh', 'dept/disaster-shorts/tools/run_crosspost.sh']
        for path in paths:
            tree = (ROOT / path).read_text().splitlines()
            self.assertTrue(tree[2].startswith('[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py '))
            self.assertIn('legacy_fences.py', '\n'.join(tree[3:11]))

    def test_legacy_route_is_unchanged(self):
        services = dict(self.services, registry=replace(self.registry, jobs={'fixture': dict(self.job, execution_owner='legacy')}))
        result = self.route(services)
        self.assertEqual(result['route'], 'legacy')
        fixture = self.root / 'legacy.sh'
        fixture.write_text('#!/bin/sh\nprintf legacy\n')
        calls = 0
        if result['route'] == 'legacy':
            done = subprocess.run(['/bin/sh', str(fixture)], capture_output=True, text=True)
            calls += 1
        self.assertEqual((done.stdout, calls), ('legacy', 1))
        self.assertEqual(self.store.list_runs(), [])

    def test_inventory_incomplete_blocks_managed_cutover(self):
        for change in ({'inventory_complete': False}, {'managed_eligible': False}):
            row = dict(self.services['action_routes'][self.key], **change)
            with self.assertRaises(StoreError):
                self.route(dict(self.services, action_routes={self.key: row}))
        with self.assertRaises(StoreError):
            self.route(key=('personal', 'blogger', 'new-unknown-action'))
        self.assertEqual(self.store.list_runs(), [])

    def test_spoofed_request_never_reaches_server_submit(self):
        attempted = []
        services = dict(self.services, submit=lambda *args: attempted.append(args) or {'run_id': 'bad'})
        services['request'] = dict(services['request'], source='launchd')
        with self.assertRaises(StoreError) as caught:
            self.route(services)
        self.assertEqual(caught.exception.code, 'source_mismatch')
        self.assertEqual(attempted, [])

    def test_isolated_cli_guard_resolves_worktree_root(self):
        from common.shared import owner_fence
        expected = str(ROOT / 'common/operations/legacy_fences.py')
        def fixture_process(argv, **kwargs):
            self.assertEqual(argv[:3], [sys.executable, '-I', expected])
            self.assertEqual(argv[3:], ['personal', 'blogger', 'publish-cli'])
            return subprocess.CompletedProcess(argv, 0, '{"route":"legacy"}', '')
        with patch.object(owner_fence.subprocess, 'run', side_effect=fixture_process):
            result = owner_fence.require_legacy_cli(('personal', 'blogger', 'publish-cli'))
        self.assertEqual(result['route'], 'legacy')

    def test_imported_tistory_main_is_fenced_before_argument_or_file_access(self):
        # tistory_patch는 tp.main()을 호출한다. __main__ guard만으로는 보호되지 않는다.
        class Blocked(Exception):
            pass
        def stop(key):
            self.assertEqual(key, ('personal', 'tistory', 'tistory-post-cli'))
            raise Blocked()
        ns = {}
        functions('personal/naver-blog-auto/tistory_post.py', {'main'}, ns)
        with patch('shared.owner_fence.require_legacy_cli', side_effect=stop):
            with self.assertRaises(Blocked):
                ns['main']()

    def test_youtube_public_cli_checks_both_possible_owners_before_legacy_import(self):
        # SMUDS_EDITION/config 때문에 일반 CLI도 개인 업로드가 될 수 있다.
        tree = ast.parse((ROOT / 'dept/youtube-shorts-auto/youtube_upload.py').read_text())
        guard = next(x for x in tree.body if isinstance(x, ast.If))
        calls = []
        ns = dict(__name__='__main__', __file__=str(ROOT / 'dept/youtube-shorts-auto/youtube_upload.py'),
                  sys=sys, os=__import__('os'))
        with patch('shared.owner_fence.require_legacy_cli', side_effect=lambda key: calls.append(key)):
            exec(compile(ast.Module(body=[guard], type_ignores=[]), '<public-cli-fixture>', 'exec'), ns)
        self.assertEqual(calls, [('dept', 'youtube', 'youtube-upload-cli'), ('personal', 'youtube', 'youtube-upload-cli')])

    def test_all_known_actions_remain_legacy_without_changing_registry(self):
        from common.operations.legacy_fences import ACTION_ROUTES, build_legacy_catalog, inventory_allows_managed
        from common.operations.registry import load_registry
        path = ROOT / 'ax-console/config/operations.json'
        before = path.read_bytes()
        registry = load_registry(path)
        services = dict(registry=registry, catalog=build_legacy_catalog())
        with patch('subprocess.Popen', side_effect=AssertionError('등록 조회는 외부 실행 금지')):
            for key, row in ACTION_ROUTES.items():
                result = entrypoints.route_legacy_action(key, services=services)
                self.assertEqual(result['route'], 'legacy', key)
                for job in row['job_ids']:
                    self.assertFalse(inventory_allows_managed(job), job)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_action_and_missing_job_never_fall_back(self):
        from common.operations.legacy_fences import build_legacy_catalog
        services = dict(self.services, registry=replace(self.registry, jobs={}))
        with self.assertRaises(StoreError) as caught:
            self.route(services)
        self.assertEqual(caught.exception.code, 'unknown_job')
        self.assertEqual(self.store.list_runs(), [])

    def test_direct_cli_guard_failure_blocks_legacy(self):
        from common.shared import owner_fence
        bad_results = [subprocess.CompletedProcess([], 1, '{"error":"entrypoint_inventory_incomplete"}', ''),
                       subprocess.CompletedProcess([], 0, 'not-json', '')]
        for done in bad_results:
            with patch.object(owner_fence.subprocess, 'run', return_value=done), contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as caught:
                    owner_fence.require_legacy_cli(('personal', 'blogger', 'publish-cli'))
            self.assertEqual(caught.exception.code, 1)
            self.assertEqual(json.loads(out.getvalue())['status'], 'error')

    def test_invalid_account_rejected_before_personal_fallback(self):
        with self.assertRaises(StoreError) as caught:
            self.route(key=('dept-typo', 'blogger', 'publish'))
        self.assertEqual(caught.exception.code, 'unknown_account')
        ns = dict(sys=sys, os=__import__('os'), json=json,
            route_legacy_action=entrypoints.route_legacy_action,
            ADAPTERS={'blogger': lambda *a: self.fail('개인 fallback 금지')})
        functions('ax-console/app/publishers.py', {'main'}, ns)
        with patch.object(sys, 'argv', ['publishers.py', '/missing', 'typo', 'blogger']), contextlib.redirect_stdout(io.StringIO()) as out:
            ns['main']()
        self.assertEqual(json.loads(out.getvalue())['status'], 'error')
        self.assertEqual(self.store.list_runs(), [])


if __name__ == '__main__':
    unittest.main()
