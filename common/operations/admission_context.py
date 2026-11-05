"""최초 대상 관측용 읽기 문맥. 발행 승인·permit·인증 증거를 표현하지 않는다."""
from dataclasses import dataclass, asdict
from .models import ContractError


@dataclass(frozen=True)
class AdmissionReadContext:
    connection_id: str
    destination_account_id: str
    target_id: str
    platform: str
    registry_revision: str
    owner_account_id: str
    policy_revision: str
    run_id: str
    planned_delivery_id: str
    plan_version: int
    scope: str = 'admission_read'

    def __post_init__(self):
        if self.scope != 'admission_read' or type(self.plan_version) is not int or self.plan_version < 1:
            raise ContractError('invalid_read_context')
        if any(not isinstance(value,str) or not value for key,value in asdict(self).items() if key!='plan_version'):
            raise ContractError('invalid_read_context')

    def to_dict(self):
        return asdict(self)


def decode_bridge_context(value, action):
    from .runtime_models import PublicationContext
    if value.get('scope') == 'admission_read':
        if action != 'inspect_target':raise ContractError('bridge_read_action_required')
        return AdmissionReadContext(**value)
    return PublicationContext(**value)


def validate_admission_read(store, registry, context):
    plan=store.get_plan_delivery(context.planned_delivery_id)
    if (not plan or plan.get('version',1)!=context.plan_version or plan.get('status')=='cancelled'
            or plan.get('owner_account_id')!=context.owner_account_id
            or plan.get('destination_account_id')!=context.destination_account_id
            or plan.get('connection_id')!=context.connection_id):
        raise ContractError('plan_changed')
    run=store.get_run(context.run_id);occurrence=(run or {}).get('occurrence') or {}
    job=registry.jobs.get(occurrence.get('job_id'))
    if (not job or job.get('enabled') is not True or job.get('execution_owner')!='managed'
        or job.get('schedule_owner') not in ('console','launchd') or occurrence.get('source')!=job.get('schedule_owner')
        or occurrence.get('mode')!='live' or occurrence.get('phase')!='submit'
        or job.get('owner_account_id')!=context.owner_account_id or job.get('policy_revision')!=context.policy_revision
        or context.connection_id not in (job.get('connection_ids') or (job.get('connection_id'),))):
        raise ContractError('bridge_job_mismatch')
    connection=registry.connections.get(context.connection_id)
    if (not connection or not connection.enabled or not connection.target_id
            or connection.target_id!=context.target_id or connection.platform!=context.platform
            or registry.revision!=context.registry_revision):raise ContractError('target_unverified')
    if context.owner_account_id!=context.destination_account_id:
        if not any(rule.get('enabled') is True and rule.get('owner_account_id')==context.owner_account_id
                   and rule.get('destination_connection_id')==context.connection_id
                   and registry.connections.get(rule.get('source_connection_id')) is not None
                   and registry.connections[rule['source_connection_id']].account_id==context.owner_account_id
                   for rule in registry.crossposts.values()):raise ContractError('crosspost_not_allowed')
    return plan
