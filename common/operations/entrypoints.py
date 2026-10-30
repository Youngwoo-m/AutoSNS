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


def route_legacy_action(action_key: tuple[str, str, str], *, services=None) -> dict:
    """등록된 기존 action만 legacy 실행 또는 서버 등록 접수로 분기한다.

    services는 서버/fixture만 주입한다. action key 이외의 클라이언트 값으로
    caller/job/owner를 선택하지 않는다. 관리 접수 실패는 legacy fallback이 아니다.
    """
    from collections.abc import Mapping
    from .legacy_fences import ACTION_ROUTES, LOCAL_CHANNELS, legacy_services, inventory_allows_managed
    if not isinstance(action_key, tuple) or len(action_key) != 3 or not all(isinstance(x, str) and x for x in action_key):
        raise StoreError('invalid_action')
    account, channel, action = action_key
    if account not in ('dept', 'personal', 'common'):
        raise StoreError('unknown_account')
    if action in ('memo', 'test') and channel in LOCAL_CHANNELS.get(account, ()):
        return dict(route='legacy', caller_id='legacy.local', job_id=None)
    services = legacy_services() if services is None else services
    if not isinstance(services, Mapping):
        raise StoreError('services_unavailable')
    routes = services.get('action_routes', ACTION_ROUTES)
    spec = routes.get(action_key)
    if spec is None:
        raise StoreError('unknown_action')
    registry, catalog = services.get('registry'), services.get('catalog')
    if not isinstance(registry, Registry):
        raise StoreError('invalid_registry')
    if not isinstance(catalog, ExecutionCatalog):
        raise StoreError('invalid_catalog')
    caller_id = spec['caller_id']
    if caller_id not in catalog.callers:
        raise StoreError('unknown_caller')
    job_ids = spec['job_ids']
    resolved = []
    for job_id in job_ids:
        if job_id not in registry.jobs:
            if spec.get('observed_unregistered') is True and job_id in catalog.callers[caller_id]['job_ids']:
                continue
            raise StoreError('unknown_job')
        if registry.jobs[job_id].get('owner_account_id') != account:
            raise StoreError('owner_mismatch')
        resolved.append(resolve_entrypoint(caller_id, job_id, registry, catalog))
    managed = [r for r in resolved if r['route'] == 'managed']
    if not managed:
        return dict(route='legacy', caller_id=caller_id, job_id=job_ids[0])
    # 다중 부수효과 wrapper나 caller 하나라도 미확인인 job은 전체 관리 전환 금지.
    if len(job_ids) != 1 or not inventory_allows_managed(job_ids[0], action_routes=routes):
        raise StoreError('entrypoint_inventory_incomplete')
    request = services.get('request')
    if not isinstance(request, dict) or request.get('job_id') != job_ids[0]:
        raise StoreError('managed_request_required')
    if set(request) != _FIELDS:
        raise StoreError('invalid_request')
    if request['source'] != managed[0]['source']:
        raise StoreError('source_mismatch')
    if request['phase'] not in catalog.executors[managed[0]['executor_id']].phases:
        raise StoreError('executor_phase_forbidden')
    submit = services.get('submit')
    if callable(submit):
        result = submit(dict(request), caller_id)
    else:
        result = submit_registered(dict(request), caller_id=caller_id, store=services.get('store'),
            registry=registry, catalog=catalog, policy=services.get('policy'),
            production_policy_resolver=services.get('production_policy_resolver'))
    run_id = result.get('run_id') or result.get('id')
    if not isinstance(run_id, str) or not run_id:
        raise StoreError('managed_result_invalid')
    return dict(route='managed', status='queued', state='queued', run_id=run_id,
                job_id=job_ids[0], caller_id=caller_id)
