"""순수 로컬 계획 계약. 참조는 기호 이름이며 비밀값을 읽지 않는다."""
from dataclasses import dataclass, fields
from collections.abc import Mapping
from types import MappingProxyType


class ContractError(ValueError):
    def __init__(self, code: str, message: str = ''):
        self.code = code
        super().__init__(message or code)


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def _freeze_json(value):
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractError('invalid_registry')
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ContractError('invalid_registry', 'JSON 메타데이터만 허용합니다')


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    return value


def _strings(model, required, nullable, code):
    for name in required:
        if not isinstance(getattr(model, name), str):
            raise ContractError(code, name)
    for name in nullable:
        value = getattr(model, name)
        if value is not None and not isinstance(value, str):
            raise ContractError(code, name)


def _booleans(model, names, code):
    for name in names:
        if type(getattr(model, name)) is not bool:
            raise ContractError(code, name)


class DictModel:
    def to_dict(self, *, public=False):
        result = {field.name: thaw(getattr(self, field.name)) for field in fields(self)}
        if public:
            for key in ('credential_ref', 'profile_ref', 'expected_login_subject'):
                result.pop(key, None)
        return result


@dataclass(frozen=True)
class Connection(DictModel):
    id: str
    account_id: str
    platform: str
    target_id: str | None = None
    credential_ref: str | None = None
    profile_ref: str | None = None
    capabilities: tuple = ()
    enabled: bool = False
    auth_checked_at: str | None = None
    last_success_at: str | None = None
    expected_login_subject: str | None = None
    target_label: str = ''
    auth_status: str = 'unknown'
    planning_enabled: bool = True
    target_evidence: tuple = ()
    warnings: tuple = ()

    def __post_init__(self):
        _strings(self, ('id', 'account_id', 'platform', 'target_label', 'auth_status'),
            ('target_id', 'credential_ref', 'profile_ref', 'auth_checked_at', 'last_success_at', 'expected_login_subject'), 'invalid_registry')
        if not all(getattr(self, name) for name in ('id', 'account_id', 'platform')):
            raise ContractError('invalid_registry')
        _booleans(self, ('enabled', 'planning_enabled'), 'invalid_registry')
        for name in ('capabilities', 'target_evidence', 'warnings'):
            if not isinstance(getattr(self, name), (list, tuple)):
                raise ContractError('invalid_registry', name)
        if not all(isinstance(item, str) for item in self.capabilities):
            raise ContractError('invalid_registry', 'capabilities')
        object.__setattr__(self, 'capabilities', freeze(self.capabilities))
        object.__setattr__(self, 'target_evidence', _freeze_json(self.target_evidence))
        object.__setattr__(self, 'warnings', _freeze_json(self.warnings))

    @property
    def target_status(self):
        return 'verified' if self.target_id else 'unverified'

    def to_dict(self, *, public=False):
        if public:
            return dict(id=self.id, account_id=self.account_id, platform=self.platform,
                target_label=self.target_label, target_status=self.target_status,
                capabilities=thaw(self.capabilities), planning_enabled=self.planning_enabled,
                auth_status=self.auth_status, execution_enabled=False)
        return super().to_dict()


@dataclass(frozen=True)
class Registry(DictModel):
    revision: str
    accounts: Mapping
    credentials: Mapping
    profiles: Mapping
    connections: Mapping
    jobs: Mapping
    policies: Mapping
    crossposts: Mapping
    schema_version: int = 1

    def __post_init__(self):
        for name in ('accounts', 'credentials', 'profiles', 'connections', 'jobs', 'policies', 'crossposts'):
            object.__setattr__(self, name, freeze(getattr(self, name)))


@dataclass(frozen=True)
class ExecutionRequest(DictModel):
    run_id: str
    job_id: str
    owner_account_id: str
    content_id: str
    content_revision: int
    connection_id: str
    schedule_slot: str
    publication_purpose: str
    action: str = 'plan'
    dry_run: bool = True
    crosspost_rule_id: str | None = None

    def __post_init__(self):
        _strings(self, ('run_id', 'job_id', 'owner_account_id', 'content_id', 'connection_id',
            'schedule_slot', 'publication_purpose', 'action'), ('crosspost_rule_id',), 'invalid_request')
        _booleans(self, ('dry_run',), 'invalid_request')
        if type(self.content_revision) is not int:
            raise ContractError('invalid_request', 'content_revision')


@dataclass(frozen=True)
class ExecutionContext(ExecutionRequest):
    destination_account_id: str = ''
    platform: str = ''
    target_id: str | None = None
    credential_ref: str | None = None
    profile_ref: str | None = None
    expected_login_subject: str | None = None
    policy_revision: str = ''
    registry_revision: str = ''
    execution_owner: str = 'managed'
    scope: str = 'plan'
    execution_enabled: bool = False
    target_status: str = 'unverified'

    def __post_init__(self):
        super().__post_init__()
        _strings(self, ('destination_account_id', 'platform', 'policy_revision', 'registry_revision',
            'execution_owner', 'scope', 'target_status'),
            ('target_id', 'credential_ref', 'profile_ref', 'expected_login_subject'), 'invalid_request')
        _booleans(self, ('execution_enabled',), 'invalid_request')
        if self.dry_run is not True or self.action not in ('plan', 'prepare') or self.scope != 'plan' or self.execution_enabled is not False:
            raise ContractError('invalid_request', '로컬 계획 컨텍스트만 허용합니다')
