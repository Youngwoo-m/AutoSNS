"""제작 전용 웹 application lifecycle.

신뢰된 서버 코드가 주입한 ProductionRuntime으로 기존 web_server.create_server를 조립한다.
build_production_application()은 소켓 준비까지만 하며 worker/thread/serve_forever를 시작하지 않고
DB 초기화·모델·native·브라우저에 접근하지 않는다. 명시적인 serve_forever() 호출 때만, 정책이 enabled인
runtime에 한해 worker thread 하나를, enabled인 영상 서비스가 있으면 독립 영상 worker thread 하나를 더 시작하고
HTTP를 제공한다. 두 worker는 서로 독립이라 영상만 켜도 된다. signal handler나 자동 재시작은 없다.
"""
import importlib.util
import math
import time
from socketserver import BaseServer
from pathlib import Path
import threading

from common.operations.bootstrap_config import BootstrapConfig
from common.operations.models import ContractError, Registry
from common.operations.production_startup import ProductionRuntime
from common.operations.video_tasks import VideoTaskService
from common.operations.video_worker import VideoTaskWorker

DEFAULT_JOIN_TIMEOUT = 30.0
_WEB_SERVER = Path(__file__).resolve().with_name('web_server.py')
_claimed = set()
_claim_lock = threading.Lock()


class _StopServing(Exception):
    pass


class ProductionApplicationError(ContractError):
    """worker 실패/미종료처럼 호출자가 반드시 알아야 하는 lifecycle 오류."""


