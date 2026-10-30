"""호출자 신원과 현재 등록부의 단일 실행 owner를 연결하는 순수 경계."""
from .content_store import StoreError
from .dispatch import submit_trigger, _FIELDS
from .execution_catalog import ExecutionCatalog
from .models import Registry


def resolve_entrypoint(caller_id: str, job_id: str, registry, catalog) -> dict:
    if not isinstance(registry, Registry):
        raise StoreError('invalid_registry')
    if not isinstance(catalog, ExecutionCatalog):
        raise StoreError('invalid_catalog')
    if not isinstance(caller_id, str) or caller_id not in catalog.callers:
        raise StoreError('unknown_caller')
    if not isinstance(job_id, str) or job_id not in registry.jobs:
        raise StoreError('unknown_job')
    caller = catalog.callers[caller_id]
    job = registry.jobs[job_id]
    base_id = job.get('base_job_id', job_id)
    if not isinstance(base_id, str) or base_id not in caller['job_ids']:
        raise StoreError('caller_job_forbidden')
    base = registry.jobs.get(base_id)
    if base is None:
        raise StoreError('unknown_job')
    if base_id != job_id:
        if (base.get('kind') != 'production' or base_id not in catalog.production_jobs or
            not isinstance(job.get('binding_id'), str) or not job['binding_id'] or
            base.get('base_job_id') is not None):
            raise StoreError('invalid_binding')
        for field in ('owner_account_id', 'executor_id', 'schedule_owner', 'execution_owner', 'enabled', 'policy_revision', 'kind', 'provider_policy_id'):
            if job.get(field) != base.get(field):
                # 현재 base가 비활성/legacy라면 구체적인 fence 사유를 보존한다.
                if base.get('execution_owner') != 'managed':
                    raise StoreError('legacy_owner')
                if base.get('enabled') is not True:
                    raise StoreError('job_disabled')
                raise StoreError('invalid_binding')
    owner = base.get('execution_owner')
    if owner == 'legacy':
        if not caller['legacy_allowed']:
            raise StoreError('legacy_owner')
        return dict(route='legacy', caller_id=caller_id, job_id=job_id, base_job_id=base_id,
                    source=caller['source'], owner_account_id=base.get('owner_account_id'))
    if owner != 'managed' or base.get('schedule_owner') not in ('launchd', 'console'):
        raise StoreError('invalid_owner')
    executor = catalog.executors.get(base.get('executor_id'))
    if executor is None:
        raise StoreError('unknown_executor')
    if base_id not in executor.job_ids:
        raise StoreError('executor_job_forbidden')
    if base.get('kind') == 'production' and base_id not in catalog.production_jobs:
        raise StoreError('unknown_production_job')
    return dict(route='managed', caller_id=caller_id, job_id=job_id, base_job_id=base_id,
                source=caller['source'], executor_id=executor.id,
                owner_account_id=base.get('owner_account_id'))


def submit_registered(request: dict, *, caller_id: str, store, registry, policy, catalog,
                      production_policy_resolver=None) -> dict:
    if not isinstance(request, dict) or set(request) != _FIELDS:
        raise StoreError('invalid_request')
    route = resolve_entrypoint(caller_id, request['job_id'], registry, catalog)
    if request['source'] != route['source']:
        raise StoreError('source_mismatch')
    if route['route'] != 'managed':
        raise StoreError('legacy_owner')
    executor = catalog.executors[route['executor_id']]
    if request['phase'] not in executor.phases:
        raise StoreError('executor_phase_forbidden')
    return submit_trigger(store, request, registry, policy,
                          production_policy_resolver=production_policy_resolver)
