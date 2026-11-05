"""제작 전용 웹 application lifecycle. 가짜 server/worker만 사용하며 소켓·DB·외부 호출이 없다."""
import importlib.util
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from common.operations.bootstrap_config import BootstrapConfig
from common.operations.models import ContractError, Registry
from common.operations.production_startup import ProductionRuntime

APP = Path(__file__).resolve().parents[2] / 'ax-console' / 'app' / 'production_application.py'
SPEC = importlib.util.spec_from_file_location('production_application_under_test', APP)
production_application = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_application)
build = production_application.build_production_application
AppError = production_application.ProductionApplicationError

WAIT = 5


class FakeServer:
    def __init__(self, serve_error=None):
        self.serve_error = serve_error
        self.entered, self.stop, self.done = threading.Event(), threading.Event(), threading.Event()
        self.serve_calls = self.close_calls = 0
        self.server_address = ('127.0.0.1', 0)

    def serve_forever(self):
        self.serve_calls += 1
        self.entered.set()
        try:
            if self.serve_error is not None:
                raise self.serve_error
            self.stop.wait(WAIT)
        finally:
            self.done.set()

    def shutdown(self):
        self.stop.set()
        if self.entered.is_set():
            self.done.wait(WAIT)

    def server_close(self):
        self.close_calls += 1


class FakeWorker:
    """기본은 stop_event가 설정될 때까지 도는 worker. mode로 실패/정지 무시를 흉내낸다."""
    def __init__(self, mode='wait'):
        self.mode = mode
        self.stop_event = threading.Event()
        self.started, self.release, self.finished = threading.Event(), threading.Event(), threading.Event()
        self.run_calls = 0
        self.services = None

    def run(self, once=False):
        self.run_calls += 1
        self.started.set()
        try:
            if self.mode == 'fail':
                raise RuntimeError('worker boom')
            if self.mode == 'ignore_stop':
                self.release.wait(WAIT)
            else:
                self.stop_event.wait(WAIT)
            return 0
        finally:
            self.finished.set()


