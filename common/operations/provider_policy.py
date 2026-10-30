"""계정/작업별 명시 정책만 해석한다. legacy client나 설정/키를 읽지 않는다."""
from collections.abc import Mapping
from types import MappingProxyType

from .models import ContractError
from .production_models import ProviderPolicy

# 이번 단계에서 유료/학교 공급자 및 정책을 기본 허가하지 않는다.
DEFAULT_PROVIDER_POLICY_CATALOG = MappingProxyType({})


def resolve_provider_policy(job, execution_policy, catalog) -> ProviderPolicy:
    if not isinstance(job, Mapping) or not isinstance(catalog, Mapping):
        raise ContractError('provider_policy_violation')
    owner, job_id = job.get('owner_account_id'), job.get('id')
    if owner not in ('personal', 'dept') or not isinstance(job_id, str) or not job_id:
        raise ContractError('provider_policy_violation')
    policy_id = job.get('provider_policy_id')
    if policy_id:
        selected = catalog.get(policy_id)
        if isinstance(selected, Mapping):
            try:
                selected = ProviderPolicy(**selected)
            except (TypeError, ValueError) as exc:
                raise ContractError('provider_policy_violation') from exc
        if not isinstance(selected, ProviderPolicy) or selected.id != policy_id:
            raise ContractError('provider_policy_unavailable')
        if selected.owner_account_id != owner or job_id not in selected.job_ids:
            raise ContractError('provider_policy_violation')
        if job.get('subscription_only') is True and not selected.subscription_only:
            raise ContractError('provider_policy_violation')
        return selected
    # 기존 명시 True fixture만 동일한 텍스트 전용 구독 정책으로 변환한다.
    # 전역 True만으로 학과 작업에 개인 정책을 덮어씌우지 않는다.
    if (job.get('subscription_only') is True
            and getattr(execution_policy, 'provider_policy', {}).get('subscription_only') is True):
        return ProviderPolicy('legacy-subscription:' + owner + ':' + job_id, owner, (job_id,),
                              True, ('claude-subscription',), ('text',), ())
    raise ContractError('provider_policy_unavailable')


def validate_provider_use(policy, provider_id, media_kind) -> None:
    if (not isinstance(policy, ProviderPolicy) or provider_id not in policy.allowed_provider_ids
            or media_kind not in policy.allowed_media):
        raise ContractError('provider_policy_violation')


def _merge_job_policy(job, job_policy):
    """공유 정책과 작업의 구독 제한은 작업 override로 완화하지 않는다."""
    if not isinstance(job, Mapping) or not isinstance(job_policy, Mapping):
        raise ContractError('provider_policy_violation')
    merged = dict(job_policy, **job)
    merged['id'] = job.get('base_job_id', job.get('id'))
    if job_policy.get('subscription_only') is True:
        merged['subscription_only'] = True
    return merged


def resolve_job_provider_policy(job, registry, execution_policy) -> ProviderPolicy:
    """dispatch/A8용 서버 어댑터. base 작업과 서버 catalog만 소비한다."""
    policies = getattr(registry, 'policies', None)
    if not isinstance(job, Mapping) or not isinstance(policies, Mapping):
        raise ContractError('provider_policy_violation')
    base_id = job.get('base_job_id')
    if base_id is not None:
        jobs = getattr(registry, 'jobs', {})
        base = jobs.get(base_id) if isinstance(jobs, Mapping) and isinstance(base_id,str) else None
        if (not isinstance(base,Mapping) or base.get('kind') != 'production'
                or base.get('base_job_id') is not None or job.get('kind') != 'production'
                or not isinstance(job.get('binding_id'),str) or not job['binding_id']):
            raise ContractError('invalid_binding')
        if base.get('execution_owner') != 'managed':
            raise ContractError('legacy_owner')
        if base.get('enabled') is not True:
            raise ContractError('job_disabled')
        for field in ('owner_account_id','executor_id','schedule_owner','execution_owner',
                      'enabled','policy_revision','kind','provider_policy_id'):
            if job.get(field) != base.get(field):
                raise ContractError('invalid_binding')
    job_policy = policies.get(job.get('policy_revision'))
    if not isinstance(job_policy, Mapping):
        raise ContractError('unknown_policy')
    catalog = getattr(execution_policy, 'provider_policy', {}).get('catalog', {})
    return resolve_provider_policy(_merge_job_policy(job, job_policy), execution_policy, catalog)
