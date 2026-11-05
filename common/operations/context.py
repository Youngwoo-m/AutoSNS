"""서버 등록부만으로 결정하는 계획 컨텍스트."""
import re
from .models import ExecutionRequest, ExecutionContext, Registry, ContractError


def resolve_context(request: ExecutionRequest, registry: Registry, content_owner_account_id: str,
                    *, allow_unverified: bool = False) -> ExecutionContext:
    if not isinstance(request, ExecutionRequest):
        raise ContractError('invalid_request')
    owner = request.owner_account_id
    if owner not in registry.accounts or owner not in ('dept', 'personal'):
        raise ContractError('unknown_account')
    if content_owner_account_id != owner:
        raise ContractError('owner_mismatch')
    if request.dry_run is not True or request.action not in ('plan', 'prepare'):
        raise ContractError('invalid_request')
    if (not all(isinstance(v, str) and v for v in (request.run_id, request.content_id, request.job_id, request.connection_id))
        or type(request.content_revision) is not int or request.content_revision < 1
        or request.publication_purpose not in ('initial', 'followup', 'republication')
        or not isinstance(request.schedule_slot, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,99}', request.schedule_slot)):
        raise ContractError('invalid_request')
    job = registry.jobs.get(request.job_id)
    if job is None:
        raise ContractError('unknown_job')
    if job['owner_account_id'] != owner:
        raise ContractError('owner_mismatch')
    if job.get('planning_enabled') is not True:
        raise ContractError('planning_disabled')
    connection = registry.connections.get(request.connection_id)
    if connection is None:
        raise ContractError('unknown_connection')
    if not connection.planning_enabled:
        raise ContractError('planning_disabled')
    if connection.account_id != owner or request.crosspost_rule_id is not None:
        rule = registry.crossposts.get(request.crosspost_rule_id)
        if (rule is None or rule.get('owner_account_id') != owner
            or rule.get('destination_connection_id') != connection.id
            or registry.connections[rule['source_connection_id']].account_id != owner):
            raise ContractError('crosspost_not_allowed')
    if not connection.target_id and (not allow_unverified or request.action != 'plan'):
        raise ContractError('target_unverified')
    return ExecutionContext(**request.to_dict(), destination_account_id=connection.account_id,
        platform=connection.platform, target_id=connection.target_id, credential_ref=connection.credential_ref,
        profile_ref=connection.profile_ref, expected_login_subject=connection.expected_login_subject,
        policy_revision=job['policy_revision'], registry_revision=registry.revision,
        execution_owner=job.get('execution_owner', 'managed'), target_status=connection.target_status)