class ProductionApplicationTests(unittest.TestCase):
    def setUp(self):
        root = Path('/fixture')
        self.config = BootstrapConfig(code_root=root / 'code', source_root=root / 'source',
                                      workspace_root=root / 'managed', registry_path=root / 'registry.json')
        self.registry = Registry('rev', {}, {}, {}, {}, {}, {}, {})
        self.servers, self.factory_calls = [], []

    def runtime(self, enabled=True, mode='wait', store_root=None, lock_root=None):
        worker = FakeWorker(mode)
        service = SimpleNamespace(policy=SimpleNamespace(enabled=enabled),
            store=SimpleNamespace(root=store_root or self.config.workspace_root),
            locks=SimpleNamespace(paths=SimpleNamespace(root=lock_root or self.config.source_root)))
        worker.services = service
        return ProductionRuntime(service, worker)

    def factory(self, serve_error=None):
        def make(host, port, **kwargs):
            self.factory_calls.append((host, port, kwargs))
            server = FakeServer(serve_error)
            self.servers.append(server)
            return server
        return make

    def app(self, runtime=None, serve_error=None, **overrides):
        args = dict(runtime=runtime or self.runtime(), config=self.config, planning_registry=self.registry,
                    web_root=Path('/fixture/web'), server_factory=self.factory(serve_error))
        return build(**dict(args, **overrides))

    def serve_in_thread(self, app, **kwargs):
        outcome = {}

        def target():
            try:
                outcome['result'] = app.serve_forever(**kwargs)
            except BaseException as error:  # noqa: BLE001
                outcome['error'] = error
        thread = threading.Thread(target=target)
        thread.start()
        self.addCleanup(thread.join, WAIT)
        return thread, outcome

    def production_threads(self):
        return [t for t in threading.enumerate() if t.name == 'production-worker']

    def test_build_starts_nothing_and_passes_roots(self):
        runtime = self.runtime()
        before = threading.active_count()
        app = self.app(runtime)
        self.assertEqual(threading.active_count(), before)
        self.assertEqual((app.state, app.worker_state), ('built', 'not_started'))
        self.assertEqual((runtime.worker.run_calls, self.servers[0].serve_calls, self.servers[0].close_calls), (0, 0, 0))
        host, port, kwargs = self.factory_calls[0]
        self.assertEqual((host, port), ('127.0.0.1', 8769))
        self.assertIs(kwargs['execution_service'], runtime.service)
        self.assertIs(kwargs['planning_registry'], self.registry)
        self.assertEqual((kwargs['source_root'], kwargs['workspace_root']), (self.config.source_root, self.config.workspace_root))
        self.assertEqual(kwargs['web_root'], Path('/fixture/web'))
        self.assertNotIn('operations_registry', kwargs)

    def test_build_rejects_invalid_inputs(self):
        with self.assertRaises(ContractError) as ctx:
            self.app(config=object())
        self.assertEqual(ctx.exception.code, 'invalid_bootstrap_config')
        with self.assertRaises(ContractError) as ctx:
            self.app(planning_registry={})
        self.assertEqual(ctx.exception.code, 'invalid_registry')
        with self.assertRaises(ContractError) as ctx:
            self.app(runtime=SimpleNamespace(service=None, worker=None))
        self.assertEqual(ctx.exception.code, 'invalid_runtime')
        with self.assertRaises(ContractError) as ctx:
            self.app(runtime=self.runtime(store_root=Path('/other/managed')))
        self.assertEqual(ctx.exception.code, 'runtime_config_mismatch')
        with self.assertRaises(ContractError) as ctx:
            self.app(runtime=self.runtime(lock_root=Path('/other/source')))
        self.assertEqual(ctx.exception.code, 'runtime_config_mismatch')
        mismatched = self.runtime()
        mismatched.worker.services = object()
        with self.assertRaises(ContractError) as ctx:
            self.app(runtime=mismatched)
        self.assertEqual(ctx.exception.code, 'runtime_worker_mismatch')
        self.assertEqual(self.servers, [])

    def test_enabled_normal_lifecycle_drains_worker_then_closes_server(self):
        runtime = self.runtime()
        app = self.app(runtime)
        thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertTrue(runtime.worker.started.wait(WAIT))
        self.assertEqual((app.state, app.worker_state), ('serving', 'running'))
        self.assertEqual(len(self.production_threads()), 1)
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome, {'result': None})
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertTrue(runtime.worker.finished.is_set())
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'stopped', 1))
        self.assertEqual(self.production_threads(), [])

    def test_disabled_runtime_serves_http_without_worker(self):
        runtime = self.runtime(enabled=False)
        app = self.app(runtime)
        thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        self.assertEqual(self.production_threads(), [])
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome, {'result': None})
        self.assertEqual((runtime.worker.run_calls, app.worker_state, app.state), (0, 'not_started', 'closed'))
        self.assertFalse(runtime.worker.stop_event.is_set())
        self.assertEqual(self.servers[0].close_calls, 1)

    def test_duplicate_serve_and_restart_after_close_are_rejected(self):
        runtime = self.runtime()
        app = self.app(runtime)
        thread, outcome = self.serve_in_thread(app)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        with self.assertRaises(AppError) as ctx:
            app.serve_forever()
        self.assertEqual(ctx.exception.code, 'application_serving')
        with self.assertRaises(AppError) as ctx:
            app.close()
        self.assertEqual(ctx.exception.code, 'application_serving')
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(runtime.worker.run_calls, 1)
        with self.assertRaises(AppError) as ctx:
            app.serve_forever()
        self.assertEqual(ctx.exception.code, 'application_closed')
        self.assertEqual((runtime.worker.run_calls, self.servers[0].serve_calls), (1, 1))
        with self.assertRaises(AppError):
            app.request_shutdown()

    def test_same_worker_cannot_serve_in_two_applications(self):
        runtime = self.runtime()
        first, second = self.app(runtime), self.app(runtime)
        thread, _ = self.serve_in_thread(first)
        self.assertTrue(runtime.worker.started.wait(WAIT))
        with self.assertRaises(AppError) as ctx:
            second.serve_forever()
        self.assertEqual(ctx.exception.code, 'worker_in_use')
        self.assertEqual((second.state, self.servers[1].close_calls, self.servers[1].serve_calls), ('closed', 1, 0))
        self.assertFalse(runtime.worker.stop_event.is_set())
        first.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(runtime.worker.run_calls, 1)

    def test_close_before_serve_is_idempotent_and_blocks_serve(self):
        runtime = self.runtime()
        app = self.app(runtime)
        app.close()
        app.close()
        self.assertEqual((app.state, self.servers[0].close_calls), ('closed', 1))
        with self.assertRaises(AppError):
            app.serve_forever()
        self.assertEqual(runtime.worker.run_calls, 0)

    def test_server_exception_still_drains_worker_and_closes(self):
        runtime = self.runtime()
        app = self.app(runtime, serve_error=OSError('serve boom'))
        with self.assertRaises(OSError):
            app.serve_forever()
        self.assertTrue(runtime.worker.finished.wait(WAIT))
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'stopped', 1))
        self.assertEqual(self.production_threads(), [])

    def test_keyboard_interrupt_cleans_up(self):
        runtime = self.runtime()
        app = self.app(runtime, serve_error=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            app.serve_forever()
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'stopped', 1))
        self.assertEqual(self.production_threads(), [])

    def test_worker_failure_stops_http_and_reports_error(self):
        runtime = self.runtime(mode='fail')
        app = self.app(runtime)
        with self.assertRaises(AppError) as ctx:
            app.serve_forever()
        self.assertEqual(ctx.exception.code, 'worker_failed')
        self.assertIsInstance(app.worker_error, RuntimeError)
        self.assertIs(ctx.exception.__cause__, app.worker_error)
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'failed', 1))
        self.assertEqual(self.production_threads(), [])
        with self.assertRaises(AppError):
            app.serve_forever()
        self.assertEqual(runtime.worker.run_calls, 1)

    def test_worker_that_ignores_stop_is_reported_not_success(self):
        runtime = self.runtime(mode='ignore_stop')
        app = self.app(runtime)
        thread, outcome = self.serve_in_thread(app, join_timeout=0.05)
        self.assertTrue(self.servers[0].entered.wait(WAIT))
        app.request_shutdown()
        thread.join(WAIT)
        self.assertEqual(outcome['error'].code, 'worker_not_stopped')
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'stuck', 1))
        # stop_event를 되돌리거나 worker를 다시 시작하지 않고 상태를 보존한다.
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual(len(self.production_threads()), 1)
        with self.assertRaises(AppError):
            app.serve_forever()
        with self.assertRaises(AppError) as ctx:
            self.app(runtime).serve_forever()
        self.assertEqual(ctx.exception.code, 'worker_in_use')
        runtime.worker.release.set()
        self.assertTrue(runtime.worker.finished.wait(WAIT))
        for stuck in self.production_threads():
            stuck.join(WAIT)
        self.assertEqual(runtime.worker.run_calls, 1)

    def test_already_stopped_worker_is_not_reset_or_silently_skipped(self):
        runtime = self.runtime()
        runtime.worker.stop_event.set()
        app = self.app(runtime)
        with self.assertRaises(AppError) as ctx:
            app.serve_forever()
        self.assertEqual(ctx.exception.code, 'worker_stopped')
        self.assertTrue(runtime.worker.stop_event.is_set())
        self.assertEqual((runtime.worker.run_calls, self.servers[0].serve_calls, app.state, self.servers[0].close_calls),
                         (0, 0, 'closed', 1))

    def test_worker_start_failure_closes_server(self):
        runtime = self.runtime()
        app = self.app(runtime)
        with patch.object(production_application.threading.Thread, 'start', side_effect=RuntimeError('no thread')):
            with self.assertRaises(RuntimeError):
                app.serve_forever()
        self.assertEqual((runtime.worker.run_calls, self.servers[0].serve_calls), (0, 0))
        self.assertEqual((app.state, app.worker_state, self.servers[0].close_calls), ('closed', 'not_started', 1))
        retry = self.app(runtime)
        thread, _ = self.serve_in_thread(retry)
        self.assertTrue(runtime.worker.started.wait(WAIT))
        retry.request_shutdown()
        thread.join(WAIT)

    def test_invalid_join_timeout_does_not_change_state(self):
        app = self.app()
        for value in (0, -1, True, 'x', None, float('nan'), float('inf')):
            with self.assertRaises(ContractError):
                app.serve_forever(join_timeout=value)
        self.assertEqual((app.state, self.servers[0].close_calls), ('built', 0))

    def test_factory_failure_leaves_nothing_started(self):
        def broken(host, port, **kwargs):
            raise ValueError('bind failed')
        before = threading.active_count()
        with self.assertRaises(ValueError):
            self.app(server_factory=broken)
        self.assertEqual(threading.active_count(), before)

    def test_external_access_policy_explicit_forwarding_and_default_compatibility(self):
        from web_external_access import ExternalAccessPolicy
        plain=self.app(runtime=self.runtime(enabled=False))
        self.assertNotIn('external_access_policy',self.factory_calls[-1][2])
        plain.close()
        policy=ExternalAccessPolicy('https://console.example.com')
        runtime=self.runtime(enabled=False)
        app=self.app(runtime=runtime,external_access_policy=policy)
        host,port,kwargs=self.factory_calls[-1]
        self.assertEqual(host,'127.0.0.1')
        self.assertIs(kwargs['external_access_policy'],policy)
        self.assertEqual(runtime.worker.run_calls,0)
        self.assertEqual(self.servers[-1].serve_calls,0)
        app.close()

    def test_invalid_external_access_policy_rejected_before_server_factory(self):
        for policy in ({'public_origin':'https://console.example.com'},True,'https://console.example.com'):
            with self.subTest(policy=policy):
                with self.assertRaises(ContractError):
                    self.app(external_access_policy=policy)
                self.assertEqual(self.factory_calls,[])


    def test_tiktok_media_probe_forwarded_explicitly_without_inspection(self):
        plain=self.app(runtime=self.runtime(enabled=False))
        self.assertNotIn('tiktok_media_probe',self.factory_calls[-1][2]);plain.close()
        calls=[]
        probe=SimpleNamespace(inspect=lambda raw:calls.append(raw))
        runtime=self.runtime(enabled=False)
        app=self.app(runtime=runtime,tiktok_media_probe=probe)
        self.assertIs(self.factory_calls[-1][2]['tiktok_media_probe'],probe)
        self.assertEqual(calls,[]);self.assertEqual(runtime.worker.run_calls,0)
        self.assertEqual(self.servers[-1].serve_calls,0);app.close()

    def test_invalid_tiktok_media_probe_rejected_before_server_factory(self):
        for probe in (object(),True,'/fixture/ffprobe',SimpleNamespace(inspect=False)):
            with self.subTest(probe=probe),self.assertRaises(ContractError) as error:
                self.app(tiktok_media_probe=probe)
            self.assertEqual(error.exception.code,'invalid_tiktok_media_probe')
            self.assertEqual(self.factory_calls,[])

    def test_initialize_storage_preserves_instagram_review_store_only(self):
        app=self.app(runtime=self.runtime(enabled=False))
        calls=[]
        self.servers[-1].instagram_review_store=SimpleNamespace(initialize=lambda:calls.append('instagram_review'))
        self.servers[-1].media_lease_store=SimpleNamespace(initialize=lambda:(_ for _ in ()).throw(AssertionError('media leases remain inert')))
        with patch('subprocess.Popen',side_effect=AssertionError('no native process')):
            app.initialize_storage()
        self.assertEqual(calls,['instagram_review'])
        self.assertEqual(self.servers[-1].serve_calls,0)
        self.assertEqual(app.runtime.worker.run_calls,0)
        app.close()

if __name__ == '__main__':
    unittest.main()
