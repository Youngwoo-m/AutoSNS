"""부수효과 없는 로컬 도구 정책. HTTP 입력을 정책/증거로 해석하지 않는다."""
from dataclasses import dataclass
from datetime import datetime
from .provider_capabilities import DEFAULT_CAPABILITIES


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone_required')
    return value


@dataclass(frozen=True)
class ToolkitPolicy:
    enabled: bool = False

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError('enabled')


@dataclass(frozen=True)
class CostEvidence:
    kind: str
    credit_units: int
    additional_cost_zero: bool | None
    evidence_ref: str
    valid_until: str | None

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in ('no_additional_cost', 'credits', 'paid', 'unknown'):
            raise ValueError('kind')
        if type(self.credit_units) is not int or self.credit_units < 0:
            raise ValueError('credit_units')
        if self.additional_cost_zero is not None and type(self.additional_cost_zero) is not bool:
            raise ValueError('additional_cost_zero')
        if type(self.evidence_ref) is not str:
            raise ValueError('evidence_ref')
        if self.valid_until is not None:
            if type(self.valid_until) is not str:
                raise ValueError('valid_until')
            _aware(datetime.fromisoformat(self.valid_until))


LOCAL_COST_EVIDENCE = CostEvidence('no_additional_cost', 0, True, 'builtin:local-toolkit:v1', None)


@dataclass(frozen=True)
class ToolActionContext:
    owner_account_id: str | None
    destination_account_id: str | None
    connection_id: str | None
    target_id: str | None
    policy: ToolkitPolicy
    runtime_kind: str
    cost_evidence: CostEvidence
    now: datetime
    cross_account_local_authorized: bool = False
    read_scope_status: str = 'unknown'
    write_scope_status: str = 'unknown'

    def __post_init__(self):
        for name in ('owner_account_id', 'destination_account_id', 'connection_id', 'target_id'):
            value = getattr(self, name)
            if value is not None and (type(value) is not str or not value):
                raise ValueError(name)
        if type(self.policy) is not ToolkitPolicy or type(self.cost_evidence) is not CostEvidence:
            raise ValueError('invalid_nested_contract')
        if type(self.cross_account_local_authorized) is not bool:
            raise ValueError('cross_account_local_authorized')
        _aware(self.now)
        if type(self.runtime_kind) is not str or self.runtime_kind not in ('local', 'codex_assisted', 'unavailable'):
            raise ValueError('runtime_kind')
        for name in ('read_scope_status', 'write_scope_status'):
            if type(getattr(self, name)) is not str or getattr(self, name) not in ('unknown', 'granted', 'denied'):
                raise ValueError(name)


def evaluate_tool_action(action_id: str, context: ToolActionContext, *, catalog=DEFAULT_CAPABILITIES) -> dict:
    reasons, refs = [], []
    if type(context) is not ToolActionContext or type(action_id) is not str:
        return dict(allowed=False, reason_codes=['invalid_context'], evidence_refs=[])
    if catalog is not DEFAULT_CAPABILITIES:
        reasons.append('catalog_override_forbidden')
    capability = DEFAULT_CAPABILITIES.get(action_id)
    if capability is None:
        reasons.append('unknown_action')
    if not context.policy.enabled:
        reasons.append('toolkit_disabled')
    if not context.owner_account_id or not context.destination_account_id:
        reasons.append('account_required')
    elif context.owner_account_id != context.destination_account_id and not context.cross_account_local_authorized:
        reasons.append('account_mismatch')
    if capability is not None:
        if capability.runtime_kind != 'local' or capability.implementation_status != 'implemented' or capability.effect == 'external_write':
            reasons.append('external_execution_unsupported')
        if context.runtime_kind != capability.runtime_kind:
            reasons.append('runtime_mismatch')
        if capability.cost_kind != 'no_additional_cost':
            reasons.append('cost_not_zero')
    evidence = context.cost_evidence
    if evidence.kind != 'no_additional_cost' or evidence.credit_units != 0 or evidence.additional_cost_zero is not True:
        reasons.append('cost_not_zero')
    if evidence.evidence_ref != LOCAL_COST_EVIDENCE.evidence_ref:
        reasons.append('cost_evidence_untrusted')
    if evidence.valid_until is not None:
        if datetime.fromisoformat(evidence.valid_until) <= context.now:
            reasons.append('cost_evidence_expired')
    if not reasons:
        refs.append(evidence.evidence_ref)
    return dict(allowed=not reasons, reason_codes=list(dict.fromkeys(reasons)), evidence_refs=refs)
