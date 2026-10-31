"""최종 검토 회귀: 임시 원장과 fake Selenium만 사용한다."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from dataclasses import replace
from datetime import timedelta

from common.operations.content_store import StoreError
from common.operations.runtime_models import SubmissionResult
from common.operations.worker_service import WorkerService
from tests.integration.test_worker_service import ServiceTests as _Production, PublicationServiceTests as _Publication
from tests.operations.test_runtime_store import NOW


class ApprovalCandidateTests(unittest.TestCase):
    setUp = _Publication.setUp
    build = _Publication.build
    service = _Publication.service
    observe_quota = _Publication.observe_quota
    adapter = _Publication.adapter

    def add_waiting(self, revoked=False):
        plan = dict(self.plan, id='waiting', schedule_slot='waiting')
        with self.store._db(True) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',
                       ('waiting', self.content['id'], self.content['revision'], 'x', 'initial',
                        'waiting', 'waiting', json.dumps(plan)))
        ctx = replace(self.ctx, schedule_slot='waiting')
        self.store.create_delivery('waiting', self.run, ctx)
        if revoked:
            self.store.record_publication_approval('waiting', 1, ctx.context_hash, 'revoked',
                                                  ctx.review_report_hashes, decision='revoked')

    def assert_waiting_does_not_starve(self, revoked):
        self.observe_quota()
        self.add_waiting(revoked)
        calls = []
        def submit(ctx, prepared, permit):
            calls.append(ctx.schedule_slot)
            return SubmissionResult('submitted', remote_id='approved-only')
        worker = WorkerService(self.service(self.adapter(submit)), clock=lambda: NOW,
                               stop_event=threading.Event())
        self.assertEqual(worker.tick(), {'state': 'processed', 'delivery_id': 'd'})
        for _ in range(2):
            self.assertEqual(worker.tick(), {'state': 'blocked', 'reason_code': 'publication_approval_required'})
        self.assertEqual(calls, ['slot'])
        self.assertEqual(self.store.get_delivery('d')['remote_id'], 'approved-only')
        self.assertEqual(self.store.get_delivery('waiting')['state'], 'queued')
        self.assertEqual(self.store.attempts('waiting'), [])
        self.assertEqual(len(self.store.attempts('d')), 1)
        with self.store._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quota_reservations WHERE delivery_id='waiting'").fetchone()[0], 0)
        self.assertTrue(all(bucket['reserved'] == 1 for bucket in self.store.quota_buckets()))

    def test_unapproved_newest_delivery_does_not_starve_approved_delivery(self):
        self.assert_waiting_does_not_starve(False)

    def test_revoked_newest_delivery_does_not_starve_approved_delivery(self):
        self.assert_waiting_does_not_starve(True)

    def test_approval_storage_failure_blocks_all_candidates(self):
        self.add_waiting()
        calls = []
        worker = WorkerService(self.service(self.adapter(lambda *args: calls.append(args))),
                               clock=lambda: NOW, stop_event=threading.Event())
        with patch.object(self.store, 'get_publication_approval', side_effect=StoreError('storage_error')):
            self.assertEqual(worker.tick(), {'state': 'blocked', 'reason_code': 'storage_error'})
        self.assertEqual(calls, [])
        self.assertEqual(self.store.attempts('d'), [])
        self.assertEqual(self.store.attempts('waiting'), [])

    def test_policy_failure_after_skipping_waiting_delivery_stays_blocked(self):
        self.add_waiting()
        calls = []
        service = self.service(self.adapter(lambda *args: calls.append(args)))
        service.policy = replace(service.policy, allowed_connection_ids=())
        worker = WorkerService(service, clock=lambda: NOW, stop_event=threading.Event())
        self.assertEqual(worker.tick(), {'state': 'blocked', 'reason_code': 'connection_not_allowed'})
        self.assertEqual(calls, [])
        self.assertEqual(self.store.attempts('d'), [])

    def test_all_waiting_service_retains_poll_delay_and_no_claim(self):
        self.store.record_publication_approval('d', self.store.get_delivery('d')['version'], self.ctx.context_hash, 'revoked',
                                              self.ctx.review_report_hashes, decision='revoked')
        stop = threading.Event()
        worker = WorkerService(self.service(self.adapter()), clock=lambda: NOW, stop_event=stop)
        before = (self.store.root / 'operations.sqlite3').read_bytes()
        with patch.object(stop, 'wait', side_effect=lambda seconds: stop.set()) as wait:
            worker.run()
        wait.assert_called_once_with(.25)
        self.assertEqual(self.store.get_run(self.run)['state'], 'queued')
        self.assertEqual(self.store.attempts('d'), [])
        self.assertEqual(before, (self.store.root / 'operations.sqlite3').read_bytes())


class PrepareResumeTests(unittest.TestCase):
    setUp = _Production.setUp
    service = _Production.service
    request = _Production.request
    submit = _Production.submit

    def test_unknown_resume_does_not_create_binding_or_occurrence(self):
        service = self.service()
        before = (self.store.root / 'operations.sqlite3').read_bytes()
        with self.assertRaisesRegex(StoreError, 'unknown_occurrence'):
            service.submit(dict(self.request(), request_kind='resume'), 'console',
                           content_id=self.snapshot['id'], expected_revision=1)
        self.assertEqual(self.production.list_bindings(), [])
        self.assertEqual(self.store.list_runs(), [])
        self.assertEqual(self.calls, [])
        self.assertEqual(before, (self.store.root / 'operations.sqlite3').read_bytes())

    def test_known_binding_unknown_occurrence_is_read_only(self):
        service = self.service()
        self.submit(service)
        before = (self.store.root / 'operations.sqlite3').read_bytes()
        request = dict(self.request(), request_kind='resume', scheduled_at_utc=(NOW + timedelta(days=1)).isoformat())
        with self.assertRaisesRegex(StoreError, 'unknown_occurrence'):
            service.submit(request, 'console', content_id=self.snapshot['id'], expected_revision=1)
        self.assertEqual(before, (self.store.root / 'operations.sqlite3').read_bytes())
        self.assertEqual(len(self.production.list_bindings()), 1)
        self.assertEqual(len(self.store.list_runs()), 1)
        self.assertEqual(self.calls, [])

    def test_known_resume_reuses_run_without_writes(self):
        service = self.service()
        queued = self.submit(service)
        before = (self.store.root / 'operations.sqlite3').read_bytes()
        replay = service.submit(dict(self.request(), request_kind='resume'), 'console',
                                content_id=self.snapshot['id'], expected_revision=1)
        self.assertEqual(queued, replay)
        self.assertEqual(before, (self.store.root / 'operations.sqlite3').read_bytes())
        self.assertEqual(self.calls, [])


class NaverIndependentDriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(__file__).resolve().parents[2] / 'dept/naver-blog-auto'
        self.events = []
        events = self.events
        class Element:
            def __init__(self, selector): self.selector = selector
            def click(self): events.append(('click', self.selector))
            def send_keys(self, value): events.append(('key', value))
        class Driver:
            current_url = ''
            def get(self, url): self.current_url = url; events.append(('get', url))
            def find_element(self, by, selector): return Element(selector)
            def execute_script(self, script): return ''
            def save_screenshot(self, path): events.append(('screenshot', path))
            def quit(self): events.append(('quit',))
        class Options:
            def add_argument(self, value): pass
            def add_experimental_option(self, *args): pass
            def set_capability(self, *args): pass
        class Wait:
            def __init__(self, driver, timeout): self.driver = driver
            def until(self, condition): return condition(self.driver)
        driver = Driver()
        def chrome(**kwargs): events.append(('driver',)); return driver
        conditions = SimpleNamespace(
            element_to_be_clickable=lambda locator: lambda d: d.find_element(*locator),
            presence_of_element_located=lambda locator: lambda d: d.find_element(*locator),
            frame_to_be_available_and_switch_to_it=lambda locator: lambda d: True)
        self.modules = {}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.chrome',
                     'selenium.webdriver.chrome.options', 'selenium.webdriver.common',
                     'selenium.webdriver.common.by', 'selenium.webdriver.common.keys',
                     'selenium.webdriver.support', 'selenium.webdriver.support.ui', 'common'):
            self.modules[name] = ModuleType(name)
        self.modules['selenium'].webdriver = self.modules['selenium.webdriver']
        self.modules['selenium.webdriver'].Chrome = chrome
        self.modules['selenium.webdriver.chrome.options'].Options = Options
        self.modules['selenium.webdriver.common.by'].By = SimpleNamespace(ID='id', XPATH='xpath')
        self.modules['selenium.webdriver.common.keys'].Keys = SimpleNamespace(ENTER='enter')
        self.modules['selenium.webdriver.support'].expected_conditions = conditions
        self.modules['selenium.webdriver.support.ui'].WebDriverWait = Wait
        self.modules['common'].PROFILE_DIR = '/fixture/profile-never-opened'
        self.modules['common'].LOGS_DIR = self.tmp.name
        self.modules['common'].log = lambda *args: None
        self.driver = driver

    def load(self, name, filename):
        spec = importlib.util.spec_from_file_location(name, self.root / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_click_helper_with_independent_driver(self):
        with patch.dict(sys.modules, self.modules):
            leaf = self.load('fixture_publish_naver', 'publish_naver.py')
            self.assertEqual(self.events, [])
            self.assertTrue(leaf.click_if_present(self.driver, 'xpath', 'fixture-button'))
        self.assertEqual(self.events, [('click', 'fixture-button')])

    def test_tag_editor_own_driver_can_click_and_save_screenshot(self):
        with patch.dict(sys.modules, self.modules), patch.dict(os.environ), patch.object(sys, 'path', list(sys.path)):
            leaf = self.load('fixture_publish_naver', 'publish_naver.py')
            self.assertEqual(self.events, [])
            with patch.dict(sys.modules, {'publish_naver': leaf}):
                caller = self.load('fixture_naver_add_tags', 'naver_add_tags.py')
                # 실함수/자체 build_driver를 유지하고 Selenium I/O와 시간 대기만 대체한다.
                with patch.object(caller.time, 'sleep'):
                    self.assertEqual(caller.add_tags('fixture-post', ['fixture-tag'], False), 'dry')
        self.assertEqual(self.events[0], ('driver',))
        clicks = [event[1] for event in self.events if event[0] == 'click']
        self.assertEqual(len(clicks), 2)
        self.assertIn("contains(@class,'publish')", clicks[1])
        self.assertIn(('key', 'fixture-tag'), self.events)
        shots = [event[1] for event in self.events if event[0] == 'screenshot']
        self.assertEqual(len(shots), 1)
        self.assertEqual(Path(shots[0]).parent, Path(self.tmp.name))
        self.assertTrue(shots[0].endswith('_tags_fixture-post.png'))
        self.assertEqual(self.events[-1], ('quit',))


# 재사용 fixture의 테스트가 이 모듈에서 중복 수집되지 않도록 한다.
del _Production, _Publication
