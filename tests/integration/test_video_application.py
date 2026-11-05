"""제작 application의 독립 영상 worker lifecycle. 가짜 server/worker만 쓰며 소켓·렌더·DB·외부 호출이 없다.

VideoTaskService는 실제 인스턴스를 I/O 없는 가짜 의존성으로 만들어 타입·root 검증을 실제와 같게 한다.
"""
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from common.operations.content_store import ContentStore
from common.operations.media_plans import MediaPlanStore
from common.operations.models import ContractError
from common.operations.video_tasks import VideoTaskService, VideoTaskStore
from tests.integration import test_production_application as base

production_application = base.production_application
build = base.build
AppError = base.AppError
WAIT = base.WAIT


class FakeVideoWorker(base.FakeWorker):
    """base.FakeWorker에 service 연결과 'HTTP 시작 뒤 실패' 모드를 더한 영상 worker."""
    def __init__(self, service, mode='wait'):
        super().__init__(mode)
        self.service = service

    def run(self, once=False):
        if self.mode != 'fail_on_release':
            return super().run(once)
        self.run_calls += 1
        self.started.set()
        try:
            self.release.wait(WAIT)
            raise RuntimeError('video boom')
        finally:
            self.finished.set()


class VideoApplicationTests(unittest.TestCase):
    runtime = base.ProductionApplicationTests.runtime
    factory = base.ProductionApplicationTests.factory
    serve_in_thread = base.ProductionApplicationTests.serve_in_thread

    def setUp(self):
        base.ProductionApplicationTests.setUp(self)
        self.video_workers, self.factory_services = [], []

    # --- 가짜 주입물 ------------------------------------------------------
    def service(self, enabled=True, store_root=None, content_root=None, plan_root=None):
        root = self.config.workspace_root
        contents = ContentStore(content_root or root)
        plans = MediaPlanStore(content_root or root, contents)
        store = VideoTaskStore(store_root or root)
        if plan_root is not None:
            plans.root = Path(plan_root)  # MediaPlanStore 생성자는 불일치를 막으므로 생성 뒤에 어긋나게 한다.
        return VideoTaskService(store, contents, plans, enabled=enabled, runner_factory=lambda **kwargs: None)

    def video_factory(self, mode='wait', shared=None):
        def make(service):
            self.factory_services.append(service)
            worker = shared if shared is not None else FakeVideoWorker(service, mode)
            self.video_workers.append(worker)
            return worker
        return make

    def app(self, runtime=None, service=None, factory=None, **overrides):
        args = dict(runtime=runtime or self.runtime(), config=self.config, planning_registry=self.registry,
                    web_root=Path('/fixture/web'), server_factory=self.factory(),
                    video_task_service=service if service is not None else self.service(),
                    video_worker_factory=factory or self.video_factory())
        return build(**dict(args, **overrides))

    def named_threads(self, name):
        return [t for t in threading.enumerate() if t.name == name]

    # --- 시험 -------------------------------------------------------------
    def test_build_creates_worker_object_only_and_validates_before_socket(self):
        service, runtime = self.service(), self.runtime()
        before = threading.active_count()
        app = self.app(runtime, service)
        worker = self.video_workers[0]
        self.assertEqual(threading.active_count(), before)
        self.assertEqual(self.factory_services, [service])
        self.assertIs(app.video_worker, worker)
        self.assertEqual((app.video_worker_state, app.video_worker_error, app.worker_state), ('not_started', None, 'not_started'))
        self.assertEqual((worker.run_calls, runtime.worker.run_calls, self.servers[0].serve_calls), (0, 0, 0))
        self.assertIs(self.factory_calls[0][2]['video_task_service'], service)
        # disabled/None이면 worker를 만들지 않는다. server에는 서비스가 그대로 전달된다.
        disabled = self.app(service=self.service(enabled=False))
        self.assertIsNone(disabled.video_worker)
        self.assertIs(self.factory_calls[1][2]['video_task_service'].enabled, False)
        none_app = build(runtime=self.runtime(), config=self.config, planning_registry=self.registry,
                         web_root=Path('/fixture/web'), server_factory=self.factory())
        self.assertIsNone(none_app.video_worker)
        self.assertNotIn('video_task_service', self.factory_calls[2][2])
        self.assertEqual(len(self.video_workers), 1)
        # 잘못된 입력은 소켓을 만들기 전에 거부한다.
        servers = len(self.servers)
        other = Path('/other/managed')
        cases = [
            ('invalid_video_service', dict(service=object())),
            ('video_config_mismatch', dict(service=self.service(store_root=other))),
            ('video_config_mismatch', dict(service=self.service(content_root=other))),
            ('video_config_mismatch', dict(service=self.service(plan_root=other))),
            ('invalid_video_worker_factory', dict(factory='not callable')),
            ('video_worker_mismatch', dict(factory=lambda service: FakeVideoWorker(object()))),
            ('invalid_video_worker', dict(factory=lambda service: type('NoStop', (), {'service': service, 'run': lambda self: 0})())),
            ('invalid_video_worker', dict(factory=lambda service: type('NoRun', (), {'service': service, 'stop_event': threading.Event()})())),
        ]
        for code, overrides in cases:
            with self.subTest(code=code):
                with self.assertRaises(ContractError) as caught:
                    self.app(**overrides)
                self.assertEqual(caught.exception.code, code)
        self.assertEqual(len(self.servers), servers)

    def test_video_only_serve_runs_independently_of_disabled_primary(self):
        runtime = self.runtime(enabled=False)
        app = self.app(runtime)
        worker = self.video_workers[0]
        thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertTrue(worker.started.wait(WAIT))
        self.assertEqual(len(self.named_threads('video-production-worker')), 1)
        self.assertEqual(self.named_threads('production-worker'), [])
        self.assertEqual((app.worker_state, app.video_worker_state), ('not_started', 'running'))
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome, {'result': None})
        self.assertTrue(worker.stop_event.is_set())
        self.assertFalse(runtime.worker.stop_event.is_set())
        self.assertEqual(runtime.worker.run_calls, 0)
        self.assertEqual((app.state, app.worker_state, app.video_worker_state, self.servers[0].close_calls),
                         ('closed', 'not_started', 'stopped', 1))
        self.assertEqual(self.named_threads('video-production-worker'), [])

    def test_normal_shutdown_drains_both_workers_before_closing_server(self):
        runtime = self.runtime()
        app = self.app(runtime)
        worker = self.video_workers[0]
        thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertTrue(runtime.worker.started.wait(WAIT) and worker.started.wait(WAIT))
        self.assertEqual((len(self.named_threads('production-worker')), len(self.named_threads('video-production-worker'))), (1, 1))
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome, {'result': None})
        self.assertTrue(runtime.worker.stop_event.is_set() and worker.stop_event.is_set())
        self.assertTrue(runtime.worker.finished.is_set() and worker.finished.is_set())
        self.assertEqual((app.state, app.worker_state, app.video_worker_state, self.servers[0].close_calls),
                         ('closed', 'stopped', 'stopped', 1))
        self.assertEqual(self.named_threads('production-worker') + self.named_threads('video-production-worker'), [])

    def test_video_failure_before_http_starts_skips_serving(self):
        runtime = self.runtime()
        app = self.app(runtime, factory=self.video_factory('fail'))
        worker = self.video_workers[0]
        original = app._start_workers

        def start_and_wait_for_failure():
            original()
            app._video_thread.join(WAIT)  # HTTP 시작 확인 전에 영상 worker 실패가 기록되게 한다.
        app._start_workers = start_and_wait_for_failure
        with self.assertRaises(AppError) as caught:
            app.serve_forever()
        self.assertEqual(caught.exception.code, 'video_worker_failed')
        self.assertIsInstance(app.video_worker_error, RuntimeError)
        self.assertIs(caught.exception.__cause__, app.video_worker_error)
        self.assertEqual(self.servers[0].serve_calls, 0)
        self.assertTrue(runtime.worker.stop_event.is_set())  # 함께 시작된 primary도 drain
        self.assertEqual((app.state, app.worker_state, app.video_worker_state, self.servers[0].close_calls),
                         ('closed', 'stopped', 'failed', 1))
        self.assertEqual(worker.run_calls, 1)
        self.assertEqual(self.named_threads('production-worker') + self.named_threads('video-production-worker'), [])

    def test_video_failure_after_http_stops_server_and_primary(self):
        runtime = self.runtime()
        app = self.app(runtime, factory=self.video_factory('fail_on_release'))
        worker = self.video_workers[0]
        outcome_thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertTrue(worker.started.wait(WAIT))
        worker.release.set()
        outcome_thread.join(WAIT)
        self.assertFalse(outcome_thread.is_alive())
        self.assertEqual(outcome['error'].code, 'video_worker_failed')
        self.assertIs(outcome['error'].__cause__, app.video_worker_error)
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual((app.state, app.worker_state, app.video_worker_state, self.servers[0].close_calls),
                         ('closed', 'stopped', 'failed', 1))
        # primary 실패는 기존 코드를 유지한다.
        primary = self.app(self.runtime(mode='fail'), factory=self.video_factory())
        with self.assertRaises(AppError) as caught:
            primary.serve_forever()
        self.assertEqual(caught.exception.code, 'worker_failed')
        self.assertEqual((primary.worker_state, primary.video_worker_state), ('failed', 'stopped'))

    def test_stuck_video_worker_is_reported_and_claim_is_kept(self):
        runtime = self.runtime()
        service = self.service()
        app = self.app(runtime, service, factory=self.video_factory('ignore_stop'))
        worker = self.video_workers[0]
        thread, outcome = self.serve_in_thread(app, join_timeout=0.05)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertTrue(worker.started.wait(WAIT))
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome['error'].code, 'video_worker_not_stopped')
        self.assertEqual((app.state, app.worker_state, app.video_worker_state, self.servers[0].close_calls),
                         ('closed', 'stopped', 'stuck', 1))
        self.assertTrue(worker.stop_event.is_set())  # 되돌리지 않는다.
        self.assertEqual(len(self.named_threads('video-production-worker')), 1)
        with self.assertRaises(AppError):
            app.serve_forever()
        # claim이 남아 같은 worker를 다른 application이 시작할 수 없다. 이 거부 때 primary도 시작하지 않는다.
        again_runtime = self.runtime()
        again = self.app(again_runtime, service, factory=self.video_factory(shared=worker))
        with self.assertRaises(AppError) as caught:
            again.serve_forever()
        self.assertEqual(caught.exception.code, 'video_worker_in_use')
        self.assertEqual(again_runtime.worker.run_calls, 0)
        worker.release.set()
        self.assertTrue(worker.finished.wait(WAIT))
        for stuck in self.named_threads('video-production-worker'):
            stuck.join(WAIT)
        self.assertEqual(worker.run_calls, 1)

    def test_duplicate_and_reused_stopped_video_worker_are_refused(self):
        service = self.service()
        first_runtime = self.runtime()
        first = self.app(first_runtime, service)
        worker = self.video_workers[0]
        thread, _ = self.serve_in_thread(first)
        self.assertTrue(worker.started.wait(WAIT))
        second_runtime = self.runtime()
        second = self.app(second_runtime, service, factory=self.video_factory(shared=worker))
        with self.assertRaises(AppError) as caught:
            second.serve_forever()
        self.assertEqual(caught.exception.code, 'video_worker_in_use')
        self.assertEqual((second.state, second.video_worker_state, self.servers[-1].close_calls, self.servers[-1].serve_calls),
                         ('closed', 'not_started', 1, 0))
        self.assertEqual(second_runtime.worker.run_calls, 0)  # primary도 시작하지 않았다.
        self.assertFalse(second_runtime.worker.stop_event.is_set() or worker.stop_event.is_set())
        first.request_shutdown()
        thread.join(WAIT)
        # 정지된 worker를 다시 쓰면 stop_event를 되돌리지 않고 거부한다(claim은 정상 종료로 풀린 상태).
        self.assertTrue(worker.stop_event.is_set())
        third_runtime = self.runtime()
        third = self.app(third_runtime, service, factory=self.video_factory(shared=worker))
        with self.assertRaises(AppError) as caught:
            third.serve_forever()
        self.assertEqual(caught.exception.code, 'video_worker_stopped')
        self.assertEqual((third_runtime.worker.run_calls, worker.run_calls, self.servers[-1].serve_calls), (0, 1, 0))
        self.assertTrue(worker.stop_event.is_set())

    def test_second_thread_start_failure_drains_primary_and_closes_server(self):
        runtime, service = self.runtime(), self.service()
        app = self.app(runtime, service)
        worker = self.video_workers[0]
        real_start, calls = threading.Thread.start, []

        def start(thread):
            calls.append(thread.name)
            if len(calls) == 2:
                raise RuntimeError('no second thread')
            return real_start(thread)
        with patch.object(production_application.threading.Thread, 'start', start):
            with self.assertRaises(RuntimeError):
                app.serve_forever()
        self.assertEqual(calls, ['production-worker', 'video-production-worker'])
        self.assertTrue(runtime.worker.finished.wait(WAIT))
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual((worker.run_calls, self.servers[0].serve_calls, self.servers[0].close_calls), (0, 0, 1))
        self.assertEqual((app.state, app.worker_state, app.video_worker_state), ('closed', 'stopped', 'not_started'))
        self.assertEqual(self.named_threads('production-worker') + self.named_threads('video-production-worker'), [])
        # 시작하지 못한 영상 worker의 claim은 풀려 있으므로 새 application에서 시작할 수 있다.
        retry = self.app(self.runtime(), service, factory=self.video_factory(shared=worker))
        thread, _ = self.serve_in_thread(retry)
        self.assertTrue(worker.started.wait(WAIT))
        retry.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(worker.run_calls, 1)

    def test_close_before_serve_starts_no_thread_and_is_idempotent(self):
        runtime = self.runtime()
        service = self.service()
        app = self.app(runtime, service)
        worker = self.video_workers[0]
        before = threading.active_count()
        app.close()
        app.close()
        self.assertEqual((app.state, self.servers[0].close_calls, threading.active_count()), ('closed', 1, before))
        with self.assertRaises(AppError) as caught:
            app.serve_forever()
        self.assertEqual(caught.exception.code, 'application_closed')
        self.assertEqual((worker.run_calls, runtime.worker.run_calls), (0, 0))
        self.assertFalse(worker.stop_event.is_set() or runtime.worker.stop_event.is_set())
        self.assertEqual((app.video_worker_state, app.video_worker_error), ('not_started', None))


if __name__ == '__main__':
    unittest.main()