def _default_server_factory():
    # ax-console은 패키지 이름이 아니므로 파일 경로로 불러온다. build 시점에만 import한다.
    spec = importlib.util.spec_from_file_location('production_web_server', _WEB_SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_server


def _same_path(left, right):
    return Path(left).resolve() == Path(right).resolve()


def _has_stop_event(worker):
    stop_event = getattr(worker, 'stop_event', None)
    return callable(getattr(stop_event, 'set', None)) and callable(getattr(stop_event, 'is_set', None))


def _validate_runtime(runtime, config):
    if not isinstance(runtime, ProductionRuntime):
        raise ContractError('invalid_runtime')
    service, worker = runtime.service, runtime.worker
    try:
        if not (_same_path(service.store.root, config.workspace_root)
                and _same_path(service.locks.paths.root, config.source_root)):
            raise ContractError('runtime_config_mismatch')
        enabled = service.policy.enabled
    except (AttributeError, TypeError, OSError):
        raise ContractError('invalid_runtime') from None
    if type(enabled) is not bool or not callable(getattr(worker, 'run', None)):
        raise ContractError('invalid_runtime')
    if not _has_stop_event(worker):
        raise ContractError('invalid_runtime')
    if getattr(worker, 'services', service) is not service:
        raise ContractError('runtime_worker_mismatch')


def _build_video_worker(video_service, config, factory):
    """소켓을 열기 전에 영상 서비스를 검증하고, enabled일 때만 worker를 만든다(시작은 하지 않는다)."""
    if video_service is None:
        return None
    if not isinstance(video_service, VideoTaskService):
        raise ContractError('invalid_video_service')
    try:
        roots = (video_service.store.root, video_service.content_store.root, video_service.plan_store.root)
        matched = all(_same_path(root, config.workspace_root) for root in roots)
    except (AttributeError, TypeError, OSError):
        raise ContractError('invalid_video_service') from None
    if not matched:
        raise ContractError('video_config_mismatch')
    if video_service.enabled is not True:
        return None
    worker = factory(video_service)
    if getattr(worker, 'service', None) is not video_service:
        raise ContractError('video_worker_mismatch')
    if not callable(getattr(worker, 'run', None)) or not _has_stop_event(worker):
        raise ContractError('invalid_video_worker')
    return worker


class ProductionApplication:
    """상태: built -> serving -> closed. closed는 재시작할 수 없다."""

    def __init__(self, runtime, server, video_worker=None):
        for name in ('serve_forever', 'shutdown', 'server_close'):
            if not callable(getattr(server, name, None)):
                raise ContractError('invalid_server')
        self.runtime, self.server, self.video_worker = runtime, server, video_worker
        self.state = 'built'
        self.worker_state = 'not_started'  # not_started|running|stopped|failed|stuck
        self.worker_error = None
        self.video_worker_state = 'not_started'  # worker_state와 같은 값 집합
        self.video_worker_error = None
        self._thread = None
        self._claim = None
        self._video_thread = None
        self._video_claim = None
        self._lock = threading.Lock()
        self._http_started = False
        self._shutdown_requested = False
        self._poll_shutdown = isinstance(server, BaseServer)
        self._original_actions = None

    @property
    def server_address(self):
        return getattr(self.server, 'server_address', None)

    def initialize_storage(self):
        """명시 기동 준비에서만 관리 저장소를 초기화한다. build는 무변이다."""
        with self._lock:
            if self.state != 'built':
                raise ProductionApplicationError('application_' + self.state)
            for name in ('content_store', 'integration_store', 'ledger', 'runtime_store',
                         'production_store', 'metrics_store', 'production_settings_store', 'media_plan_store', 'voice_task_store', 'video_task_store', 'reuse_approval_store', 'image_task_store'):
                store = getattr(self.server, name, None)
                if store is not None:
                    store.initialize()

    def serve_forever(self, *, join_timeout=DEFAULT_JOIN_TIMEOUT):
        """HTTP를 제공한다. 반환/예외 시점에는 worker 정리와 server_close가 끝나 있다.

        worker가 실패하면 HTTP를 멈춘 뒤 ProductionApplicationError를,
        join_timeout 안에 worker가 끝나지 않으면 worker_not_stopped 오류를 낸다.
        영상 worker는 같은 규칙으로 video_worker_failed/video_worker_not_stopped를 낸다.
        """
        if type(join_timeout) not in (int, float) or isinstance(join_timeout, bool) or not math.isfinite(join_timeout) or join_timeout <= 0:
            raise ContractError('invalid_join_timeout')
        with self._lock:
            if self.state != 'built':
                raise ProductionApplicationError('application_' + self.state)
            self.state = 'serving'
        try:
            self._start_workers()
            with self._lock:
                self._http_started = True
                failed = self.worker_error is not None or self.video_worker_error is not None
            if not failed and not self._shutdown_requested:
                if self._poll_shutdown:
                    self._original_actions = self.server.service_actions
                    self.server.service_actions = self._service_actions
                try:
                    self.server.serve_forever()
                except _StopServing:
                    pass
        finally:
            self._cleanup(join_timeout)
        if self.worker_state == 'stuck':
            raise ProductionApplicationError('worker_not_stopped')
        if self.video_worker_state == 'stuck':
            raise ProductionApplicationError('video_worker_not_stopped')
        if self.worker_state == 'failed':
            raise ProductionApplicationError('worker_failed') from self.worker_error
        if self.video_worker_state == 'failed':
            raise ProductionApplicationError('video_worker_failed') from self.video_worker_error

    def request_shutdown(self):
        """다른 thread에서 HTTP loop 종료를 요청한다. serve 중이 아니면 거부한다."""
        with self._lock:
            if self.state != 'serving':
                raise ProductionApplicationError('application_not_serving')
            self._shutdown_requested = True
            started = self._http_started
        if started and not self._poll_shutdown:
            self.server.shutdown()

    def _service_actions(self):
        # BaseServer.shutdown()은 loop 진입 전 실패 시 영원히 기다릴 수 있다.
        # 공개 service_actions hook으로 loop 안에서 종료하여 그 경합을 없앤다.
        if self._shutdown_requested or self.worker_error is not None or self.video_worker_error is not None:
            raise _StopServing()
        self._original_actions()

    def close(self):
        """serve 전의 application 소켓을 닫는다. 멱등이며 serve 중에는 거부한다."""
        with self._lock:
            if self.state == 'serving':
                raise ProductionApplicationError('application_serving')
            if self.state == 'closed':
                return
            self.state = 'closed'
        self.server.server_close()

    # --- worker 시작 ------------------------------------------------------
    @staticmethod
    def _acquire(worker, in_use, stopped):
        key = id(worker)
        with _claim_lock:
            if key in _claimed:
                raise ProductionApplicationError(in_use)
            if worker.stop_event.is_set():
                raise ProductionApplicationError(stopped)
            _claimed.add(key)
        return key

    @staticmethod
    def _release(key):
        if key is not None:
            with _claim_lock:
                _claimed.discard(key)

    def _start_workers(self):
        """두 worker의 claim을 먼저 모두 잡은 뒤 thread를 시작한다. 한쪽이라도 거부되면 아무것도 시작하지 않는다."""
        worker, video = self.runtime.worker, self.video_worker
        try:
            if self.runtime.service.policy.enabled:
                self._claim = self._acquire(worker, 'worker_in_use', 'worker_stopped')
            if video is not None:
                self._video_claim = self._acquire(video, 'video_worker_in_use', 'video_worker_stopped')
        except BaseException:
            self._release(self._claim)
            self._release(self._video_claim)
            self._claim = self._video_claim = None
            raise
        try:
            if self._claim is not None:
                self._thread = self._launch('production-worker', self._run_worker, 'worker_state')
            if self._video_claim is not None:
                self._video_thread = self._launch('video-production-worker', self._run_video_worker,
                                                  'video_worker_state')
        except BaseException:
            # 시작하지 못한 쪽의 claim만 풀고, 이미 시작한 thread는 _cleanup이 stop/join한다.
            if self._thread is None:
                self._release(self._claim)
                self._claim = None
            if self._video_thread is None:
                self._release(self._video_claim)
                self._video_claim = None
            raise

    def _launch(self, name, target, state_name):
        thread = threading.Thread(target=target, name=name, daemon=True)
        setattr(self, state_name, 'running')
        try:
            thread.start()
        except BaseException:
            setattr(self, state_name, 'not_started')
            raise
        return thread

    def _run_worker(self):
        try:
            self.runtime.worker.run()
        except BaseException as error:  # noqa: BLE001 - 어떤 실패도 호출자에게 전달해야 한다.
            self._finished('worker', error)
        else:
            self._finished('worker', None)

    def _run_video_worker(self):
        try:
            self.video_worker.run()
        except BaseException as error:  # noqa: BLE001
            self._finished('video_worker', error)
        else:
            self._finished('video_worker', None)

    def _finished(self, prefix, error):
        state_name, error_name = prefix + '_state', prefix + '_error'
        with self._lock:
            if error is not None:
                setattr(self, error_name, error)
                setattr(self, state_name, 'failed')
            elif getattr(self, state_name) == 'running':
                setattr(self, state_name, 'stopped')
            shutdown = error is not None and self._http_started
        if shutdown and not self._poll_shutdown:
            self.server.shutdown()

    def _cleanup(self, join_timeout):
        """예외를 내지 않고 모든 worker를 drain한 뒤 server_close를 수행한다."""
        lanes = []
        if self._thread is not None:
            lanes.append((self._thread, self.runtime.worker, self._claim, 'worker_state'))
        if self._video_thread is not None:
            lanes.append((self._video_thread, self.video_worker, self._video_claim, 'video_worker_state'))
        for _, worker, _, _ in lanes:  # 먼저 전부 정지를 알려 동시에 drain되게 한다.
            worker.stop_event.set()
        deadline = time.monotonic() + join_timeout
        for thread, _, claim, state_name in lanes:
            if threading.current_thread() is not thread:
                thread.join(max(deadline - time.monotonic(), 0))
            if thread.is_alive():
                with self._lock:
                    setattr(self, state_name, 'stuck')  # 재기동·reset 없이 상태와 claim만 보존한다.
            else:
                self._release(claim)
                with self._lock:
                    if getattr(self, state_name) == 'running':
                        setattr(self, state_name, 'stopped')
        with self._lock:
            self.state = 'closed'
        if self._original_actions is not None:
            self.server.service_actions = self._original_actions
        try:
            self.server.server_close()
        except OSError:
            pass


def build_production_application(*, runtime, config, planning_registry, host='127.0.0.1', port=8769,
                                 web_root, auth_backend=None, toolkit_policy=None, server_factory=None, voice_task_service=None,
                                 video_task_service=None, video_worker_factory=VideoTaskWorker, image_task_service=None):
    """검증 후 서버 소켓만 준비한다. worker/thread/serve_forever는 시작하지 않는다."""
    if not isinstance(config, BootstrapConfig):
        raise ContractError('invalid_bootstrap_config')
    if not isinstance(planning_registry, Registry):
        raise ContractError('invalid_registry')
    _validate_runtime(runtime, config)
    if server_factory is not None and not callable(server_factory):
        raise ContractError('invalid_server_factory')
    if not callable(video_worker_factory):
        raise ContractError('invalid_video_worker_factory')
    video_worker = _build_video_worker(video_task_service, config, video_worker_factory)
    factory = server_factory if server_factory is not None else _default_server_factory()
    extra = {'voice_task_service':voice_task_service} if voice_task_service is not None else {}
    if image_task_service is not None:extra['image_task_service']=image_task_service
    if video_task_service is not None:extra['video_task_service']=video_task_service
    server = factory(host, port, source_root=config.source_root, web_root=Path(web_root),
        workspace_root=config.workspace_root, execution_service=runtime.service,
        planning_registry=planning_registry, auth_backend=auth_backend, toolkit_policy=toolkit_policy,**extra)
    try:
        return ProductionApplication(runtime, server, video_worker)
    except BaseException:
        close = getattr(server, 'server_close', None)
        if callable(close):
            close()
        raise
