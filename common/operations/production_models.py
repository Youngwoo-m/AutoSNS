"""제작 입력과 공급자 허용 범위. 발행 권한/비밀 참조를 포함하지 않는다."""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json

from .models import ContractError, _freeze_json, thaw


def _strings(value, *, nonempty=True):
    if (not isinstance(value, (tuple, list)) or (nonempty and not value)
            or not all(isinstance(item, str) and item.strip() for item in value)
            or len(set(value)) != len(value)):
        raise ContractError('invalid_production_contract')
    return tuple(value)


@dataclass(frozen=True)
class ProductionRequest:
    job_id: str
    owner_account_id: str
    occurrence_id: str
    content_id: str
    expected_revision: int
    brief: Mapping | str
    required_outputs: tuple[str, ...]
    production_unit_id: str = ''

    def __post_init__(self):
        if not all(isinstance(getattr(self, key), str) and getattr(self, key).strip()
                   for key in ('job_id', 'owner_account_id', 'occurrence_id', 'content_id')):
            raise ContractError('invalid_production_request')
        if type(self.expected_revision) is not int or self.expected_revision < 1:
            raise ContractError('invalid_production_request')
        if not isinstance(self.brief, (Mapping, str)):
            raise ContractError('invalid_production_request')
        outputs = _strings(self.required_outputs)
        object.__setattr__(self, 'required_outputs', outputs)
        if isinstance(self.brief, Mapping):
            object.__setattr__(self, 'brief', _freeze_json(self.brief))
        inputs = {key: thaw(getattr(self, key)) for key in
                  ('job_id', 'owner_account_id', 'occurrence_id', 'content_id',
                   'expected_revision', 'brief', 'required_outputs')}
        try:
            digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError) as exc:
            raise ContractError('invalid_production_request') from exc
        unit = 'production-' + digest
        if self.production_unit_id not in ('', unit):
            raise ContractError('production_unit_mismatch')
        object.__setattr__(self, 'production_unit_id', unit)


@dataclass(frozen=True)
class ProviderPolicy:
    id: str
    owner_account_id: str
    job_ids: tuple[str, ...]
    subscription_only: bool
    allowed_provider_ids: tuple[str, ...]
    allowed_media: tuple[str, ...]
    budget_refs: tuple[str, ...]

    def __post_init__(self):
        if (not isinstance(self.id, str) or not self.id.strip()
                or self.owner_account_id not in ('personal', 'dept')
                or type(self.subscription_only) is not bool):
            raise ContractError('provider_policy_violation')
        for name in ('job_ids', 'allowed_provider_ids', 'allowed_media', 'budget_refs'):
            object.__setattr__(self, name, _strings(getattr(self, name), nonempty=name != 'budget_refs'))
        if self.owner_account_id == 'personal' and not self.subscription_only:
            raise ContractError('provider_policy_violation')
        if self.subscription_only and (self.allowed_provider_ids != ('claude-subscription',)
                                       or self.allowed_media != ('text',) or self.budget_refs):
            raise ContractError('provider_policy_violation')
        if not self.subscription_only and not self.budget_refs:
            raise ContractError('provider_budget_required')
