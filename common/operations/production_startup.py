"""제작 전용 서버 startup. 발행 adapter/bridge/publisher를 만들지 않는다.

registry/catalog/policy/producers/config는 모두 신뢰된 서버 코드가 주입한다.
HTTP/env/stdin으로 enabled, 실행파일, 권한을 받지 않는다. 이 모듈은 provider를
호출하지 않으며 worker thread/signal handler도 시작하지 않는다. 제작 실행은
호출자가 WorkerService.tick()/run()을 명시 호출할 때만 일어난다.
"""
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
import sqlite3
from types import MappingProxyType

from .bootstrap_config import BootstrapConfig
from .execution_catalog import ExecutionCatalog
from .execution_service import ExecutionService
from .models import ContractError, Registry
from .runtime_models import ExecutionPolicy


@dataclass(frozen=True)
class ProductionRuntime:
    service: object
    worker: object


class ProductionExecutionService(ExecutionService):
    """제작 전용 조립에서는 발행 접수·승인·검증도 제공하지 않는다."""
    def status_info(self):
        info = super().status_info()
        info['capabilities'] = dict(request=self.policy.enabled, observe=False, admit=False, approve=False)
        for job in info['production_jobs']:
            if job['available'] and job['id'] not in self.producers:
                job.update(available=False, reason='producer_unavailable')
        return info

    def status(self, run_id=None):
        result = super().status(run_id)
        if run_id is None:
            result['capabilities'] = dict(submit=self.policy.enabled, observe=False, approve=False)
        return result

    def submit(self, request, caller_id, **kwargs):
        if not isinstance(request, dict) or request.get('phase') != 'prepare':
            raise ContractError('unsupported')
        return super().submit(request, caller_id, **kwargs)

    def observe(self, *args, **kwargs):
        raise ContractError('unsupported')

    admit = observe
    approve = observe
    verify = observe
    reconcile = observe


def _production_job_ids(registry):
    if not isinstance(registry, Registry):
        raise ContractError('invalid_registry')
    # 발행 연결/교차게시가 섞인 등록부는 일부만 줄이지 않고 거부한다.
    if registry.connections or registry.crossposts:
        raise ContractError('publication_registry_forbidden')
    ids = set()
    for key, job in registry.jobs.items():
        if job.get('kind') != 'production' or job.get('base_job_id') is not None:
            raise ContractError('publication_job_forbidden', key)
        if job.get('connection_id') or job.get('connection_ids'):
            raise ContractError('publication_job_forbidden', key)
        ids.add(key)
    return ids


def _validate_catalog(catalog, jobs):
    if not isinstance(catalog, ExecutionCatalog):
        raise ContractError('invalid_catalog')
    for caller_id, caller in catalog.callers.items():
        if caller['legacy_allowed'] or not set(caller['job_ids']) <= jobs:
            raise ContractError('publication_caller_forbidden', caller_id)
    for executor_id, spec in catalog.executors.items():
        if set(spec.phases) != {'prepare'} or spec.mutation_actions or not set(spec.job_ids) <= jobs:
            raise ContractError('publication_executor_forbidden', executor_id)
    if not set(catalog.production_jobs) <= jobs:
        raise ContractError('publication_job_forbidden')


def _validate_policy(policy):
    if not isinstance(policy, ExecutionPolicy) or policy.allowed_connection_ids:
        raise ContractError('invalid_runtime')


def _copy_producers(producers, jobs):
    if producers is None:
        return {}
    if not isinstance(producers, Mapping):
        raise ContractError('invalid_production_producer')
    result = {}
    for job_id, producer in producers.items():
        if (job_id not in jobs or not isinstance(producer, Mapping)
                or not callable(getattr(producer.get('provider'), 'generate', None))):
            raise ContractError('invalid_production_producer', str(job_id))
        result[job_id] = dict(producer)
    return result


def _subscription_producers(runner, registry, policy):
    """검증을 마친 구독 실행기를 명시 정책의 텍스트 제작 작업에만 결속한다."""
    from .installed_claude import InstalledClaudeRunner
    from .production_providers import ClaudeSubscriptionProvider
    from .provider_policy import resolve_job_provider_policy, validate_provider_use
    if not isinstance(runner, InstalledClaudeRunner) or runner.capability_evidence['text_only_verified'] is not True:
        raise ContractError('provider_unavailable')
    result = {}
    for job_id, job in registry.jobs.items():
        if tuple(job.get('required_outputs', ())) != ('text',):
            raise ContractError('provider_media_unavailable')
        provider_policy = resolve_job_provider_policy(dict(job, id=job_id), registry, policy)
        if not provider_policy.subscription_only:
            raise ContractError('provider_policy_violation')
        validate_provider_use(provider_policy, 'claude-subscription', 'text')
        result[job_id] = dict(provider=ClaudeSubscriptionProvider(runner.executable, runner.model, spawn=runner),
                              media_runner={})
    return result


def _database_ready(root):
    from .database import connect_database
    try:
        with closing(connect_database(root, writable=False)) as db:
            return db.execute('PRAGMA user_version').fetchone()[0] == 3
    except (OSError, sqlite3.Error):
        # 없거나 읽을 수 없는 DB는 쓰기 가능으로 표시하지 않는다.
        return False


def build_production_runtime(*, config, registry, catalog, producers=None, subscription_runner=None, policy=None, clock=None, initialize=False):
    """제작 전용 ExecutionService와 WorkerService를 조립한다. 기본은 비활성·무변이."""
    from datetime import datetime, timezone
    from .content_store import ContentStore
    from .ledger import Ledger
    from .production_store import ProductionStore
    from .runtime_store import RuntimeStore
    from .worker_service import WorkerService
    from common.shared.axlock import AxLock, LockPaths
    if not isinstance(config, BootstrapConfig) or type(initialize) is not bool:
        raise ContractError('invalid_bootstrap_config')
    policy = ExecutionPolicy() if policy is None else policy
    jobs = _production_job_ids(registry)
    _validate_catalog(catalog, jobs)
    _validate_policy(policy)
    if subscription_runner is not None:
        if producers is not None:
            raise ContractError('invalid_production_producer')
        producers = _subscription_producers(subscription_runner, registry, policy)
    producers = _copy_producers(producers, jobs)
    root = config.workspace_root
    content = ContentStore(root)
    store = RuntimeStore(root, registry, content)
    production = ProductionStore(root, registry=registry)
    ledger = Ledger(root, registry, content)
    locks = AxLock(LockPaths.from_root(config.source_root))
    parts = (content, production.content_store, store, production, ledger)
    if initialize:
        for part in parts:
            part.initialize()
    elif _database_ready(root):
        # 기존 v3 저장소만 쓰기 가능으로 표시한다. 이행/파일 생성은 하지 않는다.
        for part in parts:
            part._initialized = True
    service = ProductionExecutionService(store, ledger, registry, catalog, policy, {}, producers, production, locks,
        clock or (lambda: datetime.now(timezone.utc)))
    # 제작 전용: 정책이 enabled여도 발행 adapter는 비어 있고 추가할 수 없다.
    service.adapters = MappingProxyType({})
    return ProductionRuntime(service, WorkerService(service, clock=service.clock))
